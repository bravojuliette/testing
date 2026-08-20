"""Descarga y cachea en SQLite el historico crudo (partidos TT-Series + cuota de
apertura BetsAPI) para un rango de fechas.

Esta es la unica parte "cara" en red/cuota. Separarla de la evaluacion
(replay.py) es lo que te da la flexibilidad que pedias: una vez recolectado
un periodo, puedes correr cientos de variantes de parametros sobre el mismo
dataset en segundos, sin volver a tocar la red.

Resumible: guarda en la tabla `meta` la siguiente fecha pendiente, asi que si
se corta a mitad de camino (cuota, red, etc.) puedes volver a lanzar
`collect_range` y continua donde se quedo.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from ..textutil import pair_key, strong_name
from .. import config
from ..sources.betsapi import fetch_ended, fill_missing_results_from_events, find_event, best_opening_line
from ..sources.tt_series import load_sessions_for_date
from ..sources.http_cache import ApiClient
from .. import db as dbmod


def _meta_key(start: date, end: date) -> str:
    return f"collect_next_date::{start.isoformat()}::{end.isoformat()}"


def _upsert_match(conn, sess: dict, m: dict, day: date) -> str:
    uid = f"{day.isoformat()}|{sess['url']}|{m['time']}|{pair_key(m['p1'], m['p2'])}"
    conn.execute(
        """INSERT INTO raw_matches
           (match_uid, session_url, session_title, date, time, dt, rel_min,
            p1, p2, p1_key, p2_key, completed, s1, s2, result_source)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(match_uid) DO UPDATE SET
             completed=excluded.completed, s1=excluded.s1, s2=excluded.s2,
             result_source=excluded.result_source""",
        (
            uid, sess["url"], sess["title"], day.isoformat(), m["time"],
            m["dt"].isoformat() if m.get("dt") else None, m.get("rel_min"),
            m["p1"], m["p2"], m["p1k"], m["p2k"],
            1 if m["completed"] else 0, m.get("s1"), m.get("s2"), m.get("result_source"),
        ),
    )
    return uid


def _store_odds(conn, match_uid: str, line: dict) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO raw_odds
           (match_uid, book, source, is_fallback, event_id, odds1, odds2, mp1, mp2, add_time, quality, captured_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            match_uid, line["book"], line["source"], 1 if line["fallback"] else 0, line["event_id"],
            line["odds1"], line["odds2"], line["mp1"], line["mp2"], line.get("add_time"), line["quality"],
            date.today().isoformat(),
        ),
    )


def collect_range(start: date, end: date, *, db_path=None, progress=sys.stdout, fetch_odds: bool = True) -> None:
    """Recolecta [start, end] (inclusive). Reanuda automaticamente si ya hay progreso."""
    with dbmod.get_conn(db_path) as conn:
        client = ApiClient(conn, config.BETSAPI_TOKEN)
        meta_key = _meta_key(start, end)
        resume = dbmod.get_meta(conn, meta_key)
        d = date.fromisoformat(resume) if resume else start
        if resume:
            print(f"Reanudando collect desde {d} (rango {start}..{end})", file=progress, flush=True)

        while d <= end:
            try:
                sessions = load_sessions_for_date(client, d)
                scheduled = sum(len(s["schedule"]) for s in sessions)
                completed = sum(sum(1 for m in s["schedule"] if m["completed"]) for s in sessions)

                events = None
                if sessions and completed < scheduled:
                    events = []
                    for dd in (d - timedelta(days=1), d, d + timedelta(days=1)):
                        events.extend(fetch_ended(client, dd))
                    by_id = {str(e.get("id")): e for e in events if e.get("id")}
                    events = list(by_id.values())
                    filled, unresolved = fill_missing_results_from_events(sessions, events)
                    completed = sum(sum(1 for m in s["schedule"] if m["completed"]) for s in sessions)
                    missing = scheduled - completed
                    ratio = (missing / scheduled) if scheduled else 0
                    if missing > config.MAX_UNRESOLVED_MATCHES_PER_DAY or ratio > config.MAX_UNRESOLVED_RATIO_PER_DAY:
                        raise RuntimeError(
                            f"DATA_GAP_GRANDE {d}: faltan {missing}/{scheduled} ({ratio:.1%}), "
                            f"supera limite {config.MAX_UNRESOLVED_MATCHES_PER_DAY} o {config.MAX_UNRESOLVED_RATIO_PER_DAY:.1%}"
                        )
                    if missing:
                        print(f"[{d}] WARN gap tolerado: faltan {missing}/{scheduled} ({ratio:.1%}), rellenados={filled}", file=progress, flush=True)

                uids_by_match: dict[str, tuple[dict, dict]] = {}
                for sess in sessions:
                    for m in sess["schedule"]:
                        uid = _upsert_match(conn, sess, m, d)
                        uids_by_match[uid] = (sess, m)

                if fetch_odds and sessions:
                    if events is None:
                        events = []
                        for dd in (d - timedelta(days=1), d, d + timedelta(days=1)):
                            events.extend(fetch_ended(client, dd))
                        by_id = {str(e.get("id")): e for e in events if e.get("id")}
                        events = list(by_id.values())
                    n_odds = 0
                    for uid, (sess, m) in uids_by_match.items():
                        if not m["completed"]:
                            continue  # backtest solo necesita cuota de partidos con resultado conocido
                        ts = int(m["dt"].timestamp()) if m.get("dt") else 0
                        e = find_event(m["p1"], m["p2"], ts, events)
                        if not e:
                            continue
                        line = best_opening_line(client, e)
                        if not line:
                            continue
                        home = (e.get("home") or {}).get("name", "")
                        if strong_name(home, m["p2"]):
                            line["odds1"], line["odds2"] = line["odds2"], line["odds1"]
                            line["mp1"], line["mp2"] = line["mp2"], line["mp1"]
                        _store_odds(conn, uid, line)
                        n_odds += 1
                    print(f"[{d}] sesiones={len(sessions)} partidos={scheduled} cuotas={n_odds}", file=progress, flush=True)
                else:
                    print(f"[{d}] sesiones={len(sessions)} partidos={scheduled}", file=progress, flush=True)

                dbmod.set_meta(conn, meta_key, (d + timedelta(days=1)).isoformat())
                conn.commit()
            except Exception as exc:
                conn.commit()  # conserva lo ya insertado este dia hasta el fallo
                print(f"[{d}] ERROR: {exc}. Collect detenido; vuelve a correr collect para reanudar aqui.", file=progress, flush=True)
                raise
            d += timedelta(days=1)

        print(f"Collect completo: {start} -> {end}", file=progress, flush=True)
