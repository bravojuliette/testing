"""Teoria del usuario: 'hay dias de overs y dias de unders en una misma
competicion' -- ¿los resultados over/under de los partidos YA TERMINADOS de
un dia predicen los siguientes partidos de ese dia (misma liga)? Y la version
generalizada: ¿la tasa de overs de la liga en los ultimos D dias predice?

Dos capas:
1. CALIBRACION (sin cuotas): P(over) en los partidos posteriores segun el
   neto over/under de los partidos previos del dia. Si es ~50%, la teoria
   muere aqui, con o sin margen.
2. APUESTA: ejecucion al CIERRE real (kickoff) de las casas legales, en las
   dos direcciones (momentum y contrarian), split 2025-26 / 2024-25.

Anti-fuga: un partido previo del dia solo cuenta si su inicio fue >= 2.5h
antes del inicio del partido evaluado (ya habra terminado al pitido). El
over/under de cada partido se mide contra SU consenso de cierre (mediana de
lineas kickoff; fallback apertura).
"""
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, ".")  # correr desde la raiz del repo

from bball import db
from bball.backtest.replay import load_games

SPLIT = "2025-10-01"
LEGAL_BOOKS = ["Bet365", "Betway", "BWin"]
FINISH_GAP_S = int(2.5 * 3600)
MIN_N = 30

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds, snapshot FROM bball_odds "
        "WHERE market='18_3' AND snapshot IN ('start','kickoff')"
    ).fetchall()

kick = defaultdict(dict)
opens = defaultdict(dict)
for r in rows:
    (kick if r["snapshot"] == "kickoff" else opens)[r["event_id"]][r["book"]] = r

# por partido: linea de referencia del mercado (consenso de cierre) y resultado O/U
info = {}
for g in games:
    ks = kick.get(g.event_id, {})
    lines = [r["line"] for r in ks.values()] or [r["line"] for r in opens.get(g.event_id, {}).values()]
    if not lines:
        continue
    ref = statistics.median(lines)
    ou = 1 if g.total > ref else (-1 if g.total < ref else 0)
    info[g.event_id] = dict(ref=ref, ou=ou)

# features walk-forward: neto del dia (previos terminados, misma liga) y tasa rodante
games_sorted = sorted(games, key=lambda g: g.time_ts)
by_league_day = defaultdict(list)   # (liga, fecha) -> [(time_ts, ou)]
daily_net = defaultdict(dict)       # (liga, fecha) -> neto del dia completo (para rolling por dias previos)
for g in games_sorted:
    i = info.get(g.event_id)
    if i is None:
        continue
    by_league_day[(g.league_name, g.date)].append((g.time_ts, i["ou"]))

# tasa de overs por (liga, fecha) para la version rodante multi-dia
day_rate = {}
for key, lst in by_league_day.items():
    dec = [ou for _, ou in lst if ou != 0]
    if dec:
        day_rate[key] = (sum(1 for x in dec if x > 0), len(dec))

samples = []
for g in games_sorted:
    i = info.get(g.event_id)
    if i is None:
        continue  # sin ninguna linea: ni referencia ni cuota que apostar
    prev = [ou for ts, ou in by_league_day[(g.league_name, g.date)]
            if ts + FINISH_GAP_S <= g.time_ts and ou != 0]
    net = sum(prev)
    d = date.fromisoformat(g.date)
    rolling = {}
    for D in (3, 7, 14):
        ov = tot_n = 0
        for k in range(1, D + 1):
            r = day_rate.get((g.league_name, (d - timedelta(days=k)).isoformat()))
            if r:
                ov += r[0]
                tot_n += r[1]
        rolling[D] = (ov / tot_n, tot_n) if tot_n else (None, 0)
    s = dict(date=g.date, league=g.league_name, final=g.total,
             net=net, n_prev=len(prev), rolling=rolling, ou=i["ou"])
    for b in LEGAL_BOOKS:
        r = kick.get(g.event_id, {}).get(b)
        s[b] = None if r is None else dict(L=r["line"], under=r["under_odds"], over=r["over_odds"])
    samples.append(s)

search = [s for s in samples if s["date"] >= SPLIT]
hold = [s for s in samples if s["date"] < SPLIT]
print(f"Partidos con linea de referencia: {len(samples)} (2025-26: {len(search)} / 2024-25: {len(hold)})\n")

# ---------- CAPA 1: ¿existe el fenomeno? (calibracion, sin cuotas) ----------
print("CAPA 1 -- CALIBRACION (sin cuotas): P(over vs consenso de cierre) segun el dia previo")
print("neto = overs - unders de los partidos YA TERMINADOS del dia, misma liga\n")
print(f"{'condicion':<34} {'n':>5} {'P(over)':>8}")
buckets = [
    ("neto <= -3", lambda s: s["net"] <= -3),
    ("neto == -2", lambda s: s["net"] == -2),
    ("neto == -1", lambda s: s["net"] == -1),
    ("neto == 0 (o sin previos)", lambda s: s["net"] == 0),
    ("neto == +1", lambda s: s["net"] == 1),
    ("neto == +2", lambda s: s["net"] == 2),
    ("neto >= +3", lambda s: s["net"] >= 3),
]
for name, cond in buckets:
    sub = [s for s in samples if cond(s) and s["ou"] != 0]
    if not sub:
        continue
    p = sum(1 for s in sub if s["ou"] > 0) / len(sub) * 100
    print(f"{name:<34} {len(sub):>5} {p:>7.1f}%")

print("\nVersion rodante: P(over) segun la tasa de overs de la liga en los D dias previos")
for D in (3, 7, 14):
    for lo, hi, label in ((0.0, 0.40, f"tasa {D}d <= 40%"), (0.60, 1.01, f"tasa {D}d >= 60%")):
        sub = [s for s in samples if s["ou"] != 0 and s["rolling"][D][1] >= 12
               and s["rolling"][D][0] is not None and lo <= s["rolling"][D][0] < hi]
        if len(sub) < 30:
            continue
        p = sum(1 for s in sub if s["ou"] > 0) / len(sub) * 100
        print(f"  {label:<18} n={len(sub):>5}  P(over)={p:.1f}%")

# ---------- CAPA 2: ¿es apostable al cierre real? ----------
SIGNALS = []
def sig(name, fn):
    SIGNALS.append((name, fn))

for thr in (1, 2, 3):
    sig(f"MOMENTUM O: neto dia >= +{thr}", lambda s, bk, thr=thr: "O" if s["net"] >= thr else None)
    sig(f"MOMENTUM U: neto dia <= -{thr}", lambda s, bk, thr=thr: "U" if s["net"] <= -thr else None)
    sig(f"CONTRARIAN U: neto dia >= +{thr}", lambda s, bk, thr=thr: "U" if s["net"] >= thr else None)
    sig(f"CONTRARIAN O: neto dia <= -{thr}", lambda s, bk, thr=thr: "O" if s["net"] <= -thr else None)
for D in (3, 7, 14):
    sig(f"MOMENTUM O: tasa {D}d >= 60%",
        lambda s, bk, D=D: "O" if s["rolling"][D][1] >= 12 and s["rolling"][D][0] is not None and s["rolling"][D][0] >= 0.60 else None)
    sig(f"MOMENTUM U: tasa {D}d <= 40%",
        lambda s, bk, D=D: "U" if s["rolling"][D][1] >= 12 and s["rolling"][D][0] is not None and s["rolling"][D][0] <= 0.40 else None)
    sig(f"CONTRARIAN U: tasa {D}d >= 60%",
        lambda s, bk, D=D: "U" if s["rolling"][D][1] >= 12 and s["rolling"][D][0] is not None and s["rolling"][D][0] >= 0.60 else None)
    sig(f"CONTRARIAN O: tasa {D}d <= 40%",
        lambda s, bk, D=D: "O" if s["rolling"][D][1] >= 12 and s["rolling"][D][0] is not None and s["rolling"][D][0] <= 0.40 else None)

LEAGUES = [None, "NBA", "WNBA", "Euroleague"]

def evaluate(fn, book, league, subset):
    pnls, wins, dec = [], 0, 0
    for s in subset:
        if league is not None and s["league"] != league:
            continue
        bk = s[book]
        if bk is None:
            continue
        side = fn(s, bk)
        if not side:
            continue
        odds = bk["under"] if side == "U" else bk["over"]
        if not odds or odds <= 1:
            continue
        if s["final"] == bk["L"]:
            pnls.append(0.0)
            continue
        won = s["final"] < bk["L"] if side == "U" else s["final"] > bk["L"]
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

results = []
for name, fn in SIGNALS:
    for book in LEGAL_BOOKS:
        for lg in LEAGUES:
            r = evaluate(fn, book, lg, search)
            if r is None or r["n"] < MIN_N:
                continue
            h = evaluate(fn, book, lg, hold)
            results.append(dict(name=name, book=book, lg=lg or "todas", s=r, h=h))

results.sort(key=lambda x: -x["s"]["roi"])
print(f"\nCAPA 2 -- APUESTA AL CIERRE REAL. Combinaciones con n>={MIN_N}: {len(results)}")
print(f"\nTOP 12 POR ROI EN BUSQUEDA (2025-26):")
print(f"{'señal':<32} {'casa':<8} {'liga':<11} | {'n':>4} {'hit%':>5} {'ROI%':>7} {'t':>5} | {'n24':>4} {'ROI24%':>7} {'t24':>5}")
for x in results[:12]:
    s, h = x["s"], x["h"]
    t_s = f"{s['t']:.2f}" if s["t"] is not None else "-"
    if h is None:
        h_str = f"{'--':>4} {'--':>7} {'--':>5}"
    else:
        t_h = f"{h['t']:.2f}" if h["t"] is not None else "-"
        h_str = f"{h['n']:>4} {h['roi']:>+7.1f} {t_h:>5}"
    print(f"{x['name']:<32} {x['book']:<8} {x['lg']:<11} | {s['n']:>4} {s['hit']:>5.1f} {s['roi']:>+7.1f} {t_s:>5} | {h_str}")

print("\nROBUSTOS (positivo y t>=1.5 en ambas temporadas, n24>=20):")
found = False
for x in results:
    s, h = x["s"], x["h"]
    if h is None or h["n"] < 20:
        continue
    if s["roi"] > 0 and h["roi"] > 0 and s["t"] and h["t"] and s["t"] >= 1.5 and h["t"] >= 1.5:
        found = True
        print(f"  {x['name']} @ {x['book']} [{x['lg']}]: "
              f"25-26 n={s['n']} ROI{s['roi']:+.1f}% t={s['t']:.2f} | "
              f"24-25 n={h['n']} ROI{h['roi']:+.1f}% t={h['t']:.2f}")
if not found:
    print("  (ninguno)")
