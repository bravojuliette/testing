"""Primer analisis con LINEAS DE CIERRE REALES (snapshot 'kickoff', cuota al
pitido inicial) para las casas legales en España -- posible gracias al
reparse-kickoff de la cache. A diferencia de todo lo anterior (que solo tenia
la apertura de Bet365/Betway/BWin), aqui señal y ejecucion estan en el mismo
instante (justo antes del pitido), asi que lo que salga es ejecutable de
verdad:

  - teoria original del usuario (linea de cierre - suma de medias >= umbral)
  - desviacion del consenso DE CIERRE (kickoff vs kickoff, mismo instante)
  - desviacion vs Pinnacle de cierre
  - movimiento apertura->cierre del mercado, apostando el CIERRE de la casa

Split por temporada como siempre: 2025-26 (busqueda) / 2024-25. Ambas ya han
sido miradas antes, asi que esto sigue siendo exploracion: lo que pase ambas
con t>=2 es candidato a pre-registro contra datos futuros, no confirmacion.
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")  # correr desde la raiz del repo: python3 bball/analysis/cierres_reales.py

from bball import db
from bball.backtest.replay import load_games

N = 10
SPLIT = "2025-10-01"
LEGAL_BOOKS = ["Bet365", "Betway", "BWin"]
MIN_N = 30

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds, snapshot FROM bball_odds "
        "WHERE market='18_3' AND snapshot IN ('start','kickoff') "
        "ORDER BY event_id, book, snapshot"
    ).fetchall()

open_of, close_of = {}, {}
for r in rows:
    key = (r["event_id"], r["book"])
    (close_of if r["snapshot"] == "kickoff" else open_of)[key] = r

by_event_close = defaultdict(dict)
for (eid, book), r in close_of.items():
    by_event_close[eid][book] = r

pf, tot = defaultdict(list), defaultdict(list)
samples = []
for g in games:
    closes = by_event_close.get(g.event_id, {})
    if closes and len(pf[g.home_key]) >= N and len(pf[g.away_key]) >= N:
        sum_avg = sum(pf[g.home_key][-N:]) / N + sum(pf[g.away_key][-N:]) / N
        max_tot = max(sum(tot[g.home_key][-N:]) / N, sum(tot[g.away_key][-N:]) / N)
        pin = closes.get("PinnacleSports")
        moves = []
        for book, c in closes.items():
            o = open_of.get((g.event_id, book))
            if o is not None:
                moves.append(c["line"] - o["line"])
        s = dict(
            date=g.date, league=g.league_name, final=g.total,
            sum_avg=sum_avg, max_tot=max_tot, gap=max_tot - sum_avg,
            pin_close=pin["line"] if pin else None,
            med_move=statistics.median(moves) if moves else None,
        )
        for b in LEGAL_BOOKS:
            c = closes.get(b)
            o = open_of.get((g.event_id, b))
            others = [r["line"] for bk, r in closes.items() if bk != b]
            s[b] = None if c is None else dict(
                L=c["line"], under=c["under_odds"], over=c["over_odds"],
                own_move=(c["line"] - o["line"]) if o else None,
                consensus=statistics.median(others) if others else None,
            )
        samples.append(s)
    pf[g.home_key].append(g.home_score)
    pf[g.away_key].append(g.away_score)
    tot[g.home_key].append(g.total)
    tot[g.away_key].append(g.total)

search = [s for s in samples if s["date"] >= SPLIT]
hold = [s for s in samples if s["date"] < SPLIT]
n_b365 = sum(1 for s in samples if s["Bet365"] is not None)
print(f"Partidos con algun CIERRE + historial N={N}: {len(samples)} "
      f"(2025-26: {len(search)} / 2024-25: {len(hold)}; con cierre de Bet365: {n_b365})\n")

SIGNALS = []

def sig(name, fn):
    SIGNALS.append((name, fn))

# teoria original del usuario, ahora sobre el cierre real
for thr in (6, 8, 10, 12):
    sig(f"U: cierre - sum_avg >= {thr} (teoria original)",
        lambda s, bk, thr=thr: "U" if (bk["L"] - s["sum_avg"]) >= thr else None)
for thr in (4, 6, 8):
    sig(f"O: sum_avg - cierre >= {thr}",
        lambda s, bk, thr=thr: "O" if (s["sum_avg"] - bk["L"]) >= thr else None)
for thr in (8, 10, 12):
    sig(f"U: max_tot - sum_avg >= {thr}",
        lambda s, bk, thr=thr: "U" if s["gap"] >= thr else None)
# desviacion del consenso de cierre (mismo instante -- ahora es legitimo)
for thr in (1, 1.5, 2, 3):
    sig(f"U: cierre >= consenso_cierre + {thr}",
        lambda s, bk, thr=thr: "U" if bk["consensus"] is not None and (bk["L"] - bk["consensus"]) >= thr else None)
    sig(f"O: cierre <= consenso_cierre - {thr}",
        lambda s, bk, thr=thr: "O" if bk["consensus"] is not None and (bk["consensus"] - bk["L"]) >= thr else None)
# desviacion vs Pinnacle de cierre
for thr in (1, 1.5, 2, 3):
    sig(f"U: cierre >= Pinnacle_cierre + {thr}",
        lambda s, bk, thr=thr: "U" if s["pin_close"] is not None and (bk["L"] - s["pin_close"]) >= thr else None)
    sig(f"O: cierre <= Pinnacle_cierre - {thr}",
        lambda s, bk, thr=thr: "O" if s["pin_close"] is not None and (s["pin_close"] - bk["L"]) >= thr else None)
# seguir el movimiento del mercado, ejecutado al cierre de la casa
for thr in (1, 1.5, 2):
    sig(f"U: mercado bajo linea >= {thr} (apertura->cierre)",
        lambda s, bk, thr=thr: "U" if s["med_move"] is not None and s["med_move"] <= -thr else None)
    sig(f"O: mercado subio linea >= {thr} (apertura->cierre)",
        lambda s, bk, thr=thr: "O" if s["med_move"] is not None and s["med_move"] >= thr else None)
# la propia casa movio su linea
for thr in (1, 2):
    sig(f"U: la casa bajo su linea >= {thr}",
        lambda s, bk, thr=thr: "U" if bk["own_move"] is not None and bk["own_move"] <= -thr else None)
    sig(f"O: la casa subio su linea >= {thr}",
        lambda s, bk, thr=thr: "O" if bk["own_move"] is not None and bk["own_move"] >= thr else None)

LEAGUES = [None, "NBA", "WNBA", "Euroleague"]


def evaluate(fn, book, league, subset):
    pnls, wins, dec = [], 0, 0
    for s in subset:
        if league is not None and s["league"] != league:
            continue
        bk = s[book]
        if bk is None:
            continue
        side = fn(s, bk)
        if not side:
            continue
        odds = bk["under"] if side == "U" else bk["over"]
        if not odds or odds <= 1:
            continue
        if s["final"] == bk["L"]:
            pnls.append(0.0)
            continue
        won = s["final"] < bk["L"] if side == "U" else s["final"] > bk["L"]
        pnls.append(odds - 1 if won else -1.0)
        dec += 1
        wins += won
    n = len(pnls)
    if n == 0:
        return None
    roi = sum(pnls) / n * 100
    sd = statistics.pstdev(pnls) if n > 1 else 0
    t = (statistics.mean(pnls) / sd) * (n ** 0.5) if sd > 0 else None
    return dict(n=n, roi=roi, t=t, hit=wins / dec * 100 if dec else 0)


results = []
for name, fn in SIGNALS:
    for book in LEGAL_BOOKS:
        for lg in LEAGUES:
            r = evaluate(fn, book, lg, search)
            if r is None or r["n"] < MIN_N:
                continue
            h = evaluate(fn, book, lg, hold)
            results.append(dict(name=name, book=book, lg=lg or "todas", s=r, h=h))

results.sort(key=lambda x: -x["s"]["roi"])
print(f"Combinaciones con n>={MIN_N} en busqueda: {len(results)}")
print(f"\nTOP 15 POR ROI EN BUSQUEDA (2025-26) -- ejecucion al CIERRE real:")
print(f"{'señal':<46} {'casa':<8} {'liga':<11} | {'n':>4} {'hit%':>5} {'ROI%':>7} {'t':>5} | {'n24':>4} {'ROI24%':>7} {'t24':>5}")
for x in results[:15]:
    s, h = x["s"], x["h"]
    t_s = f"{s['t']:.2f}" if s["t"] is not None else "-"
    if h is None:
        h_str = f"{'--':>4} {'--':>7} {'--':>5}"
    else:
        t_h = f"{h['t']:.2f}" if h["t"] is not None else "-"
        h_str = f"{h['n']:>4} {h['roi']:>+7.1f} {t_h:>5}"
    print(f"{x['name']:<46} {x['book']:<8} {x['lg']:<11} | {s['n']:>4} {s['hit']:>5.1f} {s['roi']:>+7.1f} {t_s:>5} | {h_str}")

print("\nROBUSTOS con cierre real (positivo y t>=1.5 en AMBAS temporadas, n24>=20):")
found = False
for x in results:
    s, h = x["s"], x["h"]
    if h is None or h["n"] < 20:
        continue
    if s["roi"] > 0 and h["roi"] > 0 and s["t"] and h["t"] and s["t"] >= 1.5 and h["t"] >= 1.5:
        found = True
        print(f"  {x['name']} @ {x['book']} [{x['lg']}]: "
              f"25-26 n={s['n']} ROI{s['roi']:+.1f}% t={s['t']:.2f} | "
              f"24-25 n={h['n']} ROI{h['roi']:+.1f}% t={h['t']:.2f}")
if not found:
    print("  (ninguno -- con precios reales de cierre, el espejismo desaparece)")

# la teoria original del usuario, explicitamente, al cierre de Bet365
print("\nTeoria original al CIERRE de Bet365 (under si cierre - suma de medias >= umbral):")
for thr in (6, 8, 10, 12):
    fn = lambda s, bk, thr=thr: "U" if (bk["L"] - s["sum_avg"]) >= thr else None
    a = evaluate(fn, "Bet365", None, search)
    b = evaluate(fn, "Bet365", None, hold)
    fmt = lambda r: "sin apuestas" if r is None else f"n={r['n']} hit={r['hit']:.0f}% ROI={r['roi']:+.1f}% t={(r['t'] or 0):.2f}"
    print(f"  umbral {thr:>2}: 25-26 {fmt(a)} | 24-25 {fmt(b)}")
