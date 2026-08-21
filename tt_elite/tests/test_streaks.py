"""Rachas dentro de sesion: verifica que la deteccion de racha y la
probabilidad Elo pre-sesion (sin look-ahead) se calculan bien sobre un
escenario sintetico simple."""
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tt_elite import db as dbmod
from tt_elite.backtest.streaks import (
    compute_streak_observations,
    compute_streak_observations_full_model,
    summarize,
    summarize_full_model,
)

TZ = ZoneInfo("Europe/Warsaw")
SESSION_URL = "https://example.test/session-01-01-2026"
SESSION_BASE = datetime(2026, 1, 1, 10, 0, tzinfo=TZ)


class StreaksTests(unittest.TestCase):
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

    def test_losing_streak_is_tracked_per_player_without_lookahead(self):
        rivals = ["A", "C", "E", "G", "I", "K"]
        for i, r in enumerate(rivals):
            self._insert(f"m{i}", i * 10, r, "B", 3, 0)  # B pierde cada vez
        self._insert("m6", 60, "B", "Z", 1, 3)  # 7o partido: B sigue perdiendo
        self.conn.commit()

        obs = compute_streak_observations(self.conn, date(2026, 1, 1), date(2026, 1, 1))
        # 7 partidos * 2 jugadores = 14 observaciones.
        self.assertEqual(len(obs), 14)

        # La observacion de B entrando al 7o partido debe traer racha L de longitud 6.
        b_last = [o for o in obs if o.streak_len == 6 and o.streak_type == "L"]
        self.assertEqual(len(b_last), 1)
        self.assertFalse(b_last[0].won)

        # Sin partidos previos entre estos jugadores, el Elo pre-sesion es igual
        # para ambos (initial_elo) -- la racha no debe filtrarse al Elo esperado
        # de este mismo partido (no hay look-ahead intra-sesion).
        self.assertAlmostEqual(b_last[0].elo_win_prob, 0.5, places=6)

    def test_summarize_buckets_by_streak_length_and_caps_at_max_bucket(self):
        rivals = ["A", "C", "E", "G", "I", "K", "M", "O"]
        for i, r in enumerate(rivals):
            self._insert(f"m{i}", i * 10, r, "B", 3, 0)
        self.conn.commit()

        obs = compute_streak_observations(self.conn, date(2026, 1, 1), date(2026, 1, 1))
        rows = summarize(obs, max_bucket=3)
        by_key = {(r["streak_type"], r["streak_len"]): r for r in rows}

        # Longitudes 3 a 7 de la racha de B deben quedar todas agrupadas en el bucket "3".
        self.assertIn(("L", 3), by_key)
        self.assertEqual(by_key[("L", 3)]["n"], 5)  # longitudes 3,4,5,6,7 -> 5 observaciones
        self.assertNotIn(("L", 4), by_key)


    def test_full_model_diverges_from_raw_elo_when_h2h_history_exists(self):
        # C le gana a D tres veces en sesiones separadas (h2h_adjust solo
        # entra en juego con >=3 cruces previos). En una 4a sesion posterior
        # vuelven a jugar: el Elo puro (sin memoria de quien gano antes) no
        # ve diferencia, pero el modelo completo (con h2h_adjust) debe
        # favorecer claramente a C. Cada sesion usa un rel_min base distinto
        # y creciente para que el orden cronologico entre sesiones sea
        # deterministico (rel_min es relativo a cada sesion, como en
        # produccion -- ver replay.py).
        def _insert_session(idx, s1, s2, base_rel_min):
            url = f"https://example.test/session-01-01-2026-{idx}"
            self.conn.execute(
                """INSERT INTO raw_matches
                   (match_uid, session_url, session_title, date, time, dt, rel_min,
                    p1, p2, p1_key, p2_key, completed, s1, s2, result_source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?, 'TEST')""",
                (f"h{idx}", url, f"sess{idx}", "2026-01-01", "10:00",
                 (SESSION_BASE + timedelta(minutes=base_rel_min)).isoformat(), base_rel_min,
                 "C", "D", "c", "d", s1, s2),
            )

        for i in range(3):
            _insert_session(i, 3, 0, i * 200)  # C gana las 3 primeras
        _insert_session(3, 3, 1, 3 * 200)      # 4o cruce: el que se evalua
        self.conn.commit()

        obs = compute_streak_observations_full_model(self.conn, date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual(len(obs), 8)  # 4 partidos * 2 jugadores
        c_fourth = obs[6]  # 4o partido = obs[6]/obs[7] (C es p1 -> obs[6])
        # El Elo rodante ya sube algo a C tras 3 victorias, pero el h2h_adjust
        # (>=3 cruces previos, los 3 ganados por C) suma un empuje extra que
        # el Elo puro no captura -- el modelo completo debe quedar por encima.
        self.assertGreater(c_fourth.model_win_prob, c_fourth.elo_win_prob + 0.02)


if __name__ == "__main__":
    unittest.main()
