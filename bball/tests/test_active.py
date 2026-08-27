import tempfile
import unittest
from pathlib import Path

from bball import db as dbmod
from bball.live.active import DEFAULT_PARAMS, load_active_params, params_label, save_active_params


class ActiveParamsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        self.conn = dbmod.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_defaults_when_nothing_promoted(self):
        params = load_active_params(self.conn)
        self.assertEqual(params, DEFAULT_PARAMS)

    def test_save_and_reload_roundtrip(self):
        custom = {"n_window": 15, "threshold": 8.0, "leagues": ["NBA"]}
        save_active_params(self.conn, custom)
        self.assertEqual(load_active_params(self.conn), custom)

    def test_save_overwrites_previous(self):
        save_active_params(self.conn, {"n_window": 5, "threshold": 3.0, "leagues": ["WNBA"]})
        save_active_params(self.conn, {"n_window": 20, "threshold": 10.0, "leagues": ["EUROLEAGUE"]})
        params = load_active_params(self.conn)
        self.assertEqual(params["n_window"], 20)
        self.assertEqual(params["leagues"], ["EUROLEAGUE"])

    def test_params_label_format(self):
        label = params_label({"n_window": 10, "threshold": 8.0, "leagues": ["NBA", "WNBA"]})
        self.assertEqual(label, "N=10 umbral=8.0 [NBA+WNBA]")


if __name__ == "__main__":
    unittest.main()
