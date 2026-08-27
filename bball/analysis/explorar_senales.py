"""Busqueda amplia de señales en totales de basketball, con disciplina
busqueda/reserva: TODO se barre en la ventana de busqueda; solo lo que pase
n>=40 y t>=2 alli se evalua en la reserva (fecha >= HOLDOUT_START, jamas
usada para elegir). Con ~30 estrategias probadas, esperar 1-2 falsos
positivos en busqueda es normal -- la reserva decide.

Sin look-ahead: features calculadas solo con partidos ESTRICTAMENTE
anteriores; historiales se actualizan despues de evaluar cada partido.
Cuotas: snapshot 'end' (ultimo pre-partido) si existe, si no 'start' --
ambos ya filtrados a pre-partido en el collect.
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")  # correr desde la raiz del repo: python3 bball/analysis/<script>.py

from bball import db
from bball.backtest.replay import load_games

N = 10
HOLDOUT_START = "2026-02-15"

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds, snapshot FROM bball_odds "
        "WHERE market='18_3' ORDER BY event_id, book, snapshot"
    ).fetchall()

# Por (evento, casa): quedarse con el snapshot 'end' si existe, si no 'start'.
by_eb = {}
start_of = {}
for r in rows:
    key = (r["event_id"], r["book"])
    if r["snapshot"] == "end":
        by_eb[key] = r
    else:
        start_of[key] = r
        by_eb.setdefault(key, r)

odds_by_event = defaultdict(list)   # evento -> [(book, line, over, under)]
moves_by_event = defaultdict(list)  # evento -> [line_end - line_start]
for (eid, book), r in by_eb.items():
    odds_by_event[eid].append((book, r["line"], r["over_odds"], r["under_odds"]))
    s = start_of.get((eid, book))
    if s is not None and r["snapshot"] == "end":
        moves_by_event[eid].append(r["line"] - s["line"])

# ------------------- features walk-forward -------------------
pf = defaultdict(list)
tot = defaultdict(list)
last_ts = {}

samples = []  # un dict por partido evaluable
for g in games:
    o = odds_by_event.get(g.event_id, [])
    if o and len(pf[g.home_key]) >= N and len(pf[g.away_key]) >= N:
        sum_avg = sum(pf[g.home_key][-N:]) / N + sum(pf[g.away_key][-N:]) / N
        max_tot = max(sum(tot[g.home_key][-N:]) / N, sum(tot[g.away_key][-N:]) / N)
        lines = [x[1] for x in o]
        consensus = statistics.median(lines)
        pin = next((x for x in o if x[0] == "PinnacleSports"), None)
        moves = moves_by_event.get(g.event_id, [])
        rest_h = (g.time_ts - last_ts[g.home_key]) / 86400 if g.home_key in last_ts else None
        rest_a = (g.time_ts - last_ts[g.away_key]) / 86400 if g.away_key in last_ts else None
        samples.append(dict(
            date=g.date, league=g.league_name, final=g.total, odds=o,
            sum_avg=sum_avg, max_tot=max_tot, gap=max_tot - sum_avg,
            consensus=consensus, pin_line=pin[1] if pin else None,
            med_move=statistics.median(moves) if moves else None,
            rest_min=min(x for x in (rest_h, rest_a) if x is not None) if (rest_h or rest_a) else None,
        ))
    pf[g.home_key].append(g.home_score)
    pf[g.away_key].append(g.away_score)
    tot[g.home_key].append(g.total)
    tot[g.away_key].append(g.total)
    last_ts[g.home_key] = g.time_ts
    last_ts[g.away_key] = g.time_ts

print(f"Partidos evaluables (cuotas + historial N={N} ambos equipos): {len(samples)}")
n_search = sum(1 for s in samples if s["date"] < HOLDOUT_START)
print(f"Busqueda (< {HOLDOUT_START}): {n_search} | Reserva: {len(samples) - n_search}\n")


def settle(side, line, odds, final):
    if final == line:
        return 0.0, None
    if side == "U":
        won = final < line
    else:
        won = final > line
    return (odds - 1 if won else -1.0), won


def best_under(o):   # linea mas alta; a igual linea, mejor cuota
    c = [x for x in o if x[3] and x[3] > 1]
    return max(c, key=lambda x: (x[1], x[3])) if c else None


def best_over(o):    # linea mas baja; a igual linea, mejor cuota
    c = [x for x in o if x[2] and x[2] > 1]
    return min(c, key=lambda x: (x[1], -x[2])) if c else None


STRATS = []

def strat(name):
    def deco(fn):
        STRATS.append((name, fn))
        return fn
    return deco

# --- familia A: gaps de medias (tu familia, ambas direcciones) ---
for thr in (8, 10, 12, 15):
    def a_under(s, thr=thr):
        b = best_under(s["odds"])
        if b and (b[1] - s["sum_avg"]) >= thr:
            return ("U", b[1], b[3])
    STRATS.append((f"A: under mejor linea, linea-sum_avg>={thr}", a_under))
for thr in (10, 12, 14):
    def a_gap_under(s, thr=thr):
        b = best_under(s["odds"])
        if b and s["gap"] >= thr:
            return ("U", b[1], b[3])
    STRATS.append((f"A: under mejor linea, max_tot-sum_avg>={thr}", a_gap_under))
    def a_gap_over(s, thr=thr):
        b = best_over(s["odds"])
        if b and s["gap"] >= thr:
            return ("O", b[1], b[2])
    STRATS.append((f"A: OVER mejor linea, max_tot-sum_avg>={thr}", a_gap_over))
for thr in (5, 8):
    def a_over(s, thr=thr):
        b = best_over(s["odds"])
        if b and (s["sum_avg"] - b[1]) >= thr:
            return ("O", b[1], b[2])
    STRATS.append((f"A: OVER mejor linea, sum_avg-linea>={thr}", a_over))

# --- familia B: casa desviada del consenso ---
for thr in (1.5, 2, 2.5, 3, 4):
    def b_under(s, thr=thr):
        c = [x for x in s["odds"] if x[3] and x[3] > 1]
        if not c:
            return None
        b = max(c, key=lambda x: (x[1] - s["consensus"], x[3]))
        if (b[1] - s["consensus"]) >= thr:
            return ("U", b[1], b[3])
    STRATS.append((f"B: under en casa con linea >= consenso+{thr}", b_under))
    def b_over(s, thr=thr):
        c = [x for x in s["odds"] if x[2] and x[2] > 1]
        if not c:
            return None
        b = max(c, key=lambda x: (s["consensus"] - x[1], x[2]))
        if (s["consensus"] - b[1]) >= thr:
            return ("O", b[1], b[2])
    STRATS.append((f"B: over en casa con linea <= consenso-{thr}", b_over))

# --- familia C: casa desviada de Pinnacle (referencia sharp) ---
for thr in (1.5, 2, 3, 4):
    def c_under(s, thr=thr):
        if s["pin_line"] is None:
            return None
        c = [x for x in s["odds"] if x[0] != "PinnacleSports" and x[3] and x[3] > 1]
        if not c:
            return None
        b = max(c, key=lambda x: (x[1] - s["pin_line"], x[3]))
        if (b[1] - s["pin_line"]) >= thr:
            return ("U", b[1], b[3])
    STRATS.append((f"C: under en casa con linea >= Pinnacle+{thr}", c_under))
    def c_over(s, thr=thr):
        if s["pin_line"] is None:
            return None
        c = [x for x in s["odds"] if x[0] != "PinnacleSports" and x[2] and x[2] > 1]
        if not c:
            return None
        b = max(c, key=lambda x: (s["pin_line"] - x[1], x[2]))
        if (s["pin_line"] - b[1]) >= thr:
            return ("O", b[1], b[2])
    STRATS.append((f"C: over en casa con linea <= Pinnacle-{thr}", c_over))

# --- familia D: seguir el movimiento apertura->cierre ---
for thr in (1.5, 2, 3):
    def d_under(s, thr=thr):
        if s["med_move"] is not None and s["med_move"] <= -thr:
            b = best_under(s["odds"])
            if b:
                return ("U", b[1], b[3])
    STRATS.append((f"D: under si el mercado bajo la linea >={thr} pts", d_under))
    def d_over(s, thr=thr):
        if s["med_move"] is not None and s["med_move"] >= thr:
            b = best_over(s["odds"])
            if b:
                return ("O", b[1], b[2])
    STRATS.append((f"D: over si el mercado subio la linea >={thr} pts", d_over))

# --- familia E: back-to-back (cansancio -> menos puntos?) ---
def e_b2b(s):
    if s["rest_min"] is not None and s["rest_min"] <= 1.2:
        b = best_under(s["odds"])
        if b:
            return ("U", b[1], b[3])
STRATS.append(("E: under si algun equipo juega back-to-back", e_b2b))


def evaluate(fn, subset):
    pnls, wins, dec = [], 0, 0
    for s in subset:
        bet = fn(s)
        if not bet:
            continue
        side, line, odds = bet
        pnl, won = settle(side, line, odds, s["final"])
        pnls.append(pnl)
        if won is not None:
            dec += 1
            wins += won
    n = len(pnls)
    if n == 0:
        return None
    roi = sum(pnls) / n * 100
    sd = statistics.pstdev(pnls) if n > 1 else 0
    t = (statistics.mean(pnls) / sd) * (n ** 0.5) if sd > 0 else None
    hit = wins / dec * 100 if dec else 0
    return dict(n=n, roi=roi, t=t, hit=hit)


search = [s for s in samples if s["date"] < HOLDOUT_START]
hold = [s for s in samples if s["date"] >= HOLDOUT_START]

print(f"{'estrategia':<52} {'n':>5} {'hit%':>6} {'ROI%':>7} {'t':>6}")
survivors = []
for name, fn in STRATS:
    r = evaluate(fn, search)
    if r is None:
        continue
    t_str = f"{r['t']:.2f}" if r["t"] is not None else "-"
    flag = ""
    if r["n"] >= 40 and r["t"] is not None and r["t"] >= 2:
        flag = "  <-- pasa a reserva"
        survivors.append((name, fn))
    print(f"{name:<52} {r['n']:>5} {r['hit']:>6.1f} {r['roi']:>+7.1f} {t_str:>6}{flag}")

print(f"\n=== RESERVA (>= {HOLDOUT_START}, solo supervivientes de busqueda) ===")
if not survivors:
    print("Ninguna estrategia paso el liston (n>=40 y t>=2) en la busqueda.")
for name, fn in survivors:
    r = evaluate(fn, hold)
    if r is None:
        print(f"{name}: sin apuestas en la reserva")
        continue
    t_str = f"{r['t']:.2f}" if r["t"] is not None else "-"
    print(f"{name:<52} n={r['n']} hit={r['hit']:.1f}% ROI={r['roi']:+.1f}% t={t_str}")
