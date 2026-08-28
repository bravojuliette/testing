"""Mercado de HANDICAP (18_2) al cierre -- territorio sin explorar.

Se recupero de la cache (58806 cuotas de cierre, 4607 eventos) pero nunca se
analizo. Tiene angulos clasicos distintos a los de totales y ganador, asi que
merece su propia pasada, con el mismo orden de siempre:

1. CALIBRACION sin filtro: ¿cubre el local tanto como implica el precio?
   ¿cambia segun el tamaño del handicap? Aqui es donde se ve si hay terreno.
2. ANGULOS CLASICOS pre-especificados (no minados): underdog local, favorito
   grande, descanso, back-to-back... una lista corta y decidida de antemano.
3. BUSQUEDA AMPLIA de filtros con disciplina busqueda/reserva.

Convencion de la base (ver reparse_moneyline_spread): over_odds = cuota del
LOCAL, under_odds = cuota del VISITANTE, line = handicap aplicado al LOCAL.
Ya normalizado local/visitante. Se excluye el tramo con orientacion no
fiable (config.orientation_is_reliable -> WNBA 2026).
"""
import random
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")  # correr desde la raiz del repo

from bball import config, db
from bball.backtest.replay import load_games

N = 10
SPLIT = "2025-10-01"
BOOKS = ("Bet365", "Betway", "BWin")
MIN_N = 40

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds "
        "WHERE market = ? AND snapshot = 'kickoff'", (config.SPREAD_MARKET_KEY,)
    ).fetchall()

sp = defaultdict(dict)
for r in rows:
    sp[r["event_id"]][r["book"]] = (r["line"], r["over_odds"], r["under_odds"])

scored, allowed, wins_h, margins, totals_h = (defaultdict(list) for _ in range(5))
last_ts = {}

def streak_up(h):
    k = 0
    for i in range(len(h) - 1, 0, -1):
        if h[i] > h[i - 1]:
            k += 1
        else:
            break
    return k

muestras = []
for g in sorted(games, key=lambda x: x.time_ts):
    d = sp.get(g.event_id, {})
    pick = next((d[b] for b in BOOKS if b in d), None)
    if (pick and config.orientation_is_reliable(g.league_name, g.date)
            and len(scored[g.home_key]) >= N and len(scored[g.away_key]) >= N):
        hcap, o_loc, o_vis = pick
        avg = lambda L, k=N: sum(L[-k:]) / min(len(L), k)
        margen_real = g.home_score - g.away_score
        cubre_loc = margen_real + hcap          # >0 cubre local, <0 cubre visitante
        rest_h = (g.time_ts - last_ts[g.home_key]) / 86400 if g.home_key in last_ts else 5.0
        rest_a = (g.time_ts - last_ts[g.away_key]) / 86400 if g.away_key in last_ts else 5.0
        muestras.append(dict(
            date=g.date, lg=g.league_name, hcap=hcap, o_loc=o_loc, o_vis=o_vis,
            cubre_loc=cubre_loc, margen_real=margen_real,
            loc_es_fav=1.0 if hcap < 0 else 0.0,
            hcap_abs=abs(hcap),
            loc_anota=avg(scored[g.home_key]), vis_anota=avg(scored[g.away_key]),
            loc_encaja=avg(allowed[g.home_key]), vis_encaja=avg(allowed[g.away_key]),
            loc_winpct=avg(wins_h[g.home_key]), vis_winpct=avg(wins_h[g.away_key]),
            loc_margen=avg(margins[g.home_key]), vis_margen=avg(margins[g.away_key]),
            loc_margen3=avg(margins[g.home_key], 3), vis_margen3=avg(margins[g.away_key], 3),
            loc_racha=float(streak_up(scored[g.home_key])),
            descanso_loc=min(rest_h, 5.0), descanso_vis=min(rest_a, 5.0),
            vent_descanso=min(rest_h, 5.0) - min(rest_a, 5.0),
            ritmo=(avg(totals_h[g.home_key]) + avg(totals_h[g.away_key])) / 2,
        ))
    for key, pf, pa in ((g.home_key, g.home_score, g.away_score),
                        (g.away_key, g.away_score, g.home_score)):
        scored[key].append(pf); allowed[key].append(pa)
        wins_h[key].append(1.0 if pf > pa else 0.0)
        margins[key].append(float(pf - pa)); totals_h[key].append(g.total)
        last_ts[key] = g.time_ts

print(f"Partidos con handicap de cierre e historial: {len(muestras)}")
print(f"(excluida WNBA 2026 por orientacion no fiable)\n")

def apostar(m, lado):
    """lado 'L' = local con su handicap, 'V' = visitante. Devuelve pnl o None si push."""
    c = m["cubre_loc"]
    if c == 0:
        return 0.0
    odds = m["o_loc"] if lado == "L" else m["o_vis"]
    gana = (c > 0) if lado == "L" else (c < 0)
    return (odds - 1) if gana else -1.0

def stat(sub, lado):
    p = [apostar(m, lado) for m in sub]
    p = [x for x in p if x is not None]
    n = len(p)
    if n == 0:
        return None
    sd = statistics.pstdev(p) if n > 1 else 0
    dec = [x for x in p if x != 0]
    return dict(n=n, roi=sum(p) / n * 100,
                t=(statistics.mean(p) / sd) * (n ** 0.5) if sd > 0 else 0,
                hit=sum(1 for x in dec if x > 0) / len(dec) * 100 if dec else 0)

# ---------- 1. calibracion ----------
print("1. CALIBRACION SIN FILTRO -- apostar SIEMPRE un lado del handicap:")
print(f"{'grupo':<30} {'n':>5} {'cubre loc':>10} {'ROI local':>10} {'ROI visit':>10}")
def fila(nombre, sub):
    if len(sub) < 30:
        return
    sl, sv = stat(sub, "L"), stat(sub, "V")
    dec = [m for m in sub if m["cubre_loc"] != 0]
    pc = sum(1 for m in dec if m["cubre_loc"] > 0) / len(dec) * 100 if dec else 0
    print(f"{nombre:<30} {len(sub):>5} {pc:>9.1f}% {sl['roi']:>+9.1f}% {sv['roi']:>+9.1f}%")

fila("TODOS", muestras)
for lg in ("NBA", "WNBA", "Euroleague"):
    fila(f"  {lg}", [m for m in muestras if m["lg"] == lg])
print()
fila("local FAVORITO (hcap<0)", [m for m in muestras if m["loc_es_fav"] > 0])
fila("local UNDERDOG (hcap>0)", [m for m in muestras if m["loc_es_fav"] == 0])
print()
for lo, hi in ((0, 3), (3, 6), (6, 9), (9, 13), (13, 99)):
    fila(f"|handicap| {lo}-{hi}", [m for m in muestras if lo <= m["hcap_abs"] < hi])

# ---------- 2. angulos clasicos, pre-especificados ----------
print("\n2. ANGULOS CLASICOS (lista fijada de antemano, no minada):")
print(f"{'angulo':<44} {'lado':>5} {'n':>5} {'hit%':>7} {'ROI%':>8} {'t':>6}")
ANGULOS = [
    ("underdog LOCAL cubre", "L", lambda m: m["loc_es_fav"] == 0),
    ("underdog local muy grande (hcap>=8)", "L", lambda m: m["hcap"] >= 8),
    ("favorito grande no cubre (hcap<=-10)", "V", lambda m: m["hcap"] <= -10),
    ("favorito muy grande no cubre (<=-14)", "V", lambda m: m["hcap"] <= -14),
    ("local en back-to-back", "V", lambda m: m["descanso_loc"] <= 1.2),
    ("visitante en back-to-back", "L", lambda m: m["descanso_vis"] <= 1.2),
    ("local mucho mas descansado", "L", lambda m: m["vent_descanso"] >= 2),
    ("visitante mucho mas descansado", "V", lambda m: m["vent_descanso"] <= -2),
    ("favorito viene de paliza (marg3>=15)", "V", lambda m: m["loc_es_fav"] > 0 and m["loc_margen3"] >= 15),
    ("dog local viene de perder mucho", "L", lambda m: m["loc_es_fav"] == 0 and m["loc_margen3"] <= -10),
]
for nombre, lado, f in ANGULOS:
    sub = [m for m in muestras if f(m)]
    s = stat(sub, lado)
    if s and s["n"] >= 30:
        print(f"{nombre:<44} {lado:>5} {s['n']:>5} {s['hit']:>6.1f}% {s['roi']:>+8.1f} {s['t']:>6.2f}")

# ---------- 3. busqueda amplia con reserva ----------
FEATS = [k for k in muestras[0] if k not in ("date", "lg", "hcap", "o_loc", "o_vis",
                                             "cubre_loc", "margen_real")]
qs = {}
for k in FEATS:
    v = sorted(m[k] for m in muestras)
    qs[k] = [v[int(p * (len(v) - 1))] for p in (0.15, 0.3, 0.5, 0.7, 0.85)]
busq = [m for m in muestras if m["date"] >= SPLIT]
res = [m for m in muestras if m["date"] < SPLIT]
print(f"\n3. BUSQUEDA AMPLIA -- busqueda {len(busq)} / reserva {len(res)}")

rnd = random.Random(20260828)
cands = []
for _ in range(6000):
    conds = [(rnd.choice(FEATS), rnd.choice([">=", "<="]), 0) for _ in range(rnd.choice([1, 2, 2, 3]))]
    conds = [(k, op, rnd.choice(qs[k])) for k, op, _ in conds]
    lado = rnd.choice(["L", "V"])
    def ok(m, c=conds):
        for k, op, thr in c:
            if (op == ">=" and not m[k] >= thr) or (op == "<=" and not m[k] <= thr):
                return False
        return True
    sb = stat([m for m in busq if ok(m)], lado)
    if sb is None or sb["n"] < MIN_N:
        continue
    sr = stat([m for m in res if ok(m)], lado)
    if sr is None or sr["n"] < 30:
        continue
    cands.append((conds, lado, sb, sr))

fmt = lambda c: " Y ".join(f"{k}{op}{thr:.1f}" for k, op, thr in c)
cands.sort(key=lambda x: -x[2]["roi"])
print(f"   {len(cands)} reglas con muestra suficiente. Top 10 por ROI en busqueda:\n")
print(f"{'busqueda':>24} | {'RESERVA':>24}  regla")
for conds, lado, sb, sr in cands[:10]:
    print(f"n={sb['n']:>4} ROI={sb['roi']:>+6.1f}% t={sb['t']:>5.2f} | "
          f"n={sr['n']:>4} ROI={sr['roi']:>+6.1f}% t={sr['t']:>5.2f}  [{lado}] {fmt(conds)[:40]}")

print("\nROBUSTAS (ROI>0 y t>=1.5 en AMBAS ventanas):")
rob = [x for x in cands if x[2]["roi"] > 0 and x[3]["roi"] > 0 and x[2]["t"] >= 1.5 and x[3]["t"] >= 1.5]
if not rob:
    print("  (ninguna)")
for conds, lado, sb, sr in rob[:8]:
    print(f"  [{lado}] {fmt(conds)}")
    print(f"     busqueda: n={sb['n']} hit={sb['hit']:.1f}% ROI={sb['roi']:+.1f}% t={sb['t']:.2f}")
    print(f"     RESERVA : n={sr['n']} hit={sr['hit']:.1f}% ROI={sr['roi']:+.1f}% t={sr['t']:.2f}")

if cands:
    todas = [x[3]["roi"] for x in cands]
    sel = [x[3]["roi"] for x in cands if x[2]["roi"] >= 10]
    print(f"\nControl de sobreajuste -- ROI medio en RESERVA:")
    print(f"  todas ({len(todas)}): {statistics.mean(todas):+.2f}%")
    if len(sel) >= 5:
        print(f"  las que dieron >=+10% en busqueda ({len(sel)}): {statistics.mean(sel):+.2f}%")
