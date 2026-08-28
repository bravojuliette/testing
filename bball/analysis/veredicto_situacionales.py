"""Veredicto de PREREGISTRO_situacionales.md -- ESCRITO ANTES DE MIRAR LOS
DATOS DE NCAAB, para que el procedimiento quede cerrado en codigo y no solo
en prosa.

Comprueba las dos hipotesis pre-registradas sobre partidos que NO
participaron en ningun analisis previo:

  H1 (altitud)    local juega a >=1300 m  -> over a la linea de cierre
  H2 (viaje largo) visitante encadena >=4 partidos fuera -> over

Criterio fijado de antemano, identico para las dos:
  CONFIRMADA     ROI > 0 y t >= 2
  REFUTADA       cualquier otro caso (incluido ROI>0 con t<2)
  NO CONCLUYENTE n < 100

Uso:  python bball/analysis/veredicto_situacionales.py
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")  # correr desde la raiz del repo

from bball import config, db
from bball.backtest.replay import load_games

# Ver ENMIENDA 1 del pre-registro: el requisito de historial se elimina
# (con n=0 y cero resultados vistos). Ninguna de las dos hipotesis usa medias
# de anotacion, asi que no hay nada que "calentar"; H2 se autolimita porque
# exigir viaje>=4 ya obliga a haber observado 4 partidos de ese equipo.
N = 0                       # historial minimo exigido a ambos equipos
BOOKS = ("Bet365", "Betway", "BWin")   # primera disponible, en este orden
VIAJE = 4                   # umbral de H2, fijado en el pre-registro
MIN_N = 100                 # por debajo -> NO CONCLUYENTE

# Ligas ya usadas para FORMULAR las hipotesis: quedan fuera del veredicto.
LIGAS_QUEMADAS = {"NBA", "WNBA", "EUROLEAGUE"}

# Lista de altitud CERRADA en PREREGISTRO_situacionales.md (>= 1300 m).
# Cualquier nombre que no este aqui cuenta como NO altitud.
ALTITUD = {
    # NBA (origen de la hipotesis; no entra en el veredicto, solo control)
    "DEN Nuggets", "UTA Jazz",
    # NCAAB, nombres ya presentes en la base al pre-registrar
    "Adams State", "Air Force", "BYU", "Colorado", "Colorado Christian",
    "Colorado Mesa", "Colorado School of Mines", "Colorado State Pueblo",
    "Colorado-Colorado Springs", "Denver", "Fort Lewis", "Idaho St",
    "Metropolitan State", "Montana State", "Nevada", "New Mexico",
    "New Mexico Highlands", "Northern Arizona", "Northern Colorado",
    "Regis", "Southern Utah", "Utah", "Utah State", "Utah Valley",
    "Weber State", "Western Colorado", "Wyoming",
    # NCAAB, pre-comprometidos por si aparecen al terminar la recoleccion
    "Colorado State", "Colorado College", "Northern New Mexico",
    "Western New Mexico", "Trinidad State",
}
# Altitud aproximada de la sede, solo para el control de gradiente.
MUY_ALTA = {
    "Adams State", "Air Force", "Colorado-Colorado Springs", "Fort Lewis",
    "New Mexico Highlands", "Northern Arizona", "Western Colorado",
    "Wyoming", "Colorado College", "Northern New Mexico",
    "Western New Mexico", "Trinidad State",
}   # >= 1800 m


def construir_muestras(games, tot):
    """Recorre los partidos en orden y emite una muestra por partido
    apostable, con las features derivadas SOLO de partidos anteriores."""
    pf = defaultdict(list)
    seguidos_fuera = defaultdict(int)
    muestras = []
    for g in sorted(games, key=lambda x: x.time_ts):
        d = tot.get(g.event_id, {})
        pick = next((d[b] for b in BOOKS if b in d), None)
        if pick and len(pf[g.home_key]) >= N and len(pf[g.away_key]) >= N:
            linea, o_ov, o_un = pick
            if o_ov and o_un and o_ov > 1 and o_un > 1:
                muestras.append(dict(
                    date=g.date, lg=g.league_name, final=g.total, linea=linea,
                    o_ov=o_ov, o_un=o_un,
                    viaje_vis=seguidos_fuera[g.away_key],
                    altitud=g.home_team in ALTITUD,
                    muy_alta=g.home_team in MUY_ALTA,
                    vis_altitud=g.away_team in ALTITUD,
                ))
        pf[g.home_key].append(g.home_score)
        pf[g.away_key].append(g.away_score)
        seguidos_fuera[g.home_key] = 0
        seguidos_fuera[g.away_key] += 1
    return muestras


def stat(sub, lado="O"):
    pnls, ok, dec = [], 0, 0
    for m in sub:
        odds = m["o_ov"] if lado == "O" else m["o_un"]
        if m["final"] == m["linea"]:
            pnls.append(0.0)
            continue
        gano = m["final"] > m["linea"] if lado == "O" else m["final"] < m["linea"]
        pnls.append(odds - 1 if gano else -1.0)
        dec += 1
        ok += gano
    n = len(pnls)
    if n == 0:
        return None
    sd = statistics.pstdev(pnls) if n > 1 else 0.0
    return dict(n=n, roi=sum(pnls) / n * 100, hit=ok / dec * 100 if dec else 0,
                t=(statistics.mean(pnls) / sd) * (n ** 0.5) if sd > 0 else 0.0,
                pnl=sum(pnls),
                desv=statistics.mean(m["final"] - m["linea"] for m in sub))


def veredicto(r):
    if r is None or r["n"] < MIN_N:
        return f"NO CONCLUYENTE (n={0 if r is None else r['n']} < {MIN_N})"
    if r["roi"] > 0 and r["t"] >= 2:
        return "CONFIRMADA"
    return "REFUTADA"


def linea(et, r):
    if r is None:
        print(f"{et:<44} {'-':>5}")
        return
    print(f"{et:<44} {r['n']:>5} {r['hit']:>7.1f}% {r['roi']:>+8.1f}% "
          f"{r['t']:>6.2f} {r['desv']:>+8.2f}")


def main():
    with db.get_conn() as conn:
        games = load_games(conn)
        rows = conn.execute(
            "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds "
            "WHERE market = ? AND snapshot = 'kickoff'", (config.TOTALS_MARKET_KEY,)
        ).fetchall()

    tot = defaultdict(dict)
    for r in rows:
        tot[r["event_id"]][r["book"]] = (r["line"], r["over_odds"], r["under_odds"])

    muestras = construir_muestras(games, tot)
    nuevas = [m for m in muestras
              if (m["lg"] or "").strip().upper() not in LIGAS_QUEMADAS]
    print(f"Partidos apostables al cierre: {len(muestras)}")
    print(f"De ligas NO usadas para formular las hipotesis: {len(nuevas)}")
    porliga = defaultdict(int)
    for m in nuevas:
        porliga[m["lg"]] += 1
    for lg, k in sorted(porliga.items(), key=lambda kv: -kv[1]):
        print(f"   {lg:<12} {k}")
    print()

    print(f"{'':<44} {'n':>5} {'acierto':>8} {'ROI':>9} {'t':>6} {'final-linea':>9}")
    h1 = stat([m for m in nuevas if m["altitud"]])
    h2 = stat([m for m in nuevas if m["viaje_vis"] >= VIAJE])
    linea("H1  altitud >=1300 m -> over", h1)
    linea(f"H2  visitante viaje >={VIAJE} -> over", h2)
    print()
    print(f"  H1 (altitud):     {veredicto(h1)}")
    print(f"  H2 (viaje largo): {veredicto(h2)}")
    print("\n  Recordatorio del pre-registro: si salen REFUTADAS no se buscan")
    print("  subgrupos para rescatarlas. Ese es todo el valor del documento.")

    print("\n--- CONTROLES (no cambian el veredicto) ---")
    print(f"{'':<44} {'n':>5} {'acierto':>8} {'ROI':>9} {'t':>6} {'final-linea':>9}")
    linea("referencia: todos los partidos nuevos", stat(nuevas))
    linea("control fisico H1 (esperado ~+5.54)", h1)
    linea("control fisico H2 (esperado ~+1.33)", h2)
    linea("gradiente: altitud >=1800 m",
          stat([m for m in nuevas if m["muy_alta"]]))
    linea("gradiente: altitud 1300-1800 m",
          stat([m for m in nuevas if m["altitud"] and not m["muy_alta"]]))
    linea("gradiente: viaje >=6", stat([m for m in nuevas if m["viaje_vis"] >= 6]))
    linea("placebo: visitante de altitud, fuera",
          stat([m for m in nuevas if m["vis_altitud"] and not m["altitud"]]))
    linea("H1 + H2 juntas (dato, no veredicto)",
          stat([m for m in nuevas if m["altitud"] or m["viaje_vis"] >= VIAJE]))


if __name__ == "__main__":
    main()
