"""Prueba de extremo a extremo del motor de backtest (sin red): inserta un
escenario sintetico directo en SQLite y verifica que replay() reproduce el
pick esperado. B tiene mala forma de sesion (pierde sus 3 primeros partidos),
D tiene forma excelente (gana sus 3 primeros) contra los MISMOS rivales
comunes (A, C, E) -- asi que cuando finalmente juegan B vs D, el modelo debe
favorecer claramente a D. El mercado (sintetico) hace de B un ligero
favorito, asi que D es el "underdog de mercado" con valor -> se espera señal SI.
"""
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tt_elite import db as dbmod
from tt_elite.backtest.replay import replay
from tt_elite.backtest.sweep import run_experiment
from tt_elite.model.params import StrategyParams

TZ = ZoneInfo("Europe/Warsaw")
SESSION_URL = "https://example.test/session-01-01-2026"
SESSION_BASE = datetime(2026, 1, 1, 10, 0, tzinfo=TZ)  # 10:00 = rel_min 0


def _dt(day, minute_offset):
    return SESSION_BASE + timedelta(minutes=minute_offset)


def _insert_match(conn, uid, time, rel_min, p1, p2, s1, s2, day="2026-01-01"):
    conn.execute(
        """INSERT INTO raw_matches
           (match_uid, session_url, session_title, date, time, dt, rel_min,
            p1, p2, p1_key, p2_key, completed, s1, s2, result_source)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?, 'TEST')""",
        (uid, SESSION_URL, "01.01.2026 test session", day, time, _dt(day, rel_min).isoformat(), rel_min,
         p1, p2, p1.lower(), p2.lower(), s1, s2),
    )


def _insert_odds(conn, uid, mp1, mp2, odds1, odds2, book="TestBook", fallback=False):
    conn.execute(
        """INSERT INTO raw_odds (match_uid, book, source, is_fallback, event_id, odds1, odds2, mp1, mp2, quality, captured_at)
           VALUES (?,?,?,?,?,?,?,?,?, 'TEST', '2026-01-01')""",
        (uid, book, book, 1 if fallback else 0, "evt1", odds1, odds2, mp1, mp2),
    )


class ReplayIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        self.conn = dbmod.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def _build_scenario(self):
        c = self.conn
        # B pierde sus 3 primeros partidos (contra A, C, E).
        _insert_match(c, "m1", "10:00", 0, "A", "B", 3, 0)
        _insert_match(c, "m2", "10:10", 10, "C", "B", 3, 0)
        _insert_match(c, "m3", "10:20", 20, "E", "B", 3, 0)
        # D gana sus 3 primeros partidos (contra los MISMOS rivales A, C, E).
        _insert_match(c, "m4", "10:30", 30, "A", "D", 0, 3)
        _insert_match(c, "m5", "10:40", 40, "C", "D", 0, 3)
        _insert_match(c, "m6", "10:50", 50, "E", "D", 0, 3)
        # Candidato: B vs D. Mercado hace a B ligero favorito (mp1=0.55); D gana 3-1.
        _insert_match(c, "m7", "11:00", 60, "B", "D", 1, 3)
        _insert_odds(c, "m7", mp1=0.55, mp2=0.45, odds1=1.818, odds2=2.222)
        c.commit()

    def test_replay_produces_expected_value_pick(self):
        self._build_scenario()
        params = StrategyParams()
        picks = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1), params)

        self.assertEqual(len(picks), 1, f"esperaba exactamente 1 pick, obtuve {picks}")
        pick = picks[0]
        self.assertEqual(pick.underdog, "D")
        self.assertEqual(pick.favorito, "B")
        self.assertEqual(pick.signal, "SI")
        self.assertEqual(pick.result, "WIN")
        self.assertAlmostEqual(pick.pnl_1u, 2.222 - 1, places=3)
        # El modelo debe favorecer a D por encima de lo que dice el mercado (0.45),
        # con edge/EV por encima de los umbrales que activaron la señal SI.
        self.assertGreater(pick.model_prob_underdog, 0.55)
        self.assertGreater(pick.edge_pp, StrategyParams().min_edge)
        self.assertGreater(pick.ev_pct, StrategyParams().min_ev)

    def test_min_matches_played_gate_blocks_early_candidate(self):
        c = self.conn
        # Solo 2 partidos previos cada uno (no llega a MIN_MATCHES_PLAYED=3).
        _insert_match(c, "n1", "10:00", 0, "A", "B", 3, 0)
        _insert_match(c, "n2", "10:10", 10, "C", "B", 3, 0)
        _insert_match(c, "n3", "10:20", 20, "A", "D", 0, 3)
        _insert_match(c, "n4", "10:30", 30, "C", "D", 0, 3)
        _insert_match(c, "n5", "10:40", 40, "B", "D", 1, 3)
        _insert_odds(c, "n5", mp1=0.55, mp2=0.45, odds1=1.818, odds2=2.222)
        c.commit()

        picks = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1), StrategyParams())
        self.assertEqual(picks, [])

    def test_sweep_run_experiment_splits_train_test_by_date(self):
        self._build_scenario()
        res = run_experiment(
            self.conn, StrategyParams(), date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
            save=False,
        )
        # Con test_start == la fecha del unico pick, cae en test, no en train.
        self.assertEqual(res["train"]["n"], 0)
        self.assertEqual(res["test"]["n"], 1)
        self.assertEqual(res["test"]["hit_rate"], 1.0)

    def test_odds_range_filter_excludes_pick_outside_bounds(self):
        self._build_scenario()
        base = StrategyParams()

        below = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
                        replace(base, max_odds_underdog=2.0))  # cuota real es 2.222
        self.assertEqual(below, [])

        above = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
                        replace(base, min_odds_underdog=2.3))
        self.assertEqual(above, [])

        inside = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
                         replace(base, min_odds_underdog=2.0, max_odds_underdog=2.3))
        self.assertEqual(len(inside), 1)

    def test_blowout_rate_filter_requires_enough_prior_history(self):
        # En el escenario base, B y D llegan al cruce final con exactamente 3
        # partidos previos cada uno, TODOS barridas (3-0) -- tasa previa = 1.0.
        self._build_scenario()
        base = StrategyParams()

        # blowout_min_prior=4 es imposible de satisfacer (solo hay 3 previos) -> filtra el pick.
        too_strict = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
                             replace(base, min_blowout_rate=0.5, blowout_min_prior=4))
        self.assertEqual(too_strict, [])

        # blowout_min_prior=3 SI se satisface, y la tasa real (1.0) supera el umbral -> pasa.
        satisfied = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
                            replace(base, min_blowout_rate=1.0, blowout_min_prior=3))
        self.assertEqual(len(satisfied), 1)

    def test_grid_sweep_loads_data_once_regardless_of_grid_size(self):
        # Regresion de rendimiento: antes, cada combinacion del grid volvia a
        # consultar raw_matches/raw_odds -- con Turso eso es una ida y vuelta
        # de red por combinacion. Ahora se carga una vez y se reproduce en
        # memoria para cada una.
        self._build_scenario()

        select_calls = {"n": 0}
        real_conn = self.conn

        class _CountingConnProxy:
            """sqlite3.Connection no deja monkeypatchear .execute (es de solo
            lectura) -- se envuelve en un proxy que cuenta las SELECT a
            raw_matches/raw_odds y delega todo lo demas a la conexion real."""
            def execute(self, sql, *args, **kwargs):
                if sql.strip().upper().startswith("SELECT") and ("RAW_MATCHES" in sql.upper() or "RAW_ODDS" in sql.upper()):
                    select_calls["n"] += 1
                return real_conn.execute(sql, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(real_conn, name)

        from tt_elite.backtest.sweep import grid_sweep
        grid = {"min_model": [0.50, 0.52, 0.55], "min_edge": [0.03, 0.06, 0.09]}  # 9 combinaciones
        grid_sweep(
            _CountingConnProxy(), StrategyParams(), grid,
            date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
            min_test_samples=0, save=False,
        )

        # Exactamente 3: una SELECT a raw_matches (partidos), una a raw_odds,
        # y una mas a raw_matches para las tasas previas de barrida (ver
        # blowouts.compute_blowout_rates_by_match) -- sin importar cuantas
        # combinaciones tenga el grid.
        self.assertEqual(select_calls["n"], 3)


if __name__ == "__main__":
    unittest.main()
