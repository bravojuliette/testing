"""Verificacion anti-espejismo para la estrategia superviviente D-over
(mercado subio la linea apertura->cierre >= 1.5 -> over en la casa con la
linea MAS BAJA disponible) y para C-under (casa >= Pinnacle+3/4).

Riesgo: la "mejor linea" elegida puede ser un snapshot VIEJO (captured_at
horas antes del pitido) de una casa lenta -- una linea que en la practica ya
no existia cuando el mercado se movio. Si el ROI depende de lineas rancias,
es un espejismo de datos, no una estrategia apostable.

Se re-evalua la estrategia exigiendo que la linea apostada haya sido
capturada a menos de X horas del inicio del partido.
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
        "SELECT event_id, book, line, over_odds, under_odds, snapshot, captured_at FROM bball_odds "
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

odds_by_event = defaultdict(list)
moves_by_event = defaultdict(list)
for (eid, book), r in by_eb.items():
    odds_by_event[eid].append((
        book, r["line"], r["over_odds"], r["under_odds"],
        int(r["captured_at"]) if r["captured_at"] is not None else None,
    ))
    s = start_of.get((eid, book))
    if s is not None and r["snapshot"] == "end":
        moves_by_event[eid].append(r["line"] - s["line"])

pf = defaultdict(list)
tot = defaultdict(list)
samples = []
for g in games:
    o = odds_by_event.get(g.event_id, [])
    if o and len(pf[g.home_key]) >= N and len(pf[g.away_key]) >= N:
        moves = moves_by_event.get(g.event_id, [])
        pin = next((x for x in o if x[0] == "PinnacleSports"), None)
        samples.append(dict(
            date=g.date, final=g.total, odds=o, time_ts=g.time_ts,
            med_move=statistics.median(moves) if moves else None,
            pin_line=pin[1] if pin else None,
        ))
    pf[g.home_key].append(g.home_score)
    pf[g.away_key].append(g.away_score)
    tot[g.home_key].append(g.total)
    tot[g.away_key].append(g.total)


def run(name, pick_bet, max_age_h):
    """pick_bet(s, fresh_odds) -> ('O'|'U', line, odds) o None"""
    out = {}
    for label, subset in (("busqueda", [s for s in samples if s["date"] < HOLDOUT_START]),
                          ("reserva", [s for s in samples if s["date"] >= HOLDOUT_START])):
        pnls, wins, dec = [], 0, 0
        ages = []
        for s in subset:
            if max_age_h is None:
                fresh = s["odds"]
            else:
                fresh = [x for x in s["odds"]
                         if x[4] is not None and 0 <= (s["time_ts"] - x[4]) <= max_age_h * 3600]
            bet = pick_bet(s, fresh)
            if not bet:
                continue
            side, line, odds, cap = bet
            if cap is not None:
                ages.append((s["time_ts"] - cap) / 3600)
            if s["final"] == line:
                pnls.append(0.0)
                continue
            won = s["final"] > line if side == "O" else s["final"] < line
            pnls.append(odds - 1 if won else -1.0)
            dec += 1
            wins += won
        n = len(pnls)
        if n == 0:
            out[label] = None
            continue
        roi = sum(pnls) / n * 100
        sd = statistics.pstdev(pnls) if n > 1 else 0
        t = (statistics.mean(pnls) / sd) * (n ** 0.5) if sd > 0 else None
        out[label] = (n, wins / dec * 100 if dec else 0, roi, t,
                      statistics.median(ages) if ages else None)
    b, h = out.get("busqueda"), out.get("reserva")
    def fmt(r):
        if r is None:
            return "sin apuestas"
        t_str = f"{r[3]:.2f}" if r[3] is not None else "-"
        age = f", antiguedad mediana {r[4]:.1f}h" if r[4] is not None else ""
        return f"n={r[0]} hit={r[1]:.1f}% ROI={r[2]:+.1f}% t={t_str}{age}"
    print(f"{name}")
    print(f"    busqueda: {fmt(b)}")
    print(f"    reserva : {fmt(h)}")


def d_over(s, fresh):
    if s["med_move"] is None or s["med_move"] < 1.5:
        return None
    c = [x for x in fresh if x[2] and x[2] > 1]
    if not c:
        return None
    b = min(c, key=lambda x: (x[1], -x[2]))
    return ("O", b[1], b[2], b[4])


def c_under(thr):
    def fn(s, fresh):
        if s["pin_line"] is None:
            return None
        c = [x for x in fresh if x[0] != "PinnacleSports" and x[3] and x[3] > 1]
        if not c:
            return None
        b = max(c, key=lambda x: (x[1] - s["pin_line"], x[3]))
        if (b[1] - s["pin_line"]) >= thr:
            return ("U", b[1], b[3], b[4])
    return fn


for age in (None, 12, 3, 1):
    label = "sin limite de frescura" if age is None else f"solo lineas capturadas < {age}h antes del inicio"
    print(f"\n=== {label} ===")
    run("D-over: mercado subio >=1.5, over en la linea mas baja", d_over, age)
    run("C-under: casa >= Pinnacle+3, under en esa casa", c_under(3), age)
    run("C-under: casa >= Pinnacle+4, under en esa casa", c_under(4), age)
