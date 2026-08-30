"""EXTENSION del pre-registro de sobre-reaccion: mismos tests en los cortes
de FIN DE Q2 (descanso) y FIN DE Q3, declarada ANTES de correrla.

Identico a sobre_reaccion_q1.py salvo el corte k (2 o 3):
- Pk = puntos acumulados al final del cuarto k (raw_json.scores).
- Entrada viva = ULTIMA entrada 18_3 cuya suma de ss == Pk (la suma del
  marcador es monotona: esas entradas son el tramo contiguo entre la ultima
  canasta del cuarto k y la primera del k+1, descanso incluido), con
  add_time en [inicio+8min, inicio+3h] y cuotas en [1.01, 20].
- A PRIMARIO: OLS de (final - linea_viva) sobre la sorpresa acumulada
  (Pk - k*L/4). beta<0 t<=-2 sobre-reaccion; beta>0 t>=2 sub-reaccion;
  resto bien calibrada.
- B apostable: umbral de sorpresa escalado con sqrt(k) (la sd acumulada
  crece asi): 6*sqrt(k) -> 8.5 en Q2, 10.4 en Q3. Cuatro patas por corte
  (contradecir y seguir, over y under), cuotas reales de la entrada.
- Aviso de comparaciones multiples, declarado ya: 2 cortes x 3 ligas x
  (beta + 4 patas) = 30 numeros; el azar puro espera ~1-2 con |t|>=2.
  Una celda suelta NO es señal: exigimos t>=2 Y coherencia entre ligas
  (misma direccion en las tres) para mover un dedo.

RESULTADOS: se anexan al final tras correr, sin tocar lo de arriba.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball import config
from bball.analysis.sobre_reaccion_q1 import BOOKS, LIGAS, ols, suma_ss, t_pnl

VENTANA = (8 * 60, 180 * 60)


def cargar_corte(db_path: str, k: int):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    kick: dict[str, dict] = defaultdict(dict)
    for r in conn.execute(
        "SELECT event_id, book, line FROM bball_odds WHERE market=? AND snapshot='kickoff'",
        (config.TOTALS_MARKET_KEY,)):
        kick[r["event_id"]][r["book"]] = r["line"]
    series: dict[str, list] = defaultdict(list)
    for r in conn.execute(
        "SELECT event_id, add_time, ss, line, over_odds, under_odds FROM bball_odds_hist "
        "WHERE market=? AND add_time IS NOT NULL AND line IS NOT NULL",
        (config.TOTALS_MARKET_KEY,)):
        series[r["event_id"]].append(r)

    claves = ("1", "2", "4", "5")[:k]
    filas = []
    for g in conn.execute(
        "SELECT event_id, league_name, time_ts, home_score, away_score, raw_json "
        "FROM bball_games WHERE completed=1"):
        if g["league_name"] not in LIGAS:
            continue
        L = next((kick[g["event_id"]][b] for b in BOOKS if b in kick.get(g["event_id"], {})), None)
        if L is None:
            continue
        try:
            sc = json.loads(g["raw_json"]).get("scores") or {}
            pk = sum(int(sc[c]["home"]) + int(sc[c]["away"]) for c in claves)
        except (KeyError, TypeError, ValueError):
            continue
        final = (g["home_score"] or 0) + (g["away_score"] or 0)
        if final <= 0:
            continue
        ts = int(g["time_ts"] or 0)
        cand = [e for e in series.get(g["event_id"], [])
                if suma_ss(e["ss"]) == pk
                and ts + VENTANA[0] <= e["add_time"] <= ts + VENTANA[1]
                and e["over_odds"] and e["under_odds"]
                and 1.01 <= e["over_odds"] <= 20 and 1.01 <= e["under_odds"] <= 20]
        if not cand:
            continue
        e = max(cand, key=lambda r: r["add_time"])
        filas.append(dict(lg=g["league_name"], L=float(L), pk=float(pk), final=float(final),
                          viva=float(e["line"]), over=float(e["over_odds"]),
                          under=float(e["under_odds"])))
    conn.close()
    return filas


def informe(filas, lg, k):
    fs = [f for f in filas if f["lg"] == lg]
    if len(fs) < 30:
        print(f"  {lg}: n={len(fs)} <30, sin potencia")
        return
    umbral = 6 * math.sqrt(k)
    xs = [f["pk"] - k * f["L"] / 4 for f in fs]
    ys = [f["final"] - f["viva"] for f in fs]
    beta, _, t, n = ols(xs, ys)
    print(f"  {lg}: beta={beta:+.4f} t={t:+.2f} n={n}")
    for nombre, cond, lado in ((f"contra: lento->OVER ", lambda f: f["pk"] <= k * f["L"] / 4 - umbral, "over"),
                               (f"contra: rapido->UNDER", lambda f: f["pk"] >= k * f["L"] / 4 + umbral, "under"),
                               (f"seguir: rapido->OVER ", lambda f: f["pk"] >= k * f["L"] / 4 + umbral, "over"),
                               (f"seguir: lento->UNDER ", lambda f: f["pk"] <= k * f["L"] / 4 - umbral, "under")):
        sel = [f for f in fs if cond(f)]
        pnls = [(f[lado] - 1.0) if ((f["final"] > f["viva"]) == (lado == "over")) else -1.0
                for f in sel if f["final"] != f["viva"]]
        if pnls:
            print(f"    {nombre}: n={len(pnls):3d} ROI={statistics.mean(pnls)*100:+6.1f}% t={t_pnl(pnls):+.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data_local/bball_local.db")
    args = ap.parse_args()
    for k in (2, 3):
        filas = cargar_corte(args.db, k)
        print(f"\n== CORTE fin de Q{k} (umbral {6*math.sqrt(k):.1f}) -- {len(filas)} partidos emparejados ==")
        for lg in LIGAS:
            informe(filas, lg, k)


if __name__ == "__main__":
    main()
