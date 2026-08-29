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

# TODAS las ligas de basket real: cuantos mas partidos, antes se junta la
# muestra, y la sobre-reaccion -- si existe -- deberia ser MAYOR en ligas
# chicas donde el modelo en vivo es mas automatico. Se excluye solo el
# basket simulado por videojuego (mismo criterio que en la recoleccion).
LIGAS_EXCLUIDAS = ("ebasketball", "h2h gg", "esports")


def scan_inplay(client, conn) -> dict:
    """Fotografia (a) los partidos EN JUEGO y (b) los que empiezan en las
    proximas ~6 horas. Las fotos pre-partido dan la evolucion intradia de
    las lineas -- el dato que hace falta para medir que casas van con
    RETRASO respecto al consenso (la estrategia clasica del profesional:
    apostar el precio viejo, sin predecir baloncesto)."""
    js = client.bets("/v3/events/inplay", {"sport_id": config.SPORT_ID},
                     prefix="inplay", use_cache=False)
    eventos = list(js.get("results") or [])
    stats = {"en_juego": len(eventos), "de_interes": 0, "fotos": 0}
    try:
        up = client.bets("/v3/events/upcoming", {"sport_id": config.SPORT_ID, "page": 1},
                         prefix="upcoming_live", use_cache=False)
        import time as _t
        for ev in (up.get("results") or []):
            try:
                if 0 <= int(ev.get("time", 0)) - _t.time() <= 6 * 3600:
                    ev["_prematch"] = True
                    eventos.append(ev)
            except (TypeError, ValueError):
                continue
        stats["proximos"] = sum(1 for e in eventos if e.get("_prematch"))
    except Exception as exc:  # la foto en vivo no debe caerse por esto
        stats["upcoming_error"] = str(exc)[:80]
    ahora = datetime.now(timezone.utc).isoformat()
    for ev in eventos:
        lg = ((ev.get("league") or {}).get("name") or "")
        if any(x in lg.lower() for x in LIGAS_EXCLUIDAS):
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
