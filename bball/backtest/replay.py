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


def load_totals_odds(conn, book: str | None = None) -> dict[str, list[dict]]:
    """book=None (por defecto): todas las casas cubiertas, picks_from_candidates()
    elige la mejor disponible cada partido -- lo que rendiria comparando
    precios entre casas. book='BWin' (o cualquier otra, ver bball_odds.book):
    restringe TODO al historico de esa unica casa -- lo que rendiria de
    verdad si solo se puede apostar ahi. Un partido sin cuota de esa casa
    simplemente no genera candidato (no hay con que comparar)."""
    # ORDER BY explicito -- sin el, el orden de las filas no esta garantizado
    # (ni en SQLite ni en Turso), y picks_from_candidates() desempata "mejor
    # cuota" tomando la PRIMERA que encuentra en caso de empate exacto (muy
    # comun: 1.90/1.91/1.95 se repiten en muchas casas a lineas DISTINTAS).
    # Sin orden estable, el mismo partido historico podia dar un pick
    # distinto -- y por tanto GANAR o PERDER distinto -- entre una corrida y
    # la siguiente, sin que cambiara ningun dato real.
    sql = "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds WHERE market = ?"
    params: list = [config.TOTALS_MARKET_KEY]
    if book:
        sql += " AND book = ?"
        params.append(book)
    sql += " ORDER BY event_id, under_odds DESC, line DESC, book"
    rows = conn.execute(sql, params).fetchall()
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


@dataclass
class Candidate:
    game: Game
    exp_total: float
    odds: list[dict]  # cuotas de totales disponibles para este partido (sin filtrar por umbral)


def compute_candidates(games: list[Game], odds_by_event: dict[str, list[dict]], n_window: int) -> list[Candidate]:
    """Un solo pase por el historico (medias moviles + cuotas disponibles),
    INDEPENDIENTE del umbral -- separado de picks_from_candidates() para que
    barrer muchos umbrales sobre el mismo N (ver backtest/sweep.py) no repita
    este calculo una vez por cada umbral. games debe venir ordenado por
    time_ts ascendente (load_games ya lo hace)."""
    pf_history: dict[str, list[int]] = defaultdict(list)
    out: list[Candidate] = []

    for g in games:
        avg_home = _rolling_avg(pf_history[g.home_key], n_window)
        avg_away = _rolling_avg(pf_history[g.away_key], n_window)
        if avg_home is not None and avg_away is not None:
            out.append(Candidate(game=g, exp_total=avg_home + avg_away, odds=odds_by_event.get(g.event_id, [])))

        # Actualiza el historial DESPUES de evaluar esta señal -- nunca antes.
        pf_history[g.home_key].append(g.home_score)
        pf_history[g.away_key].append(g.away_score)

    return out


def picks_from_candidates(candidates: list[Candidate], n_window: int, threshold: float) -> list[Pick]:
    picks: list[Pick] = []
    for c in candidates:
        qualifying = [
            o for o in c.odds
            if o["line"] is not None and o["under_odds"] and (o["line"] - c.exp_total) >= threshold
        ]
        if not qualifying:
            continue
        # Desempate DETERMINISTA: a igual cuota (muy comun -- 1.90/1.91/1.95
        # se repiten en muchas casas a lineas distintas), se prefiere la
        # linea mas alta -- mismo precio, mas colchon, estrictamente mejor
        # para quien apuesta. Sin este desempate explicito, max() se queda
        # con lo primero que encuentra en caso de empate, que dependia del
        # orden (no garantizado) en que la base devolviera las filas.
        best = max(qualifying, key=lambda o: (o["under_odds"], o["line"]))
        cushion = best["line"] - c.exp_total
        g = c.game
        if g.total < best["line"]:
            result, pnl = "WIN", best["under_odds"] - 1
        elif g.total > best["line"]:
            result, pnl = "LOSS", -1.0
        else:
            result, pnl = "PUSH", 0.0
        picks.append(Pick(
            event_id=g.event_id, date=g.date, home_team=g.home_team, away_team=g.away_team,
            n_window=n_window, threshold=threshold, exp_total=c.exp_total, book=best["book"],
            line=best["line"], under_odds=best["under_odds"], cushion=cushion,
            final_total=g.total, result=result, pnl_1u=pnl,
        ))
    return picks


def run_backtest(games: list[Game], odds_by_event: dict[str, list[dict]], n_window: int, threshold: float) -> list[Pick]:
    """Conveniencia para un (N, umbral) suelto -- cli.py backtest/risk/backtest-summary.
    Para barrer varios umbrales sobre el mismo N, usa compute_candidates()
    una vez y picks_from_candidates() por cada umbral (ver backtest/sweep.py)."""
    candidates = compute_candidates(games, odds_by_event, n_window)
    return picks_from_candidates(candidates, n_window, threshold)


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
