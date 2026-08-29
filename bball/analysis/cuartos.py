"""Teoria del usuario: equipos con PRIMEROS CUARTOS flojos + linea en vivo
hundida tras un Q1 lento -> over en directo.

No tenemos historico de cuotas EN VIVO (solo el cierre y una ultima cuota
'end'), asi que la parte de mercado no se puede backtestear. Pero la teoria
descansa en dos premisas FISICAS que si se pueden juzgar con lo que hay:

  A. ¿"Empezar flojo" es un rasgo estable de un equipo, o es ruido?
     Se mide con correlacion partida: la cuota de Q1 de cada equipo
     (puntos en Q1 / puntos totales) en sus partidos PARES vs IMPARES.
     Si un rasgo real existe, un equipo flojo en la mitad A lo es en la B.

  B. Tras un Q1 LENTO (muy por debajo de linea/4), ¿el resto del partido
     REVIERTE al ritmo esperado o SIGUE lento? Se compara el total de los
     cuartos 2-4 contra 3/4 de la linea de cierre.
     - Si revierte: la premisa del over vivo queda viva (falta saber si la
       linea viva cae de mas, que no podemos medir).
     - Si sigue lento: el Q1 lento ES informativo, el under vivo esta bien
       puesto, y la estrategia muere sin necesidad de cuotas vivas.

Los cuartos salen del raw_json usando los nombres del PROPIO raw (evita el
lio de orientacion de NCAAB: raw es consistente consigo mismo). NCAAB juega
mitades, no cuartos -- se excluye; NBA/WNBA/Euroliga juegan cuartos.
"""
import json
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball import config, db

BOOKS = ("Bet365", "Betway", "BWin")
LIGAS = ("NBA", "WNBA", "Euroleague")

with db.get_conn() as conn:
    kick = defaultdict(dict)
    for r in conn.execute(
        "SELECT event_id, book, line FROM bball_odds WHERE market=? AND snapshot='kickoff'",
        (config.TOTALS_MARKET_KEY,)).fetchall():
        kick[r["event_id"]][r["book"]] = r["line"]
    juegos = conn.execute(
        "SELECT event_id, league_name, date, raw_json FROM bball_games "
        "WHERE completed=1 AND league_name IN (?,?,?)", LIGAS).fetchall()

partidos = []
for g in juegos:
    js = json.loads(g["raw_json"])
    sc = js.get("scores") or {}
    try:
        qs = [(int(sc[k]["home"]), int(sc[k]["away"])) for k in ("1", "2", "4", "5")]
    except (KeyError, TypeError, ValueError):
        continue
    hname = (js.get("home") or {}).get("name")
    aname = (js.get("away") or {}).get("name")
    linea = next((kick[g["event_id"]][b] for b in BOOKS if b in kick.get(g["event_id"], {})), None)
    partidos.append(dict(lg=g["league_name"], date=g["date"], qs=qs,
                         h=hname, a=aname, linea=linea))

print(f"Partidos con cuartos parseados: {len(partidos)} (NBA/WNBA/Euroliga)\n")

# ---------- A. ¿Es estable el rasgo "Q1 flojo"? ----------
por_equipo = defaultdict(list)   # equipo -> [(fecha, cuota_q1_del_equipo)]
for p in partidos:
    tot_h = sum(h for h, _ in p["qs"]); tot_a = sum(a for _, a in p["qs"])
    if tot_h < 40 or tot_a < 40:
        continue
    por_equipo[(p["lg"], p["h"])].append(p["qs"][0][0] / tot_h)
    por_equipo[(p["lg"], p["a"])].append(p["qs"][0][1] / tot_a)

xs, ys = [], []
for eq, vals in por_equipo.items():
    if len(vals) < 20:
        continue
    pares = vals[0::2]; impares = vals[1::2]
    xs.append(statistics.mean(pares)); ys.append(statistics.mean(impares))
mx, my = statistics.mean(xs), statistics.mean(ys)
num = sum((a-mx)*(b-my) for a, b in zip(xs, ys))
den = (sum((a-mx)**2 for a in xs) * sum((b-my)**2 for b in ys)) ** .5
print(f"A. ESTABILIDAD del rasgo 'cuota de puntos en Q1' ({len(xs)} equipos con 20+ partidos)")
print(f"   correlacion mitad-par vs mitad-impar: {num/den:+.3f}")
print(f"   (>0.3 = rasgo real; ~0 = 'equipo de Q1 flojo' es un espejismo)")
sd_eq = statistics.pstdev([statistics.mean(v) for v in por_equipo.values() if len(v) >= 20])
sd_in = statistics.mean([statistics.pstdev(v) for v in por_equipo.values() if len(v) >= 20])
print(f"   dispersion ENTRE equipos: {sd_eq*100:.2f} pts%  |  dentro de un equipo: {sd_in*100:.2f} pts%")

# ---------- B. Tras un Q1 lento, ¿revierte o sigue? ----------
print("\nB. TRAS UN Q1 LENTO, ¿EL RESTO REVIERTE? (partidos con linea de cierre)")
print(f"{'Q1 vs linea/4':<22} {'n':>5} {'resto (Q2-4) vs 3/4 de linea':>30} {'% over de linea':>16}")
con_linea = [p for p in partidos if p["linea"]]
for et, lo, hi in (("MUY lento (<= -6)", -99, -6), ("lento (-6 a -2)", -6, -2),
                   ("normal (-2 a +2)", -2, 2), ("rapido (+2 a +6)", 2, 6),
                   ("MUY rapido (> +6)", 6, 99)):
    sub = []
    for p in con_linea:
        q1 = p["qs"][0][0] + p["qs"][0][1]
        d1 = q1 - p["linea"] / 4
        if not (lo < d1 <= hi):
            continue
        resto = sum(h + a for h, a in p["qs"][1:])
        total = q1 + resto
        sub.append((resto - 3 * p["linea"] / 4, total > p["linea"]))
    if len(sub) < 30:
        print(f"{et:<22} {len(sub):>5}   (muestra corta)")
        continue
    m = statistics.mean(x for x, _ in sub)
    pv = sum(1 for _, o in sub if o) / len(sub) * 100
    print(f"{et:<22} {len(sub):>5} {m:>+29.2f} {pv:>15.1f}%")
print("\n   'resto vs 3/4 de linea' = 0 significa reversion perfecta al ritmo")
print("   esperado; negativo = el partido SIGUE lento (el Q1 informaba).")
