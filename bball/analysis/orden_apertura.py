"""El nicho del ORDEN DE APERTURA: consenso de las casas que abrieron ANTES que
Bet365, contra la propia apertura de Bet365. Criterios, umbrales, contraste
ANTES/DESPUES y placebo fijados en PREREGISTRO_orden_apertura.md.

Uso: python3 bball/analysis/orden_apertura.py [ruta.db]
"""
import math
import random
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, ".")
from bball.analysis.alineacion import alinear_par, liga_de, votar
from bball.backtest.orientacion import clasificar_orientacion

DB = sys.argv[1] if len(sys.argv) > 1 else "data_local/bball_turso.db"
REF = "Bet365"
UMBRALES = (0.0, 0.02, 0.05)
MIN_PREVIAS = (5, 8)
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


def cargar(conn):
    orient = clasificar_orientacion(conn)
    filas = conn.execute(
        """SELECT o.event_id ev, o.book, o.over_odds a, o.under_odds b,
                  CAST(o.captured_at AS INTEGER) t, g.date fecha,
                  CASE WHEN g.league_name LIKE '%NCAA%' THEN 'NCAA' ELSE g.league_name END lg,
                  g.home_score hs, g.away_score sa
           FROM bball_odds o JOIN bball_games g ON g.event_id=o.event_id
           WHERE o.market='18_1' AND o.snapshot='start' AND g.completed=1
             AND g.home_score IS NOT NULL AND g.home_score<>g.away_score
             AND o.over_odds>1 AND o.under_odds>1 AND o.captured_at GLOB '[0-9]*'"""
    ).fetchall()
    ev = defaultdict(dict)
    meta = {}
    for r in filas:
        if r["lg"] not in LIGAS:
            continue
        ev[r["ev"]][r["book"]] = (r["a"], r["b"], r["t"])
        meta[r["ev"]] = (r["lg"], r["fecha"], r["hs"] > r["sa"])
    return ev, meta, orient


def alinear(ev, lgof):
    """POR (casa, liga). La version global de la primera pasada mezclaba dos
    convenciones opuestas (en NCAAB casi todas las casas van invertidas
    respecto a Bet365, en el resto no) y salia a cara o cruz: el consenso
    quedaba orientado al azar y acertaba el 52%. Ver alineacion.py."""
    return votar(ev, lgof)


def construir(ev, meta, orient, inv, min_previas, lado):
    """lado='antes' (ejecutable) o 'despues' (con lookahead, solo diagnostico)."""
    out = []
    for e, d in ev.items():
        ref = d.get(REF)
        if not ref or e not in meta:
            continue
        lg, fecha, gana_h = meta[e]
        oh, oa, tb = ref
        swap = False
        if lg == "NCAA":
            cl = orient.get(e, "sin_dato")
            if cl == "sin_dato":
                continue
            swap = cl == "swap"
        probs = []
        for casa, (a, b, t) in d.items():
            if casa == REF:
                continue
            if (t < tb) if lado == "antes" else (t > tb):
                par = alinear_par((a, b), casa, lg, inv)
                if par is None:
                    continue
                ca, cb = par
                s = 1 / ca + 1 / cb
                probs.append((1 / ca) / s)
        if len(probs) < min_previas:
            continue
        p_home = statistics.median(probs)
        if swap:                       # reetiquetar el SLOT, nunca el marcador
            oh, oa = oa, oh
            p_home = 1 - p_home
            gana_h = not gana_h
        out.append(dict(lg=lg, fecha=fecha, oh=oh, oa=oa, p=p_home, gana_h=gana_h))
    return out


def apostar(reg, umbral, campo="p"):
    res = []
    for x in reg:
        p = x[campo]
        eh, ea = p * x["oh"] - 1, (1 - p) * x["oa"] - 1
        if eh >= ea:
            cuota, edge, ok = x["oh"], eh, x["gana_h"]
        else:
            cuota, edge, ok = x["oa"], ea, not x["gana_h"]
        if edge >= umbral:
            res.append((((cuota - 1) if ok else -1.0), x))
    return res


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    ev, meta, orient = cargar(conn)
    lgof = {e: m[0] for e, m in meta.items()}
    inv = alinear(ev, lgof)
    print(f"eventos con apertura: {len(ev)}   pares (casa,liga) alineados: {len(inv)} "
          f"({sum(1 for v in inv.values() if v[0])} invertidos)")

    for mp in MIN_PREVIAS:
        print("\n" + "=" * 78)
        print(f"NICHO: >= {mp} casas abrieron ANTES que Bet365")
        print("=" * 78)
        antes = construir(ev, meta, orient, inv, mp, "antes")
        despues = construir(ev, meta, orient, inv, mp, "despues")
        print(f"  partidos: ANTES n={len(antes)}   DESPUES n={len(despues)}")

        # puerta de sanidad
        for nombre, reg in (("consenso ANTES", antes), ("consenso DESPUES", despues)):
            if not reg:
                continue
            ac = [1.0 if (x["p"] > 0.5) == x["gana_h"] else 0.0 for x in reg]
            mk = [1.0 if (x["oh"] < x["oa"]) == x["gana_h"] else 0.0 for x in reg]
            n = len(ac); m = sum(ac) / n
            t = (m - 0.5) / math.sqrt(m * (1 - m) / n)
            print(f"    {nombre:<18} acierto {m*100:5.2f}% (t={t:+6.2f})   "
                  f"Bet365 sobre los mismos: {sum(mk)/n*100:5.2f}%   n={n}")

        print(f"  {'version':<20}" + "".join(f"{'e>='+str(int(u*100))+'%':<31}" for u in UMBRALES))
        for nombre, reg in (("ANTES (ejecutable)", antes), ("DESPUES (lookahead)", despues)):
            print(f"  {nombre:<20}" + "".join(fmt([p for p, _ in apostar(reg, u)]) for u in UMBRALES))

        if mp != MIN_PREVIAS[0] or not antes:
            continue
        # busqueda / reserva y placebo, solo sobre la version ejecutable
        ap = apostar(antes, 0.0)
        fechas = sorted(x["fecha"] for _, x in ap)
        corte = fechas[len(fechas) // 2]
        print(f"\n  ANTES, busqueda/reserva (corte {corte}):")
        for u in UMBRALES:
            a = apostar(antes, u)
            print(f"    e>={u*100:>3.0f}%  busqueda "
                  f"{fmt([p for p, x in a if x['fecha'] < corte], 100)} reserva "
                  f"{fmt([p for p, x in a if x['fecha'] >= corte], 100)}")
        print("\n  PLACEBO (consenso barajado entre partidos, ANTES, e>=0):")
        for semilla in (1, 2, 3):
            rnd = random.Random(semilla)
            ps = [x["p"] for x in antes]
            rnd.shuffle(ps)
            for x, p in zip(antes, ps):
                x["p_fake"] = p
            print(f"    semilla {semilla}  {fmt([p for p, _ in apostar(antes, 0.0, 'p_fake')])}")
        print("\n  ANTES por liga (e>=0):")
        for lg in LIGAS:
            sel = [p for p, x in apostar(antes, 0.0) if x["lg"] == lg]
            print(f"    {lg:<12} {fmt(sel, 100)}")


if __name__ == "__main__":
    main()
