"""Backfill de elo_state/h2h_state/career_state persistentes a partir de TODO
el historico ya recolectado en raw_matches.

Por que hace falta: elo_state/h2h_state/career_state solo se alimentan desde
scan.py, sesion a sesion, a medida que el scanner en vivo va corriendo -- NO
se backfillearon nunca desde el historico ya collectado (2 anos, ~36k
partidos). Eso ya era medio problema para el Elo (arranca todo el mundo en
initial_elo hasta que juega en vivo), pero se volvio bloqueante el
2026-08-24 al descubrir que el scanner en vivo tampoco comprobaba
min_career_matches/min_career_win_rate (ver EXPERIMENTS_LOG.md): la
estrategia activa exige min_career_matches=12, y career_state empezaba
vacio -- habria tardado semanas en acumular ese historial solo con partidos
nuevos, dejando el scanner sin candidatos todo ese tiempo pese al arreglo.

Este backfill reconstruye el estado desde cero recorriendo TODAS las
sesiones ya completas en raw_matches en orden cronologico real (fecha +
rel_min), aplicando EXACTAMENTE la misma regla de "pliegue" que scan.py usa
en vivo (Elo/H2H/carrera solo se actualizan cuando la sesion entera esta
completa, nunca a mitad de sesion) -- el resultado final es identico al que
se habria acumulado si el scanner en vivo hubiera estado corriendo desde el
primer dia de datos disponibles.
"""
from __future__ import annotations

from collections import deque

from ..model.elo import update_rolling
from ..model.params import StrategyParams


def compute_backfill(conn, params: StrategyParams) -> dict:
    """Pura lectura + calculo, sin escribir nada -- ver cli.py para el
    comando que aplica el resultado."""
    rows = conn.execute(
        """SELECT match_uid, session_url, date, rel_min, p1, p2, p1_key, p2_key, s1, s2, completed
           FROM raw_matches ORDER BY date, rel_min"""
    ).fetchall()

    by_session: dict[str, list[dict]] = {}
    for r in rows:
        by_session.setdefault(r["session_url"], []).append(dict(r))

    sessions_sorted = sorted(
        by_session.items(),
        key=lambda kv: (min(m["date"] for m in kv[1]), min((m["rel_min"] or 0) for m in kv[1])) if kv[1] else ("", 0),
    )

    elo: dict[str, float] = {}
    h2h: dict[str, deque] = {}
    career_played: dict[str, int] = {}
    career_wins: dict[str, int] = {}
    names: dict[str, str] = {}
    applied_uids: list[str] = []
    sessions_folded = 0

    for _session_url, matches in sessions_sorted:
        matches = sorted(matches, key=lambda m: (m["rel_min"] or 0))
        fully_closed = bool(matches) and all(m["completed"] for m in matches)
        if not fully_closed:
            continue
        for m in matches:
            p1k, p2k = m["p1_key"], m["p2_key"]
            names[p1k] = m["p1"]
            names[p2k] = m["p2"]
            hk = "|".join(sorted((p1k, p2k)))
            arr = h2h.setdefault(hk, deque(maxlen=params.h2h_max_matches))
            p1_won = m["s1"] > m["s2"]
            arr.append(p1k if p1_won else p2k)
            update_rolling(elo, p1k, p2k, m["s1"], m["s2"], params)
            career_played[p1k] = career_played.get(p1k, 0) + 1
            career_played[p2k] = career_played.get(p2k, 0) + 1
            winner_key = p1k if p1_won else p2k
            career_wins[winner_key] = career_wins.get(winner_key, 0) + 1
            applied_uids.append(m["match_uid"])
        sessions_folded += 1

    return {
        "elo": elo, "h2h": h2h, "career_played": career_played, "career_wins": career_wins,
        "names": names, "applied_uids": applied_uids, "sessions_folded": sessions_folded,
        "sessions_total": len(sessions_sorted),
    }


def apply_backfill(conn, result: dict) -> None:
    """Escribe el resultado de compute_backfill(): limpia el estado previo y
    lo sustituye entero (evita doble conteo si ya habia algo folded-in desde
    live scans previos -- el backfill recalcula TODO desde raw_matches, asi
    que es la fuente de verdad)."""
    # Import perezoso: evita import circular (live.scan importa live.backfill
    # solo desde cli.py, nunca al reves).
    from .scan import _save_career_state, _save_elo_state, _save_h2h_state

    conn.execute("DELETE FROM elo_state")
    conn.execute("DELETE FROM h2h_state")
    conn.execute("DELETE FROM career_state")
    conn.execute("UPDATE raw_matches SET elo_applied = 0")
    conn.commit()

    _save_elo_state(conn, result["elo"], result["names"])
    _save_h2h_state(conn, result["h2h"])
    _save_career_state(conn, result["career_played"], result["career_wins"])
    if result["applied_uids"]:
        conn.executemany(
            "UPDATE raw_matches SET elo_applied = 1 WHERE match_uid = ?",
            [(u,) for u in result["applied_uids"]],
        )
    conn.commit()
