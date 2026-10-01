"""Barrido EXHAUSTIVO de combinaciones de cuartos (peticion del usuario:
'todas las combinaciones posibles para una regla universal explotable').

Diseño anti-espejismo integrado:
- Busqueda = 2025-26; reserva = anteriores. El benchmark (lo que una casa
  sabria al descanso: H2 ~ linea + H1) se ajusta SOLO con busqueda.
- Reglas: todas las condiciones atomicas (7 features del descanso x 5
  umbrales empiricos x 2 sentidos) y todos sus pares -> ~2500 reglas.
- Con N reglas, el maximo |t| esperado POR PURO AZAR es ~sqrt(2*ln(N)) ~ 3.9.
  Ese es el liston, no 2.
- La cifra que decide: correlacion entre el efecto en busqueda y en reserva
  a traves de las reglas. ~0 = elegir la mejor regla no predice nada.
"""
import itertools
import json
import math
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball import config, db
from bball.backtest.replay import load_games

BOOKS = ("Bet365", "Betway", "BWin")
SPLIT = "2025-10-01"

with db.get_conn() as conn:
    games = load_games(conn)
    raws = {r["event_id"]: r["raw_json"] for r in conn.execute(
        "SELECT event_id, raw_json FROM bball_games WHERE completed=1").fetchall()}
    kick = defaultdict(dict)
    for r in conn.execute("SELECT event_id, book, line FROM bball_odds "
                          "WHERE market=? AND snapshot='kickoff'",
                          (config.TOTALS_MARKET_KEY,)).fetchall():
        kick[r["event_id"]][r["book"]] = r["line"]

M = []
for g in games:
    if g.league_name not in ("NBA", "WNBA", "Euroleague"):
        continue
    L = next((kick[g.event_id][b] for b in BOOKS if b in kick.get(g.event_id, {})), None)
    if not L:
        continue
    try:
        sc = json.loads(raws[g.event_id]).get("scores") or {}
        q1 = int(sc["1"]["home"]) + int(sc["1"]["away"])
        q2 = int(sc["2"]["home"]) + int(sc["2"]["away"])
        q3 = int(sc["4"]["home"]) + int(sc["4"]["away"])
        q4 = int(sc["5"]["home"]) + int(sc["5"]["away"])
        m1 = abs(int(sc["1"]["home"]) - int(sc["1"]["away"]))
        mh = abs(int(sc["3"]["home"]) - int(sc["3"]["away"]))
    except Exception:
        continue
    if min(q1, q2, q3, q4) < 10:
        continue
    f = dict(q1=q1, q2=q2, d21=q2 - q1, h1=q1 + q2, dev=q1 + q2 - L / 2,
             m1=m1, mh=mh)
    M.append(dict(date=g.date, f=f, h2=q3 + q4, L=L, h1=q1 + q2))

busq = [m for m in M if m["date"] >= SPLIT]
resv = [m for m in M if m["date"] < SPLIT]
print(f"partidos: {len(M)} (busqueda {len(busq)} / reserva {len(resv)})")

# benchmark ajustado SOLO en busqueda
X = [(1.0, m["L"], m["h1"]) for m in busq]
y = [m["h2"] for m in busq]
XtX = [[sum(a[i] * a[j] for a in X) for j in range(3)] for i in range(3)]
Xty = [sum(a[i] * b for a, b in zip(X, y)) for i in range(3)]
A = [row[:] + [v] for row, v in zip(XtX, Xty)]
for i in range(3):
    for j in range(i + 1, 3):
        fpiv = A[j][i] / A[i][i]
        for k in range(i, 4):
            A[j][k] -= fpiv * A[i][k]
beta = [0.0] * 3
for i in (2, 1, 0):
    beta[i] = (A[i][3] - sum(A[i][j] * beta[j] for j in range(i + 1, 3))) / A[i][i]
for m in M:
    m["res"] = m["h2"] - (beta[0] + beta[1] * m["L"] + beta[2] * m["h1"])

FEATS = sorted(M[0]["f"].keys())
qs = {}
for k in FEATS:
    v = sorted(m["f"][k] for m in M)
    qs[k] = sorted({v[int(p * (len(v) - 1))] for p in (0.2, 0.35, 0.5, 0.65, 0.8)})
atomos = [(k, op, thr) for k in FEATS for thr in qs[k] for op in ("<=", ">=")]
reglas = [(a,) for a in atomos] + list(itertools.combinations(atomos, 2))
print(f"reglas enumeradas: {len(reglas)}  (liston de azar: |t|max ~ {math.sqrt(2*math.log(len(reglas))):.1f})\n")


def aplica(regla, f):
    for k, op, thr in regla:
        v = f[k]
        if (op == "<=" and v > thr) or (op == ">=" and v < thr):
            return False
    return True


def efecto(regla, sub):
    sel = [m["res"] for m in sub if aplica(regla, m["f"])]
    if len(sel) < 80:
        return None
    mu = statistics.mean(sel)
    t = mu / (statistics.pstdev(sel) / len(sel) ** 0.5)
    return dict(n=len(sel), mu=mu, t=t)


evaluadas = []
for r in reglas:
    eb = efecto(r, busq)
    if not eb:
        continue
    er = efecto(r, resv)
    if not er:
        continue
    evaluadas.append((r, eb, er))
print(f"reglas con muestra en ambas ventanas: {len(evaluadas)}")

xs = [eb["mu"] for _, eb, _ in evaluadas]
ys = [er["mu"] for _, _, er in evaluadas]
mx, my = statistics.mean(xs), statistics.mean(ys)
num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
print(f"\nLA CIFRA QUE DECIDE: corr(efecto busqueda, efecto reserva) = {num/den:+.3f}")

top = sorted(evaluadas, key=lambda x: -abs(x[1]["t"]))[:8]
print(f"\nTOP-8 por |t| en BUSQUEDA, y que hacen en RESERVA:")
print(f"{'regla':<52} {'busq: mu':>9} {'t':>6} | {'resv: mu':>9} {'t':>6}")
def fmt(r):
    return " Y ".join(f"{k}{op}{thr:g}" for k, op, thr in r)
for r, eb, er in top:
    print(f"{fmt(r)[:52]:<52} {eb['mu']:>+9.2f} {eb['t']:>+6.2f} | {er['mu']:>+9.2f} {er['t']:>+6.2f}")

sup = [1 for _, eb, er in evaluadas if abs(eb["t"]) >= 2 and eb["mu"] * er["mu"] > 0 and abs(er["t"]) >= 2]
print(f"\nreglas con |t|>=2 en busqueda: {sum(1 for _,eb,_ in evaluadas if abs(eb['t'])>=2)}"
      f" (por azar se esperan ~{len(evaluadas)*0.05:.0f})")
print(f"de esas, mismas señal y |t|>=2 tambien en reserva: {len(sup)}")
