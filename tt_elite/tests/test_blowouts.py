"""Tasa de barrida (0-3/3-0) acumulada cronologicamente por jugador, sin
mirar el resultado del propio partido ni partidos futuros."""
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tt_elite import db as dbmod
from tt_elite.backtest.blowouts import compute_blowout_observations, summarize

TZ = ZoneInfo("Europe/Warsaw")
SESSION_URL = "https://example.test/session-01-01-2026"
SESSION_BASE = datetime(2026, 1, 1, 10, 0, tzinfo=TZ)


class BlowoutsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.conn = dbmod.connect(Path(self.tmpdir.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def _insert(self, uid, rel_min, p1, p2, s1, s2):
        dt = SESSION_BASE + timedelta(minutes=rel_min)
        self.conn.execute(
            """INSERT INTO raw_matches
               (match_uid, session_url, session_title, date, time, dt, rel_min,
                p1, p2, p1_key, p2_key, completed, s1, s2, result_source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?, 'TEST')""",
            (uid, SESSION_URL, "sess", "2026-01-01", f"{10 + rel_min // 60:02d}:{rel_min % 60:02d}",
             dt.isoformat(), rel_min, p1, p2, p1.lower(), p2.lower(), s1, s2),
        )

    def test_no_lookahead_first_match_of_each_player_is_not_eligible(self):
        # A y B nunca jugaron antes -> el primer cruce entre ellos no cuenta
        # (no hay historial previo suficiente todavia).
        self._insert("m0", 0, "A", "B", 3, 0)
        self.conn.commit()

        obs = compute_blowout_observations(self.conn, date(2026, 1, 1), date(2026, 1, 1), min_prior_matches=1)
        self.assertEqual(obs, [])

    def test_pair_of_frequent_blowout_players_is_flagged_with_prior_rate(self):
        # A barre a C, D, E, F (4 barridas). B tambien barre a C, D, E, F.
        rivals = ["C", "D", "E", "F"]
        for i, r in enumerate(rivals):
            self._insert(f"a{i}", i * 10, "A", r, 3, 0)
        for i, r in enumerate(rivals):
            self._insert(f"b{i}", 40 + i * 10, "B", r, 3, 0)
        # Ahora A vs B, con >=4 partidos previos cada uno, todos barridas.
        self._insert("final", 80, "A", "B", 3, 0)
        self.conn.commit()

        obs = compute_blowout_observations(self.conn, date(2026, 1, 1), date(2026, 1, 1), min_prior_matches=4)
        self.assertEqual(len(obs), 1)
        o = obs[0]
        self.assertEqual(o.p1_prior_rate, 1.0)
        self.assertEqual(o.p2_prior_rate, 1.0)
        self.assertEqual(o.p1_prior_n, 4)
        self.assertEqual(o.p2_prior_n, 4)
        self.assertTrue(o.is_blowout)

        result = summarize(obs, thresholds=(0.5,))
        self.assertEqual(result["thresholds"][0]["n_matches"], 1)
        self.assertEqual(result["thresholds"][0]["actual_blowout_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
