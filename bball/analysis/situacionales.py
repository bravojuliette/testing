"""Factores SITUACIONALES -- el punto ciego que quedaba con los datos actuales.

Hasta ahora todas las features salian de medias de puntos, cuotas y rachas.
Nunca se probaron los angulos clasicos del calendario, que son informacion
de otra naturaleza: fatiga acumulada, viajes, revanchas, altitud.

Todos se derivan de lo que ya tenemos (equipos + fechas + local/visitante),
sin datos nuevos:

  - viaje: partidos consecutivos como visitante (longitud del road trip)
  - carga: partidos jugados en los ultimos 7 dias
  - revancha: mismo rival en los ultimos 15 dias, y como acabo aquel
  - enesimo enfrentamiento de la temporada entre esos dos equipos
  - altitud: Denver y Utah (los dos casos famosos de la NBA)
  - descanso asimetrico mas fino que el back-to-back ya probado

Ejecucion al cierre real, con disciplina busqueda/reserva.
"""
import statistics
import sys
from collections import defaultdict, deque

sys.path.insert(0, ".")  # correr desde la raiz del repo

from bball import config, db
from bball.backtest.replay import load_games

N = 10
SPLIT = "2025-10-01"
BOOKS = ("Bet365", "Betway", "BWin")
ALTITUD = ("DEN Nuggets", "UTA Jazz")   # ~1600 m y ~1300 m

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds "
        "WHERE market = ? AND snapshot = 'kickoff'", (config.TOTALS_MARKET_KEY,)
    ).fetchall()

tot = defaultdict(dict)
for r in rows:
    tot[r["event_id"]][r["book"]] = (r["line"], r["over_odds"], r["under_odds"])

pf = defaultdict(list)
fechas = defaultdict(list)        # equipo -> [time_ts] de partidos jugados
seguidos_fuera = defaultdict(int) # equipo -> partidos consecutivos como visitante
h2h = defaultdict(list)           # (par de equipos) -> [(ts, total)]
muestras = []
for g in sorted(games, key=lambda x: x.time_ts):
    d = tot.get(g.event_id, {})
    pick = next((d[b] for b in BOOKS if b in d), None)
    if pick and len(pf[g.home_key]) >= N and len(pf[g.away_key]) >= N:
        linea, o_ov, o_un = pick
        if o_ov and o_un and o_ov > 1 and o_un > 1:
            par = tuple(sorted((g.home_key, g.away_key)))
            previos = [x for x in h2h[par] if x[0] < g.time_ts]
            ult = previos[-1] if previos else None
            carga_h = sum(1 for t in fechas[g.home_key] if g.time_ts - t <= 7 * 86400)
            carga_a = sum(1 for t in fechas[g.away_key] if g.time_ts - t <= 7 * 86400)
            muestras.append(dict(
                date=g.date, lg=g.league_name, final=g.total, linea=linea,
                o_ov=o_ov, o_un=o_un,
                viaje_vis=float(seguidos_fuera[g.away_key]),
                carga_loc=float(carga_h), carga_vis=float(carga_a),
                carga_max=float(max(carga_h, carga_a)),
                revancha=1.0 if (ult and g.time_ts - ult[0] <= 15 * 86400) else 0.0,
                enfrentamiento=float(len(previos) + 1),
                altitud=1.0 if g.home_team in ALTITUD else 0.0,
                total_previo=float(ult[1]) if ult else 0.0,
            ))
    pf[g.home_key].append(g.home_score)
    pf[g.away_key].append(g.away_score)
    fechas[g.home_key].append(g.time_ts)
    fechas[g.away_key].append(g.time_ts)
    seguidos_fuera[g.home_key] = 0
    seguidos_fuera[g.away_key] += 1
    h2h[tuple(sorted((g.home_key, g.away_key)))].append((g.time_ts, g.total))

busq = [m for m in muestras if m["date"] >= SPLIT]
res = [m for m in muestras if m["date"] < SPLIT]
print(f"Partidos: {len(muestras)}  (busqueda {len(busq)} / reserva {len(res)})\n")

def stat(sub, lado):
    pnls, ok, dec = [], 0, 0
    for m in sub:
        odds = m["o_un"] if lado == "U" else m["o_ov"]
        if m["final"] == m["linea"]:
            pnls.append(0.0); continue
        gano = m["final"] < m["linea"] if lado == "U" else m["final"] > m["linea"]
        pnls.append(odds - 1 if gano else -1.0)
        dec += 1; ok += gano
    n = len(pnls)
    if n == 0: return None
    sd = statistics.pstdev(pnls) if n > 1 else 0
    return dict(n=n, roi=sum(pnls)/n*100, hit=ok/dec*100 if dec else 0,
                t=(statistics.mean(pnls)/sd)*(n**0.5) if sd > 0 else 0)

print("1. ¿Desvia el total? Media de (final - linea) por situacion.")
print("   Si la casa ya lo descuenta, todos deberian rondar el mismo valor.\n")
print(f"{'situacion':<42} {'n':>5} {'media(final-linea)':>20} {'% under':>9}")
SITS = [
    ("TODOS (referencia)", lambda m: True),
    ("visitante en viaje largo (>=4 fuera)", lambda m: m["viaje_vis"] >= 4),
    ("visitante en viaje MUY largo (>=6)", lambda m: m["viaje_vis"] >= 6),
    ("algun equipo con >=4 partidos en 7 dias", lambda m: m["carga_max"] >= 4),
    ("revancha (mismo rival en 15 dias)", lambda m: m["revancha"] > 0),
    ("3er+ enfrentamiento de la temporada", lambda m: m["enfrentamiento"] >= 3),
    ("en altitud (Denver / Utah)", lambda m: m["altitud"] > 0),
    ("nadie cargado (carga_max<=2)", lambda m: m["carga_max"] <= 2),
]
for et, f in SITS:
    sub = [m for m in muestras if f(m)]
    if len(sub) < 25: 
        print(f"{et:<42} {len(sub):>5}   (muestra insuficiente)")
        continue
    dec = [m for m in sub if m["final"] != m["linea"]]
    pu = sum(1 for m in dec if m["final"] < m["linea"]) / len(dec) * 100 if dec else 0
    print(f"{et:<42} {len(sub):>5} {statistics.mean(m['final']-m['linea'] for m in sub):>+19.2f} {pu:>8.1f}%")

print("\n2. ¿Se puede apostar? Cada situacion, en busqueda y reserva:\n")
print(f"{'situacion':<40} {'lado':>4} {'busqueda n/ROI/t':>26} {'RESERVA n/ROI/t':>26}")
for et, f in SITS[1:]:
    for lado in ("U", "O"):
        sb = stat([m for m in busq if f(m)], lado)
        sr = stat([m for m in res if f(m)], lado)
        if sb and sr and sb["n"] >= 30 and sr["n"] >= 30:
            marca = "  <--" if sb["roi"] > 0 and sr["roi"] > 0 else ""
            print(f"{et[:38]:<40} {lado:>4} "
                  f"{sb['n']:>6} {sb['roi']:>+7.1f}% {sb['t']:>5.2f} "
                  f"{sr['n']:>8} {sr['roi']:>+7.1f}% {sr['t']:>5.2f}{marca}")

print("\n3. Revancha: ¿arrastra el total del enfrentamiento anterior?")
rev = [m for m in muestras if m["revancha"] > 0 and m["total_previo"] > 0]
if len(rev) >= 30:
    alto = [m for m in rev if m["total_previo"] > m["linea"] + 5]
    bajo = [m for m in rev if m["total_previo"] < m["linea"] - 5]
    for et, sub in (("el anterior fue MUY alto", alto), ("el anterior fue MUY bajo", bajo)):
        if len(sub) >= 20:
            dec = [m for m in sub if m["final"] != m["linea"]]
            pu = sum(1 for m in dec if m["final"] < m["linea"]) / len(dec) * 100
            print(f"  {et:<30} n={len(sub):>4}  media(final-linea)={statistics.mean(m['final']-m['linea'] for m in sub):>+6.2f}  under {pu:.1f}%")
