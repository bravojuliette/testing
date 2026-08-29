"""Scanner de lineas EN VIVO: fotografia los totales de los partidos en
juego para medir, con el tiempo, si la linea viva sobre-reacciona al
marcador (la teoria del usuario del over tras Q1 lento -- y su espejo, el
under tras Q1 rapido).

NO apuesta ni recomienda: solo recolecta. El analisis viene despues, cuando
haya muestra: comparar la linea viva al final del Q1 contra el valor justo
(3/4 del cierre pre-partido - 0.4, medido en bball/analysis/cuartos.py) y
contra el total final real.

Se apoya en /v3/events/inplay + /v2/event/odds/summary sin cache. Cada
corrida es una pasada (pensada para un cron de Actions cada 10-15 min
mientras haya temporada); si no hay partidos en juego, sale en segundos.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .. import config
from ..sources.betsapi import fetch_odds_summary

LIGAS_INTERES = ("NBA", "WNBA", "Euroleague", "NCAAB", "WNCAAB")


def scan_inplay(client, conn) -> dict:
    js = client.bets("/v3/events/inplay", {"sport_id": config.SPORT_ID},
                     prefix="inplay", use_cache=False)
    eventos = js.get("results") or []
    stats = {"en_juego": len(eventos), "de_interes": 0, "fotos": 0}
    ahora = datetime.now(timezone.utc).isoformat()
    for ev in eventos:
        lg = ((ev.get("league") or {}).get("name") or "")
        if not any(x.lower() in lg.lower() for x in LIGAS_INTERES):
            continue
        stats["de_interes"] += 1
        eid = str(ev.get("id"))
        odds = fetch_odds_summary(client, eid, use_cache=False)
        filas = []
        for book, b in (odds.get("results") or {}).items():
            if not isinstance(b, dict):
                continue
            # 'end' en un partido en juego = la cuota viva actual
            e = ((b.get("odds") or {}).get("end") or {}).get(config.TOTALS_MARKET_KEY)
            if not isinstance(e, dict):
                continue
            try:
                filas.append((eid, ahora, lg, ev.get("ss"),
                              json.dumps(ev.get("timer")), book,
                              float(e["handicap"]), float(e["over_od"]),
                              float(e["under_od"]), json.dumps(e)))
            except (KeyError, TypeError, ValueError):
                continue
        if filas:
            conn.executemany(
                "INSERT INTO bball_live_snapshots(event_id, captured_at, league_name, "
                "ss, timer_json, book, line, over_odds, under_odds, raw_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING", filas)
            stats["fotos"] += len(filas)
    conn.commit()
    return stats
