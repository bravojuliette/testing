"""Auditoria de calibracion: ¿cuanto cobra Bwin de mas en cada peldaño de su
escalera de totales? No es mineria de estrategias (no se filtra nada, no se
elige nada) -- es medir, con TODOS los partidos que tienen linea de Bwin,
la distribucion real de (total_final - linea) y compararla con los precios
de la escalera que dio el usuario:

    peldaño -2: 2.05  (prob. implicita 48.8%)
    peldaño  0: 1.87  (53.5%)
    peldaño +2: 1.72  (58.1%)
    peldaño +4: 1.60  (62.5%)
    peldaño +6: 1.50  (66.7%)

EV de apostar under en el peldaño k SIEMPRE (sin señal alguna):
    EV = P_real(final < L+k) * (cuota-1) - (1 - P_real)
Si algun peldaño tuviera EV ~0 o positivo sin señal, alli el margen es nulo
y CUALQUIER señal pequeña seria rentable. Donde el EV sea muy negativo, la
escalera cobra caro y hara falta una señal enorme.
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")  # correr desde la raiz del repo: python3 bball/analysis/<script>.py

from bball import db

LADDER = [(-2, 2.05), (0, 1.87), (2, 1.72), (4, 1.60), (6, 1.50)]

with db.get_conn() as conn:
    rows = conn.execute(
        """SELECT o.event_id, o.line, o.under_odds, o.over_odds, o.snapshot,
                  g.home_score + g.away_score AS final, g.league_name AS league
           FROM bball_odds o JOIN bball_games g ON g.event_id = o.event_id
           WHERE o.market='18_3' AND o.book='BWin' AND g.completed=1
           ORDER BY o.event_id, o.snapshot"""
    ).fetchall()
    pin_rows = conn.execute(
        """SELECT o.event_id, o.line, o.snapshot, g.league_name AS league
           FROM bball_odds o JOIN bball_games g ON g.event_id = o.event_id
           WHERE o.market='18_3' AND o.book='PinnacleSports' AND g.completed=1
           ORDER BY o.event_id, o.snapshot"""
    ).fetchall()

# snapshot end si existe, si no start
bwin = {}
for r in rows:
    if r["snapshot"] == "end" or r["event_id"] not in bwin:
        bwin[r["event_id"]] = r
pin = {}
for r in pin_rows:
    if r["snapshot"] == "end" or r["event_id"] not in pin:
        pin[r["event_id"]] = r

diffs_all = []
diffs_by_league = defaultdict(list)
odds_main = []
for eid, r in bwin.items():
    d = r["final"] - r["line"]
    diffs_all.append(d)
    diffs_by_league[r["league"]].append(d)
    if r["under_odds"] and r["over_odds"]:
        odds_main.append((r["under_odds"], r["over_odds"]))

n = len(diffs_all)
print(f"Partidos con linea de totales de Bwin y resultado final: {n}")
print(f"final - linea: media={statistics.mean(diffs_all):+.2f}  mediana={statistics.median(diffs_all):+.1f}  "
      f"desv={statistics.pstdev(diffs_all):.1f}")
under_hits = sum(1 for d in diffs_all if d < 0)
pushes = sum(1 for d in diffs_all if d == 0)
print(f"P(final < linea principal) = {under_hits/(n-pushes)*100:.1f}%  (pushes: {pushes})")
mu = statistics.mean([u for u, o in odds_main])
mo = statistics.mean([o for u, o in odds_main])
margin = (1/mu + 1/mo - 1) * 100
print(f"Cuotas medias linea ppal: under {mu:.3f} / over {mo:.3f}  -> margen de Bwin: {margin:.1f}%\n")

print("Calibracion de la escalera (apostando under en el peldaño k SIEMPRE, sin señal):")
print(f"{'peldaño':>8} {'cuota':>6} {'P implicita':>11} {'P real':>8} {'dif':>7} {'EV%':>7}")
for k, o in LADDER:
    dec = [d for d in diffs_all if d != k]  # excluye push exacto en esa linea
    p_real = sum(1 for d in dec if d < k) / len(dec)
    p_imp = 1 / o
    ev = (p_real * (o - 1) - (1 - p_real)) * 100
    print(f"{k:>+8} {o:>6.2f} {p_imp*100:>10.1f}% {p_real*100:>7.1f}% {(p_real-p_imp)*100:>+6.1f}pp {ev:>+7.1f}")

print("\nMismo analisis del lado OVER (cuota espejo aproximada: misma escalera invertida):")
for k, o_under in LADDER:
    # cuota over en el peldaño k ~ espejo de la under en -k (simetria de la escalera)
    o_over = dict((kk, oo) for kk, oo in LADDER).get(-k)
    if o_over is None:
        continue
    dec = [d for d in diffs_all if d != k]
    p_real = sum(1 for d in dec if d > k) / len(dec)
    ev = (p_real * (o_over - 1) - (1 - p_real)) * 100
    print(f"  over peldaño {k:+d} (cuota ~{o_over:.2f}): P real {p_real*100:.1f}%  EV {ev:+.1f}%")

print("\nPor liga (final - linea Bwin):")
for lg, ds in sorted(diffs_by_league.items(), key=lambda kv: -len(kv[1])):
    if len(ds) < 10:
        continue
    dec = [d for d in ds if d != 0]
    p_under = sum(1 for d in dec if d < 0) / len(dec) * 100
    print(f"  {lg:<12} n={len(ds):>4}  media={statistics.mean(ds):+.2f}  P(under)={p_under:.1f}%")

print("\nSesgo de la linea de Bwin respecto a Pinnacle (misma cancha, por liga):")
byl = defaultdict(list)
for eid, r in bwin.items():
    p = pin.get(eid)
    if p is not None:
        byl[r["league"]].append(r["line"] - p["line"])
for lg, ds in sorted(byl.items(), key=lambda kv: -len(kv[1])):
    if len(ds) < 10:
        continue
    print(f"  {lg:<12} n={len(ds):>4}  Bwin - Pinnacle: media={statistics.mean(ds):+.2f}  mediana={statistics.median(ds):+.1f}")
