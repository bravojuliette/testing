"""Implementa PREREGISTRO_lead_lag.md -- commiteado A CIEGAS (Turso bloqueado).

Mide (1) que casa mueve la linea primero y cuanto tardan las demas en
copiarla, y (2) si apostar la linea vieja de la rezagada en la direccion
del lider tiene ROI.

Fuente UNICA: bball_live_snapshots (una fila por evento/pasada/casa, con
captured_at propio). Las tablas historicas NO sirven para esto y el
pre-registro explica por que (sin columna book, o snapshots desfasados
horas entre casas).

Uso:  python -m bball.analysis.lead_lag --db data_local/bball_turso.db
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, ".")

from bball.analysis.sobre_reaccion_q1 import t_pnl

VENTANA_CONSENSO = 600      # s: ventana para juntar movimientos de casas
FRAC_CONSENSO = 0.60        # fraccion de casas que deben moverse igual
ZOMBI_MIN_CAMBIOS = 2       # regla del proyecto (live/q1.py)
UMBRALES = (1.5, 2.5, 4.0)


def ts(x):
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def cargar(db_path):
    """-> {event_id: {"fecha":str, "fin":float|None, "pasadas":{t:{book:fila}}}}"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    finales = {}
    try:
        for g in conn.execute("SELECT event_id, date, home_score, away_score FROM bball_games WHERE completed=1"):
            fin = (g["home_score"] or 0) + (g["away_score"] or 0)
            if fin > 0:
                finales[g["event_id"]] = (g["date"], float(fin))
    except sqlite3.OperationalError:
        pass
    evs = defaultdict(lambda: {"fecha": None, "fin": None, "pasadas": defaultdict(dict)})
    n = 0
    for r in conn.execute(
        "SELECT event_id, captured_at, book, line, over_odds, under_odds, ss "
        "FROM bball_live_snapshots WHERE line IS NOT NULL AND book IS NOT NULL"):
        t = ts(r["captured_at"])
        if t is None or r["book"] == "__hist__":
            continue
        e = evs[r["event_id"]]
        e["pasadas"][round(t)][r["book"]] = dict(
            line=float(r["line"]), ov=r["over_odds"], un=r["under_odds"], ss=r["ss"])
        n += 1
    conn.close()
    for eid, e in evs.items():
        if eid in finales:
            e["fecha"], e["fin"] = finales[eid]
    print(f"cargadas {n} fotos de {len(evs)} eventos "
          f"({sum(1 for e in evs.values() if e['fin'])} con resultado final)")
    return evs


def series_por_casa(e):
    """-> {book: [(t, fila), ...]} ordenado por tiempo."""
    out = defaultdict(list)
    for t in sorted(e["pasadas"]):
        for book, fila in e["pasadas"][t].items():
            out[book].append((t, fila))
    return out


def cambios(serie):
    """movimientos de linea: [(t, linea_vieja, linea_nueva)]"""
    mov = []
    for (t0, f0), (t1, f1) in zip(serie, serie[1:]):
        if f1["line"] != f0["line"]:
            mov.append((t1, f0["line"], f1["line"]))
    return mov


def medidor(evs):
    """Parte 1: quien lidera, quien copia y con cuanto retraso."""
    lidera = defaultdict(int)
    retrasos = defaultdict(list)
    n_eventos_consenso = 0
    for eid, e in evs.items():
        por_casa = series_por_casa(e)
        movs = {b: cambios(s) for b, s in por_casa.items()}
        casas_activas = [b for b, m in movs.items() if len(m) >= ZOMBI_MIN_CAMBIOS]
        if len(casas_activas) < 3:
            continue
        # cada movimiento es candidato a semilla de un evento de consenso
        usados = set()
        todos = sorted((t, b, v, n) for b in casas_activas for t, v, n in movs[b])
        for t0, b0, v0, n0 in todos:
            if (b0, t0) in usados:
                continue
            direccion = 1 if n0 > v0 else -1
            grupo = {b0: t0}
            for t1, b1, v1, n1 in todos:
                if b1 in grupo or not (t0 <= t1 <= t0 + VENTANA_CONSENSO):
                    continue
                if (1 if n1 > v1 else -1) == direccion:
                    grupo[b1] = t1
            if len(grupo) < max(3, int(FRAC_CONSENSO * len(casas_activas))):
                continue
            n_eventos_consenso += 1
            for b, t in grupo.items():
                usados.add((b, t))
            primero = min(grupo.values())
            for b, t in grupo.items():
                if t == primero:
                    lidera[b] += 1
                else:
                    retrasos[b].append(t - primero)
    print(f"\n== MEDIDOR: {n_eventos_consenso} eventos de consenso detectados ==")
    print(f"{'casa':22s}{'lidera':>8s}{'copia':>8s}{'%lider':>8s}{'retraso_med':>13s}")
    casas = set(lidera) | set(retrasos)
    filas = []
    for b in casas:
        nl, nc = lidera[b], len(retrasos[b])
        if nl + nc < 10:
            continue
        filas.append((b, nl, nc, nl / (nl + nc) * 100,
                      statistics.median(retrasos[b]) if retrasos[b] else 0))
    for b, nl, nc, pct, ret in sorted(filas, key=lambda f: -f[3]):
        print(f"{b:22s}{nl:8d}{nc:8d}{pct:7.1f}%{ret:11.0f}s")
    return {b: pct for b, _, _, pct, _ in filas}


def test_apostable(evs, lideres, corte, placebo=False, semilla=0):
    """Parte 2: apostar la linea vieja de la rezagada hacia el lider.

    placebo=True: el papel de 'lider' se asigna AL AZAR entre las casas
    activas, ignorando quien mueve primero. CONTROL OBLIGATORIO (descubierto
    validando con fixtures antes de ver dato real): sin el, este test no
    distingue 'el lider esta informado' de 'la linea rezagada esta lejos de
    la media y revierte'. Si el placebo rinde igual que el real, NO hay
    lead-lag: hay reversion a la media, que es otra cosa (y que en un
    mercado real es justo lo que la casa ya cobra)."""
    import random as _r
    etq = "PLACEBO (lider al azar)" if placebo else "REAL (lider por quien mueve primero)"
    print(f"\n== TEST APOSTABLE -- {etq}; corte {corte} ==")
    for umbral in UMBRALES:
        mitades = {"s": [], "r": []}
        for eid, e in evs.items():
            if not e["fin"] or not e["fecha"]:
                continue
            mitad = "s" if e["fecha"] < corte else "r"
            por_casa = series_por_casa(e)
            movs = {b: cambios(s) for b, s in por_casa.items()}
            activas = {b for b, m in movs.items() if len(m) >= ZOMBI_MIN_CAMBIOS}
            abiertas = set()
            rnd = _r.Random(f"{semilla}:{eid}")
            fake = set()
            if placebo and activas:
                k = max(1, sum(1 for b in lideres if lideres[b] >= 50))
                fake = set(rnd.sample(sorted(activas), min(k, len(activas))))
            for t in sorted(e["pasadas"]):
                foto = e["pasadas"][t]
                if placebo:
                    lids = [b for b in foto if b in fake]
                else:
                    lids = [b for b in foto if b in lideres and lideres[b] >= 50 and b in activas]
                if not lids:
                    continue
                l_lider = statistics.median([foto[b]["line"] for b in lids])
                for b, f in foto.items():
                    if b in lids or b not in activas:
                        continue
                    hueco = l_lider - f["line"]
                    if abs(hueco) < umbral:
                        abiertas.discard((b, 1 if hueco > 0 else -1))
                        continue
                    clave = (b, 1 if hueco > 0 else -1)
                    if clave in abiertas:
                        continue
                    abiertas.add(clave)
                    od = f["ov"] if hueco > 0 else f["un"]
                    if not od or not (1.01 <= od <= 20) or e["fin"] == f["line"]:
                        continue
                    gana = (e["fin"] > f["line"]) if hueco > 0 else (e["fin"] < f["line"])
                    mitades[mitad].append((od - 1.0) if gana else -1.0)
        todo = mitades["s"] + mitades["r"]
        if not todo:
            print(f"  hueco>={umbral}: n=0"); continue
        rs = statistics.mean(mitades["s"]) * 100 if mitades["s"] else float("nan")
        rr = statistics.mean(mitades["r"]) * 100 if mitades["r"] else float("nan")
        print(f"  hueco>={umbral}: n={len(todo):4d} ROI={statistics.mean(todo)*100:+6.1f}% "
              f"t={t_pnl(todo):+5.2f} | S {rs:+6.1f}% (n={len(mitades['s'])}) / "
              f"R {rr:+6.1f}% (n={len(mitades['r'])})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data_local/bball_turso.db")
    args = ap.parse_args()
    evs = cargar(args.db)
    if not evs:
        print("sin fotos del scanner en esta base -- nada que medir"); return
    fechas = sorted(e["fecha"] for e in evs.values() if e["fecha"])
    corte = fechas[len(fechas) // 2] if fechas else "9999"
    # lideres SOLO con la mitad de busqueda (declarado en el pre-registro)
    busq = {k: v for k, v in evs.items() if v["fecha"] and v["fecha"] < corte}
    lideres = medidor(busq or evs)
    test_apostable(evs, lideres, corte)
    test_apostable(evs, lideres, corte, placebo=True)
    print("\nLECTURA: si REAL y PLACEBO rinden parecido, no hay lead-lag "
          "-- es reversion a la media de la linea rezagada, no informacion.")


if __name__ == "__main__":
    main()
