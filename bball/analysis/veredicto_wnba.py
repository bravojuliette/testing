"""Ejecuta EXACTAMENTE el procedimiento fijado en
bball/analysis/PREREGISTRO_wnba_underdogs.md sobre un rango de fechas.

    python3 bball/analysis/veredicto_wnba.py [fecha_ini] [fecha_fin]

Por defecto usa el rango de comprobacion del pre-registro (2022-01-01 a
2024-12-31: temporadas 2022, 2023 y 2024 de WNBA, que no estaban en la base
cuando se escribio la hipotesis).

Lee las cuotas de ganador directamente de la cache HTTP (mismo mapeo por
huella digital que reparse_moneyline_spread) para no depender de que la
reparseada haya corrido ya, y sin escribir nada.

Procedimiento fijado (no tocar):
  - mercado ganador (18_1), snapshot 'kickoff' (cierre real)
  - primera casa disponible entre Bet365, Betway, BWin
  - underdog = cuota MAYOR que la del rival; una apuesta por partido
  - historial >= 10 partidos previos de AMBOS equipos
  - tramo de cuota 2.5 - 5.0, sin ningun filtro adicional
  - stake plano de 1 unidad
Criterio: CONFIRMADA si ROI>0 y t>=2; REFUTADA en otro caso;
NO CONCLUYENTE si n<80.
"""
import json
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")  # correr desde la raiz del repo

from bball import config, db
from bball.backtest.replay import load_games

DESDE = sys.argv[1] if len(sys.argv) > 1 else "2022-01-01"
HASTA = sys.argv[2] if len(sys.argv) > 2 else "2024-12-31"
N = 10
BOOKS = ("Bet365", "Betway", "BWin")
BANDA = (2.5, 5.0)

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

# historial walk-forward sobre TODO el historico (el historial de un partido
# de 2023 puede venir de 2022), pero solo se apuesta dentro del rango pedido
hist = defaultdict(list)
apuestas = []
for g in sorted(games, key=lambda x: x.time_ts):
    pick = ml.get(g.event_id)
    if (pick and g.league_name == "WNBA" and DESDE <= g.date <= HASTA
            and len(hist[g.home_key]) >= N and len(hist[g.away_key]) >= N):
        loc, vis = pick
        for es_local in (True, False):
            odds = loc if es_local else vis
            rival = vis if es_local else loc
            if odds <= rival:
                continue
            gano = (g.home_score > g.away_score) if es_local else (g.away_score > g.home_score)
            apuestas.append(dict(date=g.date, odds=odds, gano=gano))
    hist[g.home_key].append(g.home_score)
    hist[g.away_key].append(g.away_score)


def stat(sub):
    if not sub:
        return None
    p = [(a["odds"] - 1) if a["gano"] else -1.0 for a in sub]
    n = len(p)
    roi = sum(p) / n * 100
    sd = statistics.pstdev(p) if n > 1 else 0
    t = (statistics.mean(p) / sd) * (n ** 0.5) if sd > 0 else 0
    return dict(n=n, roi=roi, t=t, hit=sum(1 for a in sub if a["gano"]) / n * 100,
                odds=statistics.mean(a["odds"] for a in sub))


print(f"PRE-REGISTRO: underdogs WNBA, cuota de cierre {BANDA[0]}-{BANDA[1]}, sin filtros")
print(f"Rango evaluado: {DESDE} .. {HASTA}")
print(f"Partidos WNBA con cuota de ganador en el rango: "
      f"{sum(1 for g in games if g.league_name=='WNBA' and DESDE <= g.date <= HASTA and g.event_id in ml)}\n")

banda = [a for a in apuestas if BANDA[0] <= a["odds"] < BANDA[1]]
r = stat(banda)
if r is None:
    print("Sin apuestas en el rango.")
    sys.exit()

print(f"RESULTADO: n={r['n']}  cuota media={r['odds']:.2f}  acierto={r['hit']:.1f}%  "
      f"ROI={r['roi']:+.1f}%  t={r['t']:.2f}")
if r["n"] < 80:
    print("\n>>> NO CONCLUYENTE (n < 80, muestra insuficiente segun el pre-registro)")
elif r["roi"] > 0 and r["t"] >= 2:
    print("\n>>> CONFIRMADA (ROI>0 y t>=2)")
else:
    print("\n>>> REFUTADA (no cumple ROI>0 y t>=2)")

print("\nPor año (informativo, NO altera el veredicto):")
for y in sorted({a["date"][:4] for a in banda}):
    s = stat([a for a in banda if a["date"].startswith(y)])
    print(f"  {y}: n={s['n']:>4} acierto={s['hit']:>5.1f}% ROI={s['roi']:>+7.1f}% t={s['t']:>5.2f}")

print("\nCONTROLES (deben mantenerse, o algo va mal en los datos):")
for lo, hi, esperado in ((1.0, 2.5, "~0"), (5.0, 8.0, "negativo"), (8.0, 99.0, "muy negativo")):
    s = stat([a for a in apuestas if lo <= a["odds"] < hi])
    if s and s["n"] >= 15:
        print(f"  cuota {lo}-{hi}: n={s['n']:>4} ROI={s['roi']:>+7.1f}%  (esperado: {esperado})")
