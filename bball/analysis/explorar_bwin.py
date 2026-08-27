"""Busqueda de señales APOSTABLES SOLO EN BWIN (linea y cuota de Bwin, una
apuesta por partido, sin arbitraje ni line-shopping). Las señales posibles
usan cualquier informacion previa al partido (medias, movimiento del mercado
apertura->cierre, la referencia Pinnacle), pero la ejecucion es siempre la
misma: under u over en la linea principal de Bwin, a la cuota de Bwin.

Disciplina busqueda/reserva igual que siempre: se elige en la busqueda
(fecha < HOLDOUT_START), la reserva solo confirma o refuta.
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")  # correr desde la raiz del repo: python3 bball/analysis/<script>.py

from bball import db
from bball.backtest.replay import load_games

N = 10
HOLDOUT_START = "2026-02-01"   # Bwin tiene ~380 eventos; corte para ~55/45

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds, snapshot FROM bball_odds "
        "WHERE market='18_3' ORDER BY event_id, book, snapshot"
    ).fetchall()

by_eb = {}
start_of = {}
for r in rows:
    key = (r["event_id"], r["book"])
    if r["snapshot"] == "end":
        by_eb[key] = r
    else:
        start_of[key] = r
        by_eb.setdefault(key, r)

odds_by_event = defaultdict(dict)
moves_by_event = defaultdict(list)
for (eid, book), r in by_eb.items():
    odds_by_event[eid][book] = r
    s = start_of.get((eid, book))
    if s is not None and r["snapshot"] == "end":
        moves_by_event[eid].append(r["line"] - s["line"])

pf = defaultdict(list)
tot = defaultdict(list)
last_ts = {}
samples = []
for g in games:
    books = odds_by_event.get(g.event_id, {})
    bw = books.get("BWin")
    if bw is not None and len(pf[g.home_key]) >= N and len(pf[g.away_key]) >= N:
        sum_avg = sum(pf[g.home_key][-N:]) / N + sum(pf[g.away_key][-N:]) / N
        max_tot = max(sum(tot[g.home_key][-N:]) / N, sum(tot[g.away_key][-N:]) / N)
        pin = books.get("PinnacleSports")
        moves = moves_by_event.get(g.event_id, [])
        others = [r["line"] for b, r in books.items() if b != "BWin"]
        rest_h = (g.time_ts - last_ts[g.home_key]) / 86400 if g.home_key in last_ts else None
        rest_a = (g.time_ts - last_ts[g.away_key]) / 86400 if g.away_key in last_ts else None
        bw_start = start_of.get((g.event_id, "BWin"))
        samples.append(dict(
            date=g.date, league=g.league_name, final=g.total,
            L=bw["line"], under=bw["under_odds"], over=bw["over_odds"],
            bw_move=(bw["line"] - bw_start["line"]) if (bw_start and bw["snapshot"] == "end") else None,
            sum_avg=sum_avg, max_tot=max_tot, gap=max_tot - sum_avg,
            pin_line=pin["line"] if pin else None,
            med_move=statistics.median(moves) if moves else None,
            consensus=statistics.median(others) if others else None,
            rest_min=min(x for x in (rest_h, rest_a) if x is not None) if (rest_h or rest_a) else None,
        ))
    pf[g.home_key].append(g.home_score)
    pf[g.away_key].append(g.away_score)
    tot[g.home_key].append(g.total)
    tot[g.away_key].append(g.total)
    last_ts[g.home_key] = g.time_ts
    last_ts[g.away_key] = g.time_ts

search = [s for s in samples if s["date"] < HOLDOUT_START]
hold = [s for s in samples if s["date"] >= HOLDOUT_START]
print(f"Partidos con Bwin + historial: {len(samples)}  (busqueda {len(search)} / reserva {len(hold)})\n")

STRATS = []

# A: gaps de medias, ejecutados en la linea de Bwin
for thr in (6, 8, 10, 12):
    STRATS.append((f"under Bwin si linea_Bwin - sum_avg >= {thr}",
                   lambda s, thr=thr: "U" if (s["L"] - s["sum_avg"]) >= thr else None))
for thr in (8, 10, 12):
    STRATS.append((f"under Bwin si max_tot - sum_avg >= {thr}",
                   lambda s, thr=thr: "U" if s["gap"] >= thr else None))
    STRATS.append((f"OVER Bwin si max_tot - sum_avg >= {thr}",
                   lambda s, thr=thr: "O" if s["gap"] >= thr else None))
for thr in (4, 6, 8):
    STRATS.append((f"OVER Bwin si sum_avg - linea_Bwin >= {thr}",
                   lambda s, thr=thr: "O" if (s["sum_avg"] - s["L"]) >= thr else None))

# P: Bwin desalineada con Pinnacle (se apuesta SOLO en Bwin)
for thr in (1.5, 2, 3):
    STRATS.append((f"under Bwin si linea_Bwin >= Pinnacle + {thr}",
                   lambda s, thr=thr: "U" if s["pin_line"] is not None and (s["L"] - s["pin_line"]) >= thr else None))
    STRATS.append((f"over Bwin si linea_Bwin <= Pinnacle - {thr}",
                   lambda s, thr=thr: "O" if s["pin_line"] is not None and (s["pin_line"] - s["L"]) >= thr else None))

# K: Bwin desalineada con el consenso del mercado (se apuesta SOLO en Bwin)
for thr in (1.5, 2, 3):
    STRATS.append((f"under Bwin si linea_Bwin >= consenso + {thr}",
                   lambda s, thr=thr: "U" if s["consensus"] is not None and (s["L"] - s["consensus"]) >= thr else None))
    STRATS.append((f"over Bwin si linea_Bwin <= consenso - {thr}",
                   lambda s, thr=thr: "O" if s["consensus"] is not None and (s["consensus"] - s["L"]) >= thr else None))

# D: seguir el movimiento del mercado, ejecutado en Bwin
for thr in (1, 1.5, 2):
    STRATS.append((f"under Bwin si el mercado bajo la linea >= {thr}",
                   lambda s, thr=thr: "U" if s["med_move"] is not None and s["med_move"] <= -thr else None))
    STRATS.append((f"over Bwin si el mercado subio la linea >= {thr}",
                   lambda s, thr=thr: "O" if s["med_move"] is not None and s["med_move"] >= thr else None))

# DB: movimiento de la PROPIA linea de Bwin
for thr in (1, 2):
    STRATS.append((f"under Bwin si Bwin bajo su linea >= {thr}",
                   lambda s, thr=thr: "U" if s["bw_move"] is not None and s["bw_move"] <= -thr else None))
    STRATS.append((f"over Bwin si Bwin subio su linea >= {thr}",
                   lambda s, thr=thr: "O" if s["bw_move"] is not None and s["bw_move"] >= thr else None))

# E: descanso
STRATS.append(("under Bwin si algun equipo en back-to-back",
               lambda s: "U" if s["rest_min"] is not None and s["rest_min"] <= 1.2 else None))


def evaluate(fn, subset):
    pnls, wins, dec = [], 0, 0
    for s in subset:
        side = fn(s)
        if not side:
            continue
        odds = s["under"] if side == "U" else s["over"]
        if not odds or odds <= 1:
            continue
        if s["final"] == s["L"]:
            pnls.append(0.0)
            continue
        won = s["final"] < s["L"] if side == "U" else s["final"] > s["L"]
        pnls.append(odds - 1 if won else -1.0)
        dec += 1
        wins += won
    n = len(pnls)
    if n == 0:
        return None
    roi = sum(pnls) / n * 100
    sd = statistics.pstdev(pnls) if n > 1 else 0
    t = (statistics.mean(pnls) / sd) * (n ** 0.5) if sd > 0 else None
    return dict(n=n, roi=roi, t=t, hit=wins / dec * 100 if dec else 0)


print(f"{'estrategia (apuesta SIEMPRE en Bwin)':<52} {'n':>4} {'hit%':>6} {'ROI%':>7} {'t':>6}")
survivors = []
for name, fn in STRATS:
    r = evaluate(fn, search)
    if r is None:
        continue
    t_str = f"{r['t']:.2f}" if r["t"] is not None else "-"
    flag = ""
    if r["n"] >= 25 and r["t"] is not None and r["t"] >= 2:
        flag = "  <-- pasa a reserva"
        survivors.append((name, fn))
    print(f"{name:<52} {r['n']:>4} {r['hit']:>6.1f} {r['roi']:>+7.1f} {t_str:>6}{flag}")

print(f"\n=== RESERVA (>= {HOLDOUT_START}) ===")
if not survivors:
    print("Ninguna señal paso el liston (n>=25, t>=2) en la busqueda.")
for name, fn in survivors:
    r = evaluate(fn, hold)
    if r is None:
        print(f"{name}: sin apuestas en la reserva")
        continue
    t_str = f"{r['t']:.2f}" if r["t"] is not None else "-"
    print(f"{name:<52} n={r['n']} hit={r['hit']:.1f}% ROI={r['roi']:+.1f}% t={t_str}")
