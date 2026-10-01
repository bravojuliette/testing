"""Estrategia de underdogs: filtrar partidos para quedarse con los underdogs
con mas opciones reales de ganar, de modo que la cuota alta compense un hit
rate bajo.

Dos partes, en este orden a proposito:

1. CALIBRACION POR TRAMO DE CUOTA (el terreno de juego). En casi todos los
   deportes existe el "sesgo favorito-underdog": los underdogs muy largos
   estan SOBREVALORADOS (se pagan menos de lo que valen) y los favoritos
   infravalorados. Si eso pasa aqui, apostar underdogs parte con desventaja
   estructural y hay que saberlo ANTES de buscar filtros. Se mide sin filtro
   alguno: para cada tramo de cuota, cuanto gana de verdad vs lo que implica
   el precio.

2. BUSQUEDA DE FILTROS sobre underdogs, con disciplina busqueda/reserva
   (2025-26 para elegir, 2024-25 solo para comprobar). Se prueban criterios
   que podrian identificar underdogs infravalorados: descanso, forma, ritmo,
   defensa, si el favorito viene de paliza, cuanto se movio la linea, etc.

Ejecucion realista: cuota de CIERRE (kickoff) de una casa legal en España,
orientacion local/visitante ya normalizada (ver config.swaps_home_away).
"""
import random
import statistics
import sys
from collections import defaultdict, deque

sys.path.insert(0, ".")  # correr desde la raiz del repo

from bball import config, db
from bball.backtest.replay import load_games

SPLIT = "2025-10-01"
N = 10
BOOKS = ("Bet365", "Betway", "BWin")
MIN_N = 40
N_RULES = 5000
SEED = 20260828

with db.get_conn() as conn:
    games = load_games(conn)
    ml_rows = conn.execute(
        "SELECT event_id, book, over_odds, under_odds FROM bball_odds "
        "WHERE market = ? AND snapshot = 'kickoff'", (config.MONEYLINE_MARKET_KEY,)
    ).fetchall()
    tot_rows = conn.execute(
        "SELECT event_id, book, line FROM bball_odds "
        "WHERE market = ? AND snapshot = 'kickoff'", (config.TOTALS_MARKET_KEY,)
    ).fetchall()

# over_odds = LOCAL, under_odds = VISITANTE (ver reparse_moneyline_spread)
ml = defaultdict(dict)
for r in ml_rows:
    ml[r["event_id"]][r["book"]] = (r["over_odds"], r["under_odds"])
tot_line = defaultdict(list)
for r in tot_rows:
    tot_line[r["event_id"]].append(r["line"])

print(f"Eventos con cuota de ganador al cierre: {len(ml)}")

def streak_up(h):
    k = 0
    for i in range(len(h) - 1, 0, -1):
        if h[i] > h[i - 1]:
            k += 1
        else:
            break
    return k

scored, allowed, totals_h, wins_h, margins = (defaultdict(list) for _ in range(5))
last_ts = {}
season_n = defaultdict(int)

def season_key(d):
    y, m = int(d[:4]), int(d[5:7])
    return y if m >= 9 else y - 1

# una fila por EQUIPO-partido que sea underdog (cuota del equipo > la del rival)
dogs = []
for g in sorted(games, key=lambda x: x.time_ts):
    d = ml.get(g.event_id, {})
    pick = next((d[b] for b in BOOKS if b in d), None)
    hs, as_ = scored[g.home_key], scored[g.away_key]
    if pick and len(hs) >= N and len(as_) >= N:
        loc_od, vis_od = pick
        avg = lambda L, k=N: sum(L[-k:]) / min(len(L), k)
        # consenso sin margen para medir "cuanto underdog" es
        ih, ia = 1 / loc_od, 1 / vis_od
        p_loc = ih / (ih + ia)
        sk = season_key(g.date)
        lines = tot_line.get(g.event_id) or []
        for is_home in (True, False):
            odds = loc_od if is_home else vis_od
            rival_odds = vis_od if is_home else loc_od
            if odds <= rival_odds:
                continue  # solo underdogs
            me = g.home_key if is_home else g.away_key
            rival = g.away_key if is_home else g.home_key
            won = (g.home_score > g.away_score) if is_home else (g.away_score > g.home_score)
            rest = (g.time_ts - last_ts[me]) / 86400 if me in last_ts else 5.0
            rest_riv = (g.time_ts - last_ts[rival]) / 86400 if rival in last_ts else 5.0
            dogs.append(dict(
                date=g.date, league=g.league_name, odds=odds, won=won,
                p_imp=(1 - p_loc) if not is_home else p_loc,
                es_local=1.0 if is_home else 0.0,
                anota=avg(scored[me]), encaja=avg(allowed[me]),
                anota_riv=avg(scored[rival]), encaja_riv=avg(allowed[rival]),
                winpct=avg(wins_h[me]), winpct_riv=avg(wins_h[rival]),
                forma3=avg(scored[me], 3), margen=avg(margins[me]),
                margen_riv=avg(margins[rival]),
                # el favorito viene de ganar por paliza? (regresion a la media)
                margen_riv3=avg(margins[rival], 3),
                racha=float(streak_up(scored[me])),
                descanso=min(rest, 5.0), descanso_riv=min(rest_riv, 5.0),
                ventaja_descanso=min(rest, 5.0) - min(rest_riv, 5.0),
                ritmo=avg(totals_h[me]), linea_total=statistics.median(lines) if lines else 0.0,
                jornada=float(min(season_n[(me, sk)], 60)),
                dia=float(__import__("datetime").date.fromisoformat(g.date).weekday()),
            ))
    sk = season_key(g.date)
    for key, pf, pa in ((g.home_key, g.home_score, g.away_score),
                        (g.away_key, g.away_score, g.home_score)):
        scored[key].append(pf); allowed[key].append(pa)
        totals_h[key].append(g.total); wins_h[key].append(1.0 if pf > pa else 0.0)
        margins[key].append(float(pf - pa))
        last_ts[key] = g.time_ts
        season_n[(key, sk)] += 1

print(f"Apuestas potenciales a underdog (una por partido): {len(dogs)}\n")

# ---------- 1. calibracion por tramo de cuota ----------
print("1. CALIBRACION POR TRAMO DE CUOTA -- apostando TODOS los underdogs del tramo,")
print("   sin filtro alguno. Muestra si el terreno favorece o castiga al underdog:\n")
print(f"{'tramo de cuota':<18} {'n':>5} {'gana real':>10} {'implicita':>10} {'dif':>8} {'ROI%':>8}")
BUCKETS = [(1.0, 1.5), (1.5, 2.0), (2.0, 2.5), (2.5, 3.5), (3.5, 5.0), (5.0, 8.0), (8.0, 99.0)]
for lo, hi in BUCKETS:
    sub = [d for d in dogs if lo <= d["odds"] < hi]
    if len(sub) < 20:
        continue
    real = sum(1 for d in sub if d["won"]) / len(sub)
    imp = statistics.mean(1 / d["odds"] for d in sub)
    roi = sum((d["odds"] - 1) if d["won"] else -1.0 for d in sub) / len(sub) * 100
    print(f"{f'{lo:.1f} - {hi:.1f}':<18} {len(sub):>5} {real*100:>9.1f}% {imp*100:>9.1f}% "
          f"{(real-imp)*100:>+7.1f} {roi:>+8.1f}")

print("\n   (la columna 'implicita' incluye el margen, asi que un mercado justo daria")
print("    'dif' ligeramente negativa en todos los tramos por igual; si la dif EMPEORA")
print("    segun sube la cuota, existe sesgo favorito-underdog y los dogs largos son")
print("    terreno hostil, no una oportunidad)\n")

# ---------- 2. busqueda de filtros ----------
FEATS = [k for k in dogs[0] if k not in ("date", "league", "odds", "won", "p_imp")]
qs = {}
for k in FEATS:
    v = sorted(d[k] for d in dogs)
    qs[k] = [v[int(p * (len(v) - 1))] for p in (0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9)]

search = [d for d in dogs if d["date"] >= SPLIT]
hold = [d for d in dogs if d["date"] < SPLIT]

def evaluate(conds, min_odds, subset):
    pnls = []
    wins = 0
    odds_l = []
    for d in subset:
        if d["odds"] < min_odds:
            continue
        ok = True
        for k, op, thr in conds:
            v = d[k]
            if (op == ">=" and not v >= thr) or (op == "<=" and not v <= thr):
                ok = False
                break
        if not ok:
            continue
        pnls.append((d["odds"] - 1) if d["won"] else -1.0)
        odds_l.append(d["odds"])
        wins += d["won"]
    n = len(pnls)
    if n == 0:
        return None
    roi = sum(pnls) / n * 100
    sd = statistics.pstdev(pnls) if n > 1 else 0
    t = (statistics.mean(pnls) / sd) * (n ** 0.5) if sd > 0 else 0
    return dict(n=n, roi=roi, t=t, hit=wins / n * 100, odds=statistics.mean(odds_l))

rnd = random.Random(SEED)
results = []
for _ in range(N_RULES):
    conds = []
    for _ in range(rnd.choice([1, 2, 2, 3])):
        f = rnd.choice(FEATS)
        conds.append((f, rnd.choice([">=", "<="]), rnd.choice(qs[f])))
    min_odds = rnd.choice([1.0, 2.0, 2.5, 3.0])
    rs = evaluate(conds, min_odds, search)
    if rs is None or rs["n"] < MIN_N:
        continue
    rh = evaluate(conds, min_odds, hold)
    if rh is None or rh["n"] < 25:
        continue
    results.append((conds, min_odds, rs, rh))

fmt = lambda c: " Y ".join(f"{k}{op}{thr:.2f}" for k, op, thr in c)
print(f"2. BUSQUEDA DE FILTROS -- {len(results)} reglas con muestra suficiente en ambas ventanas\n")
results.sort(key=lambda x: -x[2]["roi"])
print("TOP 12 por ROI en la ventana de busqueda (2025-26), con su reserva al lado:")
print(f"{'n':>4} {'cuota':>6} {'hit%':>6} {'ROI%':>7} {'t':>5} | {'n24':>4} {'ROI24%':>8} {'t24':>6}  regla")
for conds, mo, rs, rh in results[:12]:
    print(f"{rs['n']:>4} {rs['odds']:>6.2f} {rs['hit']:>6.1f} {rs['roi']:>+7.1f} {rs['t']:>5.2f} | "
          f"{rh['n']:>4} {rh['roi']:>+8.1f} {rh['t']:>6.2f}  [c>={mo}] {fmt(conds)[:46]}")

print("\nROBUSTAS (ROI>0 y t>=1.5 en AMBAS temporadas):")
found = [x for x in results if x[2]["roi"] > 0 and x[3]["roi"] > 0
         and x[2]["t"] >= 1.5 and x[3]["t"] >= 1.5]
if not found:
    print("  (ninguna)")
for conds, mo, rs, rh in found[:10]:
    print(f"  [cuota>={mo}] {fmt(conds)}")
    print(f"     25-26: n={rs['n']} cuota={rs['odds']:.2f} hit={rs['hit']:.1f}% ROI={rs['roi']:+.1f}% t={rs['t']:.2f}")
    print(f"     24-25: n={rh['n']} cuota={rh['odds']:.2f} hit={rh['hit']:.1f}% ROI={rh['roi']:+.1f}% t={rh['t']:.2f}")

if results:
    all_h = [x[3]["roi"] for x in results]
    sel = [x[3]["roi"] for x in results if x[2]["roi"] >= 10]
    print(f"\nControl de sobreajuste -- ROI medio en la RESERVA:")
    print(f"  todas las reglas ({len(all_h)}): {statistics.mean(all_h):+.2f}%")
    if len(sel) >= 5:
        print(f"  solo las que dieron ROI>=+10% en busqueda ({len(sel)}): {statistics.mean(sel):+.2f}%")
