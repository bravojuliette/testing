"""Implementa PREREGISTRO_patron_cuartos.md -- commiteado antes de correr.

Datos: data_local/bball_local.db (NBA + Euroleague; WNBA excluida, mismo
motivo que remontadas_q1.py). OJO con las claves del JSON de marcadores
(ver pre-registro): "1"=Q1, "2"=Q2, "3"=DESCANSO acumulado (NO es Q3),
"4"=Q3 real, "5"=Q4 real, "6"=prorroga.

RESULTADOS (2026-08-31, corrido tal cual; puertas de favorito PASAN en
ambas ligas: NBA 63.1%, Euroleague 61.9%; n=2933 partidos con Q1-Q3 y ML
vivo capturado tras el Q3):

1. PRIMARIO (hipotesis exacta del usuario: patron L-W-W, empatado tras
   Q3, comprar el ML vivo de ese equipo) -- REFUTADO en las 4 celdas
   declaradas (2 ligas x 2 umbrales), robusto a ambas capturas:
     NBA    favorito: +2.6%/-1.9% (t<0.3, ruido)
     NBA    underdog: -12.3%/-11.0% (t=-0.84/-0.94)
     Euro   favorito: -5.5%/-7.5% (t<0.7, ruido)
     Euro   underdog: -1.9%/-14.5% (t<1.0, ruido)
   La sospecha especifica del usuario (que el ROI estuviera del lado
   underdog) sale en la direccion CONTRARIA: el underdog con este patron
   pierde mas, no menos. Ninguna celda cerca de t=2 en ninguna direccion.

2. SECUNDARIO (barrido de 8 patrones x margen x liga x favorito/dog,
   busqueda/reserva por mediana de fecha): 20/128 celdas con n>=50 en
   ambas mitades (potencia limitada, como siempre en este proyecto).
   1 candidata en busqueda (NBA/WWW/no_tied/fav: +4.1%, t=+6.23) --
   exactamente lo que predice el azar con 20 celdas (~0.5 esperadas) --
   y muere en reserva (-0.2%, t=-0.08). 0 SUPERVIVIENTES del doble filtro.
   Nota honesta: NBA/LWL/tied/dog dio +47.1% t=+2.36 en RESERVA, pero
   +15.1% t=+0.63 en BUSQUEDA (no pasa el liston ahi) -- por protocolo
   pre-registrado (t>=2 en AMBAS mitades) no cuenta como superviviente,
   aunque tiente. Se deja escrito para que quede claro que no se ignoro.

VEREDICTO: "el patron de cuartos predice al ganador" queda REFUTADO en
NBA/Euroleague con los datos disponibles. Ni el patron exacto propuesto
por el usuario ni ningun otro de los 8 posibles sobrevive el doble
filtro. Frente cerrado, sin rescates de subgrupo mas alla de lo declarado.
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
from bball.analysis.sobre_reaccion_q1 import suma_ss, t_pnl

VENTANA = (35 * 60, 150 * 60)
LIGAS_ML = ("NBA", "Euroleague")
QKEYS = ("1", "2", "4")  # Q1, Q2, Q3 reales (ver nota de cabecera)

# Añadido pre-registrado: los tres puntos de decision, cada uno con su
# ventana de reloj de pared y cuantos cuartos usa el patron
PUNTOS = (
    ("Q1", 1, (8 * 60, 80 * 60)),
    ("Q2", 2, (20 * 60, 110 * 60)),
    ("Q3", 3, (35 * 60, 150 * 60)),
)


def cargar(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    series: dict[str, list] = defaultdict(list)
    for r in conn.execute(
        "SELECT event_id, add_time, ss, home_odds, away_odds FROM bball_odds_hist "
        "WHERE market=? AND add_time IS NOT NULL", (config.MONEYLINE_MARKET_KEY,)):
        series[r["event_id"]].append(r)

    juegos = []
    n_sin_q = 0
    for g in conn.execute(
        "SELECT event_id, league_name, date, time_ts, home_score, away_score, raw_json "
        "FROM bball_games WHERE completed=1"):
        lg = g["league_name"]
        if lg not in LIGAS_ML:
            continue
        try:
            sc = json.loads(g["raw_json"]).get("scores") or {}
            qh = [int(sc[k]["home"]) for k in QKEYS]
            qa = [int(sc[k]["away"]) for k in QKEYS]
        except (KeyError, TypeError, ValueError):
            n_sin_q += 1
            continue
        ts = int(g["time_ts"] or 0)
        ser = series.get(g["event_id"]) or []
        pre = [e for e in ser if e["add_time"] < ts - 60 and not e["ss"]
               and e["home_odds"] and e["away_odds"]]
        if not pre:
            continue
        cierre = max(pre, key=lambda e: e["add_time"])

        invertida = lg.upper() in {n.upper() for n in config.AWAY_FIRST_LEAGUES}
        # qh/qa vienen en orden CRUDO del feed; si invertida, qh=visitante real, qa=local real
        q_local = qa if invertida else qh
        q_visit = qh if invertida else qa

        j = dict(
            lg=lg, ts=ts, fecha=g["date"], invertida=invertida,
            gano_local=(g["home_score"] or 0) > (g["away_score"] or 0),
            cierre=cierre, q_local=q_local, q_visit=q_visit,
            margen_local=sum(q_local) - sum(q_visit),
        )
        # captura de ML en cada punto de decision (añadido pre-registrado)
        for nombre, nq, vent in PUNTOS:
            objetivo = sum(q_local[:nq]) + sum(q_visit[:nq])
            vivo = [e for e in ser if suma_ss(e["ss"]) == objetivo
                    and ts + vent[0] <= e["add_time"] <= ts + vent[1]
                    and e["home_odds"] and e["away_odds"]
                    and 1.01 <= e["home_odds"] <= 30 and 1.01 <= e["away_odds"] <= 30]
            if vivo:
                j[f"ult_{nombre}"] = max(vivo, key=lambda e: e["add_time"])
                j[f"pri_{nombre}"] = min(vivo, key=lambda e: e["add_time"])
        # compat con el barrido original (tras Q3)
        if "ult_Q3" in j:
            j["ult"], j["pri"] = j["ult_Q3"], j["pri_Q3"]
        if any(f"ult_{n}" in j for n, _, _ in PUNTOS):
            juegos.append(j)
    conn.close()
    return juegos, n_sin_q


def lado_real(entry, invertida, lado):
    if lado == "local":
        return entry["away_odds"] if invertida else entry["home_odds"]
    return entry["home_odds"] if invertida else entry["away_odds"]


def patron(qs_foco, qs_rival):
    """WLL/etc para el equipo foco en Q1-Q3; None si algun cuarto empata."""
    letras = []
    for a, b in zip(qs_foco, qs_rival):
        if a == b:
            return None
        letras.append("W" if a > b else "L")
    return "".join(letras)


def bucket_margen(m, corte):
    return "tied" if abs(m) <= corte else "no_tied"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data_local/bball_local.db")
    args = ap.parse_args()
    juegos, n_sin_q = cargar(args.db)
    print(f"cargados {len(juegos)} partidos con Q1-Q3 + ML vivo tras Q3 "
          f"(descartados {n_sin_q} sin datos de cuarto)")

    for lg in LIGAS_ML:
        js = [j for j in juegos if j["lg"] == lg]
        if not js:
            print(f"\n{lg}: sin datos"); continue
        fav_ok = sum(1 for j in js if
                     (lado_real(j["cierre"], j["invertida"], "local") <
                      lado_real(j["cierre"], j["invertida"], "visit")) == j["gano_local"])
        pf = fav_ok / len(js) * 100
        gate = 58 <= pf <= 78
        print(f"\n===== {lg}: n={len(js)} | puerta favorito gana {pf:.1f}% "
              f"[{'PASA' if gate else 'FALLA -> ABORTADO'}]")
        if not gate:
            continue

        # ===== PRIMARIO: patron L-W-W, tied<=3 / <=5, favorito vs underdog =====
        print("  -- PRIMARIO: patron L-W-W (usuario), local y visitante como equipo foco --")
        for cap in ("ult", "pri"):
            for corte in (3, 5):
                filas_fv, filas_dog = [], []
                for j in js:
                    if cap not in j:
                        continue
                    for foco, riv, lado_foco in (("local", "visit", True), ("visit", "local", False)):
                        qs_f = j["q_local"] if foco == "local" else j["q_visit"]
                        qs_r = j["q_visit"] if foco == "local" else j["q_local"]
                        pat = patron(qs_f, qs_r)
                        if pat != "LWW":
                            continue
                        m = j["margen_local"] if foco == "local" else -j["margen_local"]
                        if abs(m) > corte:
                            continue
                        od_cierre_f = lado_real(j["cierre"], j["invertida"], foco)
                        od_cierre_r = lado_real(j["cierre"], j["invertida"], riv)
                        es_favorito = od_cierre_f < od_cierre_r
                        od = lado_real(j[cap], j["invertida"], foco)
                        gano_foco = j["gano_local"] == lado_foco
                        pnl = (od - 1.0) if gano_foco else -1.0
                        (filas_fv if es_favorito else filas_dog).append(pnl)
                for etiqueta, pnls in (("favorito", filas_fv), ("underdog", filas_dog)):
                    if pnls:
                        print(f"    [{cap}] tied<={corte} {etiqueta:9s}: n={len(pnls):4d} "
                              f"ROI={statistics.mean(pnls)*100:+6.1f}% t={t_pnl(pnls):+.2f} "
                              f"acierto={sum(1 for p in pnls if p>0)/len(pnls)*100:.0f}%")
                    else:
                        print(f"    [{cap}] tied<={corte} {etiqueta:9s}: n=0")

    # ===== SECUNDARIO: barrido 8 patrones x 2 buckets margen x liga x fav/dog x lado =====
    print("\n===== SECUNDARIO: barrido de 8 patrones (busqueda/reserva) =====")
    cortes_fecha = {}
    for lg in LIGAS_ML:
        fechas = sorted(j["fecha"] for j in juegos if j["lg"] == lg)
        if fechas:
            cortes_fecha[lg] = fechas[len(fechas) // 2]
    print("cortes búsqueda/reserva (mediana de fecha por liga):", cortes_fecha)

    celdas: dict[tuple, dict] = defaultdict(lambda: {"s": [], "r": []})
    for j in juegos:
        if "ult" not in j or j["lg"] not in cortes_fecha:
            continue
        mitad = "s" if j["fecha"] < cortes_fecha[j["lg"]] else "r"
        for foco, riv, lado_foco in (("local", "visit", True), ("visit", "local", False)):
            qs_f = j["q_local"] if foco == "local" else j["q_visit"]
            qs_r = j["q_visit"] if foco == "local" else j["q_local"]
            pat = patron(qs_f, qs_r)
            if pat is None:
                continue
            m = j["margen_local"] if foco == "local" else -j["margen_local"]
            mb = bucket_margen(m, 5)
            od_cierre_f = lado_real(j["cierre"], j["invertida"], foco)
            od_cierre_r = lado_real(j["cierre"], j["invertida"], riv)
            fav_dog = "fav" if od_cierre_f < od_cierre_r else "dog"
            od = lado_real(j["ult"], j["invertida"], foco)
            gano_foco = j["gano_local"] == lado_foco
            pnl = (od - 1.0) if gano_foco else -1.0
            clave = (j["lg"], pat, mb, fav_dog)
            celdas[clave][mitad].append(pnl)

    filas = []
    for clave, d in celdas.items():
        if len(d["s"]) < 50 or len(d["r"]) < 50:
            continue
        rs, ts_ = statistics.mean(d["s"]) * 100, t_pnl(d["s"])
        rr, tr = statistics.mean(d["r"]) * 100, t_pnl(d["r"])
        filas.append((clave, len(d["s"]), rs, ts_, len(d["r"]), rr, tr))
    print(f"celdas con n>=50 en ambas mitades: {len(filas)} (de hasta 128 posibles)")
    cand = [f for f in filas if f[2] > 0 and f[3] >= 2]
    print(f"candidatas en BUSQUEDA (ROI>0, t>=2): {len(cand)} | falsos esperados ~{len(filas)*0.025:.1f}")
    sup = [f for f in cand if f[5] > 0 and f[6] >= 2]
    print(f"SUPERVIVIENTES (ademas ROI>0 y t>=2 en RESERVA): {len(sup)}")
    print("\ntop-10 de busqueda:")
    for clave, ns, rs, ts_, nr, rr, tr in sorted(filas, key=lambda f: -f[3])[:10]:
        print(f"  {'/'.join(clave):32s} S: n={ns:4d} {rs:+6.1f}% t={ts_:+.2f} | R: n={nr:4d} {rr:+6.1f}% t={tr:+.2f}")
    for f in sup:
        print(f"  SUPERVIVIENTE (cuarentena): {f}")

    barrido_completo(juegos, cortes_fecha)


def barrido_completo(juegos, cortes_fecha):
    """Añadido pre-registrado: los TRES puntos de decision (tras Q1/Q2/Q3),
    patrones de 1/2/3 letras, mismos estados de margen y doble filtro."""
    print("\n===== COMPLETO: barrido en los 3 puntos de decision (tras Q1/Q2/Q3) =====")
    celdas: dict[tuple, dict] = defaultdict(lambda: {"s": [], "r": []})
    for j in juegos:
        if j["lg"] not in cortes_fecha:
            continue
        mitad = "s" if j["fecha"] < cortes_fecha[j["lg"]] else "r"
        for nombre, nq, _ in PUNTOS:
            cap = f"ult_{nombre}"
            if cap not in j:
                continue
            for foco, riv, lado_foco in (("local", "visit", True), ("visit", "local", False)):
                qs_f = (j["q_local"] if foco == "local" else j["q_visit"])[:nq]
                qs_r = (j["q_visit"] if foco == "local" else j["q_local"])[:nq]
                pat = patron(qs_f, qs_r)
                if pat is None:
                    continue
                m = sum(qs_f) - sum(qs_r)
                mb = "tied" if abs(m) <= 5 else ("delante" if m > 5 else "detras")
                od_f = lado_real(j["cierre"], j["invertida"], foco)
                od_r = lado_real(j["cierre"], j["invertida"], riv)
                fav_dog = "fav" if od_f < od_r else "dog"
                od = lado_real(j[cap], j["invertida"], foco)
                gano_foco = j["gano_local"] == lado_foco
                pnl = (od - 1.0) if gano_foco else -1.0
                celdas[(j["lg"], nombre, pat, mb, fav_dog)][mitad].append(pnl)

    filas = []
    for clave, d in celdas.items():
        todo = d["s"] + d["r"]
        if len(todo) < 30:
            continue
        filas.append((clave, len(d["s"]),
                      statistics.mean(d["s"]) * 100 if d["s"] else 0, t_pnl(d["s"]),
                      len(d["r"]),
                      statistics.mean(d["r"]) * 100 if d["r"] else 0, t_pnl(d["r"]),
                      len(todo), statistics.mean(todo) * 100, t_pnl(todo)))
    con_pot = [f for f in filas if f[1] >= 50 and f[4] >= 50]
    print(f"celdas listadas (n>=30 total): {len(filas)} | con potencia (n>=50 por mitad): {len(con_pot)}")
    cand = [f for f in con_pot if f[2] > 0 and f[3] >= 2]
    sup = [f for f in cand if f[5] > 0 and f[6] >= 2]
    print(f"candidatas en BUSQUEDA: {len(cand)} | falsos esperados ~{len(con_pot)*0.025:.1f} | SUPERVIVIENTES: {len(sup)}")
    for f in sup:
        print(f"  SUPERVIVIENTE (cuarentena): {f[0]} S: n={f[1]} {f[2]:+.1f}% t={f[3]:+.2f} | R: n={f[4]} {f[5]:+.1f}% t={f[6]:+.2f}")
    print("\ntabla completa (orden: liga, punto, patron, estado, lado):")
    for clave, ns, rs, ts_, nr, rr, tr, nt, rt, tt in sorted(filas):
        marca = " *" if ns >= 50 and nr >= 50 and rs > 0 and ts_ >= 2 else ""
        print(f"  {'/'.join(clave):34s} n={nt:4d} ROI={rt:+6.1f}% t={tt:+5.2f} | S {rs:+6.1f}%/R {rr:+6.1f}%{marca}")


if __name__ == "__main__":
    main()
