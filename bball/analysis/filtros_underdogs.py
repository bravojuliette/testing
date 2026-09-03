"""¿Sirve filtrar underdogs para mejorar el ROI?

Dos preguntas distintas que se confunden con facilidad:
  A) ¿Puedo filtrar para ACERTAR MAS? -- si, trivialmente: basta quedarse
     con underdogs mas cortos. Pero la cuota baja a la vez, asi que no
     genera dinero. Se mide el intercambio acierto/cuota explicitamente.
  B) ¿Puedo filtrar para acertar mas DE LO QUE IMPLICA EL PRECIO? -- esta
     es la unica que importa, y se mide como (acierto real - prob. implicita).

Ademas: las reglas que mejor pintaban en la ventana de busqueda (2025-26)
se prueban contra los datos NUEVOS de WNBA 2022, que no existian cuando se
eligieron. Es una prueba limpia de si "filtrar" sobrevive fuera de muestra.
"""
import json
import random
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")  # correr desde la raiz del repo

from bball import config, db
from bball.backtest.replay import load_games

N = 10
BOOKS = ("Bet365", "Betway", "BWin")
SPLIT = "2025-10-01"

with db.get_conn() as conn:
    games = load_games(conn)
    league_of = {g.event_id: g.league_name for g in games}
    fp_index = defaultdict(set)
    for r in conn.execute(
        "SELECT event_id, book, line, captured_at FROM bball_odds "
        "WHERE market=? AND snapshot='start' AND captured_at IS NOT NULL",
        (config.TOTALS_MARKET_KEY,),
    ).fetchall():
        fp_index[(r["book"], str(r["captured_at"]), float(r["line"]))].add(r["event_id"])
    ml = {}
    offset = 0
    while True:
        rows = conn.execute(
            "SELECT body FROM bball_http_cache WHERE prefix='odds_summary' LIMIT 300 OFFSET ?",
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
            swap = config.swaps_home_away(league_of.get(eid))
            for book in BOOKS:
                b = results.get(book)
                if not isinstance(b, dict):
                    continue
                e = ((b.get("odds") or {}).get("kickoff") or {}).get(config.MONEYLINE_MARKET_KEY)
                if not isinstance(e, dict) or e.get("ss"):
                    continue
                try:
                    loc, vis = float(e["home_od"]), float(e["away_od"])
                except (KeyError, TypeError, ValueError):
                    continue
                if loc <= 1 or vis <= 1:
                    continue
                ml[eid] = (vis, loc) if swap else (loc, vis)
                break

scored, allowed, wins_h, margins, totals_h = (defaultdict(list) for _ in range(5))
last_ts = {}
dogs = []
for g in sorted(games, key=lambda x: x.time_ts):
    pick = ml.get(g.event_id)
    if pick and len(scored[g.home_key]) >= N and len(scored[g.away_key]) >= N:
        loc, vis = pick
        ih, ia = 1 / loc, 1 / vis
        avg = lambda L, k=N: sum(L[-k:]) / min(len(L), k)
        for es_local in (True, False):
            odds = loc if es_local else vis
            r_odds = vis if es_local else loc
            if odds <= r_odds:
                continue
            me = g.home_key if es_local else g.away_key
            riv = g.away_key if es_local else g.home_key
            gano = (g.home_score > g.away_score) if es_local else (g.away_score > g.home_score)
            p_imp = (ih if es_local else ia) / (ih + ia)   # implicita sin margen
            rest = (g.time_ts - last_ts[me]) / 86400 if me in last_ts else 5.0
            rest_r = (g.time_ts - last_ts[riv]) / 86400 if riv in last_ts else 5.0
            dogs.append(dict(
                date=g.date, lg=g.league_name, odds=odds, gano=gano, p_imp=p_imp,
                es_local=1.0 if es_local else 0.0,
                anota=avg(scored[me]), encaja=avg(allowed[me]),
                anota_riv=avg(scored[riv]), encaja_riv=avg(allowed[riv]),
                winpct=avg(wins_h[me]), winpct_riv=avg(wins_h[riv]),
                margen=avg(margins[me]), margen_riv=avg(margins[riv]),
                margen_riv3=avg(margins[riv], 3), forma3=avg(scored[me], 3),
                descanso=min(rest, 5.0), descanso_riv=min(rest_r, 5.0),
                ventaja_descanso=min(rest, 5.0) - min(rest_r, 5.0),
                ritmo=avg(totals_h[me]),
            ))
    for key, pf, pa in ((g.home_key, g.home_score, g.away_score),
                        (g.away_key, g.away_score, g.home_score)):
        scored[key].append(pf); allowed[key].append(pa)
        wins_h[key].append(1.0 if pf > pa else 0.0)
        margins[key].append(float(pf - pa)); totals_h[key].append(g.total)
        last_ts[key] = g.time_ts

print(f"Apuestas potenciales a underdog: {len(dogs)}\n")

def stat(sub):
    if not sub:
        return None
    p = [(d["odds"] - 1) if d["gano"] else -1.0 for d in sub]
    n = len(p)
    sd = statistics.pstdev(p) if n > 1 else 0
    return dict(n=n, roi=sum(p) / n * 100,
                t=(statistics.mean(p) / sd) * (n ** 0.5) if sd > 0 else 0,
                hit=sum(1 for d in sub if d["gano"]) / n * 100,
                odds=statistics.mean(d["odds"] for d in sub),
                imp=statistics.mean(d["p_imp"] for d in sub) * 100)

# ---------- A) el intercambio acierto <-> cuota ----------
print("A) EL INTERCAMBIO: filtrar para acertar mas BAJA la cuota en la misma medida.")
print("   'ventaja' = acierto real - probabilidad implicita (sin margen). Es lo unico")
print("   que genera ROI; el acierto por si solo no dice nada.\n")
print(f"{'filtro':<34} {'n':>5} {'acierto':>8} {'implicita':>10} {'ventaja':>9} {'cuota':>7} {'ROI%':>8}")
FILTROS = [
    ("(ninguno: todos los dogs)", lambda d: True),
    ("cuota < 2.0", lambda d: d["odds"] < 2.0),
    ("cuota 2.0-2.5", lambda d: 2.0 <= d["odds"] < 2.5),
    ("cuota 2.5-3.5", lambda d: 2.5 <= d["odds"] < 3.5),
    ("cuota 3.5-5.0", lambda d: 3.5 <= d["odds"] < 5.0),
    ("cuota > 5.0", lambda d: d["odds"] >= 5.0),
    ("es local", lambda d: d["es_local"] > 0),
    ("buen % victorias (>0.5)", lambda d: d["winpct"] > 0.5),
    ("rival flojo (winpct<0.4)", lambda d: d["winpct_riv"] < 0.4),
    ("mas descansado que el rival", lambda d: d["ventaja_descanso"] > 0.5),
    ("rival viene de paliza (>+10)", lambda d: d["margen_riv3"] > 10),
]
for nombre, f in FILTROS:
    s = stat([d for d in dogs if f(d)])
    if s and s["n"] >= 25:
        print(f"{nombre:<34} {s['n']:>5} {s['hit']:>7.1f}% {s['imp']:>9.1f}% "
              f"{s['hit']-s['imp']:>+8.1f} {s['odds']:>7.2f} {s['roi']:>+8.1f}")

# ---------- B) los filtros elegidos en busqueda, contra datos NUEVOS ----------
nuevos = [d for d in dogs if d["date"] < "2023-01-01"]      # WNBA 2022: datos nuevos
search = [d for d in dogs if d["date"] >= SPLIT]
print(f"\nB) PRUEBA LIMPIA: filtros elegidos mirando 2025-26, probados sobre los datos")
print(f"   NUEVOS de WNBA 2022 ({len(nuevos)} apuestas), que no existian al elegirlos.\n")

FEATS = [k for k in dogs[0] if k not in ("date", "lg", "odds", "gano", "p_imp")]
qs = {}
for k in FEATS:
    v = sorted(d[k] for d in dogs)
    qs[k] = [v[int(p * (len(v) - 1))] for p in (0.15, 0.3, 0.5, 0.7, 0.85)]

def aplica(conds, d):
    for k, op, thr in conds:
        if (op == ">=" and not d[k] >= thr) or (op == "<=" and not d[k] <= thr):
            return False
    return True

rnd = random.Random(7)
cands = []
for _ in range(4000):
    conds = [(rnd.choice(FEATS), rnd.choice([">=", "<="]), 0) for _ in range(rnd.choice([1, 2, 2]))]
    conds = [(k, op, rnd.choice(qs[k])) for k, op, _ in conds]
    s = stat([d for d in search if 2.5 <= d["odds"] < 5.0 and aplica(conds, d)])
    if s and s["n"] >= 30:
        cands.append((conds, s))
cands.sort(key=lambda x: -x[1]["roi"])
print(f"   {len(cands)} filtros con muestra suficiente en busqueda. Los 8 mejores:\n")
print(f"{'busqueda 25-26':>26} | {'WNBA 2022 (nuevo)':>26}  filtro")
rois_nuevos = []
for conds, s in cands[:8]:
    sn = stat([d for d in nuevos if 2.5 <= d["odds"] < 5.0 and aplica(conds, d)])
    txt = f"n={sn['n']:>3} ROI={sn['roi']:>+6.1f}% t={sn['t']:>5.2f}" if sn and sn["n"] >= 10 else "muestra insuficiente"
    if sn and sn["n"] >= 10:
        rois_nuevos.append(sn["roi"])
    d = " Y ".join(f"{k}{op}{thr:.1f}" for k, op, thr in conds)
    print(f"n={s['n']:>3} ROI={s['roi']:>+6.1f}% t={s['t']:>5.2f} | {txt:>26}  {d[:40]}")

base = stat([d for d in nuevos if 2.5 <= d["odds"] < 5.0])
print(f"\n   SIN filtro sobre esos mismos datos nuevos: n={base['n']} ROI={base['roi']:+.1f}%")
if rois_nuevos:
    print(f"   ROI medio de los 8 filtros 'mejores' sobre datos nuevos: {statistics.mean(rois_nuevos):+.1f}%")
    print("   (si filtrar aportara algo, esto deberia superar claramente al 'sin filtro')")
