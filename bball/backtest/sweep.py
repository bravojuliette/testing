"""Sweep con separacion busqueda/reserva -- mismo principio que
tt_elite/backtest/sweep.py: nunca te creas el ROI de una configuracion
elegida mirando el mismo periodo que la genero. `holdout_start` parte el
historico ya cargado en dos: BUSQUEDA (antes de esa fecha, se puede mirar
libremente para elegir N/umbral) y RESERVA (desde esa fecha, se usa
UNICAMENTE para comprobar -- nunca para elegir nada). Sin esto, un ROI
positivo en 'backtest' puede ser sobreajuste al ruido de la propia ventana
usada para barrer parametros, exactamente lo que le paso a la primera pasada
del sistema de tenis de mesa (ver EXPERIMENTS_LOG.md, 2026-08-23)."""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from .replay import Game, Pick, Summary, compute_candidates, picks_from_candidates, summarize


@dataclass
class SplitResult:
    n_window: int
    threshold: float
    search: Summary
    holdout: Summary
    holdout_t: float | None


def t_stat(picks: list[Pick]) -> float | None:
    """t aproximado de la media de pnl_1u contra 0 -- una t>=2 es la
    convencion informal ya usada en este repo para 'probablemente no es
    ruido' (no es un test riguroso, es una señal de alarma barata)."""
    n = len(picks)
    if n < 2:
        return None
    pnls = [p.pnl_1u for p in picks]
    sd = statistics.pstdev(pnls)
    if sd == 0:
        return None
    return (statistics.mean(pnls) / sd) * (n ** 0.5)


def run_split_sweep(
    games: list[Game],
    odds_by_event: dict[str, list[dict]],
    windows: list[int],
    thresholds: list[float],
    holdout_start: str,
) -> list[SplitResult]:
    results = []
    for n_window in windows:
        # Un solo pase de medias moviles por N -- picks_from_candidates() por
        # cada umbral es solo filtrar en memoria, nada de recalcular historia.
        candidates = compute_candidates(games, odds_by_event, n_window)
        for threshold in thresholds:
            picks = picks_from_candidates(candidates, n_window, threshold)
            search_picks = [p for p in picks if p.date < holdout_start]
            holdout_picks = [p for p in picks if p.date >= holdout_start]
            results.append(SplitResult(
                n_window=n_window, threshold=threshold,
                search=summarize(search_picks), holdout=summarize(holdout_picks),
                holdout_t=t_stat(holdout_picks),
            ))
    return results


def print_split_leaderboard(results: list[SplitResult], min_holdout_n: int = 5) -> None:
    """Ordena por ROI de RESERVA (nunca de busqueda) -- solo eso es la
    pregunta real ('¿se sostiene fuera de la ventana usada para elegir?').
    Filtra por un minimo de muestra en reserva para no dejar que 2 aciertos
    de suerte parezcan un sistema ganador."""
    qualified = [r for r in results if r.holdout.n >= min_holdout_n]
    qualified.sort(key=lambda r: r.holdout.roi_pct, reverse=True)
    print(f"{'N':>4} {'umbral':>7} | {'busqueda n/hit/ROI':>22} | {'RESERVA n/hit/ROI':>22} | {'t':>5}")
    for r in qualified:
        s, h = r.search, r.holdout
        s_str = f"{s.n:>3}/{s.hit_rate*100:>5.1f}%/{s.roi_pct:>+6.1f}%"
        h_str = f"{h.n:>3}/{h.hit_rate*100:>5.1f}%/{h.roi_pct:>+6.1f}%"
        t_str = f"{r.holdout_t:.2f}" if r.holdout_t is not None else "-"
        flag = " *" if (r.holdout_t or 0) >= 2 else ""
        print(f"{r.n_window:>4} {r.threshold:>7.1f} | {s_str:>22} | {h_str:>22} | {t_str:>5}{flag}")
    if not qualified:
        print(f"Ninguna combinacion llega a {min_holdout_n} picks en la reserva todavia -- hace falta mas historico.")
    else:
        print("\n* t>=2 en la reserva -- convencion informal de este repo para 'probablemente no es ruido' (no es un test riguroso).")
