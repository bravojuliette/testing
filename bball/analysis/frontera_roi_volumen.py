"""Peticion del usuario: filtros que mejoren el ROI SIN hundir el volumen.

Todas las busquedas anteriores rankeaban por ROI a secas, y eso selecciona
sistematicamente muestras minusculas (donde el ruido produce ROIs altos).
Aqui se hace al reves: se impone un SUELO DE VOLUMEN y se busca el mejor
ROI dentro de cada banda de cobertura.

La salida clave es la FRONTERA: para cada nivel de volumen retenido, cual
es el mejor ROI que se puede conseguir en la ventana de busqueda, y que
hace ese mismo filtro en la reserva. Si la frontera se derrumba hacia el
margen segun sube el volumen exigido, la respuesta es estructural.
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
SEED = 20260828

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds "
        "WHERE market = ? AND snapshot = 'kickoff'", (config.TOTALS_MARKET_KEY,)
    ).fetchall()

tot = defaultdict(dict)
for r in rows:
    tot[r["event_id"]][r["book"]] = (r["line"], r["over_odds"], r["under_odds"])

def racha_uo(h):
    if not h:
        return 0, 0
    s = h[-1]; k = 0
    for x in reversed(h):
        if x == s: k += 1
        else: break
    return s, k

pf, pa_, th, uo = (defaultdict(list) for _ in range(4))
last_ts = {}
muestras = []
for g in sorted(games, key=lambda x: x.time_ts):
    d = tot.get(g.event_id, {})
    pick = next((d[b] for b in BOOKS if b in d), None)
    if pick and len(pf[g.home_key]) >= N and len(pf[g.away_key]) >= N:
        linea, o_ov, o_un = pick
        if o_ov and o_un and o_ov > 1 and o_un > 1:
            avg = lambda L, k=N: sum(L[-k:]) / min(len(L), k)
            sh, kh = racha_uo(uo[g.home_key]); sa, ka = racha_uo(uo[g.away_key])
            rh = (g.time_ts - last_ts[g.home_key]) / 86400 if g.home_key in last_ts else 5.0
            ra = (g.time_ts - last_ts[g.away_key]) / 86400 if g.away_key in last_ts else 5.0
            muestras.append(dict(
                date=g.date, lg=g.league_name, final=g.total, linea=linea,
                o_ov=o_ov, o_un=o_un,
                dif=linea - (avg(pf[g.home_key]) + avg(pf[g.away_key])),
                ritmo=(avg(th[g.home_key]) + avg(th[g.away_key])) / 2,
                linea_abs=linea,
                anota=(avg(pf[g.home_key]) + avg(pf[g.away_key])) / 2,
                encaja=(avg(pa_[g.home_key]) + avg(pa_[g.away_key])) / 2,
                descanso=min(min(rh, 5.0), min(ra, 5.0)),
                b2b=1.0 if min(rh, ra) <= 1.2 else 0.0,
                racha_ov=float(max(kh if sh == 1 else 0, ka if sa == 1 else 0)),
                racha_un=float(max(kh if sh == -1 else 0, ka if sa == -1 else 0)),
                dia=float(__import__("datetime").date.fromisoformat(g.date).weekday()),
                mes=float(int(g.date[5:7])),
            ))
    pf[g.home_key].append(g.home_score); pf[g.away_key].append(g.away_score)
    pa_[g.home_key].append(g.away_score); pa_[g.away_key].append(g.home_score)
    th[g.home_key].append(g.total); th[g.away_key].append(g.total)
    last_ts[g.home_key] = g.time_ts; last_ts[g.away_key] = g.time_ts
    if pick and g.total != pick[0]:
        m = -1 if g.total < pick[0] else 1
        uo[g.home_key].append(m); uo[g.away_key].append(m)

busq = [m for m in muestras if m["date"] >= SPLIT]
res = [m for m in muestras if m["date"] < SPLIT]
print(f"Partidos: {len(muestras)}  (busqueda {len(busq)} / reserva {len(res)})\n")

def stat(sub, lado):
    pnls, ok, dec = [], 0, 0
    for m in sub:
        odds = m["o_un"] if lado == "U" else m["o_ov"]
        if m["final"] == m["linea"]:
            pnls.append(0.0); continue
        gano = m["final"] < m["linea"] if lado == "U" else m["final"] > m["linea"]
        pnls.append(odds - 1 if gano else -1.0)
        dec += 1; ok += gano
    n = len(pnls)
    if n == 0: return None
    sd = statistics.pstdev(pnls) if n > 1 else 0
    return dict(n=n, roi=sum(pnls)/n*100, hit=ok/dec*100 if dec else 0,
                t=(statistics.mean(pnls)/sd)*(n**0.5) if sd > 0 else 0)

FEATS = [k for k in muestras[0] if k not in ("date","lg","final","linea","o_ov","o_un")]
qs = {}
for k in FEATS:
    v = sorted(m[k] for m in muestras)
    qs[k] = [v[int(p*(len(v)-1))] for p in (0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9)]

rnd = random.Random(SEED)
def aplica(c, m):
    for k, op, thr in c:
        if (op == ">=" and not m[k] >= thr) or (op == "<=" and not m[k] <= thr):
            return False
    return True

print("Generando filtros y midiendo la frontera ROI/volumen...\n")
cands = []
for _ in range(8000):
    c = [(rnd.choice(FEATS), rnd.choice([">=","<="]), 0) for _ in range(rnd.choice([1,1,2]))]
    c = [(k, op, rnd.choice(qs[k])) for k, op, _ in c]
    lado = rnd.choice(["U","O"])
    sb = stat([m for m in busq if aplica(c, m)], lado)
    if sb is None or sb["n"] < 40:
        continue
    sr = stat([m for m in res if aplica(c, m)], lado)
    if sr is None or sr["n"] < 40:
        continue
    cands.append((c, lado, sb, sr, sb["n"]/len(busq)))

print(f"{len(cands)} filtros con >=40 apuestas en ambas ventanas.\n")
print("LA FRONTERA: mejor ROI alcanzable segun el volumen que se conserva\n")
print(f"{'cobertura':<22} {'filtros':>8} {'mejor ROI busq':>15} {'ese filtro en RESERVA':>23}")
BANDAS = [(0.60,1.01,">=60% de los partidos"), (0.40,0.60,"40-60%"), (0.25,0.40,"25-40%"),
          (0.15,0.25,"15-25%"), (0.08,0.15,"8-15%"), (0.0,0.08,"<8%")]
for lo, hi, et in BANDAS:
    sub = [x for x in cands if lo <= x[4] < hi]
    if not sub:
        continue
    mejor = max(sub, key=lambda x: x[2]["roi"])
    print(f"{et:<22} {len(sub):>8} {mejor[2]['roi']:>+14.1f}% {mejor[3]['roi']:>+15.1f}% (t={mejor[3]['t']:>5.2f})")

print("\nY el dato honesto: ROI MEDIO en la reserva por banda de cobertura")
print("(si seleccionar sirviera, las bandas estrechas deberian ser mejores)\n")
print(f"{'cobertura':<22} {'filtros':>8} {'ROI medio reserva':>19} {'ROI medio busqueda':>20}")
for lo, hi, et in BANDAS:
    sub = [x for x in cands if lo <= x[4] < hi]
    if len(sub) < 3:
        continue
    print(f"{et:<22} {len(sub):>8} {statistics.mean(x[3]['roi'] for x in sub):>+18.2f}% "
          f"{statistics.mean(x[2]['roi'] for x in sub):>+19.2f}%")

print("\nLOS QUE APROBARIAN: ROI>0 en AMBAS ventanas y cobertura >=15%:\n")
fmt = lambda c: " Y ".join(f"{k}{op}{thr:.1f}" for k,op,thr in c)
rob = [x for x in cands if x[4] >= 0.15 and x[2]["roi"] > 0 and x[3]["roi"] > 0]
rob.sort(key=lambda x: -min(x[2]["roi"], x[3]["roi"]))
if not rob:
    print("  (ninguno)")
for c, lado, sb, sr, cov in rob[:10]:
    print(f"  [{lado}] {fmt(c):<42} cobertura {cov*100:>4.0f}%")
    print(f"       busqueda n={sb['n']:>4} ROI={sb['roi']:>+6.1f}% t={sb['t']:>5.2f}  |  "
          f"reserva n={sr['n']:>4} ROI={sr['roi']:>+6.1f}% t={sr['t']:>5.2f}")
