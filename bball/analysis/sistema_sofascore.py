"""Sistema exacto del usuario (ejemplo Seattle Storm vs Toronto Tempo):

1. suma_medias = media pts anotados (ult. 10) local + visitante  (ej: 85+84=169)
2. max_total   = MAYOR "total medio de partido" de los dos equipos (ej: max(177,179)=179)
   -> media del total de puntos (propios+rival) en los ult. 10 partidos de cada equipo
3. FILTRO: max_total - suma_medias >= 10  (ej: 179-169=10 OK)
4. Linea a apostar: la primera de la escalera de Bwin ESTRICTAMENTE por encima
   de max_total (ej: 179.5). La escalera va en pasos de 2 desde la linea
   principal L0; la cuota de cada peldano sale del modelo ajustado a los 5
   precios que dio el usuario: p(shift) = 1/O0 + 0.022398*shift
   (-2:2.05, 0:1.87, +2:1.72, +4:1.60, +6:1.50 -- error de ajuste < 0.3pp).

Pregunta: ¿con que frecuencia pasa, y que peldano (el objetivo o mas agresivo)
maximiza el ROI? Stake de referencia: 100 EUR por apuesta.
"""
import math
import sys
from collections import defaultdict

sys.path.insert(0, ".")  # correr desde la raiz del repo: python3 bball/analysis/<script>.py

from bball import db
from bball.backtest.replay import load_games

N = 10
B = 0.022398          # pendiente prob-por-punto del ajuste de la escalera
MIN_GAP = 10.0        # filtro: max_total - suma_medias >= 10
STAKE = 100.0

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, line, under_odds FROM bball_odds "
        "WHERE market='18_3' AND book='BWin' ORDER BY event_id, under_odds DESC"
    ).fetchall()

bwin = {}
for r in rows:
    bwin.setdefault(r["event_id"], (r["line"], r["under_odds"]))

pf = defaultdict(list)    # puntos anotados por equipo, cronologico
tot = defaultdict(list)   # total del partido por equipo, cronologico

qual = []
n_evaluables_bwin = 0
for g in games:
    if g.event_id in bwin and len(pf[g.home_key]) >= N and len(pf[g.away_key]) >= N:
        n_evaluables_bwin += 1
        sum_avg = sum(pf[g.home_key][-N:]) / N + sum(pf[g.away_key][-N:]) / N
        max_tot = max(sum(tot[g.home_key][-N:]) / N, sum(tot[g.away_key][-N:]) / N)
        if max_tot - sum_avg >= MIN_GAP:
            L0, O0 = bwin[g.event_id]
            k = math.floor((max_tot - L0) / 2) + 1   # primer peldano > max_tot
            L_target = L0 + 2 * k
            qual.append(dict(
                date=g.date, league=g.league_name, home=g.home_team, away=g.away_team,
                final=g.total, sum_avg=sum_avg, max_tot=max_tot,
                L0=L0, O0=O0, L_target=L_target, shift_target=L_target - L0,
            ))
    pf[g.home_key].append(g.home_score)
    pf[g.away_key].append(g.away_score)
    tot[g.home_key].append(g.total)
    tot[g.away_key].append(g.total)

print(f"Partidos evaluables (cuota Bwin + 10 partidos previos ambos): {n_evaluables_bwin}")
print(f"Cumplen el filtro (max_total - suma_medias >= {MIN_GAP:.0f}): {len(qual)}\n")

if not qual:
    raise SystemExit("Sin partidos que cumplan el filtro.")

by_month = defaultdict(int)
for q in qual:
    by_month[q["date"][:7]] += 1
print("Frecuencia por mes:", dict(sorted(by_month.items())))
print()

print("Partidos que cumplen (todos):")
for q in qual:
    print(f"  {q['date']}  [{q['league']}] {q['home']} vs {q['away']}")
    print(f"      suma_medias={q['sum_avg']:.1f}  max_total={q['max_tot']:.1f}  (gap={q['max_tot']-q['sum_avg']:.1f})")
    print(f"      linea ppal Bwin={q['L0']} @{q['O0']:.2f}  ->  linea objetivo={q['L_target']} (shift {q['shift_target']:+.0f})")
    print(f"      total real={q['final']}")
print()

def odds_at(q, line):
    shift = line - q["L0"]
    p = 1 / q["O0"] + B * shift
    if p <= 0.02 or p >= 0.98:
        return None, shift
    return 1 / p, shift

print(f"{'peldano':>22} {'n':>4} {'hit':>7} {'ROI%':>7} {'cuota_med':>9} {'EUR netos (100/ap.)':>20} {'extrapolados':>12}")
results = []
for k_down in range(0, 6):
    label = "objetivo" if k_down == 0 else f"objetivo -{2*k_down}"
    n = wins = extrap = 0
    pnl = 0.0
    odds_sum = 0.0
    for q in qual:
        line = q["L_target"] - 2 * k_down
        o, shift = odds_at(q, line)
        if o is None:
            continue
        if shift < -2 or shift > 6:
            extrap += 1
        n += 1
        odds_sum += o
        if q["final"] < line:
            wins += 1
            pnl += o - 1
        elif q["final"] > line:
            pnl -= 1
    if n == 0:
        continue
    roi = pnl / n * 100
    eur = pnl * STAKE
    results.append((label, n, wins, roi, odds_sum / n, eur, extrap))
    print(f"{label:>22} {n:>4} {wins:>3}/{n:<3} {roi:>7.1f} {odds_sum/n:>9.2f} {eur:>+20.0f} {extrap:>12}")

best = max(results, key=lambda r: r[3])
print(f"\nMejor ROI: '{best[0]}' -> {best[3]:+.1f}% ({best[2]}/{best[1]} aciertos, cuota media {best[4]:.2f}, {best[5]:+.0f} EUR con 100 EUR/apuesta)")
print("'extrapolados' = apuestas cuyo peldano cae fuera del rango -2..+6 confirmado por el usuario (cuota estimada, menos fiable).")
