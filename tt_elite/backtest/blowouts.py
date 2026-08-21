"""Analisis descriptivo: jugadores con alta tasa de resultados "barridos"
(0-3 o 3-0 -- el perdedor no gana ningun set). Pregunta: cuando dos
jugadores con alta tasa de barrida historica se enfrentan, ¿el partido en
si termina en barrida con mas frecuencia que el promedio general?

Para que esto sea honesto (y reutilizable como señal en vivo mas adelante,
no solo curiosidad estadistica) la tasa de cada jugador se acumula en orden
CRONOLOGICO y solo cuenta lo visto ANTES de este partido -- sin mirar el
resultado del propio partido ni partidos futuros. Igual que streaks.py.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class BlowoutObs:
    p1_prior_rate: float
    p2_prior_rate: float
    p1_prior_n: int
    p2_prior_n: int
    is_blowout: bool  # el partido en si termino 0-3/3-0


def _load_matches(conn, start: date, end: date):
    rows = conn.execute(
        "SELECT match_uid, p1_key, p2_key, s1, s2 FROM raw_matches "
        "WHERE date BETWEEN ? AND ? AND completed = 1 ORDER BY dt",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    return [dict(r) for r in rows]


def _accumulate_prior_rates(rows: list[dict]) -> dict[str, tuple[float, float, int, int]]:
    """Para cada partido (rows ya ordenadas por dt), calcula la tasa de
    barrida previa de cada jugador usando SOLO partidos anteriores a ese --
    igual que compute_blowout_observations, pero indexado por match_uid para
    poder reusarse como señal dentro del motor de backtest (replay.py), no
    solo para el reporte descriptivo standalone."""
    n_matches: dict[str, int] = defaultdict(int)
    n_blowouts: dict[str, int] = defaultdict(int)
    by_uid: dict[str, tuple[float, float, int, int]] = {}

    for r in rows:
        p1k, p2k = r["p1_key"], r["p2_key"]
        blowout = min(r["s1"], r["s2"]) == 0
        n1, n2 = n_matches[p1k], n_matches[p2k]
        p1_rate = (n_blowouts[p1k] / n1) if n1 else 0.0
        p2_rate = (n_blowouts[p2k] / n2) if n2 else 0.0
        by_uid[r["match_uid"]] = (p1_rate, p2_rate, n1, n2)

        n_matches[p1k] += 1
        n_matches[p2k] += 1
        if blowout:
            n_blowouts[p1k] += 1
            n_blowouts[p2k] += 1

    return by_uid


def compute_blowout_rates_by_match(conn, start: date, end: date) -> dict[str, tuple[float, float, int, int]]:
    """match_uid -> (p1_prior_rate, p2_prior_rate, p1_prior_n, p2_prior_n),
    para TODOS los partidos completados en [start, end] -- pensado para que
    replay.py la cargue una vez (junto con matches/odds) y la use como gate
    opcional (StrategyParams.min_blowout_rate) durante el backtest."""
    return _accumulate_prior_rates(_load_matches(conn, start, end))


def compute_blowout_observations(conn, start: date, end: date, min_prior_matches: int = 5) -> list[BlowoutObs]:
    rows = _load_matches(conn, start, end)
    by_uid = _accumulate_prior_rates(rows)

    obs: list[BlowoutObs] = []
    for r in rows:
        p1_rate, p2_rate, n1, n2 = by_uid[r["match_uid"]]
        if n1 >= min_prior_matches and n2 >= min_prior_matches:
            blowout = min(r["s1"], r["s2"]) == 0
            obs.append(BlowoutObs(
                p1_prior_rate=p1_rate, p2_prior_rate=p2_rate,
                p1_prior_n=n1, p2_prior_n=n2, is_blowout=blowout,
            ))

    return obs


def summarize(obs: list[BlowoutObs], thresholds=(0.20, 0.30, 0.40, 0.50, 0.60)) -> dict:
    baseline_rate = (sum(o.is_blowout for o in obs) / len(obs)) if obs else 0.0

    rows = []
    for th in thresholds:
        qualifying = [o for o in obs if min(o.p1_prior_rate, o.p2_prior_rate) >= th]
        n = len(qualifying)
        actual = (sum(o.is_blowout for o in qualifying) / n) if n else None
        rows.append({
            "threshold": th, "n_matches": n,
            "actual_blowout_rate": actual, "baseline_rate": baseline_rate,
            "deviation_pp": ((actual - baseline_rate) * 100) if actual is not None else None,
        })

    return {"baseline_rate": baseline_rate, "n_eligible": len(obs), "thresholds": rows}


def print_blowout_table(result: dict) -> None:
    print(f"Partidos elegibles (ambos jugadores con historial previo suficiente): {result['n_eligible']}")
    print(f"Tasa de barrida (0-3/3-0) base entre esos partidos: {result['baseline_rate']*100:.1f}%\n")
    print(f"{'umbral (tasa previa, ambos)':30s} {'n':>7s} {'barrida real':>13s} {'baseline':>9s} {'desv(pp)':>9s}")
    for r in result["thresholds"]:
        actual_s = f"{r['actual_blowout_rate']*100:.1f}%" if r["actual_blowout_rate"] is not None else "n/a"
        dev_s = f"{r['deviation_pp']:+.1f}" if r["deviation_pp"] is not None else "n/a"
        label = f">= {r['threshold']*100:.0f}% en ambos"
        print(f"{label:30s} {r['n_matches']:>7d} {actual_s:>13s} {result['baseline_rate']*100:>8.1f}% {dev_s:>9s}")
