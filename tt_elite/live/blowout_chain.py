"""Detector de "cadenas de barridas transitivas" -- sistema APARTE del
scanner principal (tt_elite/live/scan.py), pedido explicito del usuario el
2026-08-24:

    "Si en una misma sesion (dia de torneo), existe alguien que haya quedado
    3-0 contra un rival X, y toque disputar su encuentro con un rival Y, que
    ha perdido 0-3 contra ese rival X, quiero que se me muestre."

Y el 2026-08-24 (mismo dia), pidio ademas que se muestre como quedo cada uno
contra el rival comun X, y que -- una vez terminado el partido A vs Y -- se
indique si se CUMPLE la teoria (A, transitivamente mas fuerte, gana) o NO
(gana Y).

Y el mismo dia, mas tarde, pidio tambien ver las cuotas que tenia cada uno
(A y Y) en el partido de la cadena -- ver _attach_odds().

No genera picks ni probabilidad de acierto -- es puramente observacional,
sin backtest ni validacion detras (a diferencia del sistema principal). La
deteccion en si se alimenta solo de raw_matches ya recolectado (sin
llamadas nuevas a BetsAPI ni TT-Series); las cuotas SI necesitan una
consulta a BetsAPI (no se guardan en ningun otro sitio para partidos que no
son picks del scanner principal), pero solo una vez por senal -- una vez
guardada una cuota no se vuelve a pedir en pasadas siguientes.

Algoritmo, por sesion (session_url), en orden cronologico (rel_min):
  Se mantiene un diccionario "wins[winner_key][loser_key] = {match_uid,
  date, time}" de barridas 3-0/0-3 YA RESUELTAS antes del partido actual
  (sin mirar al futuro). Para cada partido A vs B se comprueba, en ambos
  sentidos (A=p1,Y=p2) y (A=p2,Y=p1), si existe un X tal que A goleo 3-0 a X
  y X goleo 3-0 a Y -- si lo hay, se registra la senal (con el detalle de
  ambos partidos de barrida). Solo DESPUES de comprobar el partido actual se
  anade su propio resultado (si fue barrida) al diccionario, para partidos
  posteriores de la misma sesion.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .. import config


def compute_blowout_chains(conn, start: date, end: date) -> list[dict]:
    """Recorre raw_matches entre `start` y `end` (inclusive) y devuelve la
    lista de senales encontradas, jugadas o pendientes. Pura (sin depender
    de la hora actual) para que sea facil de testear con fechas fijas."""
    rows = conn.execute(
        """SELECT match_uid, session_url, session_title, date, time, dt, rel_min,
                  p1, p2, p1_key, p2_key, completed, s1, s2
           FROM raw_matches
           WHERE date >= ? AND date <= ?
           ORDER BY session_url, rel_min""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()

    by_session: dict[str, list[dict]] = {}
    for r in rows:
        by_session.setdefault(r["session_url"], []).append(dict(r))

    signals: list[dict] = []
    for session_url, matches in by_session.items():
        matches = sorted(matches, key=lambda m: m["rel_min"] if m["rel_min"] is not None else 0)
        name_by_key: dict[str, str] = {}
        # winner_key -> {loser_key: {match_uid, date, time}} de barridas 3-0
        # ya resueltas antes del partido actual.
        wins: dict[str, dict[str, dict]] = {}

        for m in matches:
            p1k, p2k, p1n, p2n = m["p1_key"], m["p2_key"], m["p1"], m["p2"]
            name_by_key[p1k] = p1n
            name_by_key[p2k] = p2n

            for a, y, an, yn, a_is_p1 in (
                (p1k, p2k, p1n, p2n, True),
                (p2k, p1k, p2n, p1n, False),
            ):
                for x, ax_info in wins.get(a, {}).items():
                    xy_info = wins.get(x, {}).get(y)
                    if not xy_info:
                        continue
                    completed = bool(m["completed"]) and m["s1"] is not None and m["s2"] is not None
                    a_score = y_score = theory_holds = None
                    if completed:
                        a_score, y_score = (m["s1"], m["s2"]) if a_is_p1 else (m["s2"], m["s1"])
                        theory_holds = 1 if a_score > y_score else 0
                    signals.append({
                        "id": f"{m['match_uid']}|{a}|{x}",
                        "match_uid": m["match_uid"],
                        "session_url": session_url,
                        "session_title": m["session_title"],
                        "date": m["date"], "time": m["time"],
                        "dt": m["dt"], "rel_min": m["rel_min"],
                        "player_a": an, "player_a_key": a,
                        "player_y": yn, "player_y_key": y,
                        "common_x": name_by_key.get(x, x), "common_x_key": x,
                        "ax_match_uid": ax_info["match_uid"], "ax_date": ax_info["date"], "ax_time": ax_info["time"],
                        "xy_match_uid": xy_info["match_uid"], "xy_date": xy_info["date"], "xy_time": xy_info["time"],
                        "match_completed": completed,
                        "a_score": a_score, "y_score": y_score,
                        "theory_holds": theory_holds,
                        # Se rellenan en _attach_odds() (requiere BetsAPI) --
                        # None aqui = "todavia no se ha consultado".
                        "a_odds": None, "y_odds": None, "odds_book": None,
                    })

            if m["completed"] and m["s1"] is not None and m["s2"] is not None:
                info = {"match_uid": m["match_uid"], "date": m["date"], "time": m["time"]}
                if m["s1"] == 3 and m["s2"] == 0:
                    wins.setdefault(p1k, {})[p2k] = info
                elif m["s1"] == 0 and m["s2"] == 3:
                    wins.setdefault(p2k, {})[p1k] = info

    return signals


def upsert_blowout_chain_signals(conn, signals: list[dict]) -> int:
    """Guarda las senales encontradas. INSERT ... ON CONFLICT conserva
    detected_at (primera vez que se vio esta cadena) y solo refresca el
    estado del partido (completed/marcador/veredicto/cuota) segun se va
    resolviendo."""
    if not signals:
        return 0
    now_iso = datetime.now(config.TZ).isoformat()
    rows = [
        (
            s["id"], s["match_uid"], s["session_url"], s["session_title"],
            s["date"], s["time"], s.get("dt"), s.get("rel_min"),
            s["player_a"], s["player_a_key"], s["player_y"], s["player_y_key"],
            s["common_x"], s["common_x_key"],
            s["ax_match_uid"], s["ax_date"], s["ax_time"],
            s["xy_match_uid"], s["xy_date"], s["xy_time"],
            1 if s["match_completed"] else 0, s.get("a_score"), s.get("y_score"), s.get("theory_holds"),
            s.get("a_odds"), s.get("y_odds"), s.get("odds_book"),
            now_iso,
        )
        for s in signals
    ]
    conn.executemany(
        """INSERT INTO blowout_chain_signals
               (id, match_uid, session_url, session_title, date, time, dt, rel_min,
                player_a, player_a_key, player_y, player_y_key,
                common_x, common_x_key,
                ax_match_uid, ax_date, ax_time, xy_match_uid, xy_date, xy_time,
                match_completed, a_score, y_score, theory_holds,
                a_odds, y_odds, odds_book, detected_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
               match_completed = excluded.match_completed,
               a_score = excluded.a_score,
               y_score = excluded.y_score,
               theory_holds = excluded.theory_holds,
               ax_match_uid = excluded.ax_match_uid,
               ax_date = excluded.ax_date, ax_time = excluded.ax_time,
               xy_match_uid = excluded.xy_match_uid,
               xy_date = excluded.xy_date, xy_time = excluded.xy_time,
               a_odds = excluded.a_odds, y_odds = excluded.y_odds, odds_book = excluded.odds_book""",
        rows,
    )
    return len(rows)


def _load_existing_odds(conn, signals: list[dict]) -> None:
    """Rellena a_odds/y_odds/odds_book desde lo ya guardado en pasadas
    anteriores (in-place sobre `signals`), para no volver a consultar
    BetsAPI por una senal que ya tiene cuota."""
    ids = [s["id"] for s in signals]
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id, a_odds, y_odds, odds_book FROM blowout_chain_signals WHERE id IN ({placeholders})",
        ids,
    ).fetchall()
    existing = {r["id"]: (r["a_odds"], r["y_odds"], r["odds_book"]) for r in rows}
    for s in signals:
        hit = existing.get(s["id"])
        if hit and hit[0] is not None:
            s["a_odds"], s["y_odds"], s["odds_book"] = hit


def _attach_odds(conn, signals: list[dict]) -> None:
    """Consulta BetsAPI (solo el partido A vs Y de cada senal, no los dos de
    barrida) para rellenar a_odds/y_odds/odds_book de las senales que
    todavia no la tienen guardada. No es critico -- si BetsAPI falla o no
    hay token, se deja sin cuota y se reintenta en la siguiente pasada."""
    if not config.BETSAPI_TOKEN:
        return
    from ..sources.betsapi import (
        best_opening_line, current_best_line, fetch_ended, fetch_inplay, fetch_upcoming, find_event,
    )
    from ..sources.http_cache import ApiClient
    from ..textutil import strong_name

    pending_lookup = [s for s in signals if s.get("a_odds") is None and not s["match_completed"] and s.get("dt")]
    completed_lookup = [s for s in signals if s.get("a_odds") is None and s["match_completed"] and s.get("dt")]
    if not pending_lookup and not completed_lookup:
        return

    client = ApiClient(conn, config.BETSAPI_TOKEN)

    upcoming_events = None
    if pending_lookup:
        try:
            upcoming_events = fetch_upcoming(client) + fetch_inplay(client)
        except Exception as exc:
            print(f"[blowout_chain] fetch_upcoming/fetch_inplay fallo, se sigue sin cuotas de pendientes: {exc}", flush=True)
            upcoming_events = []

    ended_by_date: dict[date, list[dict]] = {}
    for s in completed_lookup:
        d = date.fromisoformat(s["date"])
        if d not in ended_by_date:
            try:
                ended_by_date[d] = fetch_ended(client, d)
            except Exception as exc:
                print(f"[blowout_chain] fetch_ended({d}) fallo, se sigue sin esas cuotas: {exc}", flush=True)
                ended_by_date[d] = []

    for s in pending_lookup + completed_lookup:
        ts = int(datetime.fromisoformat(s["dt"]).timestamp())
        events = upcoming_events if not s["match_completed"] else ended_by_date.get(date.fromisoformat(s["date"]), [])
        event = find_event(s["player_a"], s["player_y"], ts, events)
        if not event:
            continue
        try:
            line = current_best_line(client, event) if not s["match_completed"] else best_opening_line(client, event)
        except Exception as exc:
            print(f"[blowout_chain] consulta de cuota fallo para {s['id']}: {exc}", flush=True)
            continue
        if not line:
            continue
        home = (event.get("home") or {}).get("name", "")
        if strong_name(home, s["player_y"]):
            line["odds1"], line["odds2"] = line["odds2"], line["odds1"]
        s["a_odds"], s["y_odds"], s["odds_book"] = line["odds1"], line["odds2"], line["book"]


def scan_blowout_chain(conn, days_back: int = 2, fetch_odds: bool = True) -> dict:
    """Envoltorio "de produccion": ancla la ventana a hoy (hora real,
    config.TZ) y persiste lo encontrado. fetch_odds=False salta la consulta
    a BetsAPI (util en tests o si no hay BETSAPI_TOKEN)."""
    today = datetime.now(config.TZ).date()
    start = today - timedelta(days=days_back - 1)
    signals = compute_blowout_chains(conn, start, today)
    if signals:
        _load_existing_odds(conn, signals)
        if fetch_odds:
            _attach_odds(conn, signals)
    n = upsert_blowout_chain_signals(conn, signals)
    return {"found": n}
