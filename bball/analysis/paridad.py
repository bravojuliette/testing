"""Teoria del usuario: los partidos con equipos MUY PAREJOS (segun cuotas de
ganador) acaban mas a menudo con puntuacion total PAR.

Las cuotas de ganador (mercado 18_1) estaban en la cache HTTP sin parsear
(solo habiamos guardado 18_3, totales). Se extraen aqui con el mismo mapeo
por huella digital que uso reparse_kickoff (3987/3988 eventos, 0 ambiguos).

Se mide:
1. P(total par) global -- ¿hay algun sesgo de paridad en baloncesto?
2. P(total par) segun lo parejo del partido (varios cortes)
3. Si el efecto existiera, ¿daria ROI a cuota 1.90 (precio tipico de
   par/impar)? Y ¿se sostiene en ambas temporadas?
"""
import json
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")  # correr desde la raiz del repo

from bball import config, db
from bball.backtest.replay import load_games

SPLIT = "2025-10-01"
ODDS_PAR = 1.90   # precio tipico de par/impar (no lo tenemos en los datos)

with db.get_conn() as conn:
    games = load_games(conn)
    # huella digital: (book, captured_at, line) de las filas 'start' -> event_id
    fp_index = defaultdict(set)
    for r in conn.execute(
        "SELECT event_id, book, line, captured_at FROM bball_odds "
        "WHERE market=? AND snapshot='start' AND captured_at IS NOT NULL",
        (config.TOTALS_MARKET_KEY,),
    ).fetchall():
        fp_index[(r["book"], str(r["captured_at"]), float(r["line"]))].add(r["event_id"])

    ml = {}   # event_id -> {book: (home_od, away_od)} en kickoff
    offset = 0
    while True:
        rows = conn.execute(
            "SELECT body FROM bball_http_cache WHERE prefix='odds_summary' LIMIT 200 OFFSET ?",
            (offset,),
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
                e = ((b.get("odds") or {}).get("start") or {}).get(config.TOTALS_MARKET_KEY)
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
            d = {}
            for book, b in results.items():
                if not isinstance(b, dict):
                    continue
                e = ((b.get("odds") or {}).get("kickoff") or {}).get("18_1")
                if not isinstance(e, dict) or e.get("ss"):
                    continue
                try:
                    h, a = float(e["home_od"]), float(e["away_od"])
                except (KeyError, TypeError, ValueError):
                    continue
                if h > 1 and a > 1:
                    d[book] = (h, a)
            if d:
                ml[eid] = d

print(f"Eventos con cuotas de ganador al cierre: {len(ml)}")

samples = []
for g in games:
    d = ml.get(g.event_id)
    if not d:
        continue
    # probabilidad implicita normalizada (quitando el margen), mediana entre casas
    ps = []
    for h, a in d.values():
        ih, ia = 1 / h, 1 / a
        ps.append(ih / (ih + ia))
    p_home = statistics.median(ps)
    samples.append(dict(date=g.date, league=g.league_name, total=g.total,
                        par=(g.total % 2 == 0), balance=abs(p_home - 0.5)))

print(f"Partidos con resultado + cuotas de ganador: {len(samples)}\n")

def wilson_ci(k, n):
    """Intervalo de confianza 95% (Wilson) para una proporcion."""
    if n == 0:
        return (0, 0)
    p = k / n
    z = 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (c - h, c + h)

k = sum(1 for s in samples if s["par"])
n = len(samples)
lo, hi = wilson_ci(k, n)
print(f"1. GLOBAL: P(total par) = {k/n*100:.2f}%  (n={n}, IC95%: {lo*100:.1f}% .. {hi*100:.1f}%)")
print(f"   ¿Incluye el 50%? {'SI -> indistinguible de una moneda' if lo <= 0.5 <= hi else 'NO -> hay sesgo'}\n")

print("2. SEGUN LO PAREJO DEL PARTIDO (balance = |prob. local - 50%|, menor = mas parejo):")
print(f"{'grupo':<34} {'n':>5} {'P(par)':>8} {'IC95%':>18}")
buckets = [
    ("MUY parejos (balance <= 0.02)", lambda s: s["balance"] <= 0.02),
    ("parejos (<= 0.05)", lambda s: s["balance"] <= 0.05),
    ("bastante parejos (<= 0.10)", lambda s: s["balance"] <= 0.10),
    ("medios (0.10 - 0.25)", lambda s: 0.10 < s["balance"] <= 0.25),
    ("desiguales (> 0.25)", lambda s: s["balance"] > 0.25),
]
for name, cond in buckets:
    sub = [s for s in samples if cond(s)]
    if len(sub) < 20:
        print(f"{name:<34} {len(sub):>5}   (muestra insuficiente)")
        continue
    kk = sum(1 for s in sub if s["par"])
    l, h = wilson_ci(kk, len(sub))
    print(f"{name:<34} {len(sub):>5} {kk/len(sub)*100:>7.1f}% {l*100:>8.1f}% .. {h*100:.1f}%")

print("\n3. Por liga (partidos parejos, balance <= 0.10):")
for lg in ("NBA", "WNBA", "Euroleague"):
    sub = [s for s in samples if s["league"] == lg and s["balance"] <= 0.10]
    if len(sub) < 20:
        continue
    kk = sum(1 for s in sub if s["par"])
    l, h = wilson_ci(kk, len(sub))
    print(f"  {lg:<11} n={len(sub):>4}  P(par)={kk/len(sub)*100:.1f}%  IC95%: {l*100:.1f}% .. {h*100:.1f}%")

print(f"\n4. ¿Y si se apostara PAR en los partidos parejos, a cuota {ODDS_PAR}?")
print("   (no tenemos el precio real de par/impar; se asume el tipico 1.90)")
print(f"{'grupo':<28} {'2025-26: n':>10} {'ROI%':>8} | {'2024-25: n':>10} {'ROI%':>8}")
for name, cond in buckets[:3]:
    out = []
    for lo_d, hi_d in ((SPLIT, "9999"), ("0000", SPLIT)):
        sub = [s for s in samples if cond(s) and lo_d <= s["date"] < hi_d]
        if not sub:
            out.append((0, 0.0))
            continue
        pnl = sum((ODDS_PAR - 1) if s["par"] else -1.0 for s in sub)
        out.append((len(sub), pnl / len(sub) * 100))
    print(f"{name:<28} {out[0][0]:>10} {out[0][1]:>+8.1f} | {out[1][0]:>10} {out[1][1]:>+8.1f}")

print(f"\n   Umbral de rentabilidad a cuota {ODDS_PAR}: hay que acertar "
      f"{1/ODDS_PAR*100:.1f}% de las veces.")
