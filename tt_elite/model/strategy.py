"""Evaluacion de una linea de cuotas contra el modelo -> senal accionable.

SI            = discrepancia suficiente sobre la linea de referencia (no-fallback).
SI_FALLBACK   = discrepancia FUERTE sobre una linea de un bookmaker fallback
                (mas exigente, porque la cuota es menos fiable).
REVISAR       = discrepancia moderada sobre un fallback: no se dispara alerta
                "fuerte", pero vale la pena mirarlo a mano.
NO            = no hay pick.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .params import StrategyParams


@dataclass
class PickEvaluation:
    underdog_is_p1: bool
    market_prob_underdog: float
    model_prob_underdog: float
    odds_underdog: float
    edge_pp: float
    ev_pct: float
    fair_odds: float
    market_gap: float
    signal: str  # SI | SI_FALLBACK | REVISAR | NO

    @property
    def actionable(self) -> bool:
        return self.signal in ("SI", "SI_FALLBACK")


def evaluate_pick(
    mp1: float,
    mp2: float,
    model_p1: float,
    model_p2: float,
    odds1: float,
    odds2: float,
    is_fallback: bool,
    p: StrategyParams,
) -> PickEvaluation:
    underdog_is_p1 = mp1 < mp2
    mu = mp1 if underdog_is_p1 else mp2
    mm = model_p1 if underdog_is_p1 else model_p2
    odds_u = odds1 if underdog_is_p1 else odds2

    edge = mm - mu
    ev = mm * odds_u - 1
    gap = abs(mp1 - mp2)
    odds_ok = p.min_odds_underdog <= odds_u <= p.max_odds_underdog

    standard = odds_ok and gap >= p.min_market_gap and mm >= p.min_model and edge >= p.min_edge and ev >= p.min_ev
    strong_fb = odds_ok and gap >= p.min_market_gap and mm >= p.fb_min_model and edge >= p.fb_min_edge and ev >= p.fb_min_ev

    if not is_fallback and standard:
        signal = "SI"
    elif is_fallback and strong_fb:
        signal = "SI_FALLBACK"
    elif is_fallback and standard:
        signal = "REVISAR"
    else:
        signal = "NO"

    return PickEvaluation(
        underdog_is_p1=underdog_is_p1,
        market_prob_underdog=mu,
        model_prob_underdog=mm,
        odds_underdog=odds_u,
        edge_pp=edge,
        ev_pct=ev,
        fair_odds=(1 / mm) if mm > 0 else float("inf"),
        market_gap=gap,
        signal=signal,
    )
