"""Veredicto del pre-registro de la pendiente de linea alta en WNBA
(PREREGISTRO_pendiente_wnba.md, escrito el 2026-08-29 contra partidos que no
existian todavia).

Procedimiento FIJADO en el pre-registro, sin tocar nada:
- partidos de WNBA con fecha >= 2026-09-01,
- linea de cierre = snapshot 'kickoff', primera casa entre Bet365, Betway,
  BWin, en ese orden,
- minimos cuadrados de (total final - linea) sobre (linea), sin recortes ni
  ponderar, sin subgrupos,
- CONFIRMADA si pendiente < 0 y t <= -2; NO CONCLUYENTE si hay menos de 60
  partidos apostables al cierre; REFUTADA en cualquier otro caso.

Reproducible: python3 bball/analysis/veredicto_pendiente_wnba.py
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball import config, db
from bball.backtest.replay import load_games

BOOKS = ("Bet365", "Betway", "BWin")   # orden del pre-registro, no se mueve
DESDE = "2026-09-01"
MIN_N = 60                              # umbral de "no concluyente", fijado

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds "
        "WHERE market=? AND snapshot='kickoff'", (config.TOTALS_MARKET_KEY,)).fetchall()

k = defaultdict(dict)
for r in rows:
    k[r["event_id"]][r["book"]] = r

muestra = []
por_casa = defaultdict(int)
wnba_total = 0
for g in games:
    if "WNBA" not in (g.league_name or ""):
        continue
    if (g.date or "") < DESDE:
        continue
    wnba_total += 1
    d = k.get(g.event_id, {})
    casa = next((b for b in BOOKS if b in d), None)
    if casa is None:
        continue
    p = d[casa]
    if not p["over_odds"] or not p["under_odds"]:
        continue
    if p["over_odds"] <= 1 or p["under_odds"] <= 1:
        continue
    por_casa[casa] += 1
    muestra.append((p["line"], g.total))

n = len(muestra)
print(f"Partidos WNBA terminados desde {DESDE}: {wnba_total}")
print(f"Apostables al cierre (kickoff, {'/'.join(BOOKS)}): {n}")
for b in BOOKS:
    print(f"  {b}: {por_casa.get(b, 0)}")

if n < 3:
    print("\nVEREDICTO: NO CONCLUYENTE -- muestra insuficiente para regresar.")
    raise SystemExit(0)

xs = [L for L, _ in muestra]
ys = [t - L for L, t in muestra]
mx, my = statistics.mean(xs), statistics.mean(ys)
sxx = sum((a - mx) ** 2 for a in xs)
pend = sum((a - mx) * (c - my) for a, c in zip(xs, ys)) / sxx
resid = [c - (my + pend * (a - mx)) for a, c in zip(xs, ys)]
se = (sum(r * r for r in resid) / (n - 2) / sxx) ** .5
t = pend / se

print(f"\nsesgo medio (final - linea): {statistics.mean(ys):+.2f}")
print(f"linea media: {statistics.mean(xs):.1f}  (rango {min(xs):.1f}-{max(xs):.1f})")
print(f"pendiente: {pend:+.4f}   t = {t:+.2f}   n = {n}")

if n < MIN_N:
    print(f"\nVEREDICTO: NO CONCLUYENTE. n={n} < {MIN_N}, el minimo escrito en el")
    print("pre-registro. La pendiente y su t se dejan solo para el registro: con")
    print("esta muestra no deciden nada, ni a favor ni en contra.")
elif pend < 0 and t <= -2:
    print("\nVEREDICTO: CONFIRMADA (pendiente < 0 y t <= -2).")
else:
    print("\nVEREDICTO: REFUTADA (no se cumple pendiente < 0 con t <= -2).")
    print("Significa 'sin efecto del tamaño grande', no 'efecto cero'.")
