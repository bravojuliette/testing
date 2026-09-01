"""Implementa PREREGISTRO_lead_lag_vivo.md (+ENMIENDA 1), commiteado antes.

Lead-lag EN JUEGO entre pares de casas, sobre la serie PROPIA de cada casa
(`bball_odds_hist` con `source` rellena, que baja `cosecha-src`). A diferencia
del `lead_lag.py` pre-partido, aqui cada movimiento SI lleva el nombre de la
casa que lo hizo y el marcador del momento.

Se reportan siempre cuatro columnas por celda, y las tres ultimas son las que
deciden si la primera vale algo:
  REAL   -- A se mueve >= umbral, B sigue rezagada: se compra en B hacia A.
  INVER  -- lo mismo con los papeles cambiados (control de SIMETRIA: un
            lead-lag de verdad es asimetrico; si las dos ganan, es cadencia).
  PLAC   -- igual que REAL pero con la DIRECCION del movimiento de A al azar
            (control de placebo declarado).
  GAP    -- igual que REAL pero SIN exigir que A se acabe de mover, solo que
            B lleve retraso (ENMIENDA 1: separa liderazgo de rancidez).

Uso:
  python -m bball.analysis.lead_lag_vivo --db-hist X.db --db-games Y.db
"""
from __future__ import annotations

import argparse
import random
import sqlite3
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball.analysis.sobre_reaccion_q1 import t_pnl

MERCADO = "18_3"
UMBRALES = (1.0, 2.0, 3.0)
TOL_RELOJ = 300      # s de holgura maxima entre la entrada de B y la senal
ZOMBI_MIN_CAMBIOS = 2
CUOTA_MIN, CUOTA_MAX = 1.01, 20.0


def cargar(db_hist, db_games, ligas=None, limite=0):
    """{event_id: {'lg':.., 'fecha':.., 'fin':.., 'series': {casa: [(t,linea,ov,un)]}}}"""
    ch = sqlite3.connect(db_hist)
    cg = sqlite3.connect(db_games)
    juegos = {}
    q = "SELECT event_id, league_name, date, home_score, away_score FROM bball_games WHERE completed=1"
    for eid, lg, fecha, hs, aws in cg.execute(q):
        if ligas and lg not in ligas:
            continue
        fin = (hs or 0) + (aws or 0)
        if fin > 0:
            juegos[str(eid)] = dict(lg=lg, fecha=fecha, fin=float(fin), series=defaultdict(list))
    cg.close()

    q = ("SELECT event_id, source, add_time, line, over_odds, under_odds FROM bball_odds_hist "
         "WHERE source IS NOT NULL AND market=? AND ss IS NOT NULL AND ss<>'' "
         "AND add_time IS NOT NULL AND line IS NOT NULL ORDER BY event_id, source, add_time")
    for eid, src, t, ln, ov, un in ch.execute(q, (MERCADO,)):
        g = juegos.get(str(eid))
        if g is None:
            continue
        g["series"][src].append((int(t), float(ln), ov, un))
    ch.close()

    # ZOMBI: la casa debe mover la linea al menos ZOMBI_MIN_CAMBIOS veces
    evs = {}
    for eid, g in juegos.items():
        vivas = {s: xs for s, xs in g["series"].items()
                 if len({x[1] for x in xs}) >= ZOMBI_MIN_CAMBIOS}
        if len(vivas) >= 2:
            g["series"] = vivas
            evs[eid] = g
    return dict(list(evs.items())[:limite]) if limite else evs


def _ultima_hasta(serie, t):
    """Ultima entrada de `serie` con add_time <= t (serie ya ordenada)."""
    lo, hi, res = 0, len(serie) - 1, None
    while lo <= hi:
        m = (lo + hi) // 2
        if serie[m][0] <= t:
            res = serie[m]; lo = m + 1
        else:
            hi = m - 1
    return res


def _pnl(entrada_b, lado, fin):
    """lado 'over'/'under' a las cuotas vigentes de B. None si no apostable."""
    _t, linea, ov, un = entrada_b
    od = ov if lado == "over" else un
    try:
        od = float(od)
    except (TypeError, ValueError):
        return None
    if not (CUOTA_MIN <= od <= CUOTA_MAX) or fin == linea:
        return None
    gana = (fin > linea) if lado == "over" else (fin < linea)
    return (od - 1.0) if gana else -1.0


def apuestas_par(g, a, b, umbral, modo, rnd=None):
    """Apuestas de comprar EN b hacia a. modo: 'real' | 'placebo' | 'gap'."""
    sa, sb = g["series"].get(a), g["series"].get(b)
    if not sa or not sb:
        return []
    out, abierto = [], False
    for i, (t, linea_a, _ov, _un) in enumerate(sa):
        if modo != "gap":
            if i == 0:
                continue
            salto = linea_a - sa[i - 1][1]
            if abs(salto) < umbral:
                continue
            direccion = (1 if salto > 0 else -1)
            if modo == "placebo":
                direccion = rnd.choice((1, -1))
        else:
            direccion = 0   # se decide por el signo del retraso de B
        eb = _ultima_hasta(sb, t)
        if eb is None or t - eb[0] > TOL_RELOJ:
            continue
        retraso = linea_a - eb[1]        # >0: B va por debajo de A -> OVER en B
        if modo == "gap":
            if abs(retraso) < umbral:
                abierto = False
                continue
            lado = "over" if retraso > 0 else "under"
        else:
            # B debe seguir rezagada EN LA DIRECCION en que se movio A
            if direccion > 0 and retraso < umbral:
                abierto = False
                continue
            if direccion < 0 and -retraso < umbral:
                abierto = False
                continue
            lado = "over" if direccion > 0 else "under"
        if abierto:      # sin re-entrar hasta que el desfase se cierre
            continue
        p = _pnl(eb, lado, g["fin"])
        if p is None:
            continue
        out.append((g["fecha"], p))
        abierto = True
    return out


def celda(evs, a, b, umbral, modo, semilla=0):
    rnd = random.Random(semilla)
    filas = []
    for g in evs.values():
        filas += apuestas_par(g, a, b, umbral, modo, rnd)
    return filas


def resumen(filas, corte):
    if not filas:
        return None
    pnls = [p for _f, p in filas]
    s = [p for f, p in filas if f < corte]
    r = [p for f, p in filas if f >= corte]
    return dict(n=len(pnls), roi=statistics.mean(pnls) * 100, t=t_pnl(pnls),
                s=(statistics.mean(s) * 100 if s else float("nan")), ns=len(s),
                r=(statistics.mean(r) * 100 if r else float("nan")), nr=len(r))


def _fmt(d):
    if d is None:
        return f"{'n=0':>28s}"
    return f"n={d['n']:5d} ROI={d['roi']:+6.1f}% t={d['t']:+5.2f}"


def correr(evs, nombre=""):
    casas = sorted({s for g in evs.values() for s in g["series"]})
    fechas = sorted(g["fecha"] for g in evs.values())
    if not fechas:
        print(f"== {nombre}: sin eventos =="); return
    corte = fechas[len(fechas) // 2]
    print(f"\n===== {nombre}: {len(evs)} partidos | casas={casas} | corte S/R={corte} =====")
    # cadencia: cuantas entradas publica cada casa por partido (el confundidor)
    print("  cadencia (entradas EN JUEGO por partido, mediana):")
    for c in casas:
        v = [len(g["series"][c]) for g in evs.values() if c in g["series"]]
        if v:
            print(f"    {c:10s} partidos={len(v):5d} mediana={statistics.median(v):7.0f}")
    for a in casas:
        for b in casas:
            if a == b:
                continue
            pares = sum(1 for g in evs.values() if a in g["series"] and b in g["series"])
            if not pares:
                continue
            print(f"\n  --- lider={a} rezagada={b} ({pares} partidos con las dos) ---")
            for u in UMBRALES:
                real = resumen(celda(evs, a, b, u, "real"), corte)
                inver = resumen(celda(evs, b, a, u, "real"), corte)
                plac = resumen(celda(evs, a, b, u, "placebo", semilla=7), corte)
                gap = resumen(celda(evs, a, b, u, "gap"), corte)
                print(f"    umbral>={u:.1f}  REAL  {_fmt(real)}"
                      + (f" | S {real['s']:+6.1f}%(n={real['ns']}) R {real['r']:+6.1f}%(n={real['nr']})" if real else ""))
                print(f"                 INVER {_fmt(inver)}   PLAC {_fmt(plac)}   GAP {_fmt(gap)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-hist", required=True, help="base con bball_odds_hist(source)")
    ap.add_argument("--db-games", required=True, help="base con bball_games (marcadores)")
    ap.add_argument("--leagues", help="nombres separados por comas")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--por-liga", action="store_true")
    args = ap.parse_args()
    ligas = args.leagues.split(",") if args.leagues else None
    evs = cargar(args.db_hist, args.db_games, ligas=ligas, limite=args.limite)
    print(f"cargados {len(evs)} partidos con >=2 casas vivas")
    if args.por_liga:
        for lg in sorted({g["lg"] for g in evs.values()}):
            correr({k: v for k, v in evs.items() if v["lg"] == lg}, lg)
    else:
        correr(evs, "POOLED")


if __name__ == "__main__":
    main()
