"""VEREDICTO de la confirmacion del LIDER en ligas chicas.
Implementa PREREGISTRO_lider_chicas.md (commiteado el 2026-08-31, antes de
que existieran los datos de septiembre que lo juzgan).

El candidato nacio como ESPEJO POST-HOC del bloque de remontadas de
veredicto_chicas.py (+4.3%, t=1.93, n=304) y quedo EN CUARENTENA. Este
script no reinventa el procedimiento: reutiliza cargar() y los helpers del
veredicto original, y aplica la regla congelada sin tocar un parametro.

Uso: python3 bball/analysis/veredicto_lider_chicas.py --db <ruta>
"""
from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball.analysis.sobre_reaccion_q1 import t_pnl
from bball.analysis.veredicto_chicas import cargar

GRANDES = ("NBA", "WNBA", "Euroleague", "NCAA")
UMBRAL_LIDER = 12          # fijado en el pre-registro, no se mueve
FAV_GATE = (58.0, 78.0)    # puerta declarada


def es_chica(lg: str | None) -> bool:
    """Todas las ligas reales salvo las grandes; sin videojuegos ni 3x3."""
    s = (lg or "").lower()
    if any(g.lower() in s for g in GRANDES):
        return False
    if any(x in s for x in ("esports", "e-sports", "cyber", "2k", "simulat", "3x3", "3 x 3")):
        return False
    return bool(s)


def celda(juegos, cap, umbral):
    pnls, cuotas = [], []
    for j in juegos:
        if cap not in j or j["m1"] == 0:
            continue
        if abs(j["m1"]) < umbral:
            continue
        obj_a = j["m1"] > 0                      # el LIDER tras el Q1
        od = j[cap]["home_odds"] if obj_a else j[cap]["away_odds"]
        pnls.append((od - 1.0) if j["gano_a"] == obj_a else -1.0)
        cuotas.append(od)
    return pnls, cuotas


def linea(nombre, pnls, cuotas):
    if not pnls:
        return f"  {nombre:<34} (sin apuestas)"
    roi = statistics.mean(pnls) * 100
    return (f"  {nombre:<34} n={len(pnls):<4} ROI={roi:+6.2f}% t={t_pnl(pnls):+5.2f} "
            f"acierto={sum(1 for p in pnls if p > 0)/len(pnls)*100:4.0f}% "
            f"cuota media={statistics.mean(cuotas):.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data_local/bball_chicas_sep.db")
    args = ap.parse_args()

    todos = cargar(args.db)
    juegos = [j for j in todos if es_chica(j["lg"])]
    con_ml = [j for j in juegos if "ml_cierre" in j and "ml_ult" in j]
    print(f"partidos cargados: {len(todos)} | ligas chicas: {len(juegos)} | "
          f"con ML de cierre y entrada viva Q1: {len(con_ml)}")
    print(f"ligas distintas: {len({j['lg'] for j in juegos})}")

    if not con_ml:
        print("\nVEREDICTO: NO CONCLUYENTE (sin muestra)")
        return

    # ---- PUERTA DEL FAVORITO (declarada): si falla, NO CONCLUYENTE ----
    fav_ok = sum(1 for j in con_ml
                 if (j["ml_cierre"]["home_odds"] < j["ml_cierre"]["away_odds"]) == j["gano_a"])
    pf = fav_ok / len(con_ml) * 100
    pasa = FAV_GATE[0] <= pf <= FAV_GATE[1]
    print(f"\nPUERTA DEL FAVORITO: gana {pf:.1f}% (exigido {FAV_GATE[0]}-{FAV_GATE[1]}%) -> "
          f"{'PASA' if pasa else 'FALLA'}")
    if not pasa:
        print("\nVEREDICTO: NO CONCLUYENTE (la muestra nueva no supera la puerta declarada)")
        return

    print(f"\n== LIDER tras el Q1 por >= {UMBRAL_LIDER}, al ML en vivo ==")
    res = {}
    for cap, et in (("ml_ult", "captura ULTIMA (primaria)"), ("ml_pri", "captura PRIMERA (sensibilidad)")):
        pnls, cuotas = celda(con_ml, cap, UMBRAL_LIDER)
        res[cap] = pnls
        print(linea(et, pnls, cuotas))

    print(f"\n  (referencia declarada, no decide) lider >= 8:")
    for cap, et in (("ml_ult", "ultima"), ("ml_pri", "primera")):
        pnls, cuotas = celda(con_ml, cap, 8)
        print(linea(f"    lider>=8 [{et}]", pnls, cuotas))

    # ---- VEREDICTO ----
    p = res["ml_ult"]
    n, roi, t = len(p), (statistics.mean(p) * 100 if p else 0.0), (t_pnl(p) if p else 0.0)
    ps = res["ml_pri"]
    roi_s = statistics.mean(ps) * 100 if ps else 0.0
    robusto = bool(p and ps and roi > 0 and roi_s > 0)

    print("\n" + "=" * 70)
    if n < 100:
        v = f"NO CONCLUYENTE por muestra (n={n} < 100)"
    elif roi > 0 and t >= 2 and robusto:
        v = f"CONFIRMADA (ROI {roi:+.2f}%, t={t:+.2f}, n={n}, robusta a ambas capturas)"
    else:
        motivo = []
        if roi <= 0:
            motivo.append(f"ROI {roi:+.2f}% <= 0")
        if t < 2:
            motivo.append(f"t={t:+.2f} < 2")
        if not robusto and roi > 0:
            # solo es "dependencia de captura" cuando las dos capturas DISCREPAN;
            # si ambas son negativas el motivo ya esta dicho arriba y repetirlo
            # aqui haria pensar en un artefacto de captura que no existe.
            motivo.append(f"la captura primera no acompaña ({roi_s:+.2f}%)")
        elif roi <= 0 and ps:
            motivo.append(f"ambas capturas coinciden en negativo (primera: {roi_s:+.2f}%)")
        v = f"REFUTADA ({'; '.join(motivo)})"
    print(f"VEREDICTO: {v}")
    print("=" * 70)

    por_liga = defaultdict(list)
    for j in con_ml:
        if abs(j["m1"]) >= UMBRAL_LIDER and "ml_ult" in j:
            obj_a = j["m1"] > 0
            od = j["ml_ult"]["home_odds"] if obj_a else j["ml_ult"]["away_odds"]
            por_liga[j["lg"]].append((od - 1.0) if j["gano_a"] == obj_a else -1.0)
    print("\nDesglose por liga (solo informativo, NO rescata nada):")
    for lg, ps_ in sorted(por_liga.items(), key=lambda kv: -len(kv[1]))[:8]:
        if len(ps_) >= 10:
            print(f"  {lg[:34]:<36} n={len(ps_):<4} ROI={statistics.mean(ps_)*100:+6.1f}%")


if __name__ == "__main__":
    main()
