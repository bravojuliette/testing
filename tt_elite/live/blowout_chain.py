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

No genera picks ni probabilidad de acierto -- es puramente observacional,
sin backtest ni validacion detras (a diferencia del sistema principal). Se
alimenta solo de raw_matches ya recolectado por el scanner en vivo: no hace
ninguna llamada nueva a BetsAPI ni TT-Series.

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
    estado del partido (completed/marcador/veredicto) segun se va
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
                match_completed, a_score, y_score, theory_holds, detected_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
               match_completed = excluded.match_completed,
               a_score = excluded.a_score,
               y_score = excluded.y_score,
               theory_holds = excluded.theory_holds,
               ax_match_uid = excluded.ax_match_uid,
               ax_date = excluded.ax_date, ax_time = excluded.ax_time,
               xy_match_uid = excluded.xy_match_uid,
               xy_date = excluded.xy_date, xy_time = excluded.xy_time""",
        rows,
    )
    return len(rows)


def scan_blowout_chain(conn, days_back: int = 2) -> dict:
    """Envoltorio "de produccion": ancla la ventana a hoy (hora real,
    config.TZ) y persiste lo encontrado."""
    today = datetime.now(config.TZ).date()
    start = today - timedelta(days=days_back - 1)
    signals = compute_blowout_chains(conn, start, today)
    n = upsert_blowout_chain_signals(conn, signals)
    return {"found": n}
