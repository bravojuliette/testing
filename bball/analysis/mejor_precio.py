"""Implementa PREREGISTRO_mejor_precio.md -- commiteado antes de correr."""
from __future__ import annotations
import argparse, sqlite3, statistics, sys
from collections import defaultdict
sys.path.insert(0, ".")
from bball.analysis.sobre_reaccion_q1 import t_pnl

LEGALES = ("Bet365", "Betway", "BWin")
CUBOS = [(1.01,1.40),(1.40,2.20),(2.20,3.00),(3.00,20.0)]


def _ts(x):
    try: return float(x)
    except (TypeError, ValueError): pass
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(x).replace("Z","+00:00")).timestamp()
    except Exception: return None


def cargar(db):
    c = sqlite3.connect(db); c.row_factory = sqlite3.Row
    q = ("SELECT g.event_id, g.date, g.home_score hs, g.away_score aws, o.book, "
         " o.over_odds ho, o.under_odds ao, o.captured_at cap FROM bball_games g "
         "JOIN bball_odds o ON o.event_id=g.event_id WHERE g.league_name='NCAAB' "
         "AND g.completed=1 AND g.home_score+g.away_score>0 AND o.market='18_1' "
         "AND o.snapshot='start' AND o.over_odds IS NOT NULL AND o.under_odds IS NOT NULL "
         f"AND o.book IN ({','.join('?'*len(LEGALES))})")
    ev = defaultdict(lambda: dict(casas={}))
    for r in c.execute(q, LEGALES):
        if r["ho"] == r["ao"]: continue
        e = ev[r["event_id"]]
        e.update(fecha=r["date"], gana_home=r["hs"] > r["aws"])
        e["casas"][r["book"]] = (r["ho"], r["ao"], _ts(r["cap"]))
    c.close()
    return [e for e in ev.values() if len(e["casas"]) >= 2]


def celda(filas, corte, etq):
    if not filas:
        print(f"  {etq:46s} n=0"); return
    pn = [p for _f, p in filas]
    S = [p for f, p in filas if f < corte]; R = [p for f, p in filas if f >= corte]
    rs = statistics.mean(S)*100 if S else float("nan")
    rr = statistics.mean(R)*100 if R else float("nan")
    m = "SI" if (S and R and rs > 0 and rr > 0) else "no"
    print(f"  {etq:46s} n={len(pn):5d} ROI={statistics.mean(pn)*100:+6.2f}% "
          f"t={t_pnl(pn):+5.2f} | S {rs:+6.2f}% R {rr:+6.2f}%  mismo={m}")


def apuestas(evs, modo, max_gap=None, casa=None):
    """modo: 'mejor' | 'peor' | 'casa'."""
    out = []
    for e in evs:
        cs = e["casas"]
        if max_gap is not None:
            ts = [v[2] for v in cs.values() if v[2] is not None]
            if len(ts) < 2 or (max(ts) - min(ts)) > max_gap: continue
        for idx, gana in ((0, e["gana_home"]), (1, not e["gana_home"])):
            if modo == "casa":
                if casa not in cs: continue
                od = cs[casa][idx]
            else:
                vals = [v[idx] for v in cs.values()]
                od = max(vals) if modo == "mejor" else min(vals)
            if not (1.01 <= od <= 20): continue
            out.append((e["fecha"], od, (od - 1.0) if gana else -1.0))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--db", default="data_local/bball_turso.db")
    evs = cargar(ap.parse_args().db)
    fechas = sorted(e["fecha"] for e in evs); corte = fechas[len(fechas)//2]
    print(f"NCAAB: {len(evs)} partidos con >=2 casas legales | corte {corte}")
    gaps = []
    for e in evs:
        ts = [v[2] for v in e["casas"].values() if v[2] is not None]
        if len(ts) >= 2: gaps.append(max(ts) - min(ts))
    gaps.sort()
    if gaps:
        print(f"\n== CONTROL DE CONTEMPORANEIDAD (antes de ningun ROI) ==")
        print(f"  diferencia de captura entre casas: mediana={statistics.median(gaps)/3600:.1f}h  "
              f"p90={gaps[int(len(gaps)*.9)]/3600:.1f}h  max={gaps[-1]/3600:.1f}h")
        for g in (3600, 600):
            print(f"  partidos con capturas a <= {g}s: {sum(1 for x in gaps if x <= g)}")

    print("\n== H1: MEJOR PRECIO (sin exigir contemporaneidad) ==")
    todo = apuestas(evs, "mejor")
    celda([(f,p) for f,_o,p in todo], corte, "MEJOR precio, todos los cubos")
    for lo, hi in CUBOS:
        celda([(f,p) for f,o,p in todo if lo <= o < hi], corte, f"  MEJOR, cuota [{lo:.2f},{hi:.2f})")

    print("\n== CONTROL 1: PEOR precio (misma muestra) ==")
    peor = apuestas(evs, "peor")
    celda([(f,p) for f,_o,p in peor], corte, "PEOR precio, todos los cubos")

    print("\n== EL CONTROL QUE DECIDE: exigiendo capturas contemporaneas ==")
    for g in (3600, 600):
        sub = apuestas(evs, "mejor", max_gap=g)
        celda([(f,p) for f,_o,p in sub], corte, f"MEJOR precio, capturas <= {g}s")

    print("\n== CONTROL 2: cada casa por separado (misma muestra) ==")
    for bk in LEGALES:
        sub = apuestas(evs, "casa", casa=bk)
        celda([(f,p) for f,_o,p in sub], corte, f"solo {bk}")


if __name__ == "__main__":
    main()
