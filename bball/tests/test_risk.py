import unittest

from bball.backtest.replay import Pick
from bball.backtest.risk import drawdown_curve, max_losing_streak, simulate_bankroll


def _pick(result, under_odds=2.0, pnl=None):
    if pnl is None:
        pnl = (under_odds - 1) if result == "WIN" else (-1.0 if result == "LOSS" else 0.0)
    return Pick(
        event_id="e", date="2026-01-01", home_team="H", away_team="A",
        n_window=10, threshold=5, exp_total=180.0, book="X", line=185.0,
        under_odds=under_odds, cushion=5.0, final_total=170, result=result, pnl_1u=pnl,
    )


class MaxLosingStreakTests(unittest.TestCase):
    def test_no_losses(self):
        self.assertEqual(max_losing_streak([_pick("WIN"), _pick("WIN")]), 0)

    def test_streak_broken_by_win(self):
        picks = [_pick("LOSS"), _pick("LOSS"), _pick("WIN"), _pick("LOSS")]
        self.assertEqual(max_losing_streak(picks), 2)

    def test_push_does_not_break_streak(self):
        # PUSH no es una victoria -- NO corta la racha (solo un WIN la corta).
        # LOSS, PUSH, LOSS, LOSS es una unica racha ininterrumpida de 3
        # derrotas con un PUSH neutral en medio (que tampoco suma a la cuenta).
        picks = [_pick("LOSS"), _pick("PUSH"), _pick("LOSS"), _pick("LOSS")]
        self.assertEqual(max_losing_streak(picks), 3)

    def test_win_breaks_streak_but_push_does_not(self):
        picks = [_pick("LOSS"), _pick("LOSS"), _pick("WIN"), _pick("LOSS"), _pick("PUSH"), _pick("LOSS")]
        self.assertEqual(max_losing_streak(picks), 2)

    def test_trailing_streak_counted(self):
        picks = [_pick("WIN"), _pick("LOSS"), _pick("LOSS"), _pick("LOSS")]
        self.assertEqual(max_losing_streak(picks), 3)


class DrawdownCurveTests(unittest.TestCase):
    def test_monotonic_gains_no_drawdown(self):
        picks = [_pick("WIN", pnl=1.0), _pick("WIN", pnl=1.0)]
        r = drawdown_curve(picks)
        self.assertEqual(r.max_drawdown_units, 0.0)
        self.assertEqual(r.final_pnl_units, 2.0)
        self.assertEqual(r.curve, [1.0, 2.0])

    def test_drawdown_measured_from_peak(self):
        # +2, +2 (peak=4), -1, -1, -1 (valle=1) -- drawdown = 4-1 = 3
        picks = [_pick("WIN", pnl=2.0), _pick("WIN", pnl=2.0), _pick("LOSS", pnl=-1.0),
                 _pick("LOSS", pnl=-1.0), _pick("LOSS", pnl=-1.0)]
        r = drawdown_curve(picks)
        self.assertAlmostEqual(r.max_drawdown_units, 3.0)
        self.assertAlmostEqual(r.final_pnl_units, 1.0)


class SimulateBankrollTests(unittest.TestCase):
    def test_raises_without_decided_picks(self):
        with self.assertRaises(ValueError):
            simulate_bankroll([_pick("PUSH")], n_sims=10)

    def test_all_wins_never_ruins_and_grows_bankroll(self):
        picks = [_pick("WIN", under_odds=2.0) for _ in range(20)]
        mc = simulate_bankroll(picks, n_sims=200, stake_fraction=0.02, ruin_threshold_pct=0.5)
        self.assertEqual(mc.prob_ruin, 0.0)
        self.assertGreater(mc.p50, 1.0)  # banca final mediana > banca inicial

    def test_all_losses_trend_to_ruin(self):
        picks = [_pick("LOSS") for _ in range(50)]
        mc = simulate_bankroll(picks, n_sims=200, stake_fraction=0.05, ruin_threshold_pct=0.5)
        self.assertGreater(mc.prob_ruin, 0.9)
        self.assertLess(mc.p50, 1.0)


if __name__ == "__main__":
    unittest.main()
