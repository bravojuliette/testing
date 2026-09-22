"""Elo propio contra el precio de apertura de Bet365.
Parametros, bloques, umbrales, puerta de sanidad y placebo fijados en
PREREGISTRO_modelo_propio.md (commit anterior). Nada se ajusta aqui.

Uso: python3 bball/analysis/modelo_propio.py [ruta.db]
"""
import math
import random
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, ".")
from bball.backtest.orientacion import clasificar_orientacion

DB = sys.argv[1] if len(sys.argv) > 1 else "data_local/bball_turso.db"
K, HCA, INICIAL, MIN_PREVIOS = 20.0, 100.0, 1500.0, 10
UMBRALES = (0.0, 0.02, 0.05, 0.10)
LIGAS = ("NBA", "NCAA", "WNBA", "Euroleague")


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


def liga(nombre):
    if not nombre:
        return None
    if "NCAA" in nombre:
        return "NCAA"
    return nombre if nombre in LIGAS else None


def cargar(conn):
    """Partidos en orden de fecha, ya con orientacion NCAAB corregida."""
    orient = clasificar_orientacion(conn)
    filas = conn.execute(
        """SELECT g.event_id, g.date, g.league_name, g.home_key, g.away_key,
                  g.home_score hs, g.away_score sa,
                  o.over_odds oh, o.under_odds oa
           FROM bball_games g
           LEFT JOIN bball_odds o ON o.event_id=g.event_id AND o.book='Bet365'
                AND o.market='18_1' AND o.snapshot='start'
                AND o.over_odds>1 AND o.under_odds>1
           WHERE g.completed=1 AND g.date IS NOT NULL
             AND g.home_score IS NOT NULL AND g.home_score<>g.away_score
           ORDER BY g.date, g.event_id"""
    ).fetchall()
    out = []
    for r in filas:
        lg = liga(r["league_name"])
        if lg is None:
            continue
        eh, ea, oh, oa = r["home_key"], r["away_key"], r["oh"], r["oa"]
        gana_h = r["hs"] > r["sa"]
        if lg == "NCAA":
            cl = orient.get(r["event_id"], "sin_dato")
            if cl == "sin_dato":
                continue
            if cl == "swap":          # reetiquetar el SLOT, nunca el marcador
                eh, ea = ea, eh
                oh, oa = oa, oh
                gana_h = not gana_h
        out.append(dict(lg=lg, fecha=r["date"], eh=eh, ea=ea,
                        oh=oh, oa=oa, gana_h=gana_h))
    return out


def correr_elo(reg):
    """Walk-forward estricto: predice con lo anterior, luego actualiza."""
    rating = defaultdict(lambda: INICIAL)
    vistos = defaultdict(int)
    for x in reg:
        rh, ra = rating[(x["lg"], x["eh"])], rating[(x["lg"], x["ea"])]
        p = 1.0 / (1.0 + 10 ** (-((rh - ra + HCA) / 400.0)))
        x["p_elo"] = p
        x["listo"] = vistos[(x["lg"], x["eh"])] >= MIN_PREVIOS and \
                     vistos[(x["lg"], x["ea"])] >= MIN_PREVIOS
        s = 1.0 if x["gana_h"] else 0.0
        rating[(x["lg"], x["eh"])] = rh + K * (s - p)
        rating[(x["lg"], x["ea"])] = ra + K * ((1 - s) - p)
        vistos[(x["lg"], x["eh"])] += 1
        vistos[(x["lg"], x["ea"])] += 1
    return rating


def apuestas(reg, umbral, filtro_cuota=None, campo="p_elo"):
    out = []
    for x in reg:
        if not x["listo"] or not x["oh"]:
            continue
        p = x[campo]
        eh, ea = p * x["oh"] - 1, (1 - p) * x["oa"] - 1
        if eh >= ea:
            cuota, edge, acierta = x["oh"], eh, x["gana_h"]
        else:
            cuota, edge, acierta = x["oa"], ea, not x["gana_h"]
        if edge < umbral:
            continue
        if filtro_cuota is not None and cuota >= filtro_cuota:
            continue
        out.append(((cuota - 1) if acierta else -1.0, x))
    return out


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    reg = cargar(conn)
    correr_elo(reg)
    usables = [x for x in reg if x["listo"] and x["oh"]]
    print(f"partidos cargados: {len(reg)}   con Elo maduro y cuota Bet365: {len(usables)}")

    # ---------- PUERTA DE SANIDAD ----------
    print("\n" + "=" * 74)
    print("PUERTA DE SANIDAD: ¿el Elo predice algo? (se mira ANTES que cualquier ROI)")
    print("=" * 74)
    ac_elo = [1.0 if (x["p_elo"] > 0.5) == x["gana_h"] else 0.0 for x in usables]
    ac_mkt = [1.0 if (x["oh"] < x["oa"]) == x["gana_h"] else 0.0 for x in usables]
    for nombre, ac in (("Elo", ac_elo), ("mercado Bet365", ac_mkt)):
        n = len(ac); m = sum(ac) / n
        t = (m - 0.5) / math.sqrt(m * (1 - m) / n)
        print(f"  {nombre:<16} acierto {m*100:5.2f}%  (vs 50%)  t={t:+6.2f}   n={n}")
    for lg in LIGAS:
        s = [x for x in usables if x["lg"] == lg]
        if len(s) < 100:
            continue
        e = sum(1 for x in s if (x["p_elo"] > 0.5) == x["gana_h"]) / len(s)
        m = sum(1 for x in s if (x["oh"] < x["oa"]) == x["gana_h"]) / len(s)
        print(f"    {lg:<12} Elo {e*100:5.2f}%   mercado {m*100:5.2f}%   n={len(s)}")

    # ---------- BLOQUES ----------
    bloques = (("A: todos", None), ("B: cuota < 1.10", 1.10), ("C: cuota < 1.20", 1.20))
    print("\n" + "=" * 74)
    print("ROI por bloque y umbral de ventaja del modelo")
    print("=" * 74)
    print(f"  {'bloque':<18}" + "".join(f"{'e>='+str(int(u*100))+'%':<31}" for u in UMBRALES))
    for nombre, fc in bloques:
        fila = "".join(fmt([p for p, _ in apuestas(reg, u, fc)]) for u in UMBRALES)
        print(f"  {nombre:<18}{fila}")

    # ---------- busqueda / reserva ----------
    print("\nbusqueda / reserva (bloque A, corte por mediana de fecha)")
    ap = apuestas(reg, 0.0)
    fechas = sorted(x["fecha"] for _, x in ap)
    corte = fechas[len(fechas) // 2]
    for u in UMBRALES:
        a = apuestas(reg, u)
        b = [p for p, x in a if x["fecha"] < corte]
        r = [p for p, x in a if x["fecha"] >= corte]
        print(f"  e>={u*100:>3.0f}%  busqueda {fmt(b,100)} reserva {fmt(r,100)}")

    # ---------- placebo ----------
    print("\nPLACEBO (p_elo barajada entre partidos, semillas 1/2/3; bloque A, e>=0)")
    for semilla in (1, 2, 3):
        rnd = random.Random(semilla)
        ps = [x["p_elo"] for x in reg]
        rnd.shuffle(ps)
        for x, p in zip(reg, ps):
            x["p_fake"] = p
        print(f"  semilla {semilla}  {fmt([p for p, _ in apuestas(reg, 0.0, None, 'p_fake')])}")


if __name__ == "__main__":
    main()
