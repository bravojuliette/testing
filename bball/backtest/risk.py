"""Riesgo de banca: racha de perdidas, drawdown sobre la secuencia HISTORICA
real (orden cronologico, tal cual paso), y una simulacion Monte Carlo que
remuestrea esos mismos resultados para explorar secuencias ALTERNATIVAS
igual de plausibles -- la secuencia real es solo una muestra de lo que
pudo pasar, no reproduce necesariamente el peor caso. Mismo analisis que se
hizo (a mano, sin modulo reusable) para tt_elite el 2026-08-24 antes de
promocionar una estrategia -- aqui queda como codigo para no rehacerlo cada
vez."""
from __future__ import annotations

import random
from dataclasses import dataclass

from .replay import Pick


def max_losing_streak(picks: list[Pick]) -> int:
    best = cur = 0
    for p in picks:
        if p.result == "LOSS":
            cur += 1
            best = max(best, cur)
        elif p.result == "WIN":
            cur = 0
        # PUSH ni corta ni extiende la racha -- no fue ni victoria ni derrota.
    return best


@dataclass
class DrawdownResult:
    max_drawdown_units: float
    final_pnl_units: float
    curve: list[float]  # pnl acumulado, 1 punto por pick, en orden cronologico


def drawdown_curve(picks: list[Pick]) -> DrawdownResult:
    """Apostando 1u fija por pick (no un % de banca) -- el mismo supuesto
    simplificado que se uso para reportar el drawdown de tt_elite."""
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    curve: list[float] = []
    for p in picks:
        cum += p.pnl_1u
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
        curve.append(cum)
    return DrawdownResult(max_drawdown_units=max_dd, final_pnl_units=cum, curve=curve)


@dataclass
class MonteCarloResult:
    n_sims: int
    n_bets: int
    stake_fraction: float
    ruin_threshold_pct: float
    prob_ruin: float
    p1: float  # percentil 1 de banca_final / banca_inicial
    p5: float
    p50: float
    p95: float


def simulate_bankroll(
    picks: list[Pick],
    n_sims: int = 5000,
    stake_fraction: float = 0.02,
    ruin_threshold_pct: float = 0.5,
) -> MonteCarloResult:
    """Remuestrea (bootstrap, CON reemplazo) los resultados WIN/LOSS ya
    observados -- no la secuencia original, sino resultados individuales
    sacados al azar de la bolsa de lo que ya paso -- para generar `n_sims`
    secuencias alternativas de la misma longitud, apostando siempre
    `stake_fraction` de la banca ACTUAL (nunca una cantidad fija). Reporta
    en que fraccion de esas secuencias la banca cae por debajo de
    `ruin_threshold_pct` de la inicial en algun momento (probabilidad de
    ruina), y los percentiles de banca final. PUSH se excluye -- no cambia
    la banca, remuestrearlo solo diluye la muestra sin aportar nada."""
    outcomes = [(p.result, p.under_odds) for p in picks if p.result in ("WIN", "LOSS")]
    n = len(outcomes)
    if n == 0:
        raise ValueError("No hay picks WIN/LOSS para simular.")

    finals: list[float] = []
    ruin_count = 0
    for _ in range(n_sims):
        bankroll = 1.0
        min_bankroll = bankroll
        for _ in range(n):
            result, odds = outcomes[random.randrange(n)]
            stake = bankroll * stake_fraction
            if result == "WIN":
                bankroll += stake * (odds - 1)
            else:
                bankroll -= stake
            if bankroll < min_bankroll:
                min_bankroll = bankroll
        finals.append(bankroll)
        if min_bankroll <= ruin_threshold_pct:
            ruin_count += 1

    finals.sort()

    def pct(p: float) -> float:
        idx = min(len(finals) - 1, max(0, int(round(p / 100 * (len(finals) - 1)))))
        return finals[idx]

    return MonteCarloResult(
        n_sims=n_sims, n_bets=n, stake_fraction=stake_fraction, ruin_threshold_pct=ruin_threshold_pct,
        prob_ruin=ruin_count / n_sims, p1=pct(1), p5=pct(5), p50=pct(50), p95=pct(95),
    )
