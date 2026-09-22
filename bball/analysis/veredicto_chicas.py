"""VEREDICTO de LIGAS CHICAS -- implementa PREREGISTRO_ligas_chicas.md
(commiteado antes de que existiera el dato; criterios intactos).

Datos: data_local/bball_chicas.db (~60 dias, todas las ligas reales salvo
las grandes; 4123 partidos, 150 ligas, 3191 con historial en vivo).

Bloques:
1. SOBRE-REACCION Q1 (teoria del usuario): pooled + por liga n>=100.
   Linea de cierre: Bet365/Betway/BWin; fallback mediana kickoff (declarado).
   Captura ultima entrada (primaria) + primera (sensibilidad).
2. REMONTADAS: favorito perdiendo >=8/>=12 al ML vivo (inmune a orientacion:
   lado A/B del feed es consistente entre games y hist) + local perdiendo
   >=8/>=12 (REQUIERE saber quien es local: puerta de ventaja de campo
   pooled -- el listado primero debe ganar >52% para asumir primero=local;
   <48% mapeo invertido; 48-52% se ABORTA el escenario local). Puerta del
   favorito 58-78% pooled ademas, como estaba declarado.
3. BARRIDO POR COMPETICION: malla gruesa (fase2 x delta5 x margen3 x lado)
   con la LIGA como dimension; split por fecha (busqueda < 2026-07-29 <=
   reserva, mitad del rango); doble filtro ROI>0 y t>=2 en ambas mitades,
   n>=50 por mitad; supervivientes en cuarentena hasta replica.

RESULTADOS (2026-08-31, corrido tal cual; 3965 partidos, 2203 con Q1 vivo):

1. SOBRE-REACCION Q1: beta pooled +0.002 (t=0.04) con la captura primaria
   -> la linea viva de las ligas chicas TAMBIEN esta bien calibrada en
   pendiente. Patas: fade -10.1%/-10.1% (vig chico ~8-10%, peor que el de
   las grandes). La sensibilidad primera-entrada mueve mucho las patas
   (over -32.5%, under +2.6%): por la regla declarada, dependencia de
   captura = sin señal. TEORIA REFUTADA tambien aqui; per el compromiso
   del pre-registro, el frente "linea viva mal puesta" queda CERRADO en
   todas partes.

2. REMONTADAS (puertas: favorito 69.1% PASA; listado-A gana 54.8% ->
   primero=local): comprar remontadas en ligas chicas es CATASTROFICO y
   robusto a captura:
     FAVORITO >=8: -27.9% (t=-3.8) | >=12: -45.3% (t=-3.0, acierto 16%)
     LOCAL    >=8: -28.3% (t=-2.8) | >=12: -42.1% (t=-2.5, acierto 9%)
   Mecanica: en ligas chicas las palizas de Q1 van MUY en serio (brechas de
   talento enormes) y el modelo en vivo cobra la remontada como si fuera
   NBA. El boton mas caro del proyecto.

3. BARRIDO POR COMPETICION: 0 celdas con potencia (150 ligas fragmentan
   2200 partidos; honesto y esperado por el aviso declarado).

POST-HOC declarado (espejo del bloque 2, con split por fecha como replica
interna y ambas capturas):
   LIDER >=8:  -0.5% (nada: el mercado cobra bien las ventajas moderadas)
   LIDER >=12: +4.3% TOTAL (t=1.93, n=304, cuota media 1.25) --
               busqueda +2.8% / reserva +6.3%, identico con ambas capturas.
   PRIMER CANDIDATO POSITIVO GENUINO DEL PROYECTO: positivo en ambas
   mitades, robusto, con mecanica coherente (el espejo exacto del -45% de
   la remontada). t<2 y nacido de un espejo post-hoc -> CUARENTENA.
   Confirmacion pre-registrada en PREREGISTRO_lider_chicas.md contra datos
   de septiembre que aun no existen. NO APOSTAR hasta ese veredicto.
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
from bball.analysis.sobre_reaccion_q1 import BOOKS, UMBRAL, ols, suma_ss, t_pnl

VENTANA = (8 * 60, 80 * 60)
CORTE = "2026-07-29"


def partes(ss):
    s = str(ss or "")
    sep = ":" if ":" in s else "-"
    a, _, b = s.partition(sep)
    try:
        return int(a), int(b)
    except ValueError:
        return None


def cargar(db):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    kick = defaultdict(dict)
    for r in conn.execute("SELECT event_id, book, line FROM bball_odds WHERE market=? AND snapshot='kickoff'",
                          (config.TOTALS_MARKET_KEY,)):
        kick[r["event_id"]][r["book"]] = r["line"]
    tot = defaultdict(list)
    for r in conn.execute("SELECT event_id, add_time, ss, line, over_odds, under_odds FROM bball_odds_hist "
                          "WHERE market=? AND add_time IS NOT NULL AND line IS NOT NULL",
                          (config.TOTALS_MARKET_KEY,)):
        tot[r["event_id"]].append(r)
    ml = defaultdict(list)
    for r in conn.execute("SELECT event_id, add_time, ss, home_odds, away_odds FROM bball_odds_hist "
                          "WHERE market=? AND add_time IS NOT NULL", (config.MONEYLINE_MARKET_KEY,)):
        ml[r["event_id"]].append(r)

    juegos = []
    for g in conn.execute("SELECT event_id, league_name, date, time_ts, home_score, away_score, raw_json "
                          "FROM bball_games WHERE completed=1"):
        try:
            sc = json.loads(g["raw_json"]).get("scores") or {}
            p1 = int(sc["1"]["home"]) + int(sc["1"]["away"])
            m1 = int(sc["1"]["home"]) - int(sc["1"]["away"])
        except (KeyError, TypeError, ValueError):
            continue
        fin = (g["home_score"] or 0) + (g["away_score"] or 0)
        ts = int(g["time_ts"] or 0)
        if fin <= 0 or not ts:
            continue
        ks = kick.get(g["event_id"]) or {}
        L = next((ks[b] for b in BOOKS if b in ks), None)
        if L is None and ks:
            L = statistics.median(ks.values())
        j = dict(eid=g["event_id"], lg=g["league_name"], fecha=g["date"], ts=ts, L=L,
                 fin=float(fin), p1=float(p1), m1=m1,
                 gano_a=(g["home_score"] or 0) > (g["away_score"] or 0))
        cand = [e for e in tot.get(g["event_id"], [])
                if suma_ss(e["ss"]) == p1 and ts + VENTANA[0] <= e["add_time"] <= ts + VENTANA[1]
                and e["over_odds"] and e["under_odds"]
                and 1.01 <= e["over_odds"] <= 20 and 1.01 <= e["under_odds"] <= 20]
        if cand:
            j["t_ult"] = max(cand, key=lambda r: r["add_time"])
            j["t_pri"] = min(cand, key=lambda r: r["add_time"])
        serml = ml.get(g["event_id"]) or []
        pre = [e for e in serml if e["add_time"] < ts - 60 and not e["ss"] and e["home_odds"] and e["away_odds"]]
        if pre:
            j["ml_cierre"] = max(pre, key=lambda e: e["add_time"])
        vivo = [e for e in serml if suma_ss(e["ss"]) == p1 and ts + VENTANA[0] <= e["add_time"] <= ts + VENTANA[1]
                and e["home_odds"] and e["away_odds"] and 1.01 <= e["home_odds"] <= 30 and 1.01 <= e["away_odds"] <= 30]
        if vivo:
            j["ml_ult"] = max(vivo, key=lambda e: e["add_time"])
            j["ml_pri"] = min(vivo, key=lambda e: e["add_time"])
        juegos.append(j)
    conn.close()
    return juegos


def bloque_sobre(juegos, etiqueta):
    fs = [j for j in juegos if j["L"] is not None and "t_ult" in j]
    if len(fs) < 30:
        return
    for cap in ("t_ult", "t_pri"):
        xs = [j["p1"] - j["L"] / 4 for j in fs]
        ys = [j["fin"] - j[cap]["line"] for j in fs]
        beta, _, t, n = ols(xs, ys)
        linea = f"  {etiqueta} [{'ultima' if cap=='t_ult' else 'primera'}]: beta={beta:+.4f} t={t:+.2f} n={n}"
        for nombre, cond, lado in (("lento->OVER", lambda j: j["p1"] <= j["L"] / 4 - UMBRAL, "over_odds"),
                                   ("rapido->UNDER", lambda j: j["p1"] >= j["L"] / 4 + UMBRAL, "under_odds")):
            sel = [j for j in fs if cond(j) and j["fin"] != j[cap]["line"]]
            pnls = [(j[cap][lado] - 1.0) if ((j["fin"] > j[cap]["line"]) == (lado == "over_odds")) else -1.0 for j in sel]
            if pnls:
                linea += f" | {nombre}: n={len(pnls)} ROI={statistics.mean(pnls)*100:+.1f}% t={t_pnl(pnls):+.2f}"
        print(linea)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data_local/bball_chicas.db")
    args = ap.parse_args()
    juegos = cargar(args.db)
    print(f"cargados {len(juegos)} partidos; con linea+entrada viva Q1: "
          f"{sum(1 for j in juegos if j['L'] is not None and 't_ult' in j)}")

    print("\n== 1. SOBRE-REACCION Q1 ==")
    bloque_sobre(juegos, "POOLED")
    por_liga = defaultdict(list)
    for j in juegos:
        por_liga[j["lg"]].append(j)
    for lg, js in sorted(por_liga.items(), key=lambda kv: -len(kv[1])):
        if sum(1 for j in js if j["L"] is not None and "t_ult" in j) >= 100:
            bloque_sobre(js, lg[:28])

    print("\n== 2. REMONTADAS ==")
    con_ml = [j for j in juegos if "ml_cierre" in j and "ml_ult" in j]
    pa = sum(1 for j in con_ml if j["gano_a"]) / len(con_ml) * 100 if con_ml else 0
    fav_ok = sum(1 for j in con_ml if (j["ml_cierre"]["home_odds"] < j["ml_cierre"]["away_odds"]) == j["gano_a"])
    pf = fav_ok / len(con_ml) * 100 if con_ml else 0
    print(f"  puertas pooled (n={len(con_ml)}): listado-A gana {pa:.1f}% | favorito cierre gana {pf:.1f}%")
    fav_gate = 58 <= pf <= 78
    local_map = "A" if pa > 52 else ("B" if pa < 48 else None)
    print(f"  puerta favorito: {'PASA' if fav_gate else 'FALLA'} | localidad: "
          f"{'primero=local' if local_map=='A' else ('primero=visitante' if local_map=='B' else 'AMBIGUA -> escenario local ABORTADO')}")
    if fav_gate:
        for cap in ("ml_ult", "ml_pri"):
            for esc in (["FAVORITO"] + (["LOCAL"] if local_map else [])):
                for umb in (8, 12):
                    pnls = []
                    for j in con_ml:
                        if cap not in j:
                            continue
                        if esc == "FAVORITO":
                            obj_a = j["ml_cierre"]["home_odds"] < j["ml_cierre"]["away_odds"]
                        else:
                            obj_a = (local_map == "A")
                        deficit = -j["m1"] if obj_a else j["m1"]
                        if deficit < umb:
                            continue
                        od = j[cap]["home_odds"] if obj_a else j[cap]["away_odds"]
                        pnls.append((od - 1.0) if j["gano_a"] == obj_a else -1.0)
                    if pnls:
                        print(f"  {esc} >={umb} [{'ultima' if cap=='ml_ult' else 'primera'}]: "
                              f"n={len(pnls)} ROI={statistics.mean(pnls)*100:+.1f}% t={t_pnl(pnls):+.2f} "
                              f"acierto={sum(1 for p in pnls if p>0)/len(pnls)*100:.0f}%")

    print("\n== 3. BARRIDO POR COMPETICION (gruesa, split en", CORTE, ") ==")
    celdas = defaultdict(lambda: {"s": [], "r": []})
    for j in juegos:
        if j["L"] is None or "t_ult" not in j:
            continue
        # fotos por reloj como en barrido_vivo, sobre la serie ya filtrada:
        # aqui usamos las dos capturas del Q1 + delta como estado (potencia
        # limitada a proposito: el estado Q1 es el pre-registrado)
        mitad = "s" if j["fecha"] < CORTE else "r"
        e = j["t_ult"]
        p = partes(e["ss"])
        if p is None:
            continue
        delta = e["line"] - j["L"]
        db_ = ("d<=-6" if delta <= -6 else "d-6..-2" if delta <= -2 else "d-2..2" if delta < 2 else "d2..6" if delta < 6 else "d>=6")
        mb = "m0-5" if abs(p[0] - p[1]) <= 5 else ("m6-12" if abs(p[0] - p[1]) <= 12 else "m13+")
        for lado, od in (("over", e["over_odds"]), ("under", e["under_odds"])):
            if j["fin"] == e["line"]:
                continue
            gana = (j["fin"] > e["line"]) == (lado == "over")
            celdas[(j["lg"], db_, mb, lado)][mitad].append((od - 1.0) if gana else -1.0)
    filas = [(k, len(d["s"]), statistics.mean(d["s"]) * 100, t_pnl(d["s"]),
              len(d["r"]), statistics.mean(d["r"]) * 100, t_pnl(d["r"]))
             for k, d in celdas.items() if len(d["s"]) >= 50 and len(d["r"]) >= 50]
    cand = [f for f in filas if f[2] > 0 and f[3] >= 2]
    sup = [f for f in cand if f[5] > 0 and f[6] >= 2]
    print(f"  celdas con potencia: {len(filas)} | candidatas busqueda: {len(cand)} | SUPERVIVIENTES: {len(sup)}")
    if filas:
        print(f"  ROI medio: busqueda {statistics.mean(f[2] for f in filas):+.1f}% | reserva {statistics.mean(f[5] for f in filas):+.1f}%")
    for f in sorted(filas, key=lambda f: -f[3])[:6]:
        print(f"  {'/'.join(f[0]):44s} S: n={f[1]:3d} {f[2]:+6.1f}% t={f[3]:+.2f} | R: n={f[4]:3d} {f[5]:+6.1f}% t={f[6]:+.2f}")
    for f in sup:
        print(f"  SUPERVIVIENTE (cuarentena): {f}")


if __name__ == "__main__":
    main()
