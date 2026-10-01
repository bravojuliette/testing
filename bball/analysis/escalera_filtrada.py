"""Refinamiento del usuario: en las situaciones donde la linea esta MUY por
debajo de la suma de medias ("la casa sabe que sera bajo"), no apostar el
under a la linea principal, sino MAS ARRIBA -- un under mas profundo, mas
seguro, a cuota menor.

Es un test nuevo: la calibracion de la escalera se midio antes sobre TODOS
los partidos, nunca filtrando a esta situacion concreta.

Escalera de Bwin (dada por el usuario):
    linea -2 -> 2.05    linea +0 -> 1.87
    linea +2 -> 1.72    linea +4 -> 1.60    linea +6 -> 1.50

La pregunta: ¿el filtro "media - linea >= X" hace que el under profundo
gane mas de lo que su cuota implica? Se compara SIEMPRE contra el mismo
peldaño sin filtrar, que es el control que decide si el filtro aporta algo.
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
ESCALERA = [(-2, 2.05), (0, 1.87), (2, 1.72), (4, 1.60), (6, 1.50)]

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line FROM bball_odds WHERE market = ? AND snapshot = 'kickoff'",
        (config.TOTALS_MARKET_KEY,)
    ).fetchall()

tot = defaultdict(dict)
for r in rows:
    tot[r["event_id"]][r["book"]] = r["line"]

pf = defaultdict(list)
muestras = []
for g in sorted(games, key=lambda x: x.time_ts):
    d = tot.get(g.event_id, {})
    linea = next((d[b] for b in BOOKS if b in d), None)
    if linea is not None and len(pf[g.home_key]) >= N and len(pf[g.away_key]) >= N:
        sum_avg = sum(pf[g.home_key][-N:]) / N + sum(pf[g.away_key][-N:]) / N
        muestras.append(dict(date=g.date, lg=g.league_name, final=g.total,
                             linea=linea, dif=linea - sum_avg))
    pf[g.home_key].append(g.home_score)
    pf[g.away_key].append(g.away_score)

print(f"Partidos con linea de cierre e historial: {len(muestras)}\n")

def peldaño(sub, k, cuota):
    """Apostar UNDER en linea+k a la cuota dada. Devuelve n, acierto, ROI, t."""
    pnls, ok, dec = [], 0, 0
    for m in sub:
        obj = m["linea"] + k
        if m["final"] == obj:
            pnls.append(0.0)
            continue
        gano = m["final"] < obj
        pnls.append(cuota - 1 if gano else -1.0)
        dec += 1
        ok += gano
    n = len(pnls)
    if n == 0:
        return None
    sd = statistics.pstdev(pnls) if n > 1 else 0
    return dict(n=n, roi=sum(pnls) / n * 100, hit=ok / dec * 100 if dec else 0,
                t=(statistics.mean(pnls) / sd) * (n ** 0.5) if sd > 0 else 0,
                imp=1 / cuota * 100)

print("PASO 1 -- La escalera SIN filtrar (control). ¿Hay algun peldaño barato?\n")
print(f"{'peldaño':>8} {'cuota':>6} {'necesita':>9} {'acierto':>9} {'margen':>8} {'ROI%':>8} {'t':>6}")
for k, c in ESCALERA:
    s = peldaño(muestras, k, c)
    print(f"{k:>+8} {c:>6.2f} {s['imp']:>8.1f}% {s['hit']:>8.1f}% "
          f"{s['hit']-s['imp']:>+7.1f} {s['roi']:>+8.1f} {s['t']:>6.2f}")

print("\nPASO 2 -- La misma escalera SOLO en las situaciones de tu teoria")
print("(media - linea >= umbral: la casa ha bajado la linea porque sabe algo)\n")
for umbral in (6, 8, 10, 12):
    sub = [m for m in muestras if -m["dif"] >= umbral]
    if len(sub) < 40:
        continue
    print(f"  media - linea >= {umbral}  (n={len(sub)})")
    print(f"  {'peldaño':>8} {'cuota':>6} {'necesita':>9} {'acierto':>9} {'margen':>8} {'ROI%':>8} {'t':>6}")
    for k, c in ESCALERA:
        s = peldaño(sub, k, c)
        if s:
            marca = "  <--" if s["roi"] > 0 else ""
            print(f"  {k:>+8} {c:>6.2f} {s['imp']:>8.1f}% {s['hit']:>8.1f}% "
                  f"{s['hit']-s['imp']:>+7.1f} {s['roi']:>+8.1f} {s['t']:>6.2f}{marca}")
    print()

print("=" * 78)
print("PASO 3 -- ¿Aporta el filtro? Acierto en cada peldaño, filtrado vs sin filtrar.")
print("Si el filtro sirviera, la columna 'filtrado' deberia superar a 'todos'.\n")
sub10 = [m for m in muestras if -m["dif"] >= 10]
print(f"{'peldaño':>8} {'necesita':>9} {'todos':>9} {'filtrado>=10':>14} {'diferencia':>12}")
for k, c in ESCALERA:
    a = peldaño(muestras, k, c)
    b = peldaño(sub10, k, c)
    if a and b:
        print(f"{k:>+8} {a['imp']:>8.1f}% {a['hit']:>8.1f}% {b['hit']:>13.1f}% {b['hit']-a['hit']:>+11.1f}")

print("\nPASO 4 -- El peldaño mas prometedor, partido en busqueda y reserva:\n")
mejor = None
for umbral in (8, 10, 12):
    sub = [m for m in muestras if -m["dif"] >= umbral]
    for k, c in ESCALERA:
        s = peldaño(sub, k, c)
        if s and s["n"] >= 60 and (mejor is None or s["roi"] > mejor[0]["roi"]):
            mejor = (s, umbral, k, c)
if mejor:
    s, umbral, k, c = mejor
    print(f"  Mejor: under en linea{k:+d} a {c}, con media-linea>={umbral}")
    print(f"  {'corte':<24} {'n':>5} {'acierto':>9} {'ROI%':>8} {'t':>6}")
    sub = [m for m in muestras if -m["dif"] >= umbral]
    for et, f in (("TODO", lambda m: True),
                  ("2025-26", lambda m: m["date"] >= SPLIT),
                  ("anterior", lambda m: m["date"] < SPLIT)):
        ss = peldaño([m for m in sub if f(m)], k, c)
        if ss and ss["n"] >= 15:
            print(f"  {et:<24} {ss['n']:>5} {ss['hit']:>8.1f}% {ss['roi']:>+8.1f} {ss['t']:>6.2f}")
