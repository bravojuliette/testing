"""El intento maximo con esta materia prima: en vez de teorias de UNA
variable con umbral (todas agotadas), un modelo Ridge que usa TODAS las
features derivables de los marcadores A LA VEZ para predecir el total, y se
compara contra la linea de cierre de la casa. Dos preguntas:

1. ¿Predice el modelo el total con menos error que la linea de cierre?
   (MAE modelo vs MAE linea -- la linea es el benchmark a batir)
2. Si se apuesta cuando |modelo - linea| >= umbral, al cierre real de las
   casas legales, ¿da ROI positivo en ambas temporadas?

Disciplina walk-forward estricta: el modelo se re-entrena cada mes usando
SOLO partidos anteriores a ese mes; cada prediccion usa features calculadas
solo con partidos previos. Sin informacion de cuotas en las features (el
modelo debe ser independiente del mercado para poder discrepar de el).
"""
import statistics
import sys
from collections import defaultdict, deque

import numpy as np

sys.path.insert(0, ".")  # correr desde la raiz del repo

from bball import db
from bball.backtest.replay import load_games

SPLIT = "2025-10-01"
LEGAL_BOOKS = ["Bet365", "Betway", "BWin"]
N = 10
RIDGE_ALPHA = 10.0

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds "
        "WHERE market='18_3' AND snapshot='kickoff'"
    ).fetchall()

kick = defaultdict(dict)
for r in rows:
    kick[r["event_id"]][r["book"]] = r

LG_IDX = {"NBA": 0, "WNBA": 1, "Euroleague": 2}

scored = defaultdict(list)    # puntos anotados
allowed = defaultdict(list)   # puntos encajados
totals_h = defaultdict(list)  # total de sus partidos
last_ts = {}
season_games = defaultdict(int)   # partidos jugados esta temporada (reset en octubre)
season_of = {}
lg_totals = defaultdict(lambda: deque(maxlen=100))

def season_key(date_str):
    y, m = int(date_str[:4]), int(date_str[5:7])
    return y if m >= 9 else y - 1

def team_feats(key, ts, date_str):
    sc, al, th = scored[key], allowed[key], totals_h[key]
    if len(sc) < N:
        return None
    rest = min((ts - last_ts[key]) / 86400, 5.0) if key in last_ts else 5.0
    return [
        sum(sc[-N:]) / N, sum(al[-N:]) / N, sum(th[-N:]) / N,
        sum(sc[-3:]) / 3, sum(al[-3:]) / 3,     # forma reciente
        rest, 1.0 if rest <= 1.2 else 0.0,
        min(season_games[(key, season_key(date_str))], 40) / 40.0,  # cuanto llevamos de temporada
    ]

dataset = []
for g in sorted(games, key=lambda x: x.time_ts):
    fh = team_feats(g.home_key, g.time_ts, g.date)
    fa = team_feats(g.away_key, g.time_ts, g.date)
    lgq = lg_totals[g.league_name]
    if fh is not None and fa is not None and len(lgq) >= 30:
        lg_avg = sum(lgq) / len(lgq)
        naive = (fh[0] + fa[1]) / 2 + (fa[0] + fh[1]) / 2   # ataque vs defensa cruzados
        lg_dummy = [0.0, 0.0, 0.0]
        lg_dummy[LG_IDX[g.league_name]] = 1.0
        x = fh + fa + [lg_avg, naive, (fh[2] + fa[2]) / 2] + lg_dummy
        dataset.append(dict(date=g.date, month=g.date[:7], league=g.league_name,
                            event_id=g.event_id, final=g.total, x=x))
    sk = season_key(g.date)
    for key, pts_f, pts_a in ((g.home_key, g.home_score, g.away_score),
                              (g.away_key, g.away_score, g.home_score)):
        scored[key].append(pts_f)
        allowed[key].append(pts_a)
        totals_h[key].append(g.total)
        last_ts[key] = g.time_ts
        season_games[(key, sk)] += 1
    lg_totals[g.league_name].append(g.total)

months = sorted({d["month"] for d in dataset})
print(f"Partidos con features completas: {len(dataset)} ({months[0]} .. {months[-1]})\n")

# ---------- walk-forward: re-entrenar cada mes con todo lo anterior ----------
def ridge_fit(X, y, alpha):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Xs = (X - mu) / sd
    Xs = np.hstack([Xs, np.ones((len(Xs), 1))])
    A = Xs.T @ Xs + alpha * np.eye(Xs.shape[1])
    A[-1, -1] -= alpha  # no regularizar el intercepto
    w = np.linalg.solve(A, Xs.T @ y)
    return mu, sd, w

def ridge_pred(mu, sd, w, X):
    Xs = (X - mu) / sd
    Xs = np.hstack([Xs, np.ones((len(Xs), 1))])
    return Xs @ w

preds = {}
MIN_TRAIN = 400
for i, m in enumerate(months):
    train = [d for d in dataset if d["month"] < m]
    test = [d for d in dataset if d["month"] == m]
    if len(train) < MIN_TRAIN or not test:
        continue
    X = np.array([d["x"] for d in train]); y = np.array([d["final"] for d in train], dtype=float)
    mu, sd, w = ridge_fit(X, y, RIDGE_ALPHA)
    Xt = np.array([d["x"] for d in test])
    for d, p in zip(test, ridge_pred(mu, sd, w, Xt)):
        preds[d["event_id"]] = p

# ---------- 1. ¿bate el modelo a la linea en error de prediccion? ----------
rows_cmp = []
for d in dataset:
    p = preds.get(d["event_id"])
    ks = kick.get(d["event_id"], {})
    lines = [r["line"] for r in ks.values()]
    if p is None or not lines:
        continue
    close = statistics.median(lines)
    rows_cmp.append(dict(date=d["date"], league=d["league"], final=d["final"],
                         pred=p, close=close, event_id=d["event_id"]))

print("1. ERROR DE PREDICCION DEL TOTAL (MAE, menos es mejor) -- el benchmark es la linea:")
for label, lo, hi in (("todo", "0000", "9999"), ("2024-25", "0000", SPLIT), ("2025-26", SPLIT, "9999")):
    sub = [r for r in rows_cmp if lo <= r["date"] < hi]
    if not sub:
        continue
    mae_m = statistics.mean(abs(r["final"] - r["pred"]) for r in sub)
    mae_l = statistics.mean(abs(r["final"] - r["close"]) for r in sub)
    mae_mix = statistics.mean(abs(r["final"] - (r["pred"] + r["close"]) / 2) for r in sub)
    print(f"  {label:<8} n={len(sub):>5}  MAE modelo={mae_m:.2f}  MAE linea cierre={mae_l:.2f}  MAE mezcla 50/50={mae_mix:.2f}")

corr_dat = [(r["pred"] - r["close"], r["final"] - r["close"]) for r in rows_cmp]
if len(corr_dat) > 2:
    a = np.array(corr_dat)
    corr = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
    print(f"\n  ¿La discrepancia modelo-linea predice la desviacion real del total? corr={corr:+.3f}")
    print("  (>0: cuando el modelo ve el total por encima de la linea, el partido tiende a irse over)")

# ---------- 2. apuesta cuando el modelo discrepa de la linea ----------
print("\n2. APUESTA AL CIERRE REAL cuando |modelo - linea de la casa| >= umbral:")
print(f"{'umbral':>7} {'casa':<8} | {'25-26: n':>8} {'ROI%':>7} {'t':>6} | {'24-25: n':>8} {'ROI%':>7} {'t':>6}")
for thr in (2, 4, 6, 8):
    for book in LEGAL_BOOKS:
        out = {}
        for label, lo, hi in (("s", SPLIT, "9999"), ("h", "0000", SPLIT)):
            pnls, wins, dec = [], 0, 0
            for r in rows_cmp:
                if not (lo <= r["date"] < hi):
                    continue
                bk = kick.get(r["event_id"], {}).get(book)
                if bk is None:
                    continue
                edge = r["pred"] - bk["line"]
                if abs(edge) < thr:
                    continue
                side = "O" if edge > 0 else "U"
                odds = bk["over_odds"] if side == "O" else bk["under_odds"]
                if not odds or odds <= 1:
                    continue
                if r["final"] == bk["line"]:
                    pnls.append(0.0)
                    continue
                won = r["final"] > bk["line"] if side == "O" else r["final"] < bk["line"]
                pnls.append(odds - 1 if won else -1.0)
                dec += 1
                wins += won
            n = len(pnls)
            if n == 0:
                out[label] = None
                continue
            roi = sum(pnls) / n * 100
            sd = statistics.pstdev(pnls) if n > 1 else 0
            t = (statistics.mean(pnls) / sd) * (n ** 0.5) if sd > 0 else 0
            out[label] = (n, roi, t)
        f = lambda r: f"{r[0]:>8} {r[1]:>+7.1f} {r[2]:>6.2f}" if r else f"{'-':>8} {'-':>7} {'-':>6}"
        print(f"{thr:>7} {book:<8} | {f(out['s'])} | {f(out['h'])}")
