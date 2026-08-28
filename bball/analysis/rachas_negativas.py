"""Peticion del usuario: encontrar un sistema con MENOS DE 5 derrotas
consecutivas en todo el dataset y CUOTA MEDIA > 2.0, en cualquier mercado.

Se buscan reglas sobre los tres mercados que ahora tenemos (totales 18_3,
ganador 18_1, handicap 18_2), todas ejecutadas al CIERRE real (kickoff).

Ademas se calcula la parte teorica, que es la clave para interpretar el
resultado: dado un acierto h y n apuestas, ¿cual es la probabilidad de NO
tener nunca 5 derrotas seguidas? (programacion dinamica exacta). A cuota
>2.0 el acierto necesario para ganar dinero ronda el 50%, y con ese acierto
la ausencia de rachas de 5 solo es probable en muestras pequeñas -- asi que
el propio filtro selecciona muestras chicas, que es justo donde vive el
ruido. Se verifica empiricamente comparando las dos mitades del dataset.
"""
import json
import random
import statistics
import sys
from collections import defaultdict, deque

sys.path.insert(0, ".")  # correr desde la raiz del repo

from bball import config, db
from bball.backtest.replay import load_games

SPLIT = "2025-10-01"
N = 10
MIN_ODDS = 2.0
MAX_STREAK = 4          # "menos de 5 consecutivas"
N_RULES = 6000
SEED = 20260828

# ---------------- teoria: ¿es siquiera posible? ----------------
def p_no_run(n, h, k=5):
    """P(no haya nunca k derrotas seguidas) en n apuestas con acierto h."""
    q = 1 - h
    st = [0.0] * k
    st[0] = 1.0
    for _ in range(n):
        nxt = [0.0] * k
        for r, p in enumerate(st):
            if p == 0:
                continue
            nxt[0] += p * h              # gana -> racha a 0
            if r + 1 < k:
                nxt[r + 1] += p * q      # pierde -> racha +1
        st = nxt
    return sum(st)

print("TEORIA: probabilidad de NO tener nunca 5 derrotas seguidas")
print("(a cuota 2.0 hay que acertar >50% para ganar; a 2.2, >45.5%)")
print(f"{'apuestas':>9} " + " ".join(f"{'h=' + str(int(h*100)) + '%':>9}" for h in (0.45, 0.50, 0.55, 0.60)))
for n_bets in (20, 30, 50, 100, 200, 400, 800):
    row = " ".join(f"{p_no_run(n_bets, h)*100:>8.1f}%" for h in (0.45, 0.50, 0.55, 0.60))
    print(f"{n_bets:>9} {row}")
print()

# ---------------- datos: los 3 mercados al cierre ----------------
with db.get_conn() as conn:
    games = load_games(conn)
    fp_index = defaultdict(set)
    for r in conn.execute(
        "SELECT event_id, book, line, captured_at FROM bball_odds "
        "WHERE market=? AND snapshot='start' AND captured_at IS NOT NULL",
        (config.TOTALS_MARKET_KEY,),
    ).fetchall():
        fp_index[(r["book"], str(r["captured_at"]), float(r["line"]))].add(r["event_id"])

    markets = {}   # event_id -> {'18_1': {book: (h,a)}, '18_2': {book: (hcap,h,a)}, '18_3': {book: (line,o,u)}}
    offset = 0
    while True:
        rows = conn.execute(
            "SELECT body FROM bball_http_cache WHERE prefix='odds_summary' LIMIT 200 OFFSET ?", (offset,)
        ).fetchall()
        if not rows:
            break
        offset += len(rows)
        for row in rows:
            try:
                js = json.loads(row["body"])
            except (TypeError, ValueError):
                continue
            results = js.get("results") or {}
            votes = defaultdict(int)
            for book, b in results.items():
                if not isinstance(b, dict):
                    continue
                e = ((b.get("odds") or {}).get("start") or {}).get("18_3")
                if not isinstance(e, dict) or e.get("add_time") is None:
                    continue
                try:
                    fp = (book, str(int(e["add_time"])), float(e["handicap"]))
                except (KeyError, TypeError, ValueError):
                    continue
                for eid in fp_index.get(fp, ()):
                    votes[eid] += 1
            if not votes:
                continue
            ranked = sorted(votes.items(), key=lambda kv: -kv[1])
            eid, top = ranked[0]
            if len(ranked) > 1 and (top < 2 or top == ranked[1][1]):
                continue
            m = {"18_1": {}, "18_2": {}, "18_3": {}}
            for book, b in results.items():
                if not isinstance(b, dict):
                    continue
                ko = (b.get("odds") or {}).get("kickoff") or {}
                e1 = ko.get("18_1")
                if isinstance(e1, dict) and not e1.get("ss"):
                    try:
                        h, a = float(e1["home_od"]), float(e1["away_od"])
                        if h > 1 and a > 1:
                            m["18_1"][book] = (h, a)
                    except (KeyError, TypeError, ValueError):
                        pass
                e2 = ko.get("18_2")
                if isinstance(e2, dict) and not e2.get("ss"):
                    try:
                        hc, h, a = float(e2["handicap"]), float(e2["home_od"]), float(e2["away_od"])
                        if h > 1 and a > 1:
                            m["18_2"][book] = (hc, h, a)
                    except (KeyError, TypeError, ValueError):
                        pass
                e3 = ko.get("18_3")
                if isinstance(e3, dict) and not e3.get("ss"):
                    try:
                        ln, o, u = float(e3["handicap"]), float(e3["over_od"]), float(e3["under_od"])
                        if o > 1 and u > 1:
                            m["18_3"][book] = (ln, o, u)
                    except (KeyError, TypeError, ValueError):
                        pass
            markets[eid] = m

print(f"Eventos con cuotas de cierre: {len(markets)}")

# ---------------- features walk-forward ----------------
def streak_up(h):
    k = 0
    for i in range(len(h) - 1, 0, -1):
        if h[i] > h[i - 1]:
            k += 1
        else:
            break
    return k

scored, allowed, totals_h, wins_h = (defaultdict(list) for _ in range(4))
last_ts = {}
lg_lines = defaultdict(lambda: deque(maxlen=100))
season_n = defaultdict(int)

def season_key(d):
    y, mth = int(d[:4]), int(d[5:7])
    return y if mth >= 9 else y - 1

BOOKS = ("Bet365", "Betway", "BWin")
samples = []
for g in sorted(games, key=lambda x: x.time_ts):
    m = markets.get(g.event_id)
    hs, as_ = scored[g.home_key], scored[g.away_key]
    lgq = lg_lines[g.league_name]
    if m and len(hs) >= N and len(as_) >= N and len(lgq) >= 30:
        avg = lambda L, k=N: sum(L[-k:]) / min(len(L), k)
        sk = season_key(g.date)
        pick = {}
        for mk in ("18_1", "18_2", "18_3"):
            for b in BOOKS:
                if b in m[mk]:
                    pick[mk] = m[mk][b]
                    break
        if pick.get("18_3"):
            ps = []
            for h_, a_ in m["18_1"].values():
                ih, ia = 1 / h_, 1 / a_
                ps.append(ih / (ih + ia))
            p_home = statistics.median(ps) if ps else 0.5
            ln = pick["18_3"][0]
            f = {
                "sum_avg": avg(hs) + avg(as_),
                "colchon": ln - (avg(hs) + avg(as_)),
                "linea": ln,
                "p_local": p_home,
                "balance": abs(p_home - 0.5),
                "loc_anota": avg(hs), "vis_anota": avg(as_),
                "loc_encaja": avg(allowed[g.home_key]), "vis_encaja": avg(allowed[g.away_key]),
                "loc_ritmo": avg(totals_h[g.home_key]), "vis_ritmo": avg(totals_h[g.away_key]),
                "loc_winpct": avg(wins_h[g.home_key]), "vis_winpct": avg(wins_h[g.away_key]),
                "loc_forma3": avg(hs, 3), "vis_forma3": avg(as_, 3),
                "loc_racha": float(streak_up(hs)), "vis_racha": float(streak_up(as_)),
                "descanso_min": min((g.time_ts - last_ts[g.home_key]) / 86400 if g.home_key in last_ts else 5.0,
                                    (g.time_ts - last_ts[g.away_key]) / 86400 if g.away_key in last_ts else 5.0),
                "dia_semana": float(__import__("datetime").date.fromisoformat(g.date).weekday()),
                "mes": float(int(g.date[5:7])),
                "jornada": float(min(season_n[(g.home_key, sk)], 60)),
                "deriva_liga": ln - (sum(lgq) / len(lgq)),
            }
            samples.append(dict(date=g.date, ts=g.time_ts, league=g.league_name,
                                total=g.total, hs=g.home_score, as_=g.away_score,
                                mk=pick, f=f))
    sk = season_key(g.date)
    for key, pf, pa, won in ((g.home_key, g.home_score, g.away_score, g.home_score > g.away_score),
                             (g.away_key, g.away_score, g.home_score, g.away_score > g.home_score)):
        scored[key].append(pf); allowed[key].append(pa)
        totals_h[key].append(g.total); wins_h[key].append(1.0 if won else 0.0)
        last_ts[key] = g.time_ts
        season_n[(key, sk)] += 1
    if m and m.get("18_3"):
        lg_lines[g.league_name].append(statistics.median([v[0] for v in m["18_3"].values()]))

samples.sort(key=lambda s: s["ts"])
FEATS = sorted(samples[0]["f"].keys())
print(f"Partidos apostables: {len(samples)}  |  features: {len(FEATS)}\n")

# ---------------- apuestas por mercado ----------------
def settle(s, market, side):
    """Devuelve (pnl, odds) o None si no hay precio para esa apuesta."""
    p = s["mk"].get(market)
    if not p:
        return None
    if market == "18_3":
        ln, o, u = p
        odds = o if side == "O" else u
        if s["total"] == ln:
            return (0.0, odds)
        won = s["total"] > ln if side == "O" else s["total"] < ln
    elif market == "18_1":
        h, a = p
        odds = h if side == "H" else a
        won = s["hs"] > s["as_"] if side == "H" else s["as_"] > s["hs"]
    else:  # 18_2 handicap: handicap se aplica al local
        hc, h, a = p
        odds = h if side == "H" else a
        diff = s["hs"] - s["as_"] + hc
        if diff == 0:
            return (0.0, odds)
        won = diff > 0 if side == "H" else diff < 0
    return ((odds - 1) if won else -1.0, odds)

SIDES = [("18_3", "O"), ("18_3", "U"), ("18_1", "H"), ("18_1", "A"), ("18_2", "H"), ("18_2", "A")]

qs = {}
for k in FEATS:
    v = sorted(s["f"][k] for s in samples)
    qs[k] = [v[int(p * (len(v) - 1))] for p in (0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9)]

rnd = random.Random(SEED)

def make_rule():
    conds = []
    for _ in range(rnd.choice([1, 2, 2, 3])):
        f = rnd.choice(FEATS)
        conds.append((f, rnd.choice([">=", "<="]), rnd.choice(qs[f])))
    return conds, rnd.choice(SIDES)

def matches(conds, f):
    for k, op, thr in conds:
        if op == ">=" and not f[k] >= thr:
            return False
        if op == "<=" and not f[k] <= thr:
            return False
    return True

def run_rule(conds, market, side, subset):
    pnls, odds_l, streak, worst = [], [], 0, 0
    for s in subset:
        if not matches(conds, s["f"]):
            continue
        r = settle(s, market, side)
        if r is None:
            continue
        pnl, odds = r
        pnls.append(pnl)
        odds_l.append(odds)
        if pnl < 0:
            streak += 1
            worst = max(worst, streak)
        elif pnl > 0:
            streak = 0
    n = len(pnls)
    if n == 0:
        return None
    roi = sum(pnls) / n * 100
    sd = statistics.pstdev(pnls) if n > 1 else 0
    t = (statistics.mean(pnls) / sd) * (n ** 0.5) if sd > 0 else 0
    return dict(n=n, roi=roi, t=t, worst=worst, mean_odds=statistics.mean(odds_l),
                hit=sum(1 for p in pnls if p > 0) / n * 100)

print(f"Buscando entre {N_RULES} reglas: cuota media > {MIN_ODDS} y racha maxima de derrotas <= {MAX_STREAK}")
print("(criterio aplicado sobre TODO el dataset, como pediste)\n")

survivors = []
tested = 0
for _ in range(N_RULES):
    conds, (market, side) = make_rule()
    r = run_rule(conds, market, side, samples)
    if r is None:
        continue
    tested += 1
    if r["mean_odds"] > MIN_ODDS and r["worst"] <= MAX_STREAK:
        survivors.append((conds, market, side, r))

print(f"Reglas evaluables: {tested}")
print(f"Reglas que CUMPLEN tus dos criterios: {len(survivors)}\n")

def fmt(c):
    return " Y ".join(f"{k}{op}{thr:.2f}" for k, op, thr in c)

if survivors:
    survivors.sort(key=lambda x: -x[3]["n"])
    print("Las que cumplen, ordenadas por tamaño de muestra (n = numero de apuestas):")
    print(f"{'n':>4} {'cuota':>6} {'hit%':>6} {'ROI%':>7} {'peor racha':>11}  regla")
    for conds, market, side, r in survivors[:12]:
        print(f"{r['n']:>4} {r['mean_odds']:>6.2f} {r['hit']:>6.1f} {r['roi']:>+7.1f} {r['worst']:>11}  "
              f"[{market}/{side}] {fmt(conds)}")

    ns = [r["n"] for _, _, _, r in survivors]
    print(f"\nTamaño de muestra de las supervivientes: mediana={statistics.median(ns):.0f}, "
          f"maximo={max(ns)}, minimo={min(ns)}")
    print(f"Para comparar, el dataset tiene {len(samples)} partidos.")

    # ¿se sostienen? mitad vs mitad
    print("\n¿Se sostienen? Rendimiento de las supervivientes en cada temporada por separado:")
    print(f"{'n_total':>8} {'ROI 25-26':>11} {'ROI 24-25':>11}  regla")
    s1 = [s for s in samples if s["date"] >= SPLIT]
    s2 = [s for s in samples if s["date"] < SPLIT]
    rois1, rois2 = [], []
    for conds, market, side, r in survivors[:12]:
        a = run_rule(conds, market, side, s1)
        b = run_rule(conds, market, side, s2)
        fa = f"{a['roi']:+.1f}% (n={a['n']})" if a else "sin apuestas"
        fb = f"{b['roi']:+.1f}% (n={b['n']})" if b else "sin apuestas"
        if a: rois1.append(a["roi"])
        if b: rois2.append(b["roi"])
        print(f"{r['n']:>8} {fa:>11} {fb:>11}  [{market}/{side}] {fmt(conds)[:52]}")
    if rois1 and rois2:
        print(f"\nROI medio de las supervivientes: 2025-26 {statistics.mean(rois1):+.1f}%  |  "
              f"2024-25 {statistics.mean(rois2):+.1f}%")
else:
    print("Ninguna regla cumple ambos criterios.")
