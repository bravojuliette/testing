"""Implementa PREREGISTRO_ncaa_prepartido.md -- commiteado antes de correr."""
from __future__ import annotations
import argparse, random, sqlite3, statistics, sys
sys.path.insert(0, ".")
from bball.analysis.sobre_reaccion_q1 import t_pnl
from bball.backtest.orientacion import clasificar_orientacion

LEGALES = ("Bet365", "Betway", "BWin")
CUBOS = [(1.01,1.20),(1.20,1.40),(1.40,1.70),(1.70,2.20),(2.20,3.00),(3.00,5.00),(5.00,20.0)]


def cargar(db):
    c = sqlite3.connect(db); c.row_factory = sqlite3.Row
    orient = clasificar_orientacion(c)
    q = ("SELECT g.event_id, g.date, g.home_score hs, g.away_score aws, o.book, "
         " o.over_odds ho, o.under_odds ao FROM bball_games g JOIN bball_odds o "
         "ON o.event_id=g.event_id WHERE g.league_name='NCAAB' AND g.completed=1 "
         "AND g.home_score+g.away_score>0 AND o.market='18_1' AND o.snapshot='start' "
         "AND o.over_odds IS NOT NULL AND o.under_odds IS NOT NULL AND o.book IN "
         f"({','.join('?'*len(LEGALES))})")
    ev = {}
    for r in c.execute(q, LEGALES):
        eid = r["event_id"]
        if r["ho"] == r["ao"]:
            continue
        # una sola casa por evento: la primera disponible en el orden declarado
        pri = LEGALES.index(r["book"])
        if eid in ev and ev[eid]["pri"] <= pri:
            continue
        ev[eid] = dict(pri=pri, fecha=r["date"], hs=r["hs"], aws=r["aws"],
                       ho=r["ho"], ao=r["ao"], orient=orient.get(eid, "sin_dato"))
    c.close()
    return list(ev.values())


def pnl(cuota, gana):
    return (cuota - 1.0) if gana else -1.0


def celda(filas, corte, etiqueta):
    if not filas:
        print(f"  {etiqueta:44s} n=0"); return
    pn = [p for _f, p in filas]
    S = [p for f, p in filas if f < corte]; R = [p for f, p in filas if f >= corte]
    rs = statistics.mean(S)*100 if S else float("nan")
    rr = statistics.mean(R)*100 if R else float("nan")
    mismo = "SI" if (S and R and rs > 0 and rr > 0) else "no"
    print(f"  {etiqueta:44s} n={len(pn):5d} ROI={statistics.mean(pn)*100:+6.2f}% "
          f"t={t_pnl(pn):+5.2f} | S {rs:+6.2f}% R {rr:+6.2f}%  mismo_signo={mismo}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data_local/bball_turso.db")
    a = ap.parse_args()
    evs = cargar(a.db)
    fechas = sorted(e["fecha"] for e in evs); corte = fechas[len(fechas)//2]
    print(f"NCAAB pre-partido: {len(evs)} partidos con moneyline de apertura en casa legal")
    print(f"corte busqueda/reserva: {corte}\n")

    print("== H1: SESGO FAVORITO-LONGSHOT (respaldar cada cubo de cuota) ==")
    for lo, hi in CUBOS:
        filas = []
        for e in evs:
            for cuota, gana in ((e["ho"], e["hs"] > e["aws"]), (e["ao"], e["aws"] > e["hs"])):
                if lo <= cuota < hi:
                    filas.append((e["fecha"], pnl(cuota, gana)))
        celda(filas, corte, f"cuota [{lo:.2f}, {hi:.2f})")

    print("\n== H2: EL LOCAL REAL COMO NO-FAVORITO ==")
    def h2(aleatorio, semilla=0):
        rnd = random.Random(semilla); filas = []
        for e in evs:
            if e["orient"] not in ("ok", "swap"):
                continue
            local_es_hueco_home = (e["orient"] == "ok")
            if aleatorio:
                local_es_hueco_home = rnd.random() < 0.5
            cuota_local = e["ho"] if local_es_hueco_home else e["ao"]
            cuota_visit = e["ao"] if local_es_hueco_home else e["ho"]
            if cuota_local <= cuota_visit:      # solo local NO favorito
                continue
            gana_local = (e["hs"] > e["aws"]) if local_es_hueco_home else (e["aws"] > e["hs"])
            filas.append((e["fecha"], pnl(cuota_local, gana_local)))
        return filas
    reales = h2(False)
    celda(reales, corte, "local real NO favorito (REAL)")
    for s in (1, 2, 3):
        celda(h2(True, s), corte, f"PLACEBO (localia al azar, semilla {s})")
    if reales:
        cu = [e for e in evs]  # cuota media de la celda real
        print(f"  cuota media de la celda real: "
              f"{statistics.mean([1.0 for _ in reales]):.2f} (n={len(reales)})")


if __name__ == "__main__":
    main()
