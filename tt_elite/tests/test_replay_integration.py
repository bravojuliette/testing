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

    def test_streak_bonus_shifts_model_prob_toward_player_on_win_streak(self):
        # B llega al cruce final en racha de derrotas (perdio sus 3 previos),
        # D en racha de victorias (gano sus 3 previos) -- streak_len=3 cada uno.
        self._build_scenario()
        base = StrategyParams()

        off = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1), base)
        self.assertEqual(len(off), 1)
        prob_off = off[0].model_prob_underdog

        # bonus=1.0pp/unidad, streak_len=3 (tope 4) -> +3pp para D, -3pp para B:
        # el modelo debe favorecer a D (underdog) todavia mas que sin el bonus.
        on = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
                    replace(base, streak_bonus_pp=1.0))
        self.assertEqual(len(on), 1)
        prob_on = on[0].model_prob_underdog

        self.assertGreater(prob_on, prob_off)
        self.assertAlmostEqual(prob_on - prob_off, 0.06, places=2)  # 3pp+3pp = 6pp

    def test_streak_bonus_zero_is_noop(self):
        # streak_bonus_pp=0.0 (default) no debe cambiar nada frente al baseline.
        self._build_scenario()
        base = StrategyParams()
        a = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1), base)
        b = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
                   replace(base, streak_bonus_pp=0.0))
        self.assertEqual(a[0].model_prob_underdog, b[0].model_prob_underdog)

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


    def test_hour_of_day_filter_excludes_pick_outside_clock_range(self):
        # OJO: en _build_scenario/_insert_match, rel_min es un offset
        # sintetico pequeno (0,10,20...) independiente del string "time"
        # -- NO son minutos-desde-medianoche reales como en produccion
        # (ver tt_series.assign_datetimes). El candidato B vs D esta a
        # rel_min=60 -> hour_of_day = 60%1440/60 = 1.0.
        self._build_scenario()
        base = StrategyParams()

        below = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
                        replace(base, min_hour_of_day=2.0))
        self.assertEqual(below, [])

        above = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
                        replace(base, max_hour_of_day=0.5))
        self.assertEqual(above, [])

        inside = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
                         replace(base, min_hour_of_day=0.5, max_hour_of_day=2.0))
        self.assertEqual(len(inside), 1)

    def test_day_matches_played_counts_across_sessions_same_date(self):
        # Mismo escenario de forma que _build_scenario (B pierde 3x contra
        # A/C/E, D gana 3x contra los MISMOS rivales -- para que haya edge
        # real y salga señal), pero repartido en TRES sesiones DISTINTAS de
        # la MISMA fecha: urlA (forma de B), urlA2 (forma de D), urlB
        # (candidato B-vs-D). day_played debe contar los partidos de forma
        # aunque esten en sesiones distintas -- a diferencia de
        # min_matches_played, que es solo dentro de la sesion actual.
        c = self.conn

        def _insert(uid, url, rel_min, p1, p2, s1, s2):
            c.execute(
                """INSERT INTO raw_matches
                   (match_uid, session_url, session_title, date, time, dt, rel_min,
                    p1, p2, p1_key, p2_key, completed, s1, s2, result_source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?, 'TEST')""",
                (uid, url, url, "2026-01-01", "10:00", _dt("2026-01-01", rel_min).isoformat(), rel_min,
                 p1, p2, p1.lower(), p2.lower(), s1, s2),
            )

        _insert("d1", "urlA", 0, "A", "B", 3, 0)
        _insert("d2", "urlA", 10, "C", "B", 3, 0)
        _insert("d3", "urlA", 20, "E", "B", 3, 0)
        _insert("d4", "urlA2", 30, "A", "D", 0, 3)
        _insert("d5", "urlA2", 40, "C", "D", 0, 3)
        _insert("d6", "urlA2", 50, "E", "D", 0, 3)
        _insert("cand", "urlB", 60, "B", "D", 1, 3)
        _insert_odds(c, "cand", mp1=0.55, mp2=0.45, odds1=1.818, odds2=2.222)
        c.commit()

        base = replace(StrategyParams(), min_matches_played=0)

        picks3 = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
                         replace(base, min_day_matches_played=3))
        self.assertEqual(len(picks3), 1, "ambos jugaron 3 partidos HOY en otras sesiones -- debe pasar")

        picks4 = replay(self.conn, date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1),
                         replace(base, min_day_matches_played=4))
        self.assertEqual(picks4, [], "ninguno llega a 4 partidos hoy -- debe filtrarse")

    def test_sessions_ordered_by_date_not_just_rel_min(self):
        """Regresion: rel_min se reinicia a ~0 en cada sesion nueva (no lleva
        fecha), asi que ordenar sesiones SOLO por rel_min mezcla dias
        distintos por hora-del-dia en vez de por fecha real -- una sesion de
        hace semanas con rel_min alto podia procesarse DESPUES de una sesion
        reciente con rel_min bajo. Mismo escenario que
        test_replay_produces_expected_value_pick (B con mala forma, D con
        forma excelente contra los mismos rivales comunes), pero repartido en
        DOS fechas reales: la sesion que construye la forma va en
        2026-01-01 con rel_min ALTO (800-850), y la sesion candidata va 9
        dias despues (2026-01-10) con rel_min BAJO (50) -- justo el patron
        que rompia el sort antiguo (`key=min(rel_min)` sin fecha). Si las
        sesiones se procesan en el orden equivocado, el modelo no ve la
        forma de B/D todavia y no sale señal."""
        # OJO: _insert_match usa una SESSION_URL fija -- aqui necesitamos dos
        # sesiones DISTINTAS (una por fecha, como en produccion real, donde
        # cada post de TT-Series es especifico de una fecha) para que el sort
        # entre sesiones entre en juego.
        c = self.conn

        def _insert(uid, url, day, time, rel_min, p1, p2, s1, s2):
            c.execute(
                """INSERT INTO raw_matches
                   (match_uid, session_url, session_title, date, time, dt, rel_min,
                    p1, p2, p1_key, p2_key, completed, s1, s2, result_source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?, 'TEST')""",
                (uid, url, url, day, time, _dt(day, rel_min).isoformat(), rel_min,
                 p1, p2, p1.lower(), p2.lower(), s1, s2),
            )

        # Sesion de forma: B pierde 3-0 contra A/C/E, D gana 3-0 contra los
        # MISMOS rivales -- rel_min alto (800-850), fecha temprana (01-01).
        _insert("w1", "urlA", "2026-01-01", "13:20", 800, "A", "B", 3, 0)
        _insert("w2", "urlA", "2026-01-01", "13:30", 810, "C", "B", 3, 0)
        _insert("w3", "urlA", "2026-01-01", "13:40", 820, "E", "B", 3, 0)
        _insert("w4", "urlA", "2026-01-01", "13:50", 830, "A", "D", 0, 3)
        _insert("w5", "urlA", "2026-01-01", "14:00", 840, "C", "D", 0, 3)
        _insert("w6", "urlA", "2026-01-01", "14:10", 850, "E", "D", 0, 3)
        # Sesion candidata: B vs D, 9 dias despues, rel_min BAJO (00:50).
        _insert("cand", "urlB", "2026-01-10", "00:50", 50, "B", "D", 1, 3)
        _insert_odds(c, "cand", mp1=0.55, mp2=0.45, odds1=1.818, odds2=2.222)
        c.commit()

        # min_matches_played es POR SESION (se reinicia en cada sesion nueva)
        # -- aqui la forma vive en otra sesion (urlA), asi que se pone a 0
        # para aislar justo lo que este test verifica: el orden CRONOLOGICO
        # entre sesiones (Elo/forma acumulada), no el conteo intra-sesion.
        params = replace(StrategyParams(), min_matches_played=0)
        picks = replay(self.conn, date(2026, 1, 1), date(2026, 1, 10), date(2026, 1, 10), params)

        self.assertEqual(len(picks), 1, f"esperaba 1 pick (orden cronologico correcto), obtuve {picks}")
        pick = picks[0]
        self.assertEqual(pick.underdog, "D")
        self.assertEqual(pick.signal, "SI")


if __name__ == "__main__":
    unittest.main()
