"""Implementa PREREGISTRO_outlier_consenso.md -- commiteado antes de correr.

Apuesta EN la casa outlier HACIA el consenso (mediana del resto de casas,
o Pinnacle en la variante), totales al kickoff.
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball.analysis.sobre_reaccion_q1 import t_pnl

PINN = "PinnacleSports"
UMBRALES = (2.0, 3.0, 4.0)


def _ts(cap):
    """captured_at a epoch (viene como texto ISO o como numero)."""
    if cap is None:
        return None
    try:
        return float(cap)
    except (TypeError, ValueError):
        pass
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(cap).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def cargar(db, ligas=None):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    evs = {}
    q = ("SELECT o.event_id, o.book, o.line, o.over_odds, o.under_odds, o.captured_at, "
         "g.league_name, g.date, g.home_score, g.away_score "
         "FROM bball_odds o JOIN bball_games g ON g.event_id=o.event_id "
         "WHERE o.market='18_3' AND o.snapshot='kickoff' AND o.line IS NOT NULL AND g.completed=1")
    for r in conn.execute(q):
        lg = r["league_name"]
        if ligas is not None and lg not in ligas:
            continue
        fin = (r["home_score"] or 0) + (r["away_score"] or 0)
        if fin <= 0:
            continue
        e = evs.setdefault(r["event_id"], dict(lg=lg, fecha=r["date"], fin=float(fin), casas=[]))
        e["casas"].append(dict(book=r["book"], line=float(r["line"]),
                               ov=r["over_odds"], un=r["under_odds"], cap=r["captured_at"]))
    conn.close()
    return [e for e in evs.values() if len(e["casas"]) >= 3]


def apuesta(outlier, consenso, fin):
    """pnl de apostar en la casa outlier hacia el consenso; None si no aplica."""
    if outlier["line"] > consenso:
        od, gana = outlier["un"], fin < outlier["line"]
    else:
        od, gana = outlier["ov"], fin > outlier["line"]
    if not od or not (1.01 <= od <= 20) or fin == outlier["line"]:
        return None
    return (od - 1.0) if gana else -1.0


def correr_bloque(nombre, evs, max_gap=None):
    """max_gap: sensibilidad declarada en el pre-registro (riesgo de captura):
    solo eventos donde el snapshot de la outlier esta a <=max_gap segundos
    del snapshot mas fresco del evento."""
    if not evs:
        print(f"\n== {nombre}: sin eventos =="); return
    fechas = sorted(e["fecha"] for e in evs)
    corte = fechas[len(fechas) // 2]
    etq = f" [solo outlier fresca <={max_gap}s]" if max_gap else ""
    print(f"\n== {nombre}{etq}: n_eventos={len(evs)} | corte busqueda/reserva: {corte} ==")

    for variante in ("mediana", "pinnacle"):
        for umbral in UMBRALES:
            pnls, mitades, gaps = [], {"s": [], "r": []}, []
            for e in evs:
                casas = e["casas"]
                if variante == "pinnacle":
                    pin = next((c for c in casas if c["book"] == PINN), None)
                    if pin is None:
                        continue
                    softs = [c for c in casas if c["book"] != PINN]
                    if not softs:
                        continue
                    out = max(softs, key=lambda c: abs(c["line"] - pin["line"]))
                    cons = pin["line"]
                else:
                    def desv(c):
                        resto = [x["line"] for x in casas if x is not c]
                        return c["line"] - statistics.median(resto)
                    out = max(casas, key=lambda c: abs(desv(c)))
                    cons = statistics.median([x["line"] for x in casas if x is not out])
                if abs(out["line"] - cons) < umbral:
                    continue
                if max_gap is not None:
                    oc = _ts(out["cap"])
                    caps_all = [_ts(c["cap"]) for c in casas if _ts(c["cap"]) is not None]
                    if oc is None or not caps_all or abs(oc - max(caps_all)) > max_gap:
                        continue
                p = apuesta(out, cons, e["fin"])
                if p is None:
                    continue
                pnls.append(p)
                mitades["s" if e["fecha"] < corte else "r"].append(p)
                caps = [_ts(c["cap"]) for c in casas if _ts(c["cap"]) is not None]
                oc = _ts(out["cap"])
                if oc is not None and caps:
                    gaps.append(abs(oc - max(caps)))
            if not pnls:
                print(f"  [{variante}] desv>={umbral:.0f}: n=0"); continue
            rs = statistics.mean(mitades["s"]) * 100 if mitades["s"] else float("nan")
            rr = statistics.mean(mitades["r"]) * 100 if mitades["r"] else float("nan")
            gap_med = statistics.median(gaps) if gaps else -1
            print(f"  [{variante}] desv>={umbral:.0f}: n={len(pnls):4d} "
                  f"ROI={statistics.mean(pnls)*100:+6.1f}% t={t_pnl(pnls):+5.2f} "
                  f"acierto={sum(1 for p in pnls if p>0)/len(pnls)*100:3.0f}% "
                  f"| S {rs:+6.1f}% (n={len(mitades['s'])}) / R {rr:+6.1f}% (n={len(mitades['r'])}) "
                  f"| gap_captura_med={gap_med:.0f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-grandes", default="data_local/bball_local.db")
    ap.add_argument("--db-chicas", default="data_local/bball_chicas.db")
    args = ap.parse_args()
    grandes = cargar(args.db_grandes)
    for lg in ("NBA", "WNBA", "Euroleague"):
        correr_bloque(lg, [e for e in grandes if e["lg"] == lg])
    correr_bloque("CHICAS-pooled", cargar(args.db_chicas))
    # sensibilidad declarada: el efecto debe sobrevivir con snapshots frescos
    print("\n######## SENSIBILIDAD DE FRESCURA (riesgo declarado en el pre-registro) ########")
    for lg in ("NBA", "WNBA", "Euroleague"):
        correr_bloque(lg, [e for e in grandes if e["lg"] == lg], max_gap=120)


if __name__ == "__main__":
    main()
