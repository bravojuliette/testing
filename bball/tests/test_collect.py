"""Integracion (sin red): collect_day() contra un ApiClient falso, sobre una
SQLite temporal (nunca contra Turso -- db.connect(tmp_path) con path
explicito ignora TURSO_DATABASE_URL, ver bball/db.py::connect)."""
import tempfile
import unittest
from pathlib import Path

from bball import db as dbmod
from bball.backtest.collect import collect_day


class FakeClient:
    """Sustituye a ApiClient: bets(path, params, prefix, use_cache) -> dict,
    sin tocar la red. Guarda las llamadas para poder inspeccionarlas."""

    def __init__(self, ended_response: dict, odds_by_event: dict[str, dict]):
        self.ended_response = ended_response
        self.odds_by_event = odds_by_event
        self.calls: list[tuple[str, dict]] = []

    def bets(self, path, params, *, prefix, use_cache=True):
        self.calls.append((path, dict(params)))
        if path == "/v3/events/ended":
            return self.ended_response
        if path == "/v2/event/odds/summary":
            return self.odds_by_event.get(str(params["event_id"]), {"results": {}})
        raise AssertionError(f"path inesperado: {path}")


# 2026-01-15 04:30 UTC -- cerca de medianoche UTC, el caso que exponia el bug
# de zona horaria local en date.fromtimestamp() sin tz.
KICKOFF_TS = 1768452600


def _ended_event(event_id, ss, home_id="10", away_id="20"):
    return {
        "id": event_id, "sport_id": "18", "time": str(KICKOFF_TS), "ss": ss,
        "league": {"id": "2274", "name": "NBA"},
        "home": {"id": home_id, "name": "Home Team"},
        "away": {"id": away_id, "name": "Away Team"},
    }


class CollectDayTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        self.conn = dbmod.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_finished_game_stored_with_utc_date(self):
        client = FakeClient(
            ended_response={"results": [_ended_event("e1", "111-118")], "pager": {"total": 1, "per_page": 50}},
            odds_by_event={},
        )
        counts = collect_day(client, self.conn, league_id=2274, day="20260115")
        self.assertEqual(counts, {"games": 1, "with_odds": 0, "unresolved": 0})

        row = self.conn.execute("SELECT * FROM bball_games WHERE event_id = 'e1'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["home_score"], 111)
        self.assertEqual(row["away_score"], 118)
        self.assertEqual(row["completed"], 1)
        # UTC explicito, no la zona horaria local del proceso que corre el test.
        self.assertEqual(row["date"], "2026-01-15")

    def test_unresolved_score_not_stored(self):
        client = FakeClient(
            ended_response={"results": [_ended_event("e2", None)], "pager": {"total": 1, "per_page": 50}},
            odds_by_event={},
        )
        counts = collect_day(client, self.conn, league_id=2274, day="20260115")
        self.assertEqual(counts, {"games": 0, "with_odds": 0, "unresolved": 1})
        row = self.conn.execute("SELECT * FROM bball_games WHERE event_id = 'e2'").fetchone()
        self.assertIsNone(row)

    def test_odds_rows_batched_via_totals_market(self):
        odds_json = {
            "results": {
                "Bet365": {"odds": {"start": {"18_3": {
                    "handicap": "210.5", "over_od": "1.9", "under_od": "1.9", "add_time": str(KICKOFF_TS - 3600),
                }}}},
            }
        }
        client = FakeClient(
            ended_response={"results": [_ended_event("e3", "100-95")], "pager": {"total": 1, "per_page": 50}},
            odds_by_event={"e3": odds_json},
        )
        counts = collect_day(client, self.conn, league_id=2274, day="20260115")
        self.assertEqual(counts["with_odds"], 1)
        odds_row = self.conn.execute("SELECT * FROM bball_odds WHERE event_id = 'e3'").fetchone()
        self.assertEqual(odds_row["line"], 210.5)

    def test_rerun_is_idempotent_upsert(self):
        client = FakeClient(
            ended_response={"results": [_ended_event("e4", "100-95")], "pager": {"total": 1, "per_page": 50}},
            odds_by_event={},
        )
        collect_day(client, self.conn, league_id=2274, day="20260115")
        collect_day(client, self.conn, league_id=2274, day="20260115")  # segunda pasada, mismo dia
        n = self.conn.execute("SELECT COUNT(*) c FROM bball_games WHERE event_id = 'e4'").fetchone()["c"]
        self.assertEqual(n, 1)  # UPSERT, no duplicado


if __name__ == "__main__":
    unittest.main()
