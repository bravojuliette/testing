"""Parametros del modelo/estrategia, como datos -- no como constantes de modulo.

Esta es la pieza clave para poder experimentar: cualquier combinacion de estos
valores se puede instanciar y correr contra los mismos datos historicos sin
tocar codigo ni volver a scrapear nada.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StrategyParams:
    name: str = "baseline_v7"

    # Elo / forma.
    initial_elo: float = 1000.0
    rolling_elo_k: float = 24.0
    elo_scale: float = 400.0
    session_k: float = 42.0
    session_delta_cap: float = 105.0
    common_opp_k: float = 25.0
    common_opp_cap: float = 40.0
    h2h_weight: float = 0.15
    h2h_cap: float = 35.0
    h2h_max_matches: int = 20
    min_matches_played: int = 3

    # Filtros de senal (linea "de referencia", p.ej. Interwetten).
    min_model: float = 0.52
    min_edge: float = 0.06
    min_ev: float = 0.03
    min_market_gap: float = 0.005

    # Filtros de senal cuando la cuota viene de un bookmaker fallback (mas exigentes).
    fb_min_model: float = 0.55
    fb_min_edge: float = 0.10
    fb_min_ev: float = 0.08

    def hash(self) -> str:
        d = asdict(self)
        d.pop("name", None)
        return hashlib.sha1(json.dumps(d, sort_keys=True).encode()).hexdigest()[:12]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @staticmethod
    def from_json(s: str) -> "StrategyParams":
        return StrategyParams(**json.loads(s))


# El punto de partida = los thresholds que ya tenias corriendo en Apps Script v7.1
# y en el backtest Colab v5. Sirve como baseline para comparar cualquier variante
# que salga de un sweep.
BASELINE = StrategyParams(name="baseline_v7")
