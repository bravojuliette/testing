"""Motor de backtest puro: reproduce cronologicamente los datos ya cacheados en
SQLite (por collect.py) contra un StrategyParams dado. Sin red, sin I/O lento
-- por eso un sweep de cientos de configuraciones tarda segundos, no dias.

Replica la logica de tainting por sesion del backtest Colab v5: si un partido
de una sesion no tiene resultado conocido, todos los jugadores de esa sesion
quedan "contaminados" desde ese punto (no generan mas candidatos en esa
sesion), para no inflar artificialmente partidos-previos/W-L con huecos.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .blowouts import compute_blowout_rates_by_match
from ..model.elo import compute_model, update_rolling
from ..model.params import StrategyParams
from ..model.strategy import evaluate_pick
from ..textutil import clip, pair_key


@dataclass
class BacktestPick:
    match_uid: str
    date: str
    session_title: str
    time: str
    p1: str
    p2: str
    favorito: str
    underdog: str
    book: str
    odds_underdog: float
    market_prob_underdog: float
    model_prob_underdog: float
    edge_pp: float
    ev_pct: float
    fair_odds: float
    signal: str
    result: str  # WIN | LOSS
    pnl_1u: Optional[float]


def _load_matches(conn, start: date, end: date):
    rows = conn.execute(
        "SELECT * FROM raw_matches WHERE date BETWEEN ? AND ? ORDER BY session_url, rel_min, time",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    by_session = defaultdict(list)
    for r in rows:
        by_session[r["session_url"]].append(dict(r))
    return by_session


def _load_odds(conn, start: date, end: date) -> dict[str, dict]:
    rows = conn.execute(
        """SELECT o.* FROM raw_odds o JOIN raw_matches m ON o.match_uid = m.match_uid
           WHERE m.date BETWEEN ? AND ?""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    return {r["match_uid"]: dict(r) for r in rows}


@dataclass
class ReplayData:
    """Partidos+cuotas ya cargados en memoria, listos para reproducir contra
    cualquier StrategyParams sin volver a tocar la base de datos. Cargar esto
    UNA vez y reusarlo es lo que hace que un sweep de cientos de
    configuraciones sea rapido de verdad -- antes, cada combinacion volvia a
    pedirle los mismos datos a Turso por red."""
    by_session: dict
    odds_by_uid: dict[str, dict]
    blowout_by_uid: dict[str, tuple[float, float, int, int]]


def load_replay_data(conn, warmup_start: date, eval_start: date, eval_end: date) -> ReplayData:
    return ReplayData(
        by_session=_load_matches(conn, warmup_start, eval_end),
        odds_by_uid=_load_odds(conn, eval_start, eval_end),
        # Tasas de barrida previas por partido (ver StrategyParams.min_blowout_rate).
        # Calculado sobre el mismo rango que los partidos, para que la profundidad
        # de historial previo por jugador sea consistente con el resto del motor.
        blowout_by_uid=compute_blowout_rates_by_match(conn, warmup_start, eval_end),
    )


def _next_streak(streak_type: Optional[str], streak_len: int, won: bool) -> tuple[str, int]:
    outcome = "W" if won else "L"
    return (outcome, streak_len + 1) if streak_type == outcome else (outcome, 1)


def _streak_delta(streak_type: Optional[str], streak_len: int, bonus_pp: float) -> float:
    """pp (como fraccion, ya /100) que suma/resta la racha PRE-partido del
    jugador a su propia probabilidad de ganar. Calibrado en backtest/streaks.py
    contra Elo puro; ver StrategyParams.streak_bonus_pp. 0.0 = sin efecto."""
    if streak_type is None or bonus_pp == 0.0:
        return 0.0
    d = bonus_pp * min(streak_len, 4) / 100.0
    return d if streak_type == "W" else -d


def replay_from_data(
    data: ReplayData,
    eval_start: date,
    eval_end: date,
    params: StrategyParams,
) -> list[BacktestPick]:
    """Igual que replay(), pero sobre datos ya cargados (ver load_replay_data).
    Pura funcion de calculo: nada de red ni de I/O aqui."""
    by_session = data.by_session
    odds_by_uid = data.odds_by_uid
    blowout_by_uid = data.blowout_by_uid

    elo: dict[str, float] = {}
    h2h: dict[str, deque] = {}
    career_played: dict[str, int] = {}
    picks: list[BacktestPick] = []

    # Orden cronologico global de sesiones por FECHA primero y luego por su
    # primer rel_min conocido dentro de esa fecha. rel_min por si solo NO
    # sirve para comparar sesiones de fechas distintas: se reinicia a ~0 en
    # cada sesion nueva (ver tt_series.assign_datetimes), asi que ordenar
    # solo por rel_min mezcla sesiones de dias distintos por hora-del-dia en
    # vez de por fecha real -- bug encontrado y corregido el 2026-08-22 (ver
    # EXPERIMENTS_LOG.md), afectaba a todo backtest con warmup > 1 dia.
    sessions_sorted = sorted(
        by_session.items(),
        key=lambda kv: (min(m["date"] for m in kv[1]), min((m["rel_min"] or 0) for m in kv[1])) if kv[1] else ("", 0),
    )

    for session_url, matches in sessions_sorted:
        matches = sorted(matches, key=lambda m: (m["rel_min"] or 0))
        session_day = matches[0]["date"] if matches else None
        is_eval = session_day is not None and eval_start.isoformat() <= session_day <= eval_end.isoformat()

        stats: dict[str, dict] = {}
        tainted: set[str] = set()
        streaks: dict[str, tuple[Optional[str], int]] = {}

        def get_stat(key, name):
            if key not in stats:
                stats[key] = {"name": name, "played": 0, "wins": 0, "losses": 0, "sf": 0, "sa": 0, "matches": []}
            return stats[key]

        session_ranking_snapshot = dict(elo)  # Elo previo a esta sesion (sin look-ahead)
        career_snapshot = dict(career_played)  # Partidos totales previos a esta sesion (sin look-ahead)
        session_start_rel_min = matches[0]["rel_min"] or 0 if matches else 0
        day_updates = []

        for m in matches:
            p1k, p2k = m["p1_key"], m["p2_key"]
            if not m["completed"]:
                tainted.add(p1k)
                tainted.add(p2k)
                continue

            st1 = get_stat(p1k, m["p1"])
            st2 = get_stat(p2k, m["p2"])

            blowout_ok = True
            if params.min_blowout_rate > 0:
                br = blowout_by_uid.get(m["match_uid"])
                blowout_ok = (
                    br is not None
                    and br[2] >= params.blowout_min_prior and br[3] >= params.blowout_min_prior
                    and br[0] >= params.min_blowout_rate and br[1] >= params.min_blowout_rate
                )

            career_ok = (
                career_snapshot.get(p1k, 0) >= params.min_career_matches
                and career_snapshot.get(p2k, 0) >= params.min_career_matches
            )

            elapsed = (m["rel_min"] or 0) - session_start_rel_min
            elapsed_ok = params.min_session_elapsed_min <= elapsed <= params.max_session_elapsed_min

            avg_games_p1 = (st1["sf"] / st1["played"]) if st1["played"] else 0.0
            avg_games_p2 = (st2["sf"] / st2["played"]) if st2["played"] else 0.0
            avg_games_ok = avg_games_p1 >= params.min_avg_games_won and avg_games_p2 >= params.min_avg_games_won

            if is_eval and blowout_ok and career_ok and elapsed_ok and avg_games_ok and st1["played"] >= params.min_matches_played and st2["played"] >= params.min_matches_played:
                if p1k not in tainted and p2k not in tainted:
                    line = odds_by_uid.get(m["match_uid"])
                    if line:
                        e1 = session_ranking_snapshot.get(p1k, params.initial_elo)
                        e2 = session_ranking_snapshot.get(p2k, params.initial_elo)
                        hk = "|".join(sorted((p1k, p2k)))
                        h_arr = h2h.get(hk, deque())
                        h_n = len(h_arr)
                        h_p1_wins = sum(1 for w in h_arr if w == p1k)

                        model = compute_model(e1, e2, st1["matches"], st2["matches"], h_n, h_p1_wins, session_ranking_snapshot, params)
                        s1_type, s1_len = streaks.get(p1k, (None, 0))
                        s2_type, s2_len = streaks.get(p2k, (None, 0))
                        delta1 = _streak_delta(s1_type, s1_len, params.streak_bonus_pp)
                        delta2 = _streak_delta(s2_type, s2_len, params.streak_bonus_pp)
                        model_p1 = clip(model["p1"] + delta1 - delta2, 0.0, 1.0)
                        model_p2 = 1 - model_p1
                        ev = evaluate_pick(
                            line["mp1"], line["mp2"], model_p1, model_p2,
                            line["odds1"], line["odds2"], bool(line["is_fallback"]), params,
                        )
                        if ev.actionable:
                            underdog_key = p1k if ev.underdog_is_p1 else p2k
                            won = (m["s1"] > m["s2"] and underdog_key == p1k) or (m["s2"] > m["s1"] and underdog_key == p2k)
                            pnl = (ev.odds_underdog - 1) if won else -1.0
                            picks.append(BacktestPick(
                                match_uid=m["match_uid"], date=m["date"], session_title=m["session_title"],
                                time=m["time"], p1=m["p1"], p2=m["p2"],
                                favorito=(m["p2"] if ev.underdog_is_p1 else m["p1"]),
                                underdog=(m["p1"] if ev.underdog_is_p1 else m["p2"]),
                                book=line["book"], odds_underdog=ev.odds_underdog,
                                market_prob_underdog=ev.market_prob_underdog, model_prob_underdog=ev.model_prob_underdog,
                                edge_pp=ev.edge_pp, ev_pct=ev.ev_pct, fair_odds=ev.fair_odds,
                                signal=ev.signal, result=("WIN" if won else "LOSS"), pnl_1u=pnl,
                            ))

            # H2H se actualiza con el resultado real (post-partido).
            hk = "|".join(sorted((p1k, p2k)))
            winner_key = p1k if m["s1"] > m["s2"] else p2k
            arr = h2h.setdefault(hk, deque(maxlen=params.h2h_max_matches))
            arr.append(winner_key)

            # Racha de sesion (post-partido) -- reusa el streak PRE-partido si
            # ya se calculo arriba (candidato eval), si no lo calcula ahora.
            s1_type, s1_len = streaks.get(p1k, (None, 0))
            s2_type, s2_len = streaks.get(p2k, (None, 0))
            p1_won_match = m["s1"] > m["s2"]
            streaks[p1k] = _next_streak(s1_type, s1_len, p1_won_match)
            streaks[p2k] = _next_streak(s2_type, s2_len, not p1_won_match)

            # Stats de sesion (post-partido).
            aw = m["s1"] > m["s2"]
            career_played[p1k] = career_played.get(p1k, 0) + 1
            career_played[p2k] = career_played.get(p2k, 0) + 1
            st1["played"] += 1; st2["played"] += 1
            st1["sf"] += m["s1"]; st1["sa"] += m["s2"]
            st2["sf"] += m["s2"]; st2["sa"] += m["s1"]
            if aw:
                st1["wins"] += 1; st2["losses"] += 1
            else:
                st2["wins"] += 1; st1["losses"] += 1
            st1["matches"].append({"oppKey": p2k, "sf": m["s1"], "sa": m["s2"], "win": aw})
            st2["matches"].append({"oppKey": p1k, "sf": m["s2"], "sa": m["s1"], "win": not aw})

            day_updates.append(m)

        # Elo rodante se actualiza al final de la sesion, en orden cronologico,
        # para que ningun candidato de esta misma sesion vea el resultado de un
        # partido posterior de la sesion (nada de look-ahead).
        for m in sorted(day_updates, key=lambda x: x["rel_min"] or 0):
            update_rolling(elo, m["p1_key"], m["p2_key"], m["s1"], m["s2"], params)

    return picks


def replay(
    conn,
    warmup_start: date,
    eval_start: date,
    eval_end: date,
    params: StrategyParams,
) -> list[BacktestPick]:
    """warmup_start..eval_start-1 solo alimenta Elo/H2H (sin generar picks).
    eval_start..eval_end genera picks para partidos con cuota conocida.

    Para una sola corrida esto es lo mas simple. Para un sweep de muchas
    configuraciones sobre el MISMO rango de fechas, usa load_replay_data()
    una vez + replay_from_data() por combinacion -- ver backtest/sweep.py."""
    data = load_replay_data(conn, warmup_start, eval_start, eval_end)
    return replay_from_data(data, eval_start, eval_end, params)
