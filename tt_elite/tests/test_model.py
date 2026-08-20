import unittest

from tt_elite.model.elo import compute_model, elo_prob, update_rolling
from tt_elite.model.params import StrategyParams
from tt_elite.model.strategy import evaluate_pick
from tt_elite.textutil import name_key, pair_key, parse_score


class TextUtilTests(unittest.TestCase):
    def test_name_key_collapses_order_and_accents(self):
        self.assertEqual(name_key("Kolek, Maciej"), name_key("Maciej Kolek"))
        self.assertEqual(name_key("Jose Perez"), name_key("José Pérez"))

    def test_pair_key_is_order_independent(self):
        self.assertEqual(pair_key("A B", "C D"), pair_key("C D", "A B"))

    def test_parse_score_valid_and_invalid(self):
        self.assertEqual(parse_score("3-1"), (3, 1))
        self.assertEqual(parse_score("Match: 3 - 0 (11-5, 11-3, 11-7)"), (3, 0))
        self.assertIsNone(parse_score("2-2"))  # nadie llega a 3
        self.assertIsNone(parse_score("no result"))


class EloTests(unittest.TestCase):
    def test_elo_prob_symmetry(self):
        self.assertAlmostEqual(elo_prob(1000, 1000, 400), 0.5)
        self.assertGreater(elo_prob(1200, 1000, 400), 0.5)

    def test_update_rolling_favours_upset_winner(self):
        p = StrategyParams()
        elo = {"a": 1200.0, "b": 1000.0}
        # b (underdog) gana 3-0: su Elo debe subir mas que si hubiera sido favorito.
        update_rolling(elo, "a", "b", 1, 3, p)
        self.assertLess(elo["a"], 1200.0)
        self.assertGreater(elo["b"], 1000.0)

    def test_compute_model_no_data_defaults_to_elo_diff(self):
        p = StrategyParams()
        ranking = {"a": 1100.0, "b": 900.0}
        model = compute_model(1100.0, 900.0, [], [], 0, 0, ranking, p)
        self.assertGreater(model["p1"], 0.5)
        self.assertAlmostEqual(model["p1"] + model["p2"], 1.0)


class StrategyTests(unittest.TestCase):
    def test_evaluate_pick_signals_si_on_strong_direct_edge(self):
        p = StrategyParams()
        # Mercado ve al jugador 1 como underdog (mp1=0.35) pero el modelo lo ve
        # con ventaja clara -> deberia ser señal SI (linea no-fallback).
        ev = evaluate_pick(mp1=0.35, mp2=0.65, model_p1=0.60, model_p2=0.40,
                            odds1=2.80, odds2=1.45, is_fallback=False, p=p)
        self.assertTrue(ev.underdog_is_p1)
        self.assertEqual(ev.signal, "SI")
        self.assertTrue(ev.actionable)

    def test_evaluate_pick_no_signal_when_edge_too_small(self):
        p = StrategyParams()
        ev = evaluate_pick(mp1=0.45, mp2=0.55, model_p1=0.47, model_p2=0.53,
                            odds1=2.20, odds2=1.70, is_fallback=False, p=p)
        self.assertEqual(ev.signal, "NO")
        self.assertFalse(ev.actionable)

    def test_evaluate_pick_fallback_needs_stronger_edge(self):
        p = StrategyParams()
        # Edge que alcanzaria para SI directo, pero es un fallback -> como mucho REVISAR.
        ev = evaluate_pick(mp1=0.40, mp2=0.60, model_p1=0.50, model_p2=0.50,
                            odds1=2.50, odds2=1.55, is_fallback=True, p=p)
        self.assertIn(ev.signal, ("REVISAR", "NO"))
        self.assertNotEqual(ev.signal, "SI")


if __name__ == "__main__":
    unittest.main()
