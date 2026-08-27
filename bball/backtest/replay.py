"""Motor de backtest -- puro (sin red), corre contra lo que ya este cacheado
en bball_games/bball_odds. Reproduce la teoria del usuario:

    exp_total(A,B) = avg_puntos_anotados(A, ultimos N) + avg_puntos_anotados(B, ultimos N)
    colchon = linea_de_totales - exp_total
    señal: apostar UNDER si colchon >= umbral

Las medias moviles se calculan SOLO con partidos estrictamente anteriores al
que se evalua (nunca con el propio partido ni con partidos futuros) -- evita
fuga de informacion. Un equipo con menos de N partidos previos en los datos
ya cargados no se evalua (no hay suficiente "warmup"): esto significa que los
primeros dias de cualquier rango recolectado quedan fuera del backtest por
diseño, no es un bug.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .. import config


@dataclass
class Game:
    event_id: str
    date: str
    time_ts: int
    league_name: str
    home_team: str
    away_team: str
    home_key: str
    away_key: str
    home_score: int
    away_score: int

    @property
    def total(self) -> int:
        return self.home_score + self.away_score


@dataclass
class Pick:
    event_id: str
    date: str
    home_team: str
    away_team: str
    n_window: int
    threshold: float
    exp_total: float
    book: str
    line: float
    under_odds: float
    cushion: float
    final_total: int
    result: str  # WIN | LOSS | PUSH
    pnl_1u: float


def load_games(conn, leagues: list[str] | None = None) -> list[Game]:
    league_ids = [str(config.LEAGUES[l]) for l in leagues] if leagues else None
    if league_ids:
        placeholders = ",".join("?" for _ in league_ids)
        rows = conn.execute(
            f"SELECT * FROM bball_games WHERE completed=1 AND league_id IN ({placeholders}) ORDER BY time_ts",
            tuple(league_ids),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM bball_games WHERE completed=1 ORDER BY time_ts").fetchall()
    return [
        Game(
            event_id=r["event_id"], date=r["date"], time_ts=r["time_ts"] or 0,
            league_name=r["league_name"], home_team=r["home_team"], away_team=r["away_team"],
            home_key=r["home_key"], away_key=r["away_key"],
            home_score=r["home_score"], away_score=r["away_score"],
        )
        for r in rows
    ]


def load_totals_odds(conn) -> dict[str, list[dict]]:
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds WHERE market = ?",
        (config.TOTALS_MARKET_KEY,),
    ).fetchall()
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["event_id"]].append({
            "book": r["book"], "line": r["line"], "over_odds": r["over_odds"], "under_odds": r["under_odds"],
        })
    return out


def _rolling_avg(history: list[int], n: int) -> float | None:
    if len(history) < n:
        return None
    return sum(history[-n:]) / n


def run_backtest(games: list[Game], odds_by_event: dict[str, list[dict]], n_window: int, threshold: float) -> list[Pick]:
    """games debe venir ordenado por time_ts ascendente (load_games ya lo hace)."""
    pf_history: dict[str, list[int]] = defaultdict(list)
    picks: list[Pick] = []

    for g in games:
        home_hist = pf_history[g.home_key]
        away_hist = pf_history[g.away_key]
        avg_home = _rolling_avg(home_hist, n_window)
        avg_away = _rolling_avg(away_hist, n_window)

        if avg_home is not None and avg_away is not None:
            exp_total = avg_home + avg_away
            candidates = [
                o for o in odds_by_event.get(g.event_id, [])
                if o["line"] is not None and o["under_odds"] and (o["line"] - exp_total) >= threshold
            ]
            if candidates:
                best = max(candidates, key=lambda o: o["under_odds"])
                cushion = best["line"] - exp_total
                if g.total < best["line"]:
                    result, pnl = "WIN", best["under_odds"] - 1
                elif g.total > best["line"]:
                    result, pnl = "LOSS", -1.0
                else:
                    result, pnl = "PUSH", 0.0
                picks.append(Pick(
                    event_id=g.event_id, date=g.date, home_team=g.home_team, away_team=g.away_team,
                    n_window=n_window, threshold=threshold, exp_total=exp_total, book=best["book"],
                    line=best["line"], under_odds=best["under_odds"], cushion=cushion,
                    final_total=g.total, result=result, pnl_1u=pnl,
                ))

        # Actualiza el historial DESPUES de evaluar esta señal -- nunca antes.
        pf_history[g.home_key].append(g.home_score)
        pf_history[g.away_key].append(g.away_score)

    return picks


@dataclass
class Summary:
    n: int = 0
    n_decided: int = 0
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    pnl: float = 0.0
    mean_odds: float = 0.0

    @property
    def hit_rate(self) -> float:
        return self.wins / self.n_decided if self.n_decided else 0.0

    @property
    def roi_pct(self) -> float:
        return (self.pnl / self.n * 100) if self.n else 0.0


def summarize(picks: list[Pick]) -> Summary:
    s = Summary()
    s.n = len(picks)
    odds_sum = 0.0
    for p in picks:
        s.pnl += p.pnl_1u
        odds_sum += p.under_odds
        if p.result == "WIN":
            s.wins += 1
        elif p.result == "LOSS":
            s.losses += 1
        else:
            s.pushes += 1
    s.n_decided = s.wins + s.losses
    s.mean_odds = odds_sum / s.n if s.n else 0.0
    return s
