"""Extension del usuario: ¿cambia la pelicula si AMBOS equipos vienen de
una racha de 1, 2 o 3 partidos under (o over)?

Idea: una racha de unders en ambos podria delatar algo estructural (ritmo
bajo, defensas apretadas) que la media de puntos anotados no captura. Se
prueba sola y combinada con el filtro anterior (media - linea >= 10, "la
casa sabe algo").

Racha U/O de un equipo: partidos consecutivos suyos, hacia atras, en los
que el total quedo por debajo (U) o por encima (O) de la linea de cierre
DE AQUEL partido. Solo cuenta con partidos anteriores -- sin look-ahead.

Ejecucion: linea y cuota de cierre de casa legal; peldaños profundos con
la escalera de Bwin (linea+2 -> 1.72, +4 -> 1.60, +6 -> 1.50).
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
    """(signo, longitud) de la racha U/O al final del historial.
    signo -1 = unders, +1 = overs, 0 = sin historial."""
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
uo_hist = defaultdict(list)     # por equipo: -1 under / +1 over de sus partidos
muestras = []
for g in sorted(games, key=lambda x: x.time_ts):
    d = tot.get(g.event_id, {})
    pick = next((d[b] for b in BOOKS if b in d), None)
    if pick and len(pf[g.home_key]) >= N and len(pf[g.away_key]) >= N:
        linea, o_over, o_under = pick
        if o_over and o_under and o_over > 1 and o_under > 1:
            sum_avg = sum(pf[g.home_key][-N:]) / N + sum(pf[g.away_key][-N:]) / N
            sh, kh = racha(uo_hist[g.home_key])
            sa, ka = racha(uo_hist[g.away_key])
            muestras.append(dict(
                date=g.date, lg=g.league_name, final=g.total, linea=linea,
                o_over=o_over, o_under=o_under, dif=linea - sum_avg,
                sig_h=sh, len_h=kh, sig_a=sa, len_a=ka,
            ))
    pf[g.home_key].append(g.home_score)
    pf[g.away_key].append(g.away_score)
    if pick:
        ln = pick[0]
        if g.total != ln:
            marca = -1 if g.total < ln else 1
            uo_hist[g.home_key].append(marca)
            uo_hist[g.away_key].append(marca)

print(f"Partidos evaluables: {len(muestras)}\n")

def ev(sub, k, cuota, lado="U"):
    pnls, ok, dec = [], 0, 0
    for m in sub:
        obj = m["linea"] + k
        cu = cuota if cuota else (m["o_under"] if lado == "U" else m["o_over"])
        if m["final"] == obj:
            pnls.append(0.0); continue
        gano = m["final"] < obj if lado == "U" else m["final"] > obj
        pnls.append(cu - 1 if gano else -1.0)
        dec += 1; ok += gano
    n = len(pnls)
    if n == 0:
        return None
    sd = statistics.pstdev(pnls) if n > 1 else 0
    return dict(n=n, roi=sum(pnls)/n*100, hit=ok/dec*100 if dec else 0,
                t=(statistics.mean(pnls)/sd)*(n**0.5) if sd > 0 else 0)

def ambos(m, signo, minlen):
    return (m["sig_h"] == signo and m["len_h"] >= minlen
            and m["sig_a"] == signo and m["len_a"] >= minlen)

print("PASO 1 -- La racha SOLA (sin el filtro de la linea), under a la linea principal:\n")
print(f"{'condicion':<44} {'n':>5} {'acierto':>9} {'ROI%':>8} {'t':>6}")
for minlen in (1, 2, 3):
    for signo, nom, lado in ((-1, "unders", "U"), (1, "overs", "U"), (1, "overs", "O")):
        sub = [m for m in muestras if ambos(m, signo, minlen)]
        s = ev(sub, 0, None, lado)
        if s and s["n"] >= 30:
            et = f"ambos vienen de >={minlen} {nom} -> {'UNDER' if lado=='U' else 'OVER'}"
            print(f"{et:<44} {s['n']:>5} {s['hit']:>8.1f}% {s['roi']:>+8.1f} {s['t']:>6.2f}")
print()

print("PASO 2 -- Racha de unders COMBINADA con 'la casa sabe algo' (media-linea>=10):\n")
for minlen in (1, 2, 3):
    sub = [m for m in muestras if ambos(m, -1, minlen) and -m["dif"] >= 10]
    if len(sub) < 15:
        print(f"  ambos >={minlen} unders + media-linea>=10:  n={len(sub)} -- muestra insuficiente\n")
        continue
    print(f"  ambos >={minlen} unders + media-linea>=10  (n={len(sub)})")
    print(f"  {'peldaño':>8} {'cuota':>6} {'necesita':>9} {'acierto':>9} {'ROI%':>8} {'t':>6}")
    for k, c in ESCALERA:
        s = ev(sub, k, c)
        if s:
            print(f"  {k:>+8} {c:>6.2f} {1/c*100:>8.1f}% {s['hit']:>8.1f}% {s['roi']:>+8.1f} {s['t']:>6.2f}")
    print()

print("=" * 74)
print("PASO 3 -- ¿Aporta la racha algo? Acierto con y sin el filtro de racha,")
print("dentro del grupo 'media-linea>=10':\n")
base = [m for m in muestras if -m["dif"] >= 10]
print(f"{'peldaño':>8} {'necesita':>9} {'solo linea':>12} {'+1 under':>10} {'+2 unders':>11}")
for k, c in ESCALERA:
    a = ev(base, k, c)
    b1 = ev([m for m in base if ambos(m, -1, 1)], k, c)
    b2 = ev([m for m in base if ambos(m, -1, 2)], k, c)
    f = lambda s: f"{s['hit']:.1f}%" if s and s["n"] >= 15 else "n<15"
    print(f"{k:>+8} {1/c*100:>8.1f}% {a['hit']:>11.1f}% {f(b1):>10} {f(b2):>11}")

print("\nPASO 4 -- Tamaños de muestra (lo que limita todo esto):")
for minlen in (1, 2, 3):
    n_solo = len([m for m in muestras if ambos(m, -1, minlen)])
    n_comb = len([m for m in muestras if ambos(m, -1, minlen) and -m["dif"] >= 10])
    print(f"  ambos >={minlen} unders: {n_solo:>5} partidos   |   combinado con la linea: {n_comb:>4}")
