"""Teoria del usuario: si la linea de la casa se separa mucho de la suma de
medias de los dos equipos, la casa SABE ALGO -- hay que seguirla, no
apostarle en contra.

Es distinto de lo probado antes. Antes se apostaba EN CONTRA de la
desviacion (linea alta respecto a la media -> under, buscando que la linea
estuviera inflada). Aqui la logica es la opuesta: la desviacion es
informacion, no error.

Se prueban las tres lecturas posibles de "a 10 puntos de diferencia":

  A) |linea - sum_avg| >= 10  -> UNDER   (diferencia en cualquier direccion)
  B) sum_avg - linea >= 10    -> UNDER   (linea POR DEBAJO: la casa la bajo
                                          porque sabe que sera un partido
                                          bajo -> seguirla) <- la lectura
                                          coherente con "la casa sabe algo"
  C) linea - sum_avg >= 10    -> UNDER   (linea POR ENCIMA; es lo que ya se
                                          probo, se incluye de referencia)

Y, como control de la logica "seguir a la casa", tambien el lado espejo:
  D) linea - sum_avg >= 10    -> OVER    (la casa la subio porque sabe que
                                          sera alto -> seguirla)

Ejecucion realista: linea y cuota de CIERRE (snapshot kickoff) de una casa
legal en España. Sin look-ahead: las medias usan solo partidos anteriores.
Disciplina busqueda/reserva por temporada.
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

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds "
        "WHERE market = ? AND snapshot = 'kickoff'", (config.TOTALS_MARKET_KEY,)
    ).fetchall()

tot = defaultdict(dict)
for r in rows:
    tot[r["event_id"]][r["book"]] = (r["line"], r["over_odds"], r["under_odds"])

pf = defaultdict(list)
muestras = []
for g in sorted(games, key=lambda x: x.time_ts):
    d = tot.get(g.event_id, {})
    pick = next((d[b] for b in BOOKS if b in d), None)
    if pick and len(pf[g.home_key]) >= N and len(pf[g.away_key]) >= N:
        linea, o_over, o_under = pick
        if o_over and o_under and o_over > 1 and o_under > 1:
            sum_avg = sum(pf[g.home_key][-N:]) / N + sum(pf[g.away_key][-N:]) / N
            muestras.append(dict(
                date=g.date, lg=g.league_name, final=g.total, linea=linea,
                o_over=o_over, o_under=o_under, sum_avg=sum_avg,
                dif=linea - sum_avg,          # >0 linea por ENCIMA de la media
            ))
    pf[g.home_key].append(g.home_score)
    pf[g.away_key].append(g.away_score)

print(f"Partidos con linea de cierre e historial N={N}: {len(muestras)}\n")

def stat(sub, lado):
    pnls, aciertos, dec = [], 0, 0
    for m in sub:
        odds = m["o_under"] if lado == "U" else m["o_over"]
        if m["final"] == m["linea"]:
            pnls.append(0.0)
            continue
        gano = m["final"] < m["linea"] if lado == "U" else m["final"] > m["linea"]
        pnls.append(odds - 1 if gano else -1.0)
        dec += 1
        aciertos += gano
    n = len(pnls)
    if n == 0:
        return None
    sd = statistics.pstdev(pnls) if n > 1 else 0
    return dict(n=n, roi=sum(pnls) / n * 100,
                t=(statistics.mean(pnls) / sd) * (n ** 0.5) if sd > 0 else 0,
                hit=aciertos / dec * 100 if dec else 0)

VARIANTES = [
    ("A) |linea - media| >= {u}  -> UNDER", "U", lambda m, u: abs(m["dif"]) >= u),
    ("B) media - linea >= {u}    -> UNDER", "U", lambda m, u: -m["dif"] >= u),
    ("C) linea - media >= {u}    -> UNDER", "U", lambda m, u: m["dif"] >= u),
    ("D) linea - media >= {u}    -> OVER ", "O", lambda m, u: m["dif"] >= u),
    ("E) media - linea >= {u}    -> OVER ", "O", lambda m, u: -m["dif"] >= u),
]

for umbral in (6, 8, 10, 12):
    print(f"--- umbral {umbral} puntos ---")
    print(f"{'variante':<40} {'n':>5} {'acierto':>8} {'ROI%':>8} {'t':>6}")
    for etiqueta, lado, cond in VARIANTES:
        sub = [m for m in muestras if cond(m, umbral)]
        s = stat(sub, lado)
        if s and s["n"] >= 25:
            print(f"{etiqueta.format(u=umbral):<40} {s['n']:>5} {s['hit']:>7.1f}% {s['roi']:>+8.1f} {s['t']:>6.2f}")
    print()

print("=" * 76)
print("La variante B es la lectura coherente con 'la casa sabe algo'.")
print("Desglose de B con umbral 10, por temporada y liga:\n")
sub_b = [m for m in muestras if -m["dif"] >= 10]
print(f"{'corte':<28} {'n':>5} {'acierto':>8} {'ROI%':>8} {'t':>6}")
for etiqueta, filtro in (
    ("TODO", lambda m: True),
    ("busqueda (2025-26)", lambda m: m["date"] >= SPLIT),
    ("reserva (anterior)", lambda m: m["date"] < SPLIT),
    ("  NBA", lambda m: m["lg"] == "NBA"),
    ("  WNBA", lambda m: m["lg"] == "WNBA"),
    ("  Euroleague", lambda m: m["lg"] == "Euroleague"),
):
    s = stat([m for m in sub_b if filtro(m)], "U")
    if s and s["n"] >= 15:
        print(f"{etiqueta:<28} {s['n']:>5} {s['hit']:>7.1f}% {s['roi']:>+8.1f} {s['t']:>6.2f}")

print("\nY el dato que decide si 'la casa sabe algo': cuando la linea se aleja")
print("de la media, ¿hacia donde se va el total real?\n")
print(f"{'grupo':<34} {'n':>5} {'media(final - linea)':>22} {'% under':>9}")
for etiqueta, filtro in (
    ("linea MUY por debajo (dif<=-10)", lambda m: m["dif"] <= -10),
    ("linea por debajo (-10<dif<=-4)", lambda m: -10 < m["dif"] <= -4),
    ("linea ~ media (|dif|<4)", lambda m: abs(m["dif"]) < 4),
    ("linea por encima (4<=dif<10)", lambda m: 4 <= m["dif"] < 10),
    ("linea MUY por encima (dif>=10)", lambda m: m["dif"] >= 10),
):
    sub = [m for m in muestras if filtro(m)]
    if len(sub) < 25:
        continue
    dec = [m for m in sub if m["final"] != m["linea"]]
    pu = sum(1 for m in dec if m["final"] < m["linea"]) / len(dec) * 100 if dec else 0
    print(f"{etiqueta:<34} {len(sub):>5} {statistics.mean(m['final'] - m['linea'] for m in sub):>+21.2f} {pu:>8.1f}%")
