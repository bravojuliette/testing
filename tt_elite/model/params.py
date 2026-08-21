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

    # Filtro por rango de cuota del underdog -- descarta candidatos con cuota
    # demasiado baja (poco margen real) o demasiado alta (underdogs extremos,
    # mas ruido). Por defecto sin filtro (1.0/1000.0 = deja pasar cualquier cuota valida).
    min_odds_underdog: float = 1.0
    max_odds_underdog: float = 1000.0

    # Filtro "ambos jugadores con historial de barridas" (ver backtest/blowouts.py):
    # exige que la tasa previa de resultados 0-3/3-0 de AMBOS jugadores este
    # por encima de este umbral, con al menos blowout_min_prior partidos previos
    # cada uno. 0.0 = sin filtro (comportamiento por defecto, no toca nada existente).
    min_blowout_rate: float = 0.0
    blowout_min_prior: int = 5

    # Bonus/penalizacion de racha DENTRO de la sesion, calibrado con la
    # desviacion REAL medida contra Elo puro en backtest/streaks.py (no el
    # viejo session_delta, que sobreajustaba -- ver EXPERIMENTS_LOG.md). Son
    # pp que se suman a la probabilidad del modelo por cada unidad de racha
    # (hasta streak_len=4): se suman si el jugador llega en racha de
    # victorias, se restan si llega en racha de derrotas. 0.0 = sin efecto
    # (comportamiento por defecto, no toca nada existente).
    streak_bonus_pp: float = 0.0

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
