"""Sweep de parametros: corre un StrategyParams (o muchos) sobre datos ya
cacheados, separando train (para mirar/ajustar) de test (validacion
out-of-sample real). Guarda cada corrida en la tabla `experiments` para poder
comparar variantes a lo largo del tiempo.

El objetivo de "encontrar un sistema ganador" se resuelve asi: nunca eligas
una configuracion por su ROI en train (eso es sobreajuste garantizado con
datos de apuestas). Elige por ROI/hit-rate en test, con tamano de muestra
minimo, y confirma que se sostiene walk-forward (varios splits, no uno solo).
"""
from __future__ import annotations

import itertools
import json
import statistics
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Iterable

from ..model.params import StrategyParams
from .replay import BacktestPick, ReplayData, load_replay_data, replay, replay_from_data


def _metrics(picks: list[BacktestPick]) -> dict:
    n = len(picks)
    if n == 0:
        return {"n": 0, "hit_rate": None, "roi": None, "pnl": 0.0, "sharpe": None}
    wins = sum(1 for p in picks if p.result == "WIN")
    pnl_total = sum(p.pnl_1u for p in picks)
    roi = pnl_total / n * 100
    pnl_list = [p.pnl_1u for p in picks]
    sharpe = (statistics.mean(pnl_list) / statistics.pstdev(pnl_list)) if n > 1 and statistics.pstdev(pnl_list) > 0 else None
    return {"n": n, "hit_rate": wins / n, "roi": roi, "pnl": pnl_total, "sharpe": sharpe}


def _build_result(
    picks: list[BacktestPick],
    params: StrategyParams,
    test_start: date,
    *,
    name: str,
) -> dict:
    train_picks = [p for p in picks if p.date < test_start.isoformat()]
    test_picks = [p for p in picks if p.date >= test_start.isoformat()]
    return {
        "name": name,
        "params": params,
        "train": _metrics(train_picks),
        "test": _metrics(test_picks),
        "train_picks": train_picks,
        "test_picks": test_picks,
    }


def _save_experiment(conn, result: dict, params: StrategyParams, warmup_start: date, test_start: date, test_end: date, notes: str) -> None:
    m_train, m_test = result["train"], result["test"]
    conn.execute(
        """INSERT INTO experiments
           (name, params_hash, params_json, created_at, period_start, period_end, split_date,
            n_train, hit_rate_train, roi_train, pnl_train,
            n_test, hit_rate_test, roi_test, pnl_test, sharpe_test, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            result["name"], params.hash(), params.to_json(), datetime.now(timezone.utc).isoformat(),
            warmup_start.isoformat(), test_end.isoformat(), test_start.isoformat(),
            m_train["n"], m_train["hit_rate"], m_train["roi"], m_train["pnl"],
            m_test["n"], m_test["hit_rate"], m_test["roi"], m_test["pnl"], m_test["sharpe"], notes,
        ),
    )
    conn.commit()


def run_experiment(
    conn,
    params: StrategyParams,
    warmup_start: date,
    train_start: date,
    test_start: date,
    test_end: date,
    *,
    name: str | None = None,
    save: bool = True,
    notes: str = "",
) -> dict:
    """Una sola pasada de replay cubre train+test; se separan por fecha despues
    (mas barato que recorrer dos veces el mismo historico). Para MUCHAS
    configuraciones sobre el mismo rango, usa grid_sweep -- carga los datos
    una sola vez en vez de repetir esta consulta por cada combinacion."""
    picks = replay(conn, warmup_start, train_start, test_end, params)
    result = _build_result(picks, params, test_start, name=name or params.name)
    if save:
        _save_experiment(conn, result, params, warmup_start, test_start, test_end, notes)
    return result


def run_experiment_from_data(
    data: ReplayData,
    params: StrategyParams,
    train_start: date,
    test_start: date,
    test_end: date,
    *,
    name: str | None = None,
    conn=None,
    save: bool = True,
    notes: str = "",
    warmup_start: date | None = None,
) -> dict:
    """Igual que run_experiment, pero sobre datos ya cargados (ReplayData) --
    sin volver a consultar la base de datos. Esto es lo que usa grid_sweep."""
    picks = replay_from_data(data, train_start, test_end, params)
    result = _build_result(picks, params, test_start, name=name or params.name)
    if save:
        if conn is None or warmup_start is None:
            raise ValueError("save=True requiere conn y warmup_start")
        _save_experiment(conn, result, params, warmup_start, test_start, test_end, notes)
    return result


def grid_sweep(
    conn,
    base: StrategyParams,
    grid: dict[str, list],
    warmup_start: date,
    train_start: date,
    test_start: date,
    test_end: date,
    *,
    min_test_samples: int = 20,
    save: bool = True,
) -> list[dict]:
    """Prueba todas las combinaciones de `grid` (nombre_de_campo -> lista de valores)
    sobre `base`. Carga los datos del rango UNA sola vez (nada de red por
    combinacion) y reproduce cada combinacion en memoria. Devuelve resultados
    ordenados por ROI de test (solo variantes con al menos `min_test_samples`
    picks en test, para evitar que 2 aciertos de suerte parezcan un sistema
    ganador)."""
    data = load_replay_data(conn, warmup_start, train_start, test_end)

    keys = list(grid.keys())
    results = []
    for combo in itertools.product(*[grid[k] for k in keys]):
        overrides = dict(zip(keys, combo))
        params = replace(base, **overrides)
        label = ",".join(f"{k}={v}" for k, v in overrides.items())
        res = run_experiment_from_data(
            data, params, train_start, test_start, test_end,
            name=f"{base.name}[{label}]", conn=conn, save=save, notes="", warmup_start=warmup_start,
        )
        results.append(res)

    qualified = [r for r in results if (r["test"]["n"] or 0) >= min_test_samples]
    qualified.sort(key=lambda r: (r["test"]["roi"] if r["test"]["roi"] is not None else -999), reverse=True)
    return qualified


def print_leaderboard(results: list[dict], top: int = 15) -> None:
    print(f"{'params':45s} {'train n/hit/roi':22s} {'test n/hit/roi/sharpe':30s}")
    for r in results[:top]:
        tr, te = r["train"], r["test"]
        tr_s = f"{tr['n']}/{(tr['hit_rate'] or 0):.0%}/{(tr['roi'] or 0):+.1f}%"
        te_s = f"{te['n']}/{(te['hit_rate'] or 0):.0%}/{(te['roi'] or 0):+.1f}%/{te['sharpe'] if te['sharpe'] is not None else '-'}"
        print(f"{r['name'][:45]:45s} {tr_s:22s} {te_s:30s}")
