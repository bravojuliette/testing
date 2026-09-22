"""RE-VEREDICTO de PREREGISTRO_wnba_underdogs.md sobre datos LIMPIOS.

El veredicto original (t=-2.10, 'refutada') se calculo con las cuotas de
ganador INVERTIDAS en WNBA (el bug de orientacion por casa descubierto el
2026-08-29): el 'underdog' que media era en realidad el favorito. No vale.
Este re-veredicto aplica EXACTAMENTE el procedimiento pre-registrado sobre
las cuotas corregidas. El criterio no cambia: ROI>0 y t>=2 CONFIRMADA;
n<80 NO CONCLUYENTE; resto REFUTADA.

Nota de integridad: re-juzgar es legitimo (y obligatorio) porque el motivo
es un bug de DATOS nuestro, documentado y corregido en el historial, no un
resultado que no gusto. La hipotesis y el criterio no se han tocado.
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball import config, db
from bball.backtest.replay import load_games

BOOKS = ("Bet365", "Betway", "BWin")
LO, HI = 2.5, 5.0
RANGO = ("2022-04-01", "2024-10-31")

with db.get_conn() as conn:
    games = sorted([g for g in load_games(conn) if g.league_name == "WNBA"],
                   key=lambda x: x.time_ts)
    rows = conn.execute(
        "SELECT event_id, book, over_odds h, under_odds a FROM bball_odds "
        "WHERE snapshot='kickoff' AND market='18_1'").fetchall()
ml = defaultdict(dict)
for r in rows:
    ml[r["event_id"]][r["book"]] = r

pf = defaultdict(int)
pnl, det = [], []
for g in games:
    d = ml.get(g.event_id, {})
    r = next((d[b] for b in BOOKS if b in d), None)
    listo = pf[g.home_key] >= 10 and pf[g.away_key] >= 10
    pf[g.home_key] += 1
    pf[g.away_key] += 1
    if not r or not listo or not (RANGO[0] <= g.date <= RANGO[1]):
        continue
    if not r["h"] or not r["a"] or r["h"] <= 1 or r["a"] <= 1:
        continue
    # cuotas ya normalizadas por el reparse: h = cuota del LOCAL fisico
    if r["h"] > r["a"]:
        q, gano = r["h"], g.home_score > g.away_score
    else:
        q, gano = r["a"], g.away_score > g.home_score
    if not (LO <= q <= HI):
        continue
    pnl.append(q - 1 if gano else -1.0)
    det.append((g.date, q, gano))

n = len(pnl)
print(f"apuestas del tramo pre-registrado (WNBA 2022-2024, cuota 2.5-5.0): n={n}")
if n:
    ok = sum(1 for _, _, g in det if g)
    roi = sum(pnl) / n * 100
    sd = statistics.pstdev(pnl)
    t = statistics.mean(pnl) / sd * n ** 0.5 if sd else 0
    print(f"acierto: {ok}/{n} = {ok/n*100:.1f}%  cuota media {statistics.mean(q for _, q, _ in det):.2f}")
    print(f"ROI = {roi:+.1f}%   t = {t:+.2f}   beneficio = {sum(pnl):+.1f}u")
    if n < 80:
        v = "NO CONCLUYENTE (n<80)"
    elif roi > 0 and t >= 2:
        v = "CONFIRMADA"
    else:
        v = "REFUTADA"
    print(f"\nVEREDICTO (criterio intacto del pre-registro): {v}")
    print("\npor temporada:")
    port = defaultdict(list)
    for d, q, g2 in det:
        port[d[:4]].append(q - 1 if g2 else -1.0)
    for y in sorted(port):
        v2 = port[y]
        print(f"  {y}: n={len(v2):>3}  ROI {sum(v2)/len(v2)*100:+.1f}%")
