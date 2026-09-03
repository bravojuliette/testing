"""Barrido amplio pedido por el usuario: encontrar el patron (under u over,
en UNA casa legal en España: Bet365 / Betway / BWin) que maximice el ROI.

Metodo: se construyen features walk-forward (sin look-ahead) por partido y se
prueba una bateria grande de señales x lado x casa x liga. TODO se ordena por
ROI en la ventana de busqueda (temporada 2025-26) con n>=30, y cada candidato
se muestra JUNTO a su resultado en la otra temporada (2024-25) -- porque un
ROI maximo elegido entre cientos de combinaciones es casi siempre ruido si no
se sostiene fuera de la ventana donde se eligio.

OJO honestidad estadistica: a estas alturas ya hemos mirado ambas temporadas
varias veces, asi que ni siquiera la columna 'otra temporada' es una reserva
virgen. Lo que salga de aqui es un CANDIDATO a pre-registrar contra datos
futuros (2026-27), no un sistema confirmado.
"""
import statistics
import sys
from collections import defaultdict, deque

sys.path.insert(0, ".")  # correr desde la raiz del repo: python3 bball/analysis/maximizar_roi.py

from bball import db
from bball.backtest.replay import load_games

N = 10
SPLIT = "2025-10-01"          # >= SPLIT: temporada 2025-26 (busqueda). < SPLIT: 2024-25.
LEGAL_BOOKS = ["Bet365", "Betway", "BWin"]
MIN_N_SEARCH = 30

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds, snapshot FROM bball_odds "
        "WHERE market='18_3' ORDER BY event_id, book, snapshot"
    ).fetchall()

by_eb = {}
start_of = {}
for r in rows:
    key = (r["event_id"], r["book"])
    if r["snapshot"] == "end":
        by_eb[key] = r
    else:
        start_of[key] = r
        by_eb.setdefault(key, r)

odds_by_event = defaultdict(dict)
moves_by_event = defaultdict(list)
for (eid, book), r in by_eb.items():
    odds_by_event[eid][book] = r
    s = start_of.get((eid, book))
    if s is not None and r["snapshot"] == "end":
        moves_by_event[eid].append(r["line"] - s["line"])

pf = defaultdict(list)
tot = defaultdict(list)
last_ts = {}
league_lines = defaultdict(lambda: deque(maxlen=100))  # media rodante de lineas por liga
samples = []
for g in games:
    books = odds_by_event.get(g.event_id, {})
    lines_all = [r["line"] for r in books.values()]
    consensus = statistics.median(lines_all) if lines_all else None
    if books and len(pf[g.home_key]) >= N and len(pf[g.away_key]) >= N and consensus is not None:
        sum_avg = sum(pf[g.home_key][-N:]) / N + sum(pf[g.away_key][-N:]) / N
        max_tot = max(sum(tot[g.home_key][-N:]) / N, sum(tot[g.away_key][-N:]) / N)
        pin = books.get("PinnacleSports")
        moves = moves_by_event.get(g.event_id, [])
        rest_h = (g.time_ts - last_ts[g.home_key]) / 86400 if g.home_key in last_ts else None
        rest_a = (g.time_ts - last_ts[g.away_key]) / 86400 if g.away_key in last_ts else None
        ll = league_lines[g.league_name]
        s = dict(
            date=g.date, league=g.league_name, final=g.total,
            sum_avg=sum_avg, max_tot=max_tot, gap=max_tot - sum_avg,
            consensus=consensus, pin_line=pin["line"] if pin else None,
            med_move=statistics.median(moves) if moves else None,
            lg_avg_line=(sum(ll) / len(ll)) if len(ll) >= 30 else None,
            rest_min=min(x for x in (rest_h, rest_a) if x is not None) if (rest_h or rest_a) else None,
        )
        for b in LEGAL_BOOKS:
            r = books.get(b)
            st = start_of.get((g.event_id, b))
            s[b] = None if r is None else dict(
                L=r["line"], under=r["under_odds"], over=r["over_odds"],
                move=(r["line"] - st["line"]) if (st and r["snapshot"] == "end") else None,
            )
        samples.append(s)
    pf[g.home_key].append(g.home_score)
    pf[g.away_key].append(g.away_score)
    tot[g.home_key].append(g.total)
    tot[g.away_key].append(g.total)
    last_ts[g.home_key] = g.time_ts
    last_ts[g.away_key] = g.time_ts
    if consensus is not None:
        league_lines[g.league_name].append(consensus)

search = [s for s in samples if s["date"] >= SPLIT]
hold = [s for s in samples if s["date"] < SPLIT]
print(f"Partidos evaluables: {len(samples)}  (2025-26 busqueda: {len(search)} / 2024-25: {len(hold)})\n")

# ------------- bateria de señales (side, condicion sobre s y la casa b) -------------
# cada señal devuelve 'U'/'O'/None dadas las features y los datos de la casa
SIGNALS = []

def sig(name, fn):
    SIGNALS.append((name, fn))

for thr in (6, 8, 10, 12):
    sig(f"U: linea-sum_avg>={thr}", lambda s, bk, thr=thr: "U" if (bk["L"] - s["sum_avg"]) >= thr else None)
for thr in (4, 6, 8):
    sig(f"O: sum_avg-linea>={thr}", lambda s, bk, thr=thr: "O" if (s["sum_avg"] - bk["L"]) >= thr else None)
for thr in (8, 10, 12):
    sig(f"U: max_tot-sum_avg>={thr}", lambda s, bk, thr=thr: "U" if s["gap"] >= thr else None)
    sig(f"O: max_tot-sum_avg>={thr}", lambda s, bk, thr=thr: "O" if s["gap"] >= thr else None)
for thr in (1.5, 2, 3):
    sig(f"U: linea>=Pinnacle+{thr}", lambda s, bk, thr=thr: "U" if s["pin_line"] is not None and (bk["L"] - s["pin_line"]) >= thr else None)
    sig(f"O: linea<=Pinnacle-{thr}", lambda s, bk, thr=thr: "O" if s["pin_line"] is not None and (s["pin_line"] - bk["L"]) >= thr else None)
    sig(f"U: linea>=consenso+{thr}", lambda s, bk, thr=thr: "U" if (bk["L"] - s["consensus"]) >= thr else None)
    sig(f"O: linea<=consenso-{thr}", lambda s, bk, thr=thr: "O" if (s["consensus"] - bk["L"]) >= thr else None)
for thr in (1, 1.5, 2):
    sig(f"U: mercado bajo linea>={thr}", lambda s, bk, thr=thr: "U" if s["med_move"] is not None and s["med_move"] <= -thr else None)
    sig(f"O: mercado subio linea>={thr}", lambda s, bk, thr=thr: "O" if s["med_move"] is not None and s["med_move"] >= thr else None)
for thr in (1, 2):
    sig(f"U: la casa bajo su linea>={thr}", lambda s, bk, thr=thr: "U" if bk["move"] is not None and bk["move"] <= -thr else None)
    sig(f"O: la casa subio su linea>={thr}", lambda s, bk, thr=thr: "O" if bk["move"] is not None and bk["move"] >= thr else None)
for thr in (5, 10):
    sig(f"U: linea alta vs liga (+{thr})", lambda s, bk, thr=thr: "U" if s["lg_avg_line"] is not None and (bk["L"] - s["lg_avg_line"]) >= thr else None)
    sig(f"O: linea baja vs liga (-{thr})", lambda s, bk, thr=thr: "O" if s["lg_avg_line"] is not None and (s["lg_avg_line"] - bk["L"]) >= thr else None)
sig("U: back-to-back", lambda s, bk: "U" if s["rest_min"] is not None and s["rest_min"] <= 1.2 else None)
for d in (0.08, 0.15):
    sig(f"U: under cargada (u<o-{d})", lambda s, bk, d=d: "U" if bk["under"] and bk["over"] and (bk["over"] - bk["under"]) >= d else None)
    sig(f"O: over cargada (o<u-{d})", lambda s, bk, d=d: "O" if bk["under"] and bk["over"] and (bk["under"] - bk["over"]) >= d else None)
# combos: desviacion del consenso + gap de medias apuntando igual
sig("O: consenso-linea>=1.5 y sum_avg>linea", lambda s, bk: "O" if (s["consensus"] - bk["L"]) >= 1.5 and s["sum_avg"] > bk["L"] else None)
sig("U: linea-consenso>=1.5 y sum_avg<linea", lambda s, bk: "U" if (bk["L"] - s["consensus"]) >= 1.5 and s["sum_avg"] < bk["L"] else None)

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
            if r is None or r["n"] < MIN_N_SEARCH:
                continue
            h = evaluate(fn, book, lg, hold)
            results.append(dict(name=name, book=book, lg=lg or "todas", s=r, h=h))

print(f"Combinaciones probadas con n>=%d en busqueda: {len(results)}" % MIN_N_SEARCH)
print(f"(bateria total: {len(SIGNALS)} señales x {len(LEGAL_BOOKS)} casas x {len(LEAGUES)} ambitos de liga)\n")

results.sort(key=lambda x: -x["s"]["roi"])
print("TOP 20 POR ROI EN BUSQUEDA (2025-26) -- con su resultado en 2024-25 al lado:")
print(f"{'señal':<42} {'casa':<8} {'liga':<11} | {'n':>4} {'hit%':>5} {'ROI%':>7} {'t':>5} | {'n24':>4} {'ROI24%':>7} {'t24':>5}")
for x in results[:20]:
    s, h = x["s"], x["h"]
    t_s = f"{s['t']:.2f}" if s["t"] is not None else "-"
    if h is None:
        h_str = f"{'--':>4} {'--':>7} {'--':>5}"
    else:
        t_h = f"{h['t']:.2f}" if h["t"] is not None else "-"
        h_str = f"{h['n']:>4} {h['roi']:>+7.1f} {t_h:>5}"
    print(f"{x['name']:<42} {x['book']:<8} {x['lg']:<11} | {s['n']:>4} {s['hit']:>5.1f} {s['roi']:>+7.1f} {t_s:>5} | {h_str}")

print("\nROBUSTOS: positivos con t>=1.5 en AMBAS temporadas (el filtro que importa):")
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
    print("  (ninguno)")
