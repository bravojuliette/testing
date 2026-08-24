"""Detector de "cadenas de barridas transitivas" -- sistema APARTE del
scanner principal (tt_elite/live/scan.py), pedido explicito del usuario el
2026-08-24:

    "Si en una misma sesion (dia de torneo), existe alguien que haya quedado
    3-0 contra un rival X, y toque disputar su encuentro con un rival Y, que
    ha perdido 0-3 contra ese rival X, quiero que se me muestre."

No genera picks ni probabilidad de acierto -- es puramente observacional,
sin backtest ni validacion detras (a diferencia del sistema principal). Se
alimenta solo de raw_matches ya recolectado por el scanner en vivo: no hace
ninguna llamada nueva a BetsAPI ni TT-Series.

Algoritmo, por sesion (session_url), en orden cronologico (rel_min):
  Se mantiene un grafo dirigido "beaten_by_x[x] = {y1, y2, ...}" de
  barridas 3-0/0-3 YA RESUELTAS antes del partido actual (sin mirar al
  futuro). Para cada partido A vs B se comprueba, en ambos sentidos
  (A=p1,Y=p2) y (A=p2,Y=p1), si existe un X tal que A goleo 3-0 a X y X
  goleo 3-0 a Y -- si lo hay, se registra la senal. Solo DESPUES de
  comprobar el partido actual se anade su propio resultado (si fue barrida)
  al grafo, para partidos posteriores de la misma sesion.
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
        beaten_by_x: dict[str, set] = {}  # x_key -> {y_key, ...} que x goleo 3-0

        for m in matches:
            p1k, p2k, p1n, p2n = m["p1_key"], m["p2_key"], m["p1"], m["p2"]
            name_by_key[p1k] = p1n
            name_by_key[p2k] = p2n

            for a, y, an, yn in ((p1k, p2k, p1n, p2n), (p2k, p1k, p2n, p1n)):
                for x in beaten_by_x.get(a, ()):
                    if y in beaten_by_x.get(x, ()):
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
                            "match_completed": bool(m["completed"]),
                            "match_s1": m["s1"], "match_s2": m["s2"],
                        })

            if m["completed"] and m["s1"] is not None and m["s2"] is not None:
                if m["s1"] == 3 and m["s2"] == 0:
                    beaten_by_x.setdefault(p1k, set()).add(p2k)
                elif m["s1"] == 0 and m["s2"] == 3:
                    beaten_by_x.setdefault(p2k, set()).add(p1k)

    return signals


def upsert_blowout_chain_signals(conn, signals: list[dict]) -> int:
    """Guarda las senales encontradas. INSERT ... ON CONFLICT conserva
    detected_at (primera vez que se vio esta cadena) y solo refresca el
    estado del partido (completed/s1/s2) segun se va resolviendo."""
    if not signals:
        return 0
    now_iso = datetime.now(config.TZ).isoformat()
    rows = [
        (
            s["id"], s["match_uid"], s["session_url"], s["session_title"],
            s["date"], s["time"], s.get("dt"), s.get("rel_min"),
            s["player_a"], s["player_a_key"], s["player_y"], s["player_y_key"],
            s["common_x"], s["common_x_key"],
            1 if s["match_completed"] else 0, s.get("match_s1"), s.get("match_s2"),
            now_iso,
        )
        for s in signals
    ]
    conn.executemany(
        """INSERT INTO blowout_chain_signals
               (id, match_uid, session_url, session_title, date, time, dt, rel_min,
                player_a, player_a_key, player_y, player_y_key,
                common_x, common_x_key, match_completed, match_s1, match_s2, detected_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
               match_completed = excluded.match_completed,
               match_s1 = excluded.match_s1,
               match_s2 = excluded.match_s2""",
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
