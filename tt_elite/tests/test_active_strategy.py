"""La estrategia activa vive en la tabla meta de la base de datos (antes era
un archivo en el repo -- no servia para un 'promote' disparado desde el
dashboard, porque un commit desde una corrida de GitHub Actions no persiste)."""
import tempfile
import unittest
from pathlib import Path

from tt_elite import db as dbmod
from tt_elite.model.active import load_active_params, save_active_params
from tt_elite.model.params import BASELINE, StrategyParams


class ActiveStrategyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_defaults_to_baseline_when_nothing_saved(self):
        with dbmod.get_conn(self.db_path) as conn:
            self.assertEqual(load_active_params(conn), BASELINE)

    def test_save_then_load_round_trips_through_the_db(self):
        custom = StrategyParams(name="candidata_1", min_model=0.6, min_edge=0.09)
        with dbmod.get_conn(self.db_path) as conn:
            save_active_params(conn, custom)
        # Conexion nueva (simula otra corrida de scan.py mas tarde): tiene que
        # seguir ahi, no vivir solo en la conexion que la guardo.
        with dbmod.get_conn(self.db_path) as conn:
            self.assertEqual(load_active_params(conn), custom)

    def test_promoting_again_overwrites_the_previous_active_strategy(self):
        first = StrategyParams(name="a", min_model=0.55)
        second = StrategyParams(name="b", min_model=0.6)
        with dbmod.get_conn(self.db_path) as conn:
            save_active_params(conn, first)
            save_active_params(conn, second)
            self.assertEqual(load_active_params(conn), second)


if __name__ == "__main__":
    unittest.main()
