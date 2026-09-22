"""¿Que ROI daria el sistema de linea alta, y se puede ejecutar de verdad?

Distingue DOS numeros que no son lo mismo:

  A) ROI en la ventana de busqueda -- inflado por construccion. Es el
     numero que sale de la misma ventana donde encontre la regla, asi que
     incluye toda la suerte que me llevo a fijarme en ella. No es una
     prevision.
  B) ROI implicado por el MECANISMO -- se estima la ventaja a partir de la
     pendiente (ajustada con todos los partidos, no solo la franja
     ganadora) y se traduce a probabilidad de acierto y a ROI con las
     cuotas reales. Es mucho mas honesto porque no depende de que la franja
     >=165 haya tenido suerte.

Y despues lo que decide si esto es un negocio o un ejercicio: volumen,
cobertura por casa, y como se comporta la banca (rachas y drawdown).
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball import config, db
from bball.backtest.replay import load_games

BOOKS = ("Bet365", "Betway", "BWin")
UMBRAL = 165.0

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds "
        "WHERE market = ? AND snapshot = 'kickoff'", (config.TOTALS_MARKET_KEY,)
    ).fetchall()

kick = defaultdict(dict)
for r in rows:
    kick[r["event_id"]][r["book"]] = r

m, cobertura = [], defaultdict(int)
for g in sorted(games, key=lambda x: x.time_ts):
    if "NCAA" not in (g.league_name or ""):
        continue
    d = kick.get(g.event_id, {})
    p = next((d[b] for b in BOOKS if b in d), None)
    if not p or not p["over_odds"] or not p["under_odds"]:
        continue
    if p["over_odds"] <= 1 or p["under_odds"] <= 1:
        continue
    fila = dict(date=g.date, final=g.total, L=p["line"], un=p["under_odds"],
                ov=p["over_odds"], libro=next(b for b in BOOKS if b in d))
    m.append(fila)
    if p["line"] >= UMBRAL:
        for b in BOOKS:
            if b in d:
                cobertura[b] += 1
        cobertura["__total__"] += 1

sel = [x for x in m if x["L"] >= UMBRAL]
print(f"NCAAB apostable al cierre: {len(m)}   con linea >= {UMBRAL:.0f}: {len(sel)}")
dias = len({x["date"] for x in m})
print(f"dias de calendario cubiertos: {dias}   ->  {len(sel)/dias:.1f} picks/dia\n")

# ---------- A) ROI en la ventana de busqueda (inflado) ----------
pnl = [0.0 if x["final"] == x["L"] else (x["un"] - 1 if x["final"] < x["L"] else -1.0)
       for x in sel]
dec = [x for x in sel if x["final"] != x["L"]]
ok = sum(1 for x in dec if x["final"] < x["L"])
sd = statistics.pstdev(pnl)
roi_a = sum(pnl) / len(pnl) * 100
print("A) ROI EN LA VENTANA DE BUSQUEDA (inflado -- NO es una prevision)")
print(f"   n={len(pnl)}  acierto={ok/len(dec)*100:.1f}%  ROI={roi_a:+.1f}%  "
      f"t={statistics.mean(pnl)/sd*len(pnl)**0.5:.2f}  beneficio={sum(pnl):+.1f}u")
print(f"   cuota media: {statistics.mean(x['un'] for x in sel):.2f}\n")

# ---------- B) ROI implicado por el mecanismo ----------
xs = [x["L"] for x in m]
ys = [x["final"] - x["L"] for x in m]
mx, my = statistics.mean(xs), statistics.mean(ys)
sxx = sum((a - mx) ** 2 for a in xs)
b = sum((a - mx) * (c - my) for a, c in zip(xs, ys)) / sxx
a0 = my - b * mx
resid = [c - (a0 + b * a) for a, c in zip(xs, ys)]
sr = statistics.pstdev(resid)

def p_under(L):
    """P(final < L) segun el modelo: la desviacion esperada a esa linea,
    con la dispersion real de los residuos."""
    mu = a0 + b * L
    z = -mu / sr
    return 0.5 * (1 + __import__("math").erf(z / 2 ** 0.5))

print("B) ROI IMPLICADO POR EL MECANISMO (la pendiente, no la franja ganadora)")
print(f"   pendiente={b:+.4f}  dispersion de residuos={sr:.1f} puntos")
print(f"{'linea':>7} {'desv. esperada':>15} {'P(under)':>10} {'cuota real':>11} {'ROI esperado':>13}")
for L in (160, 165, 170, 175, 180):
    sub = [x for x in m if abs(x["L"] - L) <= 2.5]
    if len(sub) < 10:
        continue
    q = statistics.mean(x["un"] for x in sub)
    p = p_under(L)
    print(f"{L:>7} {a0 + b*L:>+14.2f} {p*100:>9.1f}% {q:>11.2f} {(p*q-1)*100:>+12.1f}%")

pm = statistics.mean(p_under(x["L"]) for x in sel)
qm = statistics.mean(x["un"] for x in sel)
print(f"\n   Media sobre las {len(sel)} apuestas reales: P(under)={pm*100:.1f}%, "
      f"cuota={qm:.2f}  ->  ROI esperado = {(pm*qm-1)*100:+.1f}%")
print(f"   (frente al {roi_a:+.1f}% de la ventana de busqueda: la diferencia es la suerte)")

# ---------- C) Ejecutabilidad ----------
print(f"\nC) ¿SE PUEDE EJECUTAR? cobertura por casa en los {cobertura['__total__']} partidos con linea alta")
for bk in BOOKS:
    print(f"   {bk:<8} cotiza {cobertura[bk]:>4} de {cobertura['__total__']} "
          f"({cobertura[bk]/cobertura['__total__']*100:.0f}%)")
usados = defaultdict(int)
for x in sel:
    usados[x["libro"]] += 1
print("   casa efectivamente usada (primera disponible):",
      ", ".join(f"{k} {v}" for k, v in sorted(usados.items(), key=lambda kv: -kv[1])))

# ---------- D) Comportamiento de la banca ----------
print("\nD) COMPORTAMIENTO DE LA BANCA (con el ROI de busqueda, el optimista)")
peor, actual, eq, pico, dd = 0, 0, 0.0, 0.0, 0.0
for x in sel:
    r = 0.0 if x["final"] == x["L"] else (x["un"] - 1 if x["final"] < x["L"] else -1.0)
    actual = 0 if r >= 0 else actual + 1
    peor = max(peor, actual)
    eq += r
    pico = max(pico, eq)
    dd = max(dd, pico - eq)
print(f"   peor racha de derrotas seguidas: {peor}")
print(f"   maximo drawdown: {dd:.1f}u sobre un beneficio final de {eq:+.1f}u")
print(f"   con 1u = 10 EUR: beneficio {eq*10:+.0f} EUR, hay que aguantar "
      f"-{dd*10:.0f} EUR de bajon")

# ---------- E) ¿Cuanto tiempo para saber si funciona? ----------
print("\nE) ¿CUANTO TARDARIA EN VERSE? (apuestas para t=2 segun el ROI real)")
import math
for roi in (roi_a/100, (pm*qm-1), 0.03):
    if roi <= 0:
        continue
    p = (1 + roi) / qm
    sdp = math.sqrt(p*(qm-1-roi)**2 + (1-p)*(1+roi)**2)
    n = (2*sdp/roi)**2
    print(f"   si el ROI real fuera {roi*100:+.1f}%: {n:>6.0f} apuestas "
          f"= {n/(len(sel)/dias):>5.0f} dias de temporada")
