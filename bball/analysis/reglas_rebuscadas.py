"""¿Existe una regla lo bastante 'rebuscada' como para que la casa no la
contemple y sea rentable? Esta es la prueba directa de esa hipotesis.

En vez de inventar reglas rebuscadas a mano de una en una, se GENERAN AL AZAR
miles: cada regla es una conjuncion de 2-4 condiciones sobre 20 features
(anotacion, defensa, ritmo, rachas, descanso, dia de la semana, momento de
temporada, deriva de la liga, movimiento de mercado...), con umbrales
sacados de la distribucion empirica y lado (over/under) aleatorio. Son
exactamente el tipo de regla 'rara' que uno inventaria -- pero miles, y sin
que el sesgo humano elija cual mirar.

Se mide lo unico que importa:
  A) ¿Cuantas reglas dan ROI espectacular en la ventana de busqueda? (muchas)
  B) Esas ganadoras, ¿que hacen fuera de muestra? (la pregunta real)
  C) ¿Se distingue su rendimiento fuera de muestra del de una regla al azar?

Si (C) da que no, entonces 'rebuscada' no genera ventaja: seleccionar por
resultado in-sample no aporta NINGUNA informacion sobre el futuro, y lo
unico que queda es el margen de la casa.

Ejecucion realista: al CIERRE real (snapshot kickoff) de una casa legal.
"""
import random
import statistics
import sys
from collections import defaultdict, deque

sys.path.insert(0, ".")  # correr desde la raiz del repo

from bball import db
from bball.backtest.replay import load_games

SPLIT = "2025-10-01"
N = 10
MIN_N = 30
N_RULES = 4000
SEED = 20260828

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds, snapshot FROM bball_odds "
        "WHERE market='18_3' AND snapshot IN ('start','kickoff')"
    ).fetchall()

kick, opens = defaultdict(dict), defaultdict(dict)
for r in rows:
    (kick if r["snapshot"] == "kickoff" else opens)[r["event_id"]][r["book"]] = r


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
    y, m = int(d[:4]), int(d[5:7])
    return y if m >= 9 else y - 1

samples = []
for g in sorted(games, key=lambda x: x.time_ts):
    # casa legal con cierre: preferimos Bet365, si no Betway, si no BWin
    bk = None
    for b in ("Bet365", "Betway", "BWin"):
        r = kick.get(g.event_id, {}).get(b)
        if r and r["over_odds"] and r["under_odds"] and r["over_odds"] > 1 and r["under_odds"] > 1:
            bk = (b, r)
            break
    hs, as_ = scored[g.home_key], scored[g.away_key]
    lgq = lg_lines[g.league_name]
    if bk and len(hs) >= N and len(as_) >= N and len(lgq) >= 30:
        book, r = bk
        sk = season_key(g.date)
        avg = lambda L, k=N: sum(L[-k:]) / min(len(L), k)
        moves = []
        for b2, c in kick.get(g.event_id, {}).items():
            o = opens.get(g.event_id, {}).get(b2)
            if o:
                moves.append(c["line"] - o["line"])
        lg_avg_line = sum(lgq) / len(lgq)
        f = {
            "sum_avg": avg(hs) + avg(as_),
            "gap": max(avg(totals_h[g.home_key]), avg(totals_h[g.away_key])) - (avg(hs) + avg(as_)),
            "linea": r["line"],
            "colchon": r["line"] - (avg(hs) + avg(as_)),
            "loc_anota": avg(hs), "vis_anota": avg(as_),
            "loc_encaja": avg(allowed[g.home_key]), "vis_encaja": avg(allowed[g.away_key]),
            "loc_ritmo": avg(totals_h[g.home_key]), "vis_ritmo": avg(totals_h[g.away_key]),
            "loc_forma3": avg(hs, 3), "vis_forma3": avg(as_, 3),
            "loc_winpct": avg(wins_h[g.home_key]), "vis_winpct": avg(wins_h[g.away_key]),
            "loc_racha": streak_up(hs), "vis_racha": streak_up(as_),
            "descanso_min": min((g.time_ts - last_ts[g.home_key]) / 86400 if g.home_key in last_ts else 5.0,
                                (g.time_ts - last_ts[g.away_key]) / 86400 if g.away_key in last_ts else 5.0),
            "dia_semana": float(__import__("datetime").date.fromisoformat(g.date).weekday()),
            "mes": float(int(g.date[5:7])),
            "jornada": float(min(season_n[(g.home_key, sk)], 60)),
            "deriva_liga": r["line"] - lg_avg_line,
            "mov_mercado": statistics.median(moves) if moves else 0.0,
        }
        samples.append(dict(date=g.date, league=g.league_name, final=g.total,
                            L=r["line"], over=r["over_odds"], under=r["under_odds"], f=f))
    sk = season_key(g.date)
    for key, pf, pa, won in ((g.home_key, g.home_score, g.away_score, g.home_score > g.away_score),
                             (g.away_key, g.away_score, g.home_score, g.away_score > g.home_score)):
        scored[key].append(pf); allowed[key].append(pa)
        totals_h[key].append(g.total); wins_h[key].append(1.0 if won else 0.0)
        last_ts[key] = g.time_ts
        season_n[(key, sk)] += 1
    lg_lines[g.league_name].append(r["line"] if bk else statistics.median(
        [x["line"] for x in kick.get(g.event_id, {}).values()] or [0]) or 0)

search = [s for s in samples if s["date"] >= SPLIT]
hold = [s for s in samples if s["date"] < SPLIT]
FEATS = sorted(samples[0]["f"].keys())
print(f"Partidos apostables al cierre: {len(samples)} "
      f"(2025-26 busqueda: {len(search)} / 2024-25 fuera de muestra: {len(hold)})")
print(f"Features disponibles: {len(FEATS)} -> {N_RULES} reglas rebuscadas generadas al azar\n")

# percentiles empiricos por feature, para umbrales con sentido
qs = {}
for k in FEATS:
    v = sorted(s["f"][k] for s in samples)
    qs[k] = [v[int(p * (len(v) - 1))] for p in (0.15, 0.25, 0.35, 0.5, 0.65, 0.75, 0.85)]

rnd = random.Random(SEED)

def make_rule():
    k = rnd.choice([2, 2, 3, 3, 4])
    conds = []
    for _ in range(k):
        f = rnd.choice(FEATS)
        thr = rnd.choice(qs[f])
        op = rnd.choice([">=", "<="])
        conds.append((f, op, thr))
    side = rnd.choice(["O", "U"])
    return conds, side

def matches(conds, f):
    for k, op, thr in conds:
        v = f[k]
        if op == ">=" and not v >= thr:
            return False
        if op == "<=" and not v <= thr:
            return False
    return True

def evaluate(conds, side, subset):
    pnls, wins, dec = [], 0, 0
    for s in subset:
        if not matches(conds, s["f"]):
            continue
        odds = s["over"] if side == "O" else s["under"]
        if s["final"] == s["L"]:
            pnls.append(0.0)
            continue
        won = s["final"] > s["L"] if side == "O" else s["final"] < s["L"]
        pnls.append(odds - 1 if won else -1.0)
        dec += 1
        wins += won
    n = len(pnls)
    if n == 0:
        return None
    roi = sum(pnls) / n * 100
    sd = statistics.pstdev(pnls) if n > 1 else 0
    t = (statistics.mean(pnls) / sd) * (n ** 0.5) if sd > 0 else 0
    return dict(n=n, roi=roi, t=t, hit=wins / dec * 100 if dec else 0)

def fmt(c):
    return " Y ".join(f"{k}{op}{thr:.1f}" for k, op, thr in c)

rules = []
for _ in range(N_RULES):
    conds, side = make_rule()
    rs = evaluate(conds, side, search)
    if rs is None or rs["n"] < MIN_N:
        continue
    rh = evaluate(conds, side, hold)
    if rh is None or rh["n"] < 20:
        continue
    rules.append((conds, side, rs, rh))

print(f"Reglas con muestra suficiente en ambas ventanas: {len(rules)}\n")

# A) cuantas 'ganan' espectacularmente en busqueda
for bar in (10, 15, 20, 25):
    k = sum(1 for _, _, rs, _ in rules if rs["roi"] >= bar)
    print(f"  reglas con ROI >= +{bar}% en la ventana de busqueda: {k} ({k/len(rules)*100:.1f}%)")
best = max(rules, key=lambda x: x[2]["roi"])
print(f"\n  LA MEJOR de las {len(rules)}, elegida por su ROI in-sample:")
print(f"    {best[1]}: {fmt(best[0])}")
print(f"    busqueda      : n={best[2]['n']} hit={best[2]['hit']:.1f}% ROI={best[2]['roi']:+.1f}% t={best[2]['t']:.2f}")
print(f"    FUERA DE MUESTRA: n={best[3]['n']} hit={best[3]['hit']:.1f}% ROI={best[3]['roi']:+.1f}% t={best[3]['t']:.2f}")

# B) las 'ganadoras' in-sample, ¿que hacen fuera?
print("\nB) Rendimiento FUERA DE MUESTRA segun lo bien que fueron en busqueda:")
print(f"{'seleccionadas por':<34} {'k':>5} {'ROI fuera medio':>16} {'mediana':>9} {'% rentables':>12}")
todas = [rh["roi"] for _, _, _, rh in rules]
print(f"{'(ninguna seleccion: las 4000)':<34} {len(todas):>5} {statistics.mean(todas):>+15.2f}% "
      f"{statistics.median(todas):>+8.2f}% {sum(1 for x in todas if x>0)/len(todas)*100:>11.1f}%")
for bar in (10, 15, 20, 25):
    sel = [rh["roi"] for _, _, rs, rh in rules if rs["roi"] >= bar]
    if len(sel) < 5:
        continue
    print(f"{'ROI busqueda >= +' + str(bar) + '%':<34} {len(sel):>5} {statistics.mean(sel):>+15.2f}% "
          f"{statistics.median(sel):>+8.2f}% {sum(1 for x in sel if x>0)/len(sel)*100:>11.1f}%")
sel_t = [rh["roi"] for _, _, rs, rh in rules if rs["t"] >= 2]
if len(sel_t) >= 5:
    print(f"{'t >= 2 en busqueda':<34} {len(sel_t):>5} {statistics.mean(sel_t):>+15.2f}% "
          f"{statistics.median(sel_t):>+8.2f}% {sum(1 for x in sel_t if x>0)/len(sel_t)*100:>11.1f}%")

# C) ¿aporta algo la complejidad?
print("\nC) ¿Ser MAS rebuscada (mas condiciones) ayuda? ROI medio fuera de muestra:")
for k in (2, 3, 4):
    sub = [rh["roi"] for c, _, _, rh in rules if len(c) == k]
    if sub:
        print(f"  reglas de {k} condiciones: n={len(sub):>4}  ROI fuera medio = {statistics.mean(sub):+.2f}%")

print("\nD) Correlacion entre ROI en busqueda y ROI fuera de muestra (si >0, seleccionar sirve):")
xs = [rs["roi"] for _, _, rs, _ in rules]
ys = [rh["roi"] for _, _, _, rh in rules]
mx, my = statistics.mean(xs), statistics.mean(ys)
num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
print(f"   corr = {num/den:+.3f}   (0 = elegir la mejor regla in-sample no predice nada)")
