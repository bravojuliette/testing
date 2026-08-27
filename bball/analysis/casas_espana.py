"""Comparativa de casas CON LICENCIA EN ESPAÑA presentes en nuestros datos
(Bwin, Bet365, Betway, 888sport): cobertura por liga, margen en totales y
calibracion del under en la linea principal. Para decidir en que casa (legal
en España) el mismo sistema tendria el liston mas bajo."""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")  # correr desde la raiz del repo: python3 bball/analysis/<script>.py

from bball import db

SPAIN_BOOKS = ["BWin", "Bet365", "Betway", "888Sport"]

with db.get_conn() as conn:
    rows = conn.execute(
        """SELECT o.event_id, o.book, o.line, o.under_odds, o.over_odds, o.snapshot,
                  g.home_score + g.away_score AS final, g.league_name AS league
           FROM bball_odds o JOIN bball_games g ON g.event_id = o.event_id
           WHERE o.market='18_3' AND g.completed=1
           ORDER BY o.event_id, o.book, o.snapshot"""
    ).fetchall()

best = {}
for r in rows:
    key = (r["event_id"], r["book"])
    if r["snapshot"] == "end" or key not in best:
        best[key] = r

by_book = defaultdict(list)
for (eid, book), r in best.items():
    if book in SPAIN_BOOKS:
        by_book[book].append(r)

print(f"{'casa':<10} {'n':>5} {'ligas':<38} {'margen':>7} {'P(under) real':>13} {'media final-linea':>17}")
for book in SPAIN_BOOKS:
    rs = by_book.get(book, [])
    if not rs:
        print(f"{book:<10} {'0':>5}  (sin datos)")
        continue
    leagues = defaultdict(int)
    margins, diffs = [], []
    for r in rs:
        leagues[r["league"]] += 1
        if r["under_odds"] and r["over_odds"] and r["under_odds"] > 1 and r["over_odds"] > 1:
            margins.append((1 / r["under_odds"] + 1 / r["over_odds"] - 1) * 100)
        diffs.append(r["final"] - r["line"])
    lg_str = ", ".join(f"{k}:{v}" for k, v in sorted(leagues.items(), key=lambda kv: -kv[1]))
    dec = [d for d in diffs if d != 0]
    p_under = sum(1 for d in dec if d < 0) / len(dec) * 100 if dec else 0
    print(f"{book:<10} {len(rs):>5} {lg_str:<38} {statistics.mean(margins):>6.1f}% {p_under:>12.1f}% {statistics.mean(diffs):>+17.2f}")

print("\nEV de apostar under/over SIEMPRE en la linea principal de cada casa (sin señal):")
for book in SPAIN_BOOKS:
    rs = by_book.get(book, [])
    if len(rs) < 30:
        continue
    pnl_u = pnl_o = n = 0
    for r in rs:
        if not (r["under_odds"] and r["over_odds"] and r["under_odds"] > 1 and r["over_odds"] > 1):
            continue
        d = r["final"] - r["line"]
        if d == 0:
            continue
        n += 1
        pnl_u += (r["under_odds"] - 1) if d < 0 else -1
        pnl_o += (r["over_odds"] - 1) if d > 0 else -1
    if n:
        print(f"  {book:<10} n={n:>4}  under siempre: {pnl_u/n*100:+.1f}%   over siempre: {pnl_o/n*100:+.1f}%")
