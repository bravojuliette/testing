"""PRE-REGISTRO: BARRIDO MASIVO del espacio de estados EN VIVO (totales),
con protocolo busqueda/reserva. Commiteado antes de correrlo.

Peticion del usuario: "¿y filtrando por algun criterio masivo?" -- la unica
version aun no hecha del filtrado masivo, porque estos datos (historial en
vivo) no existian hasta hoy.

PREDICCION DEL AUTOR, escrita antes de mirar (para poder juzgarla): la
busqueda producira celdas espectaculares y la reserva las matara; ninguna
regla sobrevivira el doble liston. Si me equivoco, mejor.

DATOS: data_local/bball_local.db (NBA/WNBA/Euroleague, series 18_3).

MUESTREO SIN MIRAR AL FUTURO: para cada partido, fotos en offsets fijos de
reloj de pared (+10 a +120 min desde el inicio, cada 5): la ULTIMA entrada
conocida a esa hora (el precio vigente en ese momento -- apostable, sin
bola de cristal), solo si esta en juego (con ss) y cuotas en [1.01, 20].

REGLAS = producto cartesiano de rasgos del estado (por lado over/under):
- liga (NBA / WNBA / Euroleague)
- fase por reloj: 10-30 / 30-60 / 60-90 / 90-120 min
- delta = linea_viva - linea_cierre: <=-6 / (-6,-2] / (-2,2) / [2,6) / >=6
- |margen| del marcador: 0-5 / 6-12 / 13+ (simetrico: inmune a orientacion)
- tercil de la linea de cierre POR LIGA (cortes calculados SOLO en busqueda)
- lado: over / under a la cuota real de la foto
= 3*4*5*3*3*2 = 2160 reglas. Por (partido, regla) cuenta solo la PRIMERA
foto que matchea (una apuesta por partido y regla, ejecutable en secuencia).

SPLIT POR FECHA (declarado): busqueda = partidos con fecha < 2026-01-01;
reserva = >= 2026-01-01. Liquidacion contra el total final del partido;
push fuera.

LISTON (declarado): con 2160 reglas el azar promete max|t| ~ sqrt(2 ln N)
~ 3.9 en busqueda y ~5% de falsos t>=2. SUPERVIVIENTE = ROI>0 y t>=2 en
BUSQUEDA y ADEMAS ROI>0 y t>=2 en RESERVA, con n>=50 en cada mitad. Se
reporta tambien corr(ROI busqueda, ROI reserva) y el conteo de falsos
esperados vs observados.

ENMIENDA 1 (declarada tras ver SOLO la pasada fina, antes de correr la
gruesa): la malla de 2160 reglas fragmenta tanto que solo 8 alcanzan n>=50
por mitad (resultado de la fina: 0 candidatas, medias -6.6%/-6.5%, corr
-0.39). Se añade una PASADA GRUESA con potencia real: liga x fase(2:
<=60min / >60min) x delta(5) x |margen|(3) x lado = 180 reglas, sin tercil
de linea. Mismo doble liston; con 180 reglas y el doble filtro, la
probabilidad de UN falso superviviente es ~11%: un unico superviviente
marginal seguiria siendo sospechoso y exigiria replica (NCAA/chicas).

RESULTADOS: se anexan tras correr, sin tocar lo de arriba.
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
from bball.analysis.sobre_reaccion_q1 import BOOKS, LIGAS, suma_ss, t_pnl

CORTE_RESERVA = "2026-01-01"
OFFSETS = range(10, 121, 5)


def partes(ss):
    s = str(ss or "")
    sep = ":" if ":" in s else "-"
    a, _, b = s.partition(sep)
    try:
        return int(a), int(b)
    except ValueError:
        return None


def bucket_delta(d):
    if d <= -6: return "d<=-6"
    if d <= -2: return "d-6..-2"
    if d < 2: return "d-2..2"
    if d < 6: return "d2..6"
    return "d>=6"


def bucket_margen(m):
    if m <= 5: return "m0-5"
    if m <= 12: return "m6-12"
    return "m13+"


def bucket_fase(off, gruesa=False):
    if gruesa:
        return "f<=60" if off <= 60 else "f>60"
    if off <= 30: return "f10-30"
    if off <= 60: return "f30-60"
    if off <= 90: return "f60-90"
    return "f90-120"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data_local/bball_local.db")
    ap.add_argument("--gruesa", action="store_true")
    args = ap.parse_args()
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    kick: dict[str, dict] = defaultdict(dict)
    for r in conn.execute(
        "SELECT event_id, book, line FROM bball_odds WHERE market=? AND snapshot='kickoff'",
        (config.TOTALS_MARKET_KEY,)):
        kick[r["event_id"]][r["book"]] = r["line"]

    juegos = []
    for g in conn.execute(
        "SELECT event_id, league_name, date, time_ts, home_score, away_score FROM bball_games WHERE completed=1"):
        if g["league_name"] not in LIGAS:
            continue
        L = next((kick[g["event_id"]][b] for b in BOOKS if b in kick.get(g["event_id"], {})), None)
        fin = (g["home_score"] or 0) + (g["away_score"] or 0)
        if L is None or fin <= 0 or not g["time_ts"]:
            continue
        juegos.append((g["event_id"], g["league_name"], g["date"], int(g["time_ts"]), float(L), float(fin)))

    # terciles de linea de cierre POR LIGA, cortes SOLO con busqueda
    cortes = {}
    for lg in LIGAS:
        ls = sorted(L for _, l2, d, _, L, _ in juegos if l2 == lg and d < CORTE_RESERVA)
        if len(ls) >= 30:
            cortes[lg] = (ls[len(ls) // 3], ls[2 * len(ls) // 3])

    series: dict[str, list] = defaultdict(list)
    for r in conn.execute(
        "SELECT event_id, add_time, ss, line, over_odds, under_odds FROM bball_odds_hist "
        "WHERE market=? AND add_time IS NOT NULL AND line IS NOT NULL AND ss IS NOT NULL",
        (config.TOTALS_MARKET_KEY,)):
        series[r["event_id"]].append((r["add_time"], r["ss"], r["line"], r["over_odds"], r["under_odds"]))
    conn.close()

    celdas: dict[tuple, dict] = defaultdict(lambda: {"s": [], "r": []})
    for eid, lg, fecha, ts, L, fin in juegos:
        if lg not in cortes:
            continue
        ser = sorted(series.get(eid) or [])
        if not ser:
            continue
        mitad = "s" if fecha < CORTE_RESERVA else "r"
        c1, c2 = cortes[lg]
        terc = "Lbaja" if L < c1 else ("Lalta" if L >= c2 else "Lmedia")
        vistos = set()
        i = 0
        for off in OFFSETS:
            tope = ts + off * 60
            while i + 1 < len(ser) and ser[i + 1][0] <= tope:
                i += 1
            add_t, ss, viva, ov, un = ser[i]
            if add_t > tope or add_t < ts:
                continue
            p = partes(ss)
            if p is None or not (ov and un and 1.01 <= ov <= 20 and 1.01 <= un <= 20):
                continue
            base = ((lg, bucket_fase(off, True), bucket_delta(viva - L), bucket_margen(abs(p[0] - p[1])))
                    if args.gruesa else
                    (lg, bucket_fase(off), bucket_delta(viva - L), bucket_margen(abs(p[0] - p[1])), terc))
            for lado, od in (("over", ov), ("under", un)):
                clave = base + (lado,)
                if (eid, clave) in vistos or fin == viva:
                    continue
                vistos.add((eid, clave))
                gana = (fin > viva) if lado == "over" else (fin < viva)
                celdas[clave][mitad].append((od - 1.0) if gana else -1.0)

    filas = []
    for clave, d in celdas.items():
        if len(d["s"]) < 50 or len(d["r"]) < 50:
            continue
        rs, ts_ = statistics.mean(d["s"]) * 100, t_pnl(d["s"])
        rr, tr = statistics.mean(d["r"]) * 100, t_pnl(d["r"])
        filas.append((clave, len(d["s"]), rs, ts_, len(d["r"]), rr, tr))

    print(f"reglas con n>=50 en ambas mitades: {len(filas)} (de 2160 posibles)")
    cand = [f for f in filas if f[2] > 0 and f[3] >= 2]
    print(f"candidatas en BUSQUEDA (ROI>0, t>=2): {len(cand)}  |  falsos esperados por azar ~{len(filas)*0.025:.0f}")
    sup = [f for f in cand if f[5] > 0 and f[6] >= 2]
    print(f"SUPERVIVIENTES (ademas ROI>0 y t>=2 en RESERVA): {len(sup)}")
    if len(filas) >= 3:
        xs = [f[2] for f in filas]; ys = [f[5] for f in filas]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        den = math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
        print(f"corr(ROI busqueda, ROI reserva) = {num/den:+.3f}" if den else "corr indefinida")
        print(f"ROI medio de todas las reglas: busqueda {statistics.mean(xs):+.1f}% | reserva {statistics.mean(ys):+.1f}%")
    print("\ntop-10 de busqueda y su suerte en reserva:")
    for clave, ns, rs, ts_, nr, rr, tr in sorted(filas, key=lambda f: -f[3])[:10]:
        print(f"  {'/'.join(clave):48s} S: n={ns:4d} {rs:+6.1f}% t={ts_:+.2f} | R: n={nr:4d} {rr:+6.1f}% t={tr:+.2f}")
    for f in sup:
        print(f"  SUPERVIVIENTE: {f}")


if __name__ == "__main__":
    main()
