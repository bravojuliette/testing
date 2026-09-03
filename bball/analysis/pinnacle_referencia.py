"""Bet365 contra el valor justo de Pinnacle, apostando en Bet365 al kickoff.
Celdas, umbrales, placebos y control de frescura fijados en
PREREGISTRO_pinnacle_referencia.md (commit anterior).

Uso: python3 bball/analysis/pinnacle_referencia.py [ruta.db]
"""
import math
import random
import sqlite3
import sys

sys.path.insert(0, ".")
from bball.backtest.orientacion import clasificar_orientacion

DB = sys.argv[1] if len(sys.argv) > 1 else "data_local/bball_turso.db"
UMBRALES = (0.0, 0.01, 0.02, 0.03)
FRESCURA = (120, 600, None)   # None = sin filtro (no puede confirmar nada)


def stats(p):
    n = len(p)
    if n == 0:
        return 0, 0.0, 0.0
    m = sum(p) / n
    if n < 2:
        return n, m * 100, 0.0
    v = sum((x - m) ** 2 for x in p) / (n - 1)
    return n, m * 100, (m / math.sqrt(v / n) if v > 0 else 0.0)


def fmt(p, minimo=300):
    n, roi, t = stats(p)
    if n < minimo:
        return f"n={n:<5} (n<{minimo})".ljust(31)
    return f"n={n:<5} ROI {roi:+6.2f}%  t={t:+5.2f}".ljust(31)


def cargar(conn, referencia):
    orient = clasificar_orientacion(conn)
    filas = conn.execute(
        """SELECT g.event_id, g.date, g.league_name, g.home_score hs, g.away_score sa,
                  b.over_odds bh, b.under_odds ba, r.over_odds rh, r.under_odds ra,
                  ABS(CAST(b.captured_at AS INTEGER)-CAST(r.captured_at AS INTEGER)) gap
           FROM bball_games g
           JOIN bball_odds b ON b.event_id=g.event_id AND b.book='Bet365'
                AND b.market='18_1' AND b.snapshot='kickoff'
           JOIN bball_odds r ON r.event_id=g.event_id AND r.book=?
                AND r.market='18_1' AND r.snapshot='kickoff'
           WHERE g.completed=1 AND g.home_score<>g.away_score AND g.date IS NOT NULL
             AND b.over_odds>1 AND b.under_odds>1 AND r.over_odds>1 AND r.under_odds>1
             AND b.captured_at GLOB '[0-9]*' AND r.captured_at GLOB '[0-9]*'""",
        (referencia,)).fetchall()
    out = []
    for f in filas:
        lg = "NCAA" if "NCAA" in (f["league_name"] or "") else f["league_name"]
        if lg not in ("NBA", "NCAA", "WNBA", "Euroleague"):
            continue
        bh, ba, rh, ra = f["bh"], f["ba"], f["rh"], f["ra"]
        gana_h = f["hs"] > f["sa"]
        if lg == "NCAA":
            cl = orient.get(f["event_id"], "sin_dato")
            if cl == "sin_dato":
                continue
            if cl == "swap":            # reetiquetar el SLOT, nunca el marcador
                bh, ba, rh, ra = ba, bh, ra, rh
                gana_h = not gana_h
        # valor justo de la referencia, metodo proporcional (fijado en el pre-registro)
        s = 1 / rh + 1 / ra
        qh, qa = (1 / rh) / s, (1 / ra) / s
        eh, ea = qh * bh - 1, qa * ba - 1
        if eh >= ea:
            lado, cuota, edge, acierta = "H", bh, eh, gana_h
        else:
            lado, cuota, edge, acierta = "A", ba, ea, not gana_h
        out.append(dict(lg=lg, fecha=f["date"], gap=f["gap"], edge=edge, cuota=cuota,
                        acierta=acierta, bh=bh, ba=ba, gana_h=gana_h))
    return out


def pnl(x):
    return (x["cuota"] - 1) if x["acierta"] else -1.0


def tabla(reg, titulo, minimo=300):
    print(f"\n{titulo}")
    print(f"  {'frescura':<14}" + "".join(f"{'e>='+str(int(u*100))+'%':<31}" for u in UMBRALES))
    for fr in FRESCURA:
        sel0 = reg if fr is None else [x for x in reg if x["gap"] <= fr]
        et = "sin filtro" if fr is None else f"gap <= {fr}s"
        fila = "".join(fmt([pnl(x) for x in sel0 if x["edge"] >= u], minimo) for u in UMBRALES)
        print(f"  {et:<14}{fila}")


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    reg = cargar(conn, "PinnacleSports")
    print(f"partidos con Bet365 y Pinnacle al kickoff: {len(reg)}")
    for fr in (120, 600):
        print(f"  gap <= {fr}s: {sum(1 for x in reg if x['gap']<=fr)}")

    tabla(reg, "== REAL: referencia Pinnacle (celda que decide = gap <= 600s)")

    prin = [x for x in reg if x["gap"] <= 600]
    fechas = sorted(x["fecha"] for x in prin)
    corte = fechas[len(fechas) // 2]
    print(f"\n== busqueda / reserva dentro de gap<=600s (corte {corte})")
    for u in UMBRALES:
        b = [pnl(x) for x in prin if x["edge"] >= u and x["fecha"] < corte]
        r = [pnl(x) for x in prin if x["edge"] >= u and x["fecha"] >= corte]
        print(f"  e>={u*100:>2.0f}%   busqueda {fmt(b,100)} reserva {fmt(r,100)}")

    print("\n== PLACEBO 1: misma mecanica con Interwetten (casa cara) de referencia")
    tabla(cargar(conn, "Interwetten"), "  (si iguala al real, no es sharpness sino reversion)")

    print("\n== PLACEBO 2: lado elegido a cara o cruz (mismos partidos, gap<=600s)")
    for semilla in (1, 2, 3):
        rnd = random.Random(semilla)
        falso = []
        for x in prin:
            h = rnd.random() < 0.5
            falso.append(dict(x, cuota=x["bh"] if h else x["ba"],
                              acierta=x["gana_h"] if h else not x["gana_h"]))
        print(f"  semilla {semilla}  {fmt([pnl(x) for x in falso])}")

    print("\n== desglose por liga (gap<=600s, e>=0)")
    for lg in ("NBA", "NCAA", "WNBA", "Euroleague"):
        print(f"  {lg:<12} {fmt([pnl(x) for x in prin if x['lg']==lg and x['edge']>=0], 100)}")


if __name__ == "__main__":
    main()
