"""Analisis descriptivo: rachas de victorias/derrotas dentro de una sesion,
y si el resultado del SIGUIENTE partido se desvia de lo que ya predice el
Elo rodante (que en teoria ya deberia reflejar la forma reciente via
session_delta). Si tras controlar por Elo/forma la racha SIGUE
explicando algo, es una señal real que el modelo actual no esta usando.
Si no, es "los jugadores en racha negativa ya son mas debiles" -- confusion
de habilidad con racha, no un efecto de racha en si.

Sin red, sin I/O lento -- reproduce cronologicamente igual que replay.py,
pero sin generar picks: solo cuenta que tan bien predice el Elo pre-sesion
el resultado real de cada jugador segun la racha con la que llega.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..model.elo import elo_prob, update_rolling
from ..model.params import BASELINE, StrategyParams


@dataclass
class StreakObs:
    streak_type: Optional[str]  # 'W' | 'L' | None (primer partido de la sesion para ese jugador)
    streak_len: int             # 0 si streak_type es None
    elo_win_prob: float         # probabilidad de ganar segun Elo pre-sesion (sin ajuste de forma/h2h)
    won: bool


def _load_matches(conn, start: date, end: date):
    rows = conn.execute(
        "SELECT * FROM raw_matches WHERE date BETWEEN ? AND ? ORDER BY session_url, rel_min, time",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    by_session = defaultdict(list)
    for r in rows:
        by_session[r["session_url"]].append(dict(r))
    return by_session


def compute_streak_observations(conn, start: date, end: date, params: StrategyParams = BASELINE) -> list[StreakObs]:
    by_session = _load_matches(conn, start, end)

    elo: dict[str, float] = {}
    obs: list[StreakObs] = []

    sessions_sorted = sorted(
        by_session.items(),
        key=lambda kv: min((m["rel_min"] or 0) for m in kv[1]) if kv[1] else 0,
    )

    for session_url, matches in sessions_sorted:
        matches = sorted(matches, key=lambda m: (m["rel_min"] or 0))
        session_snapshot = dict(elo)  # Elo previo a la sesion, sin look-ahead
        streaks: dict[str, tuple[Optional[str], int]] = {}
        day_updates = []

        for m in matches:
            if not m["completed"]:
                continue
            p1k, p2k = m["p1_key"], m["p2_key"]
            e1 = session_snapshot.get(p1k, params.initial_elo)
            e2 = session_snapshot.get(p2k, params.initial_elo)
            p1_prob = elo_prob(e1, e2, params.elo_scale)
            p1_won = m["s1"] > m["s2"]

            s1_type, s1_len = streaks.get(p1k, (None, 0))
            s2_type, s2_len = streaks.get(p2k, (None, 0))
            obs.append(StreakObs(s1_type, s1_len, p1_prob, p1_won))
            obs.append(StreakObs(s2_type, s2_len, 1 - p1_prob, not p1_won))

            def _next(type_, len_, won):
                outcome = "W" if won else "L"
                return (outcome, len_ + 1) if type_ == outcome else (outcome, 1)

            streaks[p1k] = _next(s1_type, s1_len, p1_won)
            streaks[p2k] = _next(s2_type, s2_len, not p1_won)
            day_updates.append(m)

        for m in sorted(day_updates, key=lambda x: x["rel_min"] or 0):
            update_rolling(elo, m["p1_key"], m["p2_key"], m["s1"], m["s2"], params)

    return obs


def summarize(obs: list[StreakObs], max_bucket: int = 6) -> list[dict]:
    """Agrupa por (tipo de racha, longitud -- con max_bucket+ como 'max_bucket o mas')
    y compara tasa de victoria REAL vs la que ya predecia el Elo pre-sesion.
    Si actual - esperado es consistentemente negativo en rachas de derrota (o
    positivo en rachas de victoria) y crece con la longitud, hay algo que el
    Elo rodante no esta capturando. Si no hay patron, la racha ya la explica
    el rating -- no es una señal extra."""
    buckets: dict[tuple, list[StreakObs]] = defaultdict(list)
    for o in obs:
        key_type = o.streak_type or "NONE"
        key_len = min(o.streak_len, max_bucket) if o.streak_type else 0
        buckets[(key_type, key_len)].append(o)

    rows = []
    baseline_actual = statistics.mean(o.won for o in obs)
    baseline_expected = statistics.mean(o.elo_win_prob for o in obs)
    for (t, n_len), group in sorted(buckets.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        n = len(group)
        actual = statistics.mean(g.won for g in group)
        expected = statistics.mean(g.elo_win_prob for g in group)
        rows.append({
            "streak_type": t, "streak_len": n_len, "n": n,
            "actual_win_rate": actual, "elo_expected": expected,
            "deviation_pp": (actual - expected) * 100,
        })
    rows.append({
        "streak_type": "ALL", "streak_len": "-", "n": len(obs),
        "actual_win_rate": baseline_actual, "elo_expected": baseline_expected,
        "deviation_pp": (baseline_actual - baseline_expected) * 100,
    })
    return rows


def print_streak_table(rows: list[dict]) -> None:
    label = {"W": "racha VICTORIAS", "L": "racha DERROTAS", "NONE": "1er partido sesion", "ALL": "TODOS"}
    print(f"{'racha':22s} {'len':>4s} {'n':>6s} {'win% real':>10s} {'win% Elo':>10s} {'desv(pp)':>9s}")
    for r in rows:
        lbl = label.get(r["streak_type"], r["streak_type"])
        print(f"{lbl:22s} {str(r['streak_len']):>4s} {r['n']:>6d} "
              f"{r['actual_win_rate']*100:>9.1f}% {r['elo_expected']*100:>9.1f}% {r['deviation_pp']:>+8.1f}")
