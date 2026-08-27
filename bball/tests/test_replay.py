import unittest

from bball.backtest.replay import Game, compute_candidates, picks_from_candidates, run_backtest, summarize


def _game(event_id, date, time_ts, home_key, away_key, home_score, away_score, league="NBA"):
    return Game(
        event_id=event_id, date=date, time_ts=time_ts, league_name=league,
        home_team=f"Home{home_key}", away_team=f"Away{away_key}",
        home_key=home_key, away_key=away_key, home_score=home_score, away_score=away_score,
    )


class RollingAverageNoLookaheadTests(unittest.TestCase):
    """N=2: un equipo necesita 2 partidos PREVIOS para ser evaluable. La
    media nunca debe incluir el propio partido ni ninguno posterior."""

    def test_first_two_games_of_a_team_are_not_evaluated(self):
        games = [
            _game("g1", "2026-01-01", 1, "A", "B", 100, 90),
            _game("g2", "2026-01-02", 2, "A", "C", 110, 95),
        ]
        # A todavia no tiene 2 partidos PREVIOS en ninguno de los dos -- sin candidatos.
        candidates = compute_candidates(games, {}, n_window=2)
        self.assertEqual(candidates, [])

    def test_third_game_uses_only_prior_two_scores(self):
        games = [
            _game("g1", "2026-01-01", 1, "A", "X", 100, 90),   # A anota 100
            _game("g2", "2026-01-02", 2, "A", "Y", 110, 95),   # A anota 110
            _game("g3", "2026-01-03", 3, "A", "Z", 999, 1),    # a evaluar -- 999 NO debe contaminar su propia media
        ]
        candidates = compute_candidates(games, {}, n_window=2)
        self.assertEqual(len(candidates), 0)  # Z (away) no tiene historial -- sigue sin ser candidato

        # Con Z tambien con historial, A vs Z ya es evaluable y su media es (100+110)/2=105 -- no 999.
        games2 = games + [
            _game("g4", "2025-12-30", -2, "Z", "W", 80, 70),
            _game("g5", "2025-12-31", -1, "Z", "V", 85, 75),
        ]
        games2.sort(key=lambda g: g.time_ts)
        candidates2 = compute_candidates(games2, {}, n_window=2)
        g3_candidate = next(c for c in candidates2 if c.game.event_id == "g3")
        self.assertAlmostEqual(g3_candidate.exp_total, 105.0 + 82.5)  # A=105, Z=(80+85)/2=82.5


class ThresholdAndBestOddsTests(unittest.TestCase):
    def _warmed_games(self):
        # A y B llegan con historial de sobra (N=2) antes del partido a evaluar.
        return [
            _game("w1", "2026-01-01", 1, "A", "X", 100, 90),
            _game("w2", "2026-01-02", 2, "A", "Y", 100, 90),
            _game("w3", "2026-01-01", 1, "B", "P", 100, 90),
            _game("w4", "2026-01-02", 2, "B", "Q", 100, 90),
            _game("target", "2026-01-05", 5, "A", "B", 95, 90),  # total real 185, exp_total = 100+100 = 200
        ]

    def test_below_threshold_excluded(self):
        games = self._warmed_games()
        odds = {"target": [{"book": "X", "line": 205.0, "over_odds": 1.9, "under_odds": 1.9}]}
        # colchon = 205 - 200 = 5 -- por debajo de umbral 8
        picks = run_backtest(games, odds, n_window=2, threshold=8)
        self.assertEqual(picks, [])

    def test_qualifying_pick_wins_when_actual_below_line(self):
        games = self._warmed_games()
        odds = {"target": [{"book": "X", "line": 210.0, "over_odds": 1.9, "under_odds": 1.9}]}
        picks = run_backtest(games, odds, n_window=2, threshold=8)
        self.assertEqual(len(picks), 1)
        p = picks[0]
        self.assertEqual(p.result, "WIN")  # total real 185 < linea 210
        self.assertAlmostEqual(p.pnl_1u, 0.9)
        self.assertAlmostEqual(p.cushion, 10.0)

    def test_best_odds_chosen_among_qualifying_books(self):
        games = self._warmed_games()
        odds = {"target": [
            {"book": "Low", "line": 209.0, "over_odds": 1.9, "under_odds": 1.70},
            {"book": "High", "line": 215.0, "over_odds": 1.9, "under_odds": 2.10},  # mejor cuota, tambien cumple umbral
        ]}
        picks = run_backtest(games, odds, n_window=2, threshold=8)
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0].book, "High")
        self.assertEqual(picks[0].under_odds, 2.10)

    def test_push_when_total_equals_line(self):
        games = self._warmed_games()
        odds = {"target": [{"book": "X", "line": 185.0, "over_odds": 1.9, "under_odds": 1.9}]}
        picks = run_backtest(games, odds, n_window=2, threshold=-100)  # forzar candidato aunque colchon sea 0
        self.assertEqual(picks[0].result, "PUSH")
        self.assertEqual(picks[0].pnl_1u, 0.0)

    def test_loss_when_actual_above_line(self):
        games = self._warmed_games()
        odds = {"target": [{"book": "X", "line": 180.0, "over_odds": 1.9, "under_odds": 1.9}]}
        picks = run_backtest(games, odds, n_window=2, threshold=-100)
        self.assertEqual(picks[0].result, "LOSS")
        self.assertEqual(picks[0].pnl_1u, -1.0)

    def test_tied_odds_deterministically_prefer_higher_line(self):
        """Bug real encontrado el 27/08: sin desempate explicito, un empate
        de cuota (comun -- 1.90/1.91/1.95 se repiten en muchas casas a
        lineas DISTINTAS) hacia que max() se quedara con lo primero que
        encontraba, dependiendo del orden -- NO garantizado -- en que la
        base de datos devolviera las filas. El mismo partido historico podia
        cambiar de GANADA a PERDIDA entre una corrida y la siguiente sin que
        cambiara ningun dato real. El orden de la lista de abajo es
        deliberado (la linea mas alta NO es la primera) para probar que el
        desempate es por criterio, no por casualidad de orden."""
        games = self._warmed_games()
        odds = {"target": [
            {"book": "Low", "line": 205.0, "over_odds": 1.9, "under_odds": 1.91},
            {"book": "High", "line": 212.0, "over_odds": 1.9, "under_odds": 1.91},  # misma cuota, linea mas alta
            {"book": "Mid", "line": 208.0, "over_odds": 1.9, "under_odds": 1.91},
        ]}
        picks = run_backtest(games, odds, n_window=2, threshold=1)
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0].book, "High")
        self.assertEqual(picks[0].line, 212.0)

    def test_results_are_reproducible_across_repeated_calls(self):
        """Regresion directa del bug de arriba: correr el mismo backtest dos
        veces sobre los mismos datos debe dar SIEMPRE el mismo resultado."""
        games = self._warmed_games()
        odds = {"target": [
            {"book": "A", "line": 210.0, "over_odds": 1.9, "under_odds": 1.91},
            {"book": "B", "line": 215.0, "over_odds": 1.9, "under_odds": 1.91},
        ]}
        first = run_backtest(games, odds, n_window=2, threshold=1)
        second = run_backtest(games, odds, n_window=2, threshold=1)
        self.assertEqual(first, second)


class ComputeCandidatesRefactorEquivalenceTests(unittest.TestCase):
    """run_backtest() = compute_candidates() + picks_from_candidates() -- el
    refactor de perf (backtest/sweep.py) no debe cambiar resultados."""

    def test_equivalent_to_two_step_call(self):
        games = [
            _game("w1", "2026-01-01", 1, "A", "X", 100, 90),
            _game("w2", "2026-01-02", 2, "A", "Y", 105, 95),
            _game("w3", "2026-01-01", 1, "B", "P", 100, 90),
            _game("w4", "2026-01-02", 2, "B", "Q", 95, 85),
            _game("target", "2026-01-05", 5, "A", "B", 95, 90),
        ]
        odds = {"target": [{"book": "X", "line": 199.0, "over_odds": 1.9, "under_odds": 1.95}]}
        threshold = -5  # exp_total=200 (A=102.5, B=97.5), linea 199 -> colchon -1: fuerza que SI haya pick
        direct = run_backtest(games, odds, n_window=2, threshold=threshold)
        self.assertEqual(len(direct), 1)  # confirma que este test ejercita un pick real, no dos listas vacias
        candidates = compute_candidates(games, odds, n_window=2)
        two_step = picks_from_candidates(candidates, n_window=2, threshold=threshold)
        self.assertEqual(direct, two_step)


class SummarizeTests(unittest.TestCase):
    def test_empty(self):
        s = summarize([])
        self.assertEqual(s.n, 0)
        self.assertEqual(s.hit_rate, 0.0)
        self.assertEqual(s.roi_pct, 0.0)

    def test_mixed_results(self):
        games = [
            _game("w1", "2026-01-01", 1, "A", "X", 100, 90),
            _game("w2", "2026-01-02", 2, "A", "Y", 100, 90),
            _game("w3", "2025-12-30", -2, "Z1", "P", 80, 70),
            _game("w4", "2025-12-31", -1, "Z1", "Q", 80, 70),
            _game("t1", "2026-01-05", 5, "A", "Z1", 90, 80),   # total 170 < 210 -- WIN
        ]
        games.sort(key=lambda g: g.time_ts)
        odds = {"t1": [{"book": "X", "line": 210.0, "over_odds": 1.9, "under_odds": 2.0}]}
        picks = run_backtest(games, odds, n_window=2, threshold=1)
        s = summarize(picks)
        self.assertEqual(s.n, 1)
        self.assertEqual(s.wins, 1)
        self.assertEqual(s.hit_rate, 1.0)
        self.assertAlmostEqual(s.roi_pct, 100.0)  # +1u de pnl sobre 1 apuesta = +100%


if __name__ == "__main__":
    unittest.main()
