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

# ENMIENDA 2: la altitud se mide por la CIUDAD del ESTADIO (bball_venues),
# no por el nombre del equipo local. Lista de ciudades >=1300 m derivada de
# la MISMA lista cerrada en el pre-registro original (alli, ciudad y metros
# de cada equipo). El match es por prefijo de ciudad ("Denver, CO" cuadra
# con "Denver").
CIUDADES_ALTITUD = (
    "Alamosa", "Colorado Springs", "Provo", "Boulder", "Lakewood",
    "Grand Junction", "Golden", "Pueblo", "Durango", "Pocatello", "Denver",
    "Bozeman", "Reno", "Albuquerque", "Las Vegas, NM", "Flagstaff",
    "Greeley", "Cedar City", "Salt Lake City", "Logan", "Orem", "Ogden",
    "Gunnison", "Laramie", "Fort Collins", "Espanola", "Española",
    "Silver City", "Trinidad", "Colorado City",
)
MUY_ALTA_CIUDADES = ("Alamosa", "Colorado Springs", "Durango",
                     "Las Vegas, NM", "Flagstaff", "Gunnison", "Laramie",
                     "Espanola", "Española", "Silver City", "Trinidad")


def ciudad_en_altitud(ciudad):
    if not ciudad:
        return False
    return any(ciudad.startswith(c.split(",")[0]) for c in CIUDADES_ALTITUD)


def ciudad_muy_alta(ciudad):
    if not ciudad:
        return False
    return any(ciudad.startswith(c.split(",")[0]) for c in MUY_ALTA_CIUDADES)


def construir_muestras(games, tot, venues, orient):
    """Una muestra por partido apostable. ENMIENDA 2:
    - altitud = ciudad del estadio en la lista cerrada (no depende de la
      orientacion ni de canchas neutrales);
    - viaje = partidos consecutivos fuera con la orientacion CORREGIDA por
      estadio ('swap' invierte roles); los partidos neutrales o sin estadio
      no actualizan los contadores ni son candidatos de H2."""
    pf = defaultdict(list)
    seguidos_fuera = defaultdict(int)
    muestras = []
    for g in sorted(games, key=lambda x: x.time_ts):
        o = orient.get(g.event_id, "ok") if "NCAA" in (g.league_name or "") else "ok"
        hk, ak = (g.away_key, g.home_key) if o == "swap" else (g.home_key, g.away_key)
        ciudad = venues.get(g.event_id)
        d = tot.get(g.event_id, {})
        pick = next((d[b] for b in BOOKS if b in d), None)
        if pick and len(pf[hk]) >= N and len(pf[ak]) >= N:
            linea, o_ov, o_un = pick
            if o_ov and o_un and o_ov > 1 and o_un > 1:
                muestras.append(dict(
                    date=g.date, lg=g.league_name, final=g.total, linea=linea,
                    o_ov=o_ov, o_un=o_un,
                    viaje_vis=seguidos_fuera[ak] if o in ("ok", "swap") else -1,
                    altitud=ciudad_en_altitud(ciudad),
                    muy_alta=ciudad_muy_alta(ciudad),
                    con_estadio=ciudad is not None,
                ))
        pf[hk].append(g.home_score if o != "swap" else g.away_score)
        pf[ak].append(g.away_score if o != "swap" else g.home_score)
        if o in ("ok", "swap"):
            seguidos_fuera[hk] = 0
            seguidos_fuera[ak] += 1
        # neutral / sin_dato: los contadores no se tocan
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
    from ..backtest.orientacion import clasificar_orientacion  # noqa
    with db.get_conn() as conn:
        games = load_games(conn)
        rows = conn.execute(
            "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds "
            "WHERE market = ? AND snapshot = 'kickoff'", (config.TOTALS_MARKET_KEY,)
        ).fetchall()
        venues = {r["event_id"]: r["city"] for r in conn.execute(
            "SELECT event_id, city FROM bball_venues WHERE city IS NOT NULL").fetchall()}
        orient = clasificar_orientacion(conn)

    from collections import Counter
    print("orientacion NCAAB por estadio:", dict(Counter(orient.values())))

    tot = defaultdict(dict)
    for r in rows:
        tot[r["event_id"]][r["book"]] = (r["line"], r["over_odds"], r["under_odds"])

    muestras = construir_muestras(games, tot, venues, orient)
    nuevas = [m for m in muestras
              if (m["lg"] or "").strip().upper() not in LIGAS_QUEMADAS]
    print(f"Partidos apostables al cierre: {len(muestras)}")
    print(f"De ligas NO usadas para formular las hipotesis: {len(nuevas)}")
    con_est = [m for m in nuevas if m["con_estadio"]]
    print(f"   de ellos con estadio conocido (los unicos que juzgan H1): {len(con_est)}\n")

    print(f"{'':<44} {'n':>5} {'acierto':>8} {'ROI':>9} {'t':>6} {'final-linea':>9}")
    h1 = stat([m for m in con_est if m["altitud"]])
    h2 = stat([m for m in nuevas if m["viaje_vis"] >= VIAJE])
    linea("H1  estadio en altitud >=1300 m -> over", h1)
    linea(f"H2  visitante viaje >={VIAJE} -> over", h2)
    print()
    print(f"  H1 (altitud):     {veredicto(h1)}")
    print(f"  H2 (viaje largo): {veredicto(h2)}")
    print("\n  Recordatorio: REFUTADA no se rescata con subgrupos. Y la ENMIENDA 2")
    print("  declara contaminacion (la pista del +13.8%): un resultado positivo")
    print("  ajustado merece MAS escepticismo, no menos.")

    print("\n--- CONTROLES (no cambian el veredicto) ---")
    print(f"{'':<44} {'n':>5} {'acierto':>8} {'ROI':>9} {'t':>6} {'final-linea':>9}")
    linea("referencia: todos los partidos nuevos", stat(nuevas))
    linea("referencia: con estadio conocido", stat(con_est))
    linea("gradiente: estadio >=1800 m", stat([m for m in con_est if m["muy_alta"]]))
    linea("gradiente: 1300-1800 m",
          stat([m for m in con_est if m["altitud"] and not m["muy_alta"]]))
    linea("gradiente: viaje >=6", stat([m for m in nuevas if m["viaje_vis"] >= 6]))
    linea("H1 + H2 juntas (dato, no veredicto)",
          stat([m for m in nuevas if m.get("altitud") or m["viaje_vis"] >= VIAJE]))


if __name__ == "__main__":
    main()
