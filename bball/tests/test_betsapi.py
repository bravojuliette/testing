import unittest

from bball.sources.betsapi import extract_pre_match_totals, parse_score


class ParseScoreTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_score("111-118"), (111, 118))

    def test_invalid(self):
        self.assertIsNone(parse_score(None))
        self.assertIsNone(parse_score(""))
        self.assertIsNone(parse_score("sin resultado"))
        self.assertIsNone(parse_score("111"))


def _odds_json(entries: dict) -> dict:
    """entries: book -> {'start': {...} | None, 'end': {...} | None}"""
    return {"results": entries}


def _market(handicap, over_od, under_od, add_time):
    return {"18_3": {"handicap": str(handicap), "over_od": str(over_od), "under_od": str(under_od), "add_time": str(add_time)}}


class ExtractPreMatchTotalsTests(unittest.TestCase):
    KICKOFF = 1_800_000_000

    def test_pre_match_start_and_end_both_included(self):
        js = _odds_json({
            "Bet365": {
                "odds": {
                    "start": _market(160.5, 1.90, 1.90, self.KICKOFF - 3600),
                    "end": _market(158.5, 1.95, 1.85, self.KICKOFF - 60),
                }
            }
        })
        rows = extract_pre_match_totals(js, self.KICKOFF)
        self.assertEqual(len(rows), 2)
        snapshots = {r["snapshot"] for r in rows}
        self.assertEqual(snapshots, {"start", "end"})

    def test_post_kickoff_snapshot_excluded(self):
        """Mismo criterio que tt_elite best_opening_line: una cuota cuyo
        add_time es posterior (o igual) al inicio del partido ya pudo verse
        afectada por lo que paso en el partido -- se descarta."""
        js = _odds_json({
            "Bet365": {
                "odds": {
                    "start": _market(160.5, 1.90, 1.90, self.KICKOFF - 3600),
                    "end": _market(140.0, 1.20, 3.50, self.KICKOFF + 600),  # ya en juego
                }
            }
        })
        rows = extract_pre_match_totals(js, self.KICKOFF)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["snapshot"], "start")

    def test_kickoff_without_score_included_even_seconds_after_start(self):
        """El snapshot 'kickoff' es la linea de CIERRE real (cuota al pitido).
        Su add_time puede quedar unos segundos despues del inicio oficial;
        el filtro correcto para el es 'ss' (marcador): sin marcador = aun no
        ha pasado nada del partido, se acepta."""
        m = _market(158.5, 1.90, 1.90, self.KICKOFF + 30)
        js = _odds_json({"Bet365": {"odds": {"kickoff": m}}})
        rows = extract_pre_match_totals(js, self.KICKOFF)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["snapshot"], "kickoff")
        self.assertEqual(rows[0]["line"], 158.5)

    def test_kickoff_with_score_excluded(self):
        """Un 'kickoff' con marcador ya es una cuota en juego (visto en datos
        reales: end trae ss='115:96'); si kickoff trae ss, fuera."""
        m = _market(150.5, 1.50, 2.50, self.KICKOFF + 30)
        m["18_3"]["ss"] = "10:8"
        js = _odds_json({"Bet365": {"odds": {"kickoff": m}}})
        self.assertEqual(extract_pre_match_totals(js, self.KICKOFF), [])

    def test_kickoff_too_late_excluded_even_without_score(self):
        m = _market(150.5, 1.90, 1.90, self.KICKOFF + 1200)  # 20 min tarde
        js = _odds_json({"Bet365": {"odds": {"kickoff": m}}})
        self.assertEqual(extract_pre_match_totals(js, self.KICKOFF), [])

    def test_missing_market_or_fields_skipped(self):
        js = _odds_json({
            "NoTotals": {"odds": {"start": {"18_1": {"home_od": "1.5", "away_od": "2.5"}}}},
            "Malformed": {"odds": {"start": {"18_3": {"handicap": "abc", "over_od": "1.9", "under_od": "1.9"}}}},
        })
        rows = extract_pre_match_totals(js, self.KICKOFF)
        self.assertEqual(rows, [])

    def test_multiple_books_independent(self):
        js = _odds_json({
            "BookA": {"odds": {"start": _market(160.5, 1.9, 1.9, self.KICKOFF - 100)}},
            "BookB": {"odds": {"start": _market(163.5, 1.5, 2.6, self.KICKOFF - 100)}},
        })
        rows = extract_pre_match_totals(js, self.KICKOFF)
        self.assertEqual(len(rows), 2)
        lines = sorted(r["line"] for r in rows)
        self.assertEqual(lines, [160.5, 163.5])


if __name__ == "__main__":
    unittest.main()


class OrientationReliabilityTests(unittest.TestCase):
    """WNBA 2026 tiene el orden de equipos inconsistente en origen (BetsAPI):
    el favorito de cierre solo gana el 52.4% ahi, frente al 65-70% del resto.
    Debe quedar excluido de todo analisis de ganador/handicap."""

    def test_wnba_2026_marked_unreliable(self):
        from bball import config
        self.assertFalse(config.orientation_is_reliable("WNBA", "2026-06-26"))
        self.assertFalse(config.orientation_is_reliable("WNBA", "2026-08-01"))

    def test_other_wnba_seasons_are_fine(self):
        from bball import config
        self.assertTrue(config.orientation_is_reliable("WNBA", "2022-07-01"))
        self.assertTrue(config.orientation_is_reliable("WNBA", "2025-08-01"))

    def test_other_leagues_unaffected(self):
        from bball import config
        for lg in ("NBA", "Euroleague"):
            self.assertTrue(config.orientation_is_reliable(lg, "2026-06-26"))
