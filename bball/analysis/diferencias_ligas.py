"""¿Se comportan igual todas las competiciones, o lo que pasa en una no
pasa en otra? Radiografia comparada de las 4 ligas con datos, al CIERRE
real (primera casa entre Bet365/Betway/BWin, como siempre).

Por liga: calibracion de la linea (sesgo y dispersion), coste de apostar a
ciegas cada lado, margen tipico, y la pendiente de linea alta -- lo unico
que llego a parecer señal en alguna liga.
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

por = defaultdict(list)
for g in games:
    lg = "NCAAB" if "NCAA" in (g.league_name or "") else (g.league_name or "?")
    d = k.get(g.event_id, {})
    p = next((d[b] for b in BOOKS if b in d), None)
    if not p or not p["over_odds"] or not p["under_odds"]:
        continue
    if p["over_odds"] <= 1 or p["under_odds"] <= 1:
        continue
    por[lg].append((p["line"], g.total, p["over_odds"], p["under_odds"], g.date))

print(f"{'liga':<12} {'n':>5} {'sesgo':>7} {'sd':>5} {'ROI over':>9} {'ROI under':>10} "
      f"{'margen':>7} {'pendiente':>10} {'t':>6}")
for lg in ("NBA", "NCAAB", "WNBA", "Euroleague"):
    s = por.get(lg, [])
    if len(s) < 200:
        continue
    dev = [t - L for L, t, _, _, _ in s]
    ov = [0.0 if t == L else (o - 1 if t > L else -1.0) for L, t, o, _, _ in s]
    un = [0.0 if t == L else (u - 1 if t < L else -1.0) for L, t, _, u, _ in s]
    marg = statistics.median(1/o + 1/u - 1 for _, _, o, u, _ in s)
    xs = [L for L, _, _, _, _ in s]; ys = dev
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((a - mx) ** 2 for a in xs)
    b = sum((a - mx) * (c - my) for a, c in zip(xs, ys)) / sxx
    resid = [c - (my + b * (a - mx)) for a, c in zip(xs, ys)]
    se = (sum(r * r for r in resid) / (len(s) - 2) / sxx) ** .5
    print(f"{lg:<12} {len(s):>5} {statistics.mean(dev):>+7.2f} {statistics.pstdev(dev):>5.1f} "
          f"{sum(ov)/len(ov)*100:>+8.1f}% {sum(un)/len(un)*100:>+9.1f}% "
          f"{marg*100:>6.2f}% {b:>+10.4f} {b/se:>6.2f}")

print("""
Lectura de columnas: sesgo = media(final - linea), 0 seria calibracion
perfecta; ROI over/under = apostar SIEMPRE ese lado; pendiente = la del
pre-registro de linea alta (negativa = las lineas altas se pasan).""")
