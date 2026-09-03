"""Variante del usuario: en vez de rachas de UNDER, rachas de OVER en ambos
equipos -> apostar UNDER (la direccion de reversion que apuntaron los datos).

Se prueba a fondo: sola y combinada con el filtro de linea, en todos los
peldaños de la escalera, y partida por periodo para ver si se sostiene --
que es donde han muerto todas las celdas llamativas de esta sesion.
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")  # correr desde la raiz del repo

from bball import config, db
from bball.backtest.replay import load_games

N = 10
SPLIT = "2025-10-01"
BOOKS = ("Bet365", "Betway", "BWin")
ESCALERA = [(0, 1.87), (2, 1.72), (4, 1.60), (6, 1.50)]

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds "
        "WHERE market = ? AND snapshot = 'kickoff'", (config.TOTALS_MARKET_KEY,)
    ).fetchall()

tot = defaultdict(dict)
for r in rows:
    tot[r["event_id"]][r["book"]] = (r["line"], r["over_odds"], r["under_odds"])

def racha(hist):
    if not hist:
        return 0, 0
    s = hist[-1]
    k = 0
    for x in reversed(hist):
        if x == s:
            k += 1
        else:
            break
    return s, k

pf = defaultdict(list)
uo = defaultdict(list)
muestras = []
for g in sorted(games, key=lambda x: x.time_ts):
    d = tot.get(g.event_id, {})
    pick = next((d[b] for b in BOOKS if b in d), None)
    if pick and len(pf[g.home_key]) >= N and len(pf[g.away_key]) >= N:
        linea, o_over, o_under = pick
        if o_over and o_under and o_over > 1 and o_under > 1:
            sum_avg = sum(pf[g.home_key][-N:]) / N + sum(pf[g.away_key][-N:]) / N
            sh, kh = racha(uo[g.home_key])
            sa, ka = racha(uo[g.away_key])
            muestras.append(dict(
                date=g.date, lg=g.league_name, final=g.total, linea=linea,
                o_over=o_over, o_under=o_under, dif=linea - sum_avg,
                sig_h=sh, len_h=kh, sig_a=sa, len_a=ka,
            ))
    pf[g.home_key].append(g.home_score)
    pf[g.away_key].append(g.away_score)
    if pick and g.total != pick[0]:
        marca = -1 if g.total < pick[0] else 1
        uo[g.home_key].append(marca)
        uo[g.away_key].append(marca)

def ev(sub, k, cuota):
    pnls, ok, dec = [], 0, 0
    for m in sub:
        obj = m["linea"] + k
        cu = cuota if cuota else m["o_under"]
        if m["final"] == obj:
            pnls.append(0.0); continue
        gano = m["final"] < obj
        pnls.append(cu - 1 if gano else -1.0)
        dec += 1; ok += gano
    n = len(pnls)
    if n == 0:
        return None
    sd = statistics.pstdev(pnls) if n > 1 else 0
    return dict(n=n, roi=sum(pnls)/n*100, hit=ok/dec*100 if dec else 0,
                t=(statistics.mean(pnls)/sd)*(n**0.5) if sd > 0 else 0)

def ambos_over(m, minlen):
    return (m["sig_h"] == 1 and m["len_h"] >= minlen
            and m["sig_a"] == 1 and m["len_a"] >= minlen)

print(f"Partidos evaluables: {len(muestras)}\n")
print("PASO 1 -- Ambos vienen de >=k OVERS -> UNDER, en toda la escalera:\n")
for minlen in (1, 2, 3, 4):
    sub = [m for m in muestras if ambos_over(m, minlen)]
    if len(sub) < 25:
        print(f"  ambos >={minlen} overs: n={len(sub)} -- muestra insuficiente\n")
        continue
    print(f"  ambos >={minlen} overs  (n={len(sub)})")
    print(f"  {'peldaño':>8} {'cuota':>6} {'necesita':>9} {'acierto':>9} {'ROI%':>8} {'t':>6}")
    for k, c in ESCALERA:
        s = ev(sub, k, c)
        if s:
            marca = "  <--" if s["roi"] > 0 else ""
            print(f"  {k:>+8} {c:>6.2f} {1/c*100:>8.1f}% {s['hit']:>8.1f}% {s['roi']:>+8.1f} {s['t']:>6.2f}{marca}")
    print()

print("=" * 76)
print("PASO 2 -- ESTABILIDAD: las celdas positivas, partidas por periodo y liga.")
print("(aqui es donde han muerto todas las celdas llamativas de esta sesion)\n")
for minlen in (2, 3):
    sub = [m for m in muestras if ambos_over(m, minlen)]
    if len(sub) < 25:
        continue
    for k, c in ESCALERA:
        s = ev(sub, k, c)
        if not s or s["roi"] <= 0:
            continue
        print(f"  ambos >={minlen} overs, under en linea{k:+d} a {c}  ->  TOTAL "
              f"n={s['n']} acierto={s['hit']:.1f}% ROI={s['roi']:+.1f}% t={s['t']:.2f}")
        for et, f in (("    2025-26", lambda m: m["date"] >= SPLIT),
                      ("    anterior", lambda m: m["date"] < SPLIT),
                      ("    NBA", lambda m: m["lg"] == "NBA"),
                      ("    WNBA", lambda m: m["lg"] == "WNBA"),
                      ("    Euroleague", lambda m: m["lg"] == "Euroleague")):
            ss = ev([m for m in sub if f(m)], k, c)
            if ss and ss["n"] >= 10:
                print(f"{et:<16} n={ss['n']:>4} acierto={ss['hit']:>5.1f}% ROI={ss['roi']:>+7.1f}% t={ss['t']:>5.2f}")
        print()

print("=" * 76)
print("PASO 3 -- Combinado con 'la casa sabe algo' (media - linea >= 10):\n")
for minlen in (1, 2):
    sub = [m for m in muestras if ambos_over(m, minlen) and -m["dif"] >= 10]
    if len(sub) < 15:
        print(f"  ambos >={minlen} overs + media-linea>=10: n={len(sub)} -- muestra insuficiente")
        continue
    print(f"  ambos >={minlen} overs + media-linea>=10  (n={len(sub)})")
    for k, c in ESCALERA:
        s = ev(sub, k, c)
        if s:
            print(f"    peldaño {k:+d} a {c}: acierto={s['hit']:.1f}% (necesita {1/c*100:.1f}%) ROI={s['roi']:+.1f}%")
    print()

print("PASO 4 -- Control: ¿el efecto es de la RACHA o solo de que la linea sube?")
print("Comparacion del acierto del under a la linea principal:\n")
print(f"{'grupo':<38} {'n':>5} {'acierto under':>15}")
for et, f in (("todos", lambda m: True),
              ("ambos >=1 overs", lambda m: ambos_over(m, 1)),
              ("ambos >=2 overs", lambda m: ambos_over(m, 2)),
              ("ambos >=3 overs", lambda m: ambos_over(m, 3)),
              ("ambos >=1 unders", lambda m: m["sig_h"] == -1 and m["len_h"] >= 1 and m["sig_a"] == -1 and m["len_a"] >= 1)):
    s = ev([m for m in muestras if f(m)], 0, None)
    if s and s["n"] >= 25:
        print(f"{et:<38} {s['n']:>5} {s['hit']:>14.1f}%")
