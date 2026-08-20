"""Motor de rating: Elo rodante + forma de sesion + rivales comunes + H2H.

Puerto directo (parametrizado) de la logica que ya tenias validada en
tt_elite_scanner_v7_1.gs y tt_elite_backtest_colab_v5.py. Sin I/O: todo
recibe datos ya cargados en memoria, para poder correr miles de variantes
de parametros rapido durante un sweep.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, TypedDict

from ..textutil import clip
from .params import StrategyParams


class MatchRef(TypedDict):
    oppKey: str
    sf: int  # sets a favor
    sa: int  # sets en contra
    win: bool


def elo_prob(a: float, b: float, scale: float) -> float:
    return 1 / (1 + 10 ** ((b - a) / scale))


def match_perf(m: MatchRef) -> float:
    return 0.75 * (1 if m["win"] else -1) + 0.25 * clip((m["sf"] - m["sa"]) / 3, -1, 1)


def session_delta(matches: List[MatchRef], own_elo: float, ranking: Dict[str, float], p: StrategyParams) -> float:
    d = 0.0
    for m in matches:
        opp = ranking.get(m["oppKey"])
        if opp is None:
            continue
        expected = elo_prob(own_elo, opp, p.elo_scale)
        margin = min(1, abs(m["sf"] - m["sa"]) / 3)
        d += p.session_k * ((1 if m["win"] else 0) - expected) * (0.85 + 0.30 * margin)
    return clip(d, -p.session_delta_cap, p.session_delta_cap)


def common_adjust(matches_a: List[MatchRef], matches_b: List[MatchRef], p: StrategyParams):
    aa = {m["oppKey"]: match_perf(m) for m in matches_a}
    bb = {m["oppKey"]: match_perf(m) for m in matches_b}
    diffs = [aa[k] - bb[k] for k in aa if k in bb]
    if not diffs:
        return 0, 0.0
    avg = sum(diffs) / len(diffs)
    return len(diffs), clip(avg * p.common_opp_k, -p.common_opp_cap, p.common_opp_cap)


def h2h_adjust(n: int, p1_wins: int, p: StrategyParams) -> float:
    if n < 3:
        return 0.0
    prob = (p1_wins + 1.5) / (n + 3)
    return clip(p.elo_scale * math.log10(prob / (1 - prob)) * p.h2h_weight, -p.h2h_cap, p.h2h_cap)


def compute_model(
    e1: float,
    e2: float,
    matches1: List[MatchRef],
    matches2: List[MatchRef],
    h2h_n: int,
    h2h_p1_wins: int,
    ranking: Dict[str, float],
    p: StrategyParams,
) -> dict:
    d1 = session_delta(matches1, e1, ranking, p)
    d2 = session_delta(matches2, e2, ranking, p)
    common_n, common_adj = common_adjust(matches1, matches2, p)
    hadj = h2h_adjust(h2h_n, h2h_p1_wins, p)
    diff = (e1 + d1) - (e2 + d2) + common_adj + hadj
    p1 = 1 / (1 + 10 ** (-diff / p.elo_scale))
    return {
        "elo1": e1, "elo2": e2,
        "delta1": d1, "delta2": d2,
        "common_n": common_n, "common": common_adj,
        "h2h_adj": hadj,
        "p1": p1, "p2": 1 - p1,
    }


def update_rolling(elo: Dict[str, float], p1k: str, p2k: str, s1: int, s2: int, p: StrategyParams) -> None:
    a = elo.get(p1k, p.initial_elo)
    b = elo.get(p2k, p.initial_elo)
    exp = elo_prob(a, b, p.elo_scale)
    act = 1 if s1 > s2 else 0
    mult = 0.85 + 0.30 * min(1, abs(s1 - s2) / 3)
    d = p.rolling_elo_k * (act - exp) * mult
    elo[p1k] = a + d
    elo[p2k] = b - d
