"""¿Quien define mas el total de un partido: el equipo de partidos ALTOS o el
de partidos BAJOS? (pregunta del usuario, 2026-08-31)

Formulacion: si A suele jugar partidos de 200 y B de 150, ¿el total final se
pega mas al 200 o al 150? Se estima por MINIMOS CUADRADOS:

    total_final = a + b1*hist_A + b2*hist_B

Si b1 == b2, mandan por igual (el total es la media de ambos). Si b1 > b2,
manda mas A.

HISTORIAL SIN MIRAR AL FUTURO: la media de totales de cada equipo se calcula
SOLO con sus partidos ANTERIORES (>=MIN_PREV), recorriendo por fecha.

TRES ETIQUETADOS, y el orden importa:
 1. RAPIDO/LENTO -- el unico conocible ANTES del partido, y por tanto el
    unico que responde a la pregunta de forma utilizable.
 2. FAVORITO/UNDERDOG -- tambien ex ante (cuota de cierre), por si el que
    manda es el bueno y no el rapido.
 3. GANADOR/PERDEDOR -- la version literal de la pregunta. AVISO: esta
    etiqueta se conoce solo AL FINAL y esta contaminada por seleccion (quien
    anota mucho gana mas), asi que su coeficiente sale inflado por
    construccion. Se reporta para responder, no para apostar.

Se añade la LINEA de cierre como control: lo relevante para apostar no es si
el historial predice el total (obvio), sino si aporta algo que la linea no
tenga ya.
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics
import sys
from collections import defaultdict, deque

import numpy as np

sys.path.insert(0, ".")

MIN_PREV = 8


def ols(y, X, nombres):
    X = np.column_stack([np.ones(len(y))] + X)
    y = np.asarray(y, float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    s2 = resid @ resid / (n - k)
    se = np.sqrt(np.diag(s2 * np.linalg.pinv(X.T @ X)))
    r2 = 1 - (resid @ resid) / ((y - y.mean()) @ (y - y.mean()))
    return beta, se, r2, n, nombres


def imprimir(titulo, res):
    beta, se, r2, n, nombres = res
    print(f"\n  {titulo}   n={n}  R2={r2:.3f}")
    for nom, b, s in zip(["intercepto"] + nombres, beta, se):
        t = b / s if s else 0
        print(f"    {nom:26s} {b:+8.3f}  (se {s:.3f}, t={t:+6.1f})")


def cargar(db, ligas=None):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    lineas = defaultdict(list)
    for r in conn.execute("SELECT event_id, line FROM bball_odds WHERE market='18_3' "
                          "AND snapshot='kickoff' AND line IS NOT NULL"):
        lineas[r["event_id"]].append(float(r["line"]))
    cuotas = {}
    for r in conn.execute("SELECT event_id, book, over_odds, under_odds FROM bball_odds "
                          "WHERE market='18_3' AND snapshot='kickoff'"):
        pass
    juegos = []
    for g in conn.execute("SELECT event_id, league_name, date, home_team, away_team, "
                          "home_score, away_score FROM bball_games WHERE completed=1 "
                          "AND home_team IS NOT NULL ORDER BY date"):
        if ligas and g["league_name"] not in ligas:
            continue
        fin = (g["home_score"] or 0) + (g["away_score"] or 0)
        if fin <= 0 or g["home_score"] == g["away_score"]:
            continue
        ls = lineas.get(g["event_id"])
        juegos.append(dict(
            lg=g["league_name"], fecha=g["date"], home=g["home_team"], away=g["away_team"],
            fin=float(fin), gano_local=(g["home_score"] > g["away_score"]),
            linea=statistics.median(ls) if ls else None))
    conn.close()
    return juegos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data_local/bball_local.db")
    ap.add_argument("--ligas", nargs="*", default=["NBA", "WNBA", "Euroleague"])
    args = ap.parse_args()

    for lg in args.ligas:
        juegos = cargar(args.db, {lg})
        hist = defaultdict(list)
        filas = []
        for j in juegos:
            hh, ha = hist[j["home"]], hist[j["away"]]
            if len(hh) >= MIN_PREV and len(ha) >= MIN_PREV:
                mh, ma = statistics.mean(hh), statistics.mean(ha)
                filas.append(dict(fin=j["fin"], mh=mh, ma=ma, linea=j["linea"],
                                  gano_local=j["gano_local"]))
            hist[j["home"]].append(j["fin"])
            hist[j["away"]].append(j["fin"])
        if len(filas) < 100:
            print(f"\n===== {lg}: solo {len(filas)} partidos con historial suficiente -- se omite")
            continue
        print(f"\n{'='*78}\n{lg}: ¿quien manda en el total?  ({len(filas)} partidos con >= {MIN_PREV} previos cada equipo)\n{'='*78}")

        rap = [max(f["mh"], f["ma"]) for f in filas]
        len_ = [min(f["mh"], f["ma"]) for f in filas]
        y = [f["fin"] for f in filas]
        imprimir("1. RAPIDO vs LENTO (ex ante, el que vale)",
                 ols(y, [rap, len_], ["hist del RAPIDO", "hist del LENTO"]))

        gan = [f["mh"] if f["gano_local"] else f["ma"] for f in filas]
        per = [f["ma"] if f["gano_local"] else f["mh"] for f in filas]
        imprimir("3. GANADOR vs PERDEDOR (literal, CONTAMINADA por seleccion)",
                 ols(y, [gan, per], ["hist del GANADOR", "hist del PERDEDOR"]))

        con_linea = [f for f in filas if f["linea"]]
        if len(con_linea) >= 100:
            y2 = [f["fin"] for f in con_linea]
            imprimir("4. ¿aporta algo sobre la LINEA de cierre?",
                     ols(y2, [[f["linea"] for f in con_linea],
                              [max(f["mh"], f["ma"]) for f in con_linea],
                              [min(f["mh"], f["ma"]) for f in con_linea]],
                         ["linea de cierre", "hist del RAPIDO", "hist del LENTO"]))


if __name__ == "__main__":
    main()
