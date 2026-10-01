"""PRE-REGISTRO: calibracion de los TOTALES SECUNDARIOS al cierre.

Idea (vuelta pedida por el usuario tras cerrar el frente del vivo en el
mercado principal): el dinero profesional vigila el total del PARTIDO; los
mercados de total del 1er CUARTO (18_9, handicap ~ 0.25*linea) y de la 1a
MITAD (18_6, ~0.50*linea) los cotiza el modelo de la casa con menos
supervision y menos liquidez. Si en algun sitio quedo un sesgo sistematico
sin arbitrar, es mas probable aqui que en el principal. Nunca los hemos
tocado: llegaron gratis en el historial /v2/event/odds.

Commiteado ANTES de correrlo. Datos: data_local/bball_local.db.

PROCEDIMIENTO (sin mirar al futuro):
- Linea secundaria de cierre = ULTIMA entrada del mercado con add_time <
  inicio - 60s y SIN marcador (ss vacio), cuotas over/under en [1.01, 20].
- Resultado real: 18_9 vs puntos del Q1; 18_6 vs puntos de la 1a mitad
  (claves raw 1 y 1+2; prorroga irrelevante para ambos).
- Push (igual a la linea) fuera del ROI.

TESTS por liga (NBA / WNBA / Euroleague) y mercado (Q1 / H1):
  a. sesgo = media(real - linea) con su t.
  b. ROI de over ciego y de under ciego a las cuotas reales de la entrada.
  c. calibracion por magnitud: OLS de (real - linea) sobre (linea - mediana
     de lineas de su liga+mercado) -- el fantasma del viejo caso NCAAB de
     linea alta, ahora en secundarios.
CELDAS: 3 ligas x 2 mercados x ~4 numeros ~ 24; el azar espera ~1 con
|t|>=2. LISTON (fijado ya): |t|>=2 Y misma direccion en las TRES ligas para
considerar señal; una celda suelta es ruido. Cualquier señal superviviente
se re-verificaria ademas contra NCAA (llega el 1-sep) antes de apostar nada.

RESULTADOS (2026-08-30, corrido tal cual; n=1012-2407 por celda):
- Sesgos de linea: todos dentro de +-0.4 puntos. Dos celdas tocan |t|>=2
  (sesgo Q1 WNBA +0.42 t=2.06; calibracion Q1 Euro beta=+0.33 t=2.26) --
  EXACTAMENTE la ~1-2 que el azar esperaba en 24 celdas, y NINGUNA cumple
  la coherencia entre ligas exigida (WNBA + / Euro -; Euro + / WNBA -).
- ROI ciego: las 12 patas negativas (de -0.6% a -13.0%). La asimetria
  (over de Euro -13/-10 vs under -0.6/-3.6) es carga del margen por lado,
  no linea mal puesta: el sesgo real de la linea es ~0.
VEREDICTO: los totales de Q1 y 1a mitad al cierre estan tan bien calibrados
como el principal. El modelo "con menos supervision" de la casa tambien
sabe dividir entre 4. Sin señal que llevar a NCAA.
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

from bball.analysis.sobre_reaccion_q1 import LIGAS, ols, t_pnl

MERCADOS = {"18_9": ("Q1", ("1",)), "18_6": ("H1", ("1", "2"))}


def cargar(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ts = {}
    reales = {}
    ligas = {}
    for g in conn.execute(
        "SELECT event_id, league_name, time_ts, raw_json FROM bball_games WHERE completed=1"):
        if g["league_name"] not in LIGAS:
            continue
        try:
            sc = json.loads(g["raw_json"]).get("scores") or {}
            q = {k: int(sc[k]["home"]) + int(sc[k]["away"]) for k in ("1", "2")}
        except (KeyError, TypeError, ValueError):
            continue
        ts[g["event_id"]] = int(g["time_ts"] or 0)
        reales[g["event_id"]] = q
        ligas[g["event_id"]] = g["league_name"]

    filas = []
    for mk, (etq, claves) in MERCADOS.items():
        mejores = {}
        for r in conn.execute(
            "SELECT event_id, add_time, ss, line, over_odds, under_odds FROM bball_odds_hist "
            "WHERE market=? AND add_time IS NOT NULL AND line IS NOT NULL", (mk,)):
            eid = r["event_id"]
            t0 = ts.get(eid)
            if not t0 or r["add_time"] >= t0 - 60 or r["ss"]:
                continue
            if not (r["over_odds"] and r["under_odds"]
                    and 1.01 <= r["over_odds"] <= 20 and 1.01 <= r["under_odds"] <= 20):
                continue
            prev = mejores.get(eid)
            if prev is None or r["add_time"] > prev["add_time"]:
                mejores[eid] = r
        for eid, e in mejores.items():
            real = sum(reales[eid][c] for c in claves)
            filas.append(dict(lg=ligas[eid], mk=etq, linea=float(e["line"]), real=float(real),
                              over=float(e["over_odds"]), under=float(e["under_odds"])))
    conn.close()
    return filas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data_local/bball_local.db")
    args = ap.parse_args()
    filas = cargar(args.db)
    for mk in ("Q1", "H1"):
        print(f"\n== TOTAL {mk} al cierre ==")
        for lg in LIGAS:
            fs = [f for f in filas if f["lg"] == lg and f["mk"] == mk]
            if len(fs) < 30:
                print(f"  {lg}: n={len(fs)} <30, sin potencia")
                continue
            des = [f["real"] - f["linea"] for f in fs]
            sd = statistics.pstdev(des)
            t_sesgo = statistics.mean(des) / sd * math.sqrt(len(des)) if sd else 0
            roi = {}
            for lado in ("over", "under"):
                pnls = [(f[lado] - 1.0) if ((f["real"] > f["linea"]) == (lado == "over")) else -1.0
                        for f in fs if f["real"] != f["linea"]]
                roi[lado] = (statistics.mean(pnls) * 100, t_pnl(pnls), len(pnls))
            med = statistics.median(f["linea"] for f in fs)
            r = ols([f["linea"] - med for f in fs], des)
            beta, _, t_cal, _ = r if r else (0, 0, 0, 0)
            print(f"  {lg}: n={len(fs)} sesgo={statistics.mean(des):+.2f} (t={t_sesgo:+.2f}) | "
                  f"over {roi['over'][0]:+.1f}% t={roi['over'][1]:+.2f} | under {roi['under'][0]:+.1f}% t={roi['under'][1]:+.2f} | "
                  f"calibracion beta={beta:+.3f} t={t_cal:+.2f}")


if __name__ == "__main__":
    main()
