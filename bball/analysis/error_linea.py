"""¿Por cuantos puntos se equivoca la linea de totales en cada competicion?

Pregunta del usuario (2026-08-31): "en FIBA cuanto suele diferir el resultado
final de la linea de puntos inicial... y eso con todas las competiciones".

DESCRIPTIVO, no es un test de apuesta: no hay criterio de confirmacion ni
pre-registro porque no se propone ninguna jugada. Es el MAPA de precision
del mercado por competicion -- donde la linea es mas floja es donde, si
existe una grieta, seria mas facil que exista.

Linea usada: MEDIANA de las casas en el snapshot (mas robusta que elegir
una casa). Se reportan los dos momentos:
  - 'start'   = linea de APERTURA (la que pide el usuario).
  - 'kickoff' = linea de CIERRE (al pitido inicial).
Metricas por competicion:
  n, linea mediana, MAE = |final - linea| medio, mediana de |error|,
  sesgo = media de (final - linea)  [>0: el mercado se queda CORTO, los
  partidos acaban mas altos de lo que marca la linea],
  sd, % de partidos que fallan por >=10 y >=20 puntos, y el MAE relativo
  (MAE / linea) para poder comparar ligas de ritmos distintos.
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")


def cargar(db_path, snapshot):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    lineas = defaultdict(list)
    for r in conn.execute(
        "SELECT event_id, line FROM bball_odds WHERE market='18_3' AND snapshot=? AND line IS NOT NULL",
        (snapshot,)):
        lineas[r["event_id"]].append(float(r["line"]))
    out = defaultdict(list)
    for g in conn.execute(
        "SELECT event_id, league_name, home_score, away_score FROM bball_games WHERE completed=1"):
        ls = lineas.get(g["event_id"])
        fin = (g["home_score"] or 0) + (g["away_score"] or 0)
        if not ls or fin <= 0:
            continue
        out[g["league_name"]].append((statistics.median(ls), float(fin), len(ls)))
    conn.close()
    return out


def fila(lg, datos):
    err = [f - l for l, f, _ in datos]
    aerr = [abs(e) for e in err]
    lineas = [l for l, _, _ in datos]
    ncasas = statistics.median([c for _, _, c in datos])
    mae = statistics.mean(aerr)
    return dict(
        liga=lg, n=len(datos), linea=statistics.median(lineas), casas=ncasas,
        mae=mae, mediana_abs=statistics.median(aerr),
        sesgo=statistics.mean(err),
        sd=statistics.pstdev(err) if len(err) > 1 else 0.0,
        p10=sum(1 for a in aerr if a >= 10) / len(aerr) * 100,
        p20=sum(1 for a in aerr if a >= 20) / len(aerr) * 100,
        mae_rel=mae / statistics.median(lineas) * 100,
    )


def imprimir(titulo, filas, min_n):
    print(f"\n{'='*118}\n{titulo}  (solo competiciones con n>={min_n})\n{'='*118}")
    print(f"{'competicion':40s}{'n':>5s}{'linea':>7s}{'casas':>6s}{'MAE':>7s}{'med|e|':>7s}"
          f"{'sesgo':>7s}{'sd':>7s}{'>=10':>6s}{'>=20':>6s}{'MAE%':>6s}")
    for f in filas:
        print(f"{f['liga'][:39]:40s}{f['n']:5d}{f['linea']:7.1f}{f['casas']:6.0f}"
              f"{f['mae']:7.1f}{f['mediana_abs']:7.1f}{f['sesgo']:+7.1f}{f['sd']:7.1f}"
              f"{f['p10']:5.0f}%{f['p20']:5.0f}%{f['mae_rel']:5.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbs", nargs="+",
                    default=["data_local/bball_local.db", "data_local/bball_chicas.db"])
    ap.add_argument("--min-n", type=int, default=30)
    args = ap.parse_args()

    for snapshot, etq in (("start", "LINEA DE APERTURA"), ("kickoff", "LINEA DE CIERRE (al pitido)")):
        junto = defaultdict(list)
        for db in args.dbs:
            try:
                for lg, datos in cargar(db, snapshot).items():
                    junto[lg].extend(datos)
            except sqlite3.OperationalError as exc:
                print(f"[aviso] {db}: {exc}")
        filas = [fila(lg, d) for lg, d in junto.items() if len(d) >= args.min_n]
        filas.sort(key=lambda f: -f["mae"])
        imprimir(f"{etq}: por cuantos puntos se equivoca", filas, args.min_n)
        todo = [x for d in junto.values() for x in d]
        if todo:
            g = fila("TODAS JUNTAS", todo)
            print(f"\n  POOLED  n={g['n']}  MAE={g['mae']:.1f} pts  mediana|error|={g['mediana_abs']:.1f}  "
                  f"sesgo={g['sesgo']:+.1f}  sd={g['sd']:.1f}  |error|>=10 en {g['p10']:.0f}%  "
                  f">=20 en {g['p20']:.0f}%  MAE relativo={g['mae_rel']:.1f}%")


if __name__ == "__main__":
    main()
