"""Que StrategyParams usa el scanner en vivo ahora mismo.

Flujo pensado: corres sweeps -> revisas el leaderboard de `experiments` ->
cuando confias en una configuracion, la copias a config/active_strategy.json
(o corres `python -m tt_elite.cli promote <experiment_id>`) -> el scanner en
vivo la recoge automaticamente en la siguiente ejecucion.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import config
from .params import BASELINE, StrategyParams

ACTIVE_STRATEGY_PATH = config.ROOT_DIR / "config" / "active_strategy.json"


def load_active_params() -> StrategyParams:
    if ACTIVE_STRATEGY_PATH.exists():
        return StrategyParams.from_json(ACTIVE_STRATEGY_PATH.read_text())
    return BASELINE


def save_active_params(params: StrategyParams) -> None:
    ACTIVE_STRATEGY_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_STRATEGY_PATH.write_text(params.to_json())
