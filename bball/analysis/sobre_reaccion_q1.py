"""PRE-REGISTRO EN CODIGO: ¿sobre-reacciona la linea viva tras el Q1?

Teoria del usuario (el origen de todo el scanner): tras un Q1 anormalmente
lento la linea viva del total cae DEMASIADO, y el over en vivo tiene valor
(espejo: under tras Q1 rapido). La fisica ya esta medida (cuartos.py): la
reversion es casi total -- un Q1 lento solo arrastra ~0.4 puntos en los 3
cuartos restantes. Lo que nunca pudimos medir es si el MERCADO en vivo lo
sabe. El historial /v2/event/odds (serie con cada cambio en vivo y marcador
`ss` por entrada) lo permite por fin.

Commiteado el 2026-08-30 con el run de recoleccion 33309869809 aun
in_progress: el volcado local no existe todavia fuera del runner, asi que
este criterio queda fijado SIN haber visto una sola linea viva historica.

DATOS (data_local/bball_local.db, gunzip del volcado publicado por el run):
- bball_games: marcador final y cuartos (raw_json.scores claves 1/2/4/5).
- bball_odds: linea de cierre L = snapshot 'kickoff', primera casa presente
  en el orden (Bet365, Betway, BWin) -- mismo criterio que los pre-registros
  anteriores. Sin ella, el partido queda fuera.
- bball_odds_hist mercado 18_3: serie viva (fuente por defecto de BetsAPI).
  Entrada 'fin de Q1' = la ULTIMA entrada cuya suma de `ss` es EXACTAMENTE
  P1 (total del Q1) con add_time en [inicio+8min, inicio+80min] y cuotas
  over/under en [1.01, 20]. La suma del marcador es monotona, asi que esas
  entradas son un tramo contiguo (el descanso Q1/Q2 incluido) y la ultima es
  una cuota realmente apostable en ese momento. Sin entrada valida -> fuera.

TESTS (NBA es la muestra principal; WNBA y Euroliga se reportan como
replicas independientes, no se suman):

A. PRIMARIO -- calibracion de la linea viva, sin modelo propio de por medio:
   regresion OLS de (final - linea_viva) sobre la sorpresa del Q1
   (P1 - L/4). Si la linea viva digiere bien el Q1, beta ~ 0.
   - SOBRE-REACCION (teoria del usuario) si beta < 0 con t <= -2: tras Q1
     lento la linea cae de mas y el final la supera.
   - SUB-REACCION (señal contraria, tambien explotable: seguir al marcador)
     si beta > 0 con t >= 2.
   - En otro caso: la linea viva esta bien calibrada -> teoria REFUTADA.
   beta no depende de las constantes de mi valor justo: una mala calibracion
   mia mueve el intercepto, no el signo de la pendiente.

B. SECUNDARIO -- version apostable, cuotas reales de la entrada usada:
   - Q1 lento (P1 <= L/4 - 6, umbral heredado de cuartos.py): OVER a la
     linea/cuota viva de la entrada.
   - Q1 rapido (P1 >= L/4 + 6): UNDER.
   Push (final == linea) no cuenta. CONFIRMADA una pata si ROI > 0 y t >= 2
   con n >= 100; NO CONCLUYENTE con n < 100; REFUTADA en el resto.

DESCRIPTIVO (sin peso en el veredicto): exceso de la linea viva frente al
valor justo F = P1 + 0.75*L - 0.86 + 0.067*(P1 - L/4) (reversion medida:
~0.4 pts de arrastre por deficit de 6).

Uso: python bball/analysis/sobre_reaccion_q1.py [--db data_local/bball_local.db]
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

BOOKS = ("Bet365", "Betway", "BWin")
LIGAS = ("NBA", "WNBA", "Euroleague")
UMBRAL = 6.0
VENTANA = (8 * 60, 80 * 60)


def ols(xs: list[float], ys: list[float]):
    n = len(xs)
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0 or n < 3:
        return None
    beta = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    alfa = my - beta * mx
    resid = [y - (alfa + beta * x) for x, y in zip(xs, ys)]
    s2 = sum(r * r for r in resid) / (n - 2)
    se = math.sqrt(s2 / sxx) if s2 > 0 else float("inf")
    return beta, alfa, (beta / se if se > 0 else 0.0), n


def t_pnl(pnls: list[float]):
    n = len(pnls)
    if n < 2:
        return 0.0
    sd = statistics.pstdev(pnls)
    return statistics.mean(pnls) / sd * math.sqrt(n) if sd > 0 else 0.0


def suma_ss(ss: str | None):
    if not ss or "-" not in str(ss):
        return None
    a, _, b = str(ss).partition("-")
    try:
        return int(a) + int(b)
    except ValueError:
        return None


def cargar(db_path: str):
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

    filas = []
    stats = {"partidos": 0, "sin_linea": 0, "sin_cuartos": 0, "sin_entrada_viva": 0}
    for g in conn.execute(
        "SELECT event_id, league_name, date, time_ts, home_score, away_score, raw_json "
        "FROM bball_games WHERE completed=1"):
        lg = g["league_name"]
        if lg not in LIGAS:
            continue
        stats["partidos"] += 1
        L = next((kick[g["event_id"]][b] for b in BOOKS if b in kick.get(g["event_id"], {})), None)
        if L is None:
            stats["sin_linea"] += 1
            continue
        try:
            sc = json.loads(g["raw_json"]).get("scores") or {}
            p1 = int(sc["1"]["home"]) + int(sc["1"]["away"])
            qtot = sum(int(sc[k]["home"]) + int(sc[k]["away"]) for k in ("1", "2", "4", "5"))
        except (KeyError, TypeError, ValueError):
            stats["sin_cuartos"] += 1
            continue
        final = (g["home_score"] or 0) + (g["away_score"] or 0)
        if final <= 0 or qtot > final:  # cuartos incoherentes con el final (prorroga aparte)
            stats["sin_cuartos"] += 1
            continue
        ts = int(g["time_ts"] or 0)
        cand = [e for e in series.get(g["event_id"], [])
                if suma_ss(e["ss"]) == p1
                and ts + VENTANA[0] <= e["add_time"] <= ts + VENTANA[1]
                and e["over_odds"] and e["under_odds"]
                and 1.01 <= e["over_odds"] <= 20 and 1.01 <= e["under_odds"] <= 20]
        if not cand:
            stats["sin_entrada_viva"] += 1
            continue
        e = max(cand, key=lambda r: r["add_time"])
        filas.append(dict(lg=lg, L=float(L), p1=float(p1), final=float(final),
                          viva=float(e["line"]), over=float(e["over_odds"]),
                          under=float(e["under_odds"])))
    conn.close()
    return filas, stats


def informe(filas: list[dict], lg: str):
    fs = [f for f in filas if f["lg"] == lg]
    print(f"\n===== {lg}: {len(fs)} partidos con linea de cierre + entrada viva fin de Q1 =====")
    if len(fs) < 30:
        print("  n<30: sin potencia, se omite (NO CONCLUYENTE).")
        return
    xs = [f["p1"] - f["L"] / 4 for f in fs]
    ys = [f["final"] - f["viva"] for f in fs]
    r = ols(xs, ys)
    beta, alfa, t, n = r
    print(f"A. PRIMARIO  (final - linea_viva) ~ (P1 - L/4):  beta={beta:+.4f}  t={t:+.2f}  n={n}")
    if beta < 0 and t <= -2:
        ver = "SOBRE-REACCION: la teoria del usuario CONFIRMADA en este test"
    elif beta > 0 and t >= 2:
        ver = "SUB-REACCION: señal contraria (seguir al marcador, no contradecirlo)"
    else:
        ver = "linea viva bien calibrada -> teoria REFUTADA en este test"
    print(f"   veredicto A: {ver}")

    for nombre, cond, lado in (("Q1 LENTO -> OVER", lambda f: f["p1"] <= f["L"] / 4 - UMBRAL, "over"),
                               ("Q1 RAPIDO -> UNDER", lambda f: f["p1"] >= f["L"] / 4 + UMBRAL, "under")):
        sel = [f for f in fs if cond(f)]
        pnls = []
        for f in sel:
            if f["final"] == f["viva"]:
                continue
            gana = f["final"] > f["viva"] if lado == "over" else f["final"] < f["viva"]
            pnls.append((f[lado] - 1.0) if gana else -1.0)
        if not pnls:
            print(f"B. {nombre}: n=0")
            continue
        roi = statistics.mean(pnls) * 100
        t2 = t_pnl(pnls)
        est = ("CONFIRMADA" if roi > 0 and t2 >= 2 and len(pnls) >= 100
               else "NO CONCLUYENTE (n<100)" if len(pnls) < 100 else "REFUTADA")
        print(f"B. {nombre}: n={len(pnls)}  ROI={roi:+.1f}%  t={t2:+.2f}  -> {est}")

    exc = [f["viva"] - (f["p1"] + 0.75 * f["L"] - 0.86 + 0.067 * (f["p1"] - f["L"] / 4)) for f in fs]
    print(f"C. descriptivo: exceso linea_viva vs valor justo -- media {statistics.mean(exc):+.2f}, "
          f"sd {statistics.pstdev(exc):.2f} (positivo = mercado espera mas resto que la fisica)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data_local/bball_local.db")
    args = ap.parse_args()
    filas, stats = cargar(args.db)
    print(f"Cobertura: {stats}")
    for lg in LIGAS:
        informe(filas, lg)


if __name__ == "__main__":
    main()
