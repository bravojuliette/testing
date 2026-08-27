import unittest

from bball.backtest.replay import Game
from bball.backtest.sweep import print_split_leaderboard, run_split_sweep, t_stat
from bball.tests.test_risk import _pick


def _game(event_id, date, time_ts, home_key, away_key, home_score, away_score):
    return Game(
        event_id=event_id, date=date, time_ts=time_ts, league_name="NBA",
        home_team=f"H{home_key}", away_team=f"A{away_key}",
        home_key=home_key, away_key=away_key, home_score=home_score, away_score=away_score,
    )


class TStatTests(unittest.TestCase):
    def test_none_with_fewer_than_two_picks(self):
        self.assertIsNone(t_stat([]))
        self.assertIsNone(t_stat([_pick("WIN")]))

    def test_none_with_zero_variance(self):
        # Todos los pnl identicos -> desviacion 0 -> t indefinido (no infinito).
        self.assertIsNone(t_stat([_pick("WIN", pnl=1.0), _pick("WIN", pnl=1.0)]))

    def test_positive_mean_gives_positive_t(self):
        picks = [_pick("WIN", pnl=1.0), _pick("WIN", pnl=1.0), _pick("LOSS", pnl=-1.0)]
        t = t_stat(picks)
        self.assertIsNotNone(t)
        self.assertGreater(t, 0)

    def test_negative_mean_gives_negative_t(self):
        picks = [_pick("LOSS", pnl=-1.0), _pick("LOSS", pnl=-1.0), _pick("WIN", pnl=1.0)]
        self.assertLess(t_stat(picks), 0)


class RunSplitSweepTests(unittest.TestCase):
    def test_search_holdout_partition_by_date(self):
        # A y B con historial de sobra (N=2) antes de CUALQUIER partido evaluado.
        warmup = [
            _game("w1", "2025-12-01", -20, "A", "X", 100, 90),
            _game("w2", "2025-12-02", -19, "A", "Y", 100, 90),
            _game("w3", "2025-12-01", -20, "B", "P", 100, 90),
            _game("w4", "2025-12-02", -19, "B", "Q", 100, 90),
        ]
        search_game = _game("s1", "2026-01-01", 1, "A", "B", 95, 90)   # antes del corte
        holdout_game = _game("h1", "2026-02-01", 2, "A", "B", 95, 90)  # despues del corte
        games = warmup + [search_game, holdout_game]
        games.sort(key=lambda g: g.time_ts)

        odds = {
            "s1": [{"book": "X", "line": 210.0, "over_odds": 1.9, "under_odds": 1.9}],
            "h1": [{"book": "X", "line": 210.0, "over_odds": 1.9, "under_odds": 1.9}],
        }
        results = run_split_sweep(games, odds, windows=[2], thresholds=[5], holdout_start="2026-01-15")
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.search.n, 1)
        self.assertEqual(r.holdout.n, 1)

    def test_print_split_leaderboard_does_not_crash_when_empty(self):
        print_split_leaderboard([], min_holdout_n=5)  # no debe lanzar excepcion


if __name__ == "__main__":
    unittest.main()
