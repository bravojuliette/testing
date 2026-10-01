"""Veredicto de PREREGISTRO_linea_alta.md sobre la reserva completa
(NCAAB, 2026-02-01 a 2026-03-31), que no existia al pre-registrar.

H1: pendiente de (final - linea de cierre) sobre (linea) NEGATIVA con
    t <= -2. NO CONCLUYENTE si n < 500.
H2: under a linea >= 165, ROI > 0 y t >= 2. NO CONCLUYENTE si n < 100.
Primera casa entre Bet365/Betway/BWin. Sin filtros ni umbrales nuevos.
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball import config, db
from bball.backtest.replay import load_games

BOOKS = ("Bet365", "Betway", "BWin")

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds "
        "WHERE market=? AND snapshot='kickoff'", (config.TOTALS_MARKET_KEY,)).fetchall()
k = defaultdict(dict)
for r in rows:
    k[r["event_id"]][r["book"]] = r

res = []
for g in games:
    if "NCAA" not in (g.league_name or "") or not ("2026-02-01" <= g.date <= "2026-03-31"):
        continue
    d = k.get(g.event_id, {})
    p = next((d[b] for b in BOOKS if b in d), None)
    if not p or not p["over_odds"] or not p["under_odds"]:
        continue
    if p["over_odds"] <= 1 or p["under_odds"] <= 1:
        continue
    res.append((p["line"], g.total - p["line"], p["under_odds"], g.total))

print(f"RESERVA COMPLETA (feb-mar 2026): n={len(res)} partidos apostables")
xs = [a for a, _, _, _ in res]; ys = [b for _, b, _, _ in res]
mx, my = statistics.mean(xs), statistics.mean(ys)
sxx = sum((a - mx) ** 2 for a in xs)
b = sum((a - mx) * (c - my) for a, c in zip(xs, ys)) / sxx
resid = [c - (my + b * (a - mx)) for a, c in zip(xs, ys)]
se = (sum(r * r for r in resid) / (len(res) - 2) / sxx) ** .5
t1 = b / se
print(f"\nH1 (pendiente): {b:+.4f}  err.tip. {se:.4f}  t={t1:+.2f}")
v1 = ("NO CONCLUYENTE (n<500)" if len(res) < 500 else
      ("CONFIRMADA" if (b < 0 and t1 <= -2) else "REFUTADA"))
print(f"    VEREDICTO H1: {v1}   (criterio: negativa y t<=-2; busqueda dio -0.0805, t=-2.42)")

print("\n    gradiente por tramos (control):")
for et, lo, hi in (("<150", 0, 150), ("150-160", 150, 160), ("160-165", 160, 165), (">=165", 165, 999)):
    s2 = [y for x, y, _, _ in res if lo <= x < hi]
    if len(s2) >= 10:
        print(f"    {et:<9} n={len(s2):>4}  media(final-linea) {statistics.mean(s2):+.2f}")

sel = [(u, t, L) for L, _, u, t in res if L >= 165]
pnl = [0.0 if t == L else (u - 1 if t < L else -1.0) for u, t, L in sel]
dec = [x for x in pnl if x != 0]
ok = sum(1 for x in dec if x > 0)
sd = statistics.pstdev(pnl) if len(pnl) > 1 else 0
t2 = statistics.mean(pnl) / sd * len(pnl) ** .5 if sd else 0
roi = sum(pnl) / len(pnl) * 100 if pnl else 0
print(f"\nH2 (under a linea>=165): n={len(pnl)}  acierto={ok/len(dec)*100 if dec else 0:.1f}%  "
      f"ROI={roi:+.1f}%  t={t2:+.2f}")
v2 = ("NO CONCLUYENTE (n<100)" if len(pnl) < 100 else
      ("CONFIRMADA" if (roi > 0 and t2 >= 2) else "REFUTADA"))
print(f"    VEREDICTO H2: {v2}   (criterio: ROI>0 y t>=2)")
