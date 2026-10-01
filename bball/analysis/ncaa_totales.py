"""Implementa PREREGISTRO_ncaa_totales.md -- commiteado antes de correr."""
from __future__ import annotations
import argparse, sqlite3, statistics, sys
sys.path.insert(0, ".")
from bball.analysis.sobre_reaccion_q1 import t_pnl

LEGALES = ("Bet365", "Betway", "BWin")
UMBRALES = (1.0, 2.0, 3.0)


def cargar(db):
    c = sqlite3.connect(db); c.row_factory = sqlite3.Row
    q = ("SELECT g.event_id, g.date, g.home_score+g.away_score fin, o.book, o.snapshot, "
         " o.line, o.over_odds ov, o.under_odds un FROM bball_games g JOIN bball_odds o "
         "ON o.event_id=g.event_id WHERE g.league_name='NCAAB' AND g.completed=1 "
         "AND g.home_score+g.away_score>0 AND o.market='18_3' AND o.line IS NOT NULL "
         "AND o.snapshot IN ('start','kickoff') AND o.book IN "
         f"({','.join('?'*len(LEGALES))})")
    ev = {}
    for r in c.execute(q, LEGALES):
        pri = LEGALES.index(r["book"])
        e = ev.setdefault(r["event_id"], dict(pri=99, fecha=r["date"], fin=float(r["fin"])))
        if pri > e["pri"]:
            continue
        if pri < e["pri"]:
            e.update(pri=pri, book=r["book"])
            e.pop("start", None); e.pop("kickoff", None)
        e[r["snapshot"]] = (float(r["line"]), r["ov"], r["un"])
    c.close()
    return [e for e in ev.values() if "start" in e or "kickoff" in e]


def pnl(linea, cuota, fin, lado):
    try: od = float(cuota)
    except (TypeError, ValueError): return None
    if not (1.01 <= od <= 20) or fin == linea: return None
    gana = (fin > linea) if lado == "over" else (fin < linea)
    return (od - 1.0) if gana else -1.0


def celda(filas, corte, etq):
    if len(filas) < 1:
        print(f"  {etq:46s} n=0"); return
    pn = [p for _f, p in filas]
    S = [p for f, p in filas if f < corte]; R = [p for f, p in filas if f >= corte]
    rs = statistics.mean(S)*100 if S else float("nan")
    rr = statistics.mean(R)*100 if R else float("nan")
    m = "SI" if (S and R and rs > 0 and rr > 0) else "no"
    print(f"  {etq:46s} n={len(pn):5d} ROI={statistics.mean(pn)*100:+6.2f}% "
          f"t={t_pnl(pn):+5.2f} | S {rs:+6.2f}% R {rr:+6.2f}%  mismo={m}")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--db", default="data_local/bball_turso.db")
    evs = cargar(ap.parse_args().db)
    fechas = sorted(e["fecha"] for e in evs); corte = fechas[len(fechas)//2]
    print(f"NCAAB totales: {len(evs)} partidos con linea en casa legal | corte {corte}")
    con_ambos = [e for e in evs if "start" in e and "kickoff" in e]
    movs = [e["kickoff"][0] - e["start"][0] for e in con_ambos]
    if movs:
        am = sorted(abs(m) for m in movs)
        print(f"con apertura Y cierre de la MISMA casa: {len(con_ambos)}")
        print(f"  movimiento |linea|: mediana={statistics.median(am):.1f}  "
              f"p90={am[int(len(am)*.9)]:.1f}  max={am[-1]:.1f}")
        for u in UMBRALES:
            print(f"    partidos que mueven >= {u:.0f} pts: {sum(1 for m in am if m >= u)}")

    print("\n== H1: SESGO O/U AL PRECIO DE APERTURA ==")
    for lado in ("over", "under"):
        filas = []
        for e in evs:
            if "start" not in e: continue
            ln, ov, un = e["start"]
            p = pnl(ln, ov if lado == "over" else un, e["fin"], lado)
            if p is not None: filas.append((e["fecha"], p))
        celda(filas, corte, f"{lado.upper()} a la apertura")

    print("\n== H2: MOVIMIENTO DE LINEA (se apuesta al precio de KICKOFF) ==")
    for u in UMBRALES:
        for modo in ("SEGUIR", "CONTRARIAR"):
            filas = []
            for e in con_ambos:
                mv = e["kickoff"][0] - e["start"][0]
                if abs(mv) < u: continue
                lado = ("over" if mv > 0 else "under")
                if modo == "CONTRARIAR": lado = "under" if lado == "over" else "over"
                ln, ov, un = e["kickoff"]
                p = pnl(ln, ov if lado == "over" else un, e["fin"], lado)
                if p is not None: filas.append((e["fecha"], p))
            celda(filas, corte, f"{modo} movimiento >= {u:.0f} pts")
    print("\n  -- control: lado ciego al precio de kickoff (misma muestra) --")
    for lado in ("over", "under"):
        filas = []
        for e in con_ambos:
            ln, ov, un = e["kickoff"]
            p = pnl(ln, ov if lado == "over" else un, e["fin"], lado)
            if p is not None: filas.append((e["fecha"], p))
        celda(filas, corte, f"{lado.upper()} ciego al kickoff")


if __name__ == "__main__":
    main()
