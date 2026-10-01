"""Angulos que NO se han probado nunca: en vez de features del JUEGO
(anotacion, rachas, calendario), features del MERCADO en si.

Hasta ahora todo lo probado describia a los equipos. La casa tiene esos
datos mejor que nosotros. Lo que la casa NO controla es cuanta atencion
recibe cada partido: un Wyoming-Idaho St de un martes no lo mira nadie, y
la linea la pone un modelo automatico sin que el dinero listo la corrija.

Se miden cinco cosas, todas al CIERRE real y ejecutables en una sola casa:

  1. Asimetria over/under: ¿pierde lo mismo apostar siempre over que
     siempre under? Si no, hay un sesgo del publico que la casa cobra.
  2. Atencion del mercado: numero de casas que cotizan el partido. Pocas
     casas = partido ignorado = linea potencialmente blanda.
  3. Magnitud de la linea: totales extremos (muy altos / muy bajos).
  4. Movimiento apertura -> cierre: ¿seguir el movimiento o ir contra el?
  5. Desacuerdo entre casas: dispersion de lineas al cierre. NO es
     arbitraje -- se apuesta en UNA casa; la dispersion es solo la señal.

BUSQUEDA: NCAAB noviembre 2025 - enero 2026 (ya recolectado).
RESERVA : NCAAB febrero - marzo 2026 (aun descargandose, no visto).
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball import config, db
from bball.backtest.replay import load_games

BOOKS = ("Bet365", "Betway", "BWin")   # primera disponible, en ese orden
CORTE = "2026-02-01"                    # busqueda < CORTE <= reserva

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds, snapshot FROM bball_odds "
        "WHERE market = ? AND snapshot IN ('start','kickoff')", (config.TOTALS_MARKET_KEY,)
    ).fetchall()

kick, opens = defaultdict(dict), defaultdict(dict)
for r in rows:
    (kick if r["snapshot"] == "kickoff" else opens)[r["event_id"]][r["book"]] = r

m = []
for g in games:
    if "NCAA" not in (g.league_name or ""):
        continue
    d = kick.get(g.event_id, {})
    pick = next((d[b] for b in BOOKS if b in d), None)
    if not pick or not pick["over_odds"] or not pick["under_odds"]:
        continue
    if pick["over_odds"] <= 1 or pick["under_odds"] <= 1:
        continue
    lineas = [r["line"] for r in d.values() if r["line"]]
    o = opens.get(g.event_id, {})
    movs = [d[b]["line"] - o[b]["line"] for b in d if b in o and d[b]["line"] and o[b]["line"]]
    m.append(dict(
        date=g.date, final=g.total, L=pick["line"],
        ov=pick["over_odds"], un=pick["under_odds"],
        n_casas=len(d),
        dispersion=(max(lineas) - min(lineas)) if len(lineas) > 1 else 0.0,
        mov=statistics.median(movs) if movs else None,
    ))

busq = [x for x in m if x["date"] < CORTE]
res = [x for x in m if x["date"] >= CORTE]
print(f"NCAAB apostable al cierre: {len(m)}  (busqueda {len(busq)} / reserva {len(res)})")
print(f"casas que cotizan: mediana {statistics.median([x['n_casas'] for x in m]):.0f}, "
      f"rango {min(x['n_casas'] for x in m)}-{max(x['n_casas'] for x in m)}\n")


def ev(sub, lado):
    pnl, ok, dec = [], 0, 0
    for x in sub:
        odds = x["ov"] if lado == "O" else x["un"]
        if x["final"] == x["L"]:
            pnl.append(0.0); continue
        gano = x["final"] > x["L"] if lado == "O" else x["final"] < x["L"]
        pnl.append(odds - 1 if gano else -1.0)
        dec += 1; ok += gano
    n = len(pnl)
    if n == 0:
        return None
    sd = statistics.pstdev(pnl) if n > 1 else 0
    return dict(n=n, roi=sum(pnl)/n*100, hit=ok/dec*100 if dec else 0,
                t=(statistics.mean(pnl)/sd)*(n**0.5) if sd > 0 else 0)


def fila(et, sub):
    a, b = ev(sub, "O"), ev(sub, "U")
    if not a:
        print(f"{et:<38} {'(vacio)':>10}"); return
    print(f"{et:<38} {a['n']:>5} | {a['hit']:>6.1f}% {a['roi']:>+7.1f}% {a['t']:>6.2f} "
          f"| {b['hit']:>6.1f}% {b['roi']:>+7.1f}% {b['t']:>6.2f}")


hdr = f"{'':<38} {'n':>5} | {'OVER: hit':>7} {'ROI':>8} {'t':>6} | {'UNDER: hit':>7} {'ROI':>8} {'t':>6}"

print("1. ASIMETRIA OVER/UNDER (solo busqueda, nov-ene)")
print(hdr)
fila("todo NCAAB", busq)

print("\n2. ATENCION DEL MERCADO (nº de casas que cotizan)")
print(hdr)
qs = sorted(x["n_casas"] for x in busq)
c1, c2 = qs[len(qs)//3], qs[2*len(qs)//3]
for et, f in (("pocas casas (<=%d) = ignorado" % c1, lambda x: x["n_casas"] <= c1),
              ("medio (%d-%d)" % (c1+1, c2), lambda x: c1 < x["n_casas"] <= c2),
              ("muchas casas (>%d) = mirado" % c2, lambda x: x["n_casas"] > c2)):
    fila(et, [x for x in busq if f(x)])

print("\n3. MAGNITUD DE LA LINEA")
print(hdr)
for et, f in (("linea baja (<130)", lambda x: x["L"] < 130),
              ("media (130-150)", lambda x: 130 <= x["L"] < 150),
              ("alta (150-165)", lambda x: 150 <= x["L"] < 165),
              ("muy alta (>=165)", lambda x: x["L"] >= 165)):
    fila(et, [x for x in busq if f(x)])

print("\n4. MOVIMIENTO APERTURA -> CIERRE")
print(hdr)
for et, f in (("bajo mucho (<=-3)", lambda x: x["mov"] is not None and x["mov"] <= -3),
              ("bajo (-3 a -1)", lambda x: x["mov"] is not None and -3 < x["mov"] <= -1),
              ("quieta (-1 a 1)", lambda x: x["mov"] is not None and -1 < x["mov"] < 1),
              ("subio (1 a 3)", lambda x: x["mov"] is not None and 1 <= x["mov"] < 3),
              ("subio mucho (>=3)", lambda x: x["mov"] is not None and x["mov"] >= 3)):
    fila(et, [x for x in busq if f(x)])

print("\n5. DESACUERDO ENTRE CASAS (dispersion de lineas al cierre)")
print(hdr)
for et, f in (("todas de acuerdo (0)", lambda x: x["dispersion"] == 0),
              ("poco (0-2)", lambda x: 0 < x["dispersion"] <= 2),
              ("bastante (2-5)", lambda x: 2 < x["dispersion"] <= 5),
              ("mucho (>5)", lambda x: x["dispersion"] > 5)):
    fila(et, [x for x in busq if f(x)])
