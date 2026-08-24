"""Detector de "cadenas de barridas transitivas" (sistema aparte, sin
picks/probabilidad): A goleo 3-0 a X, X goleo 3-0 a Y, toca A vs Y."""
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tt_elite import config
from tt_elite import db as dbmod
from tt_elite.live.blowout_chain import compute_blowout_chains, scan_blowout_chain

TZ = ZoneInfo("Europe/Warsaw")
SESSION_URL = "https://example.test/session-01-01-2026"
SESSION_BASE = datetime(2026, 1, 1, 10, 0, tzinfo=TZ)


class BlowoutChainTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.conn = dbmod.connect(Path(self.tmpdir.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def _insert(self, uid, rel_min, p1, p2, s1, s2, completed=True, session_url=SESSION_URL, d="2026-01-01"):
        dt = SESSION_BASE + timedelta(minutes=rel_min)
        self.conn.execute(
            """INSERT INTO raw_matches
               (match_uid, session_url, session_title, date, time, dt, rel_min,
                p1, p2, p1_key, p2_key, completed, s1, s2, result_source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'TEST')""",
            (uid, session_url, "sess", d, f"{10 + rel_min // 60:02d}:{rel_min % 60:02d}",
             dt.isoformat(), rel_min, p1, p2, p1.lower(), p2.lower(), int(completed), s1, s2),
        )

    def test_simple_chain_is_detected(self):
        # A goleo 3-0 a X; X goleo 3-0 a Y; luego A vs Y -> señal.
        self._insert("m1", 0, "A", "X", 3, 0)
        self._insert("m2", 10, "X", "Y", 3, 0)
        self._insert("m3", 20, "A", "Y", 3, 1)
        self.conn.commit()

        signals = compute_blowout_chains(self.conn, date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual(len(signals), 1)
        s = signals[0]
        self.assertEqual(s["match_uid"], "m3")
        self.assertEqual(s["player_a"], "A")
        self.assertEqual(s["player_y"], "Y")
        self.assertEqual(s["common_x"], "X")
        self.assertEqual(s["ax_match_uid"], "m1")
        self.assertEqual(s["xy_match_uid"], "m2")
        # A vs Y quedo 3-1 (A gano) -> confirma la teoria.
        self.assertEqual(s["a_score"], 3)
        self.assertEqual(s["y_score"], 1)
        self.assertEqual(s["theory_holds"], 1)

    def test_theory_does_not_hold_when_y_wins(self):
        self._insert("m1", 0, "A", "X", 3, 0)
        self._insert("m2", 10, "X", "Y", 3, 0)
        self._insert("m3", 20, "A", "Y", 2, 3)  # Y gana -> refuta la teoria
        self.conn.commit()

        signals = compute_blowout_chains(self.conn, date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual(len(signals), 1)
        s = signals[0]
        self.assertEqual(s["a_score"], 2)
        self.assertEqual(s["y_score"], 3)
        self.assertEqual(s["theory_holds"], 0)

    def test_score_is_reoriented_when_a_is_away(self):
        # A vs Y jugado como "Y vs A" en raw_matches (Y es p1) -- a_score
        # debe seguir siendo el marcador de A, no el de p1 tal cual.
        self._insert("m1", 0, "A", "X", 3, 0)
        self._insert("m2", 10, "X", "Y", 3, 0)
        self._insert("m3", 20, "Y", "A", 1, 3)  # p1=Y anota 1, p2=A anota 3 -> A gana 3-1
        self.conn.commit()

        signals = compute_blowout_chains(self.conn, date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual(len(signals), 1)
        s = signals[0]
        self.assertEqual(s["player_a"], "A")
        self.assertEqual(s["player_y"], "Y")
        self.assertEqual(s["a_score"], 3)
        self.assertEqual(s["y_score"], 1)
        self.assertEqual(s["theory_holds"], 1)

    def test_reverse_order_also_detected_when_y_is_home(self):
        self._insert("m1", 0, "A", "X", 3, 0)
        self._insert("m2", 10, "X", "Y", 0, 3)  # X goleo 0-3 -> Y goleo a X, no cuenta como X goleo a Y
        self._insert("m3", 20, "Y", "A", 1, 3)  # Y vs A, con Y como p1
        self.conn.commit()

        # En este caso X NO goleo a Y (fue al reves), asi que no debe haber señal.
        signals = compute_blowout_chains(self.conn, date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual(signals, [])

    def test_no_lookahead_future_blowout_does_not_count(self):
        # A vs Y ocurre ANTES de que X barra a Y -> no debe contar (sin mirar al futuro).
        self._insert("m1", 0, "A", "X", 3, 0)
        self._insert("m2", 10, "A", "Y", 3, 1)  # todavia no hay cadena valida
        self._insert("m3", 20, "X", "Y", 3, 0)  # esto llega DESPUES del cruce A-Y
        self.conn.commit()

        signals = compute_blowout_chains(self.conn, date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual(signals, [])

    def test_no_chain_without_intermediate_blowouts(self):
        self._insert("m1", 0, "A", "X", 3, 1)  # no es barrida (3-1)
        self._insert("m2", 10, "X", "Y", 3, 0)
        self._insert("m3", 20, "A", "Y", 3, 0)
        self.conn.commit()

        signals = compute_blowout_chains(self.conn, date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual(signals, [])

    def test_pending_match_is_included_as_not_completed(self):
        self._insert("m1", 0, "A", "X", 3, 0)
        self._insert("m2", 10, "X", "Y", 3, 0)
        self._insert("m3", 20, "A", "Y", None, None, completed=False)
        self.conn.commit()

        signals = compute_blowout_chains(self.conn, date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual(len(signals), 1)
        self.assertFalse(signals[0]["match_completed"])
        self.assertIsNone(signals[0]["a_score"])
        self.assertIsNone(signals[0]["y_score"])
        self.assertIsNone(signals[0]["theory_holds"])

    def test_scan_upserts_and_preserves_first_detected_at(self):
        # scan_blowout_chain() ancla la ventana a "hoy" de verdad (config.TZ),
        # asi que aqui los datos van fechados hoy (a diferencia del resto de
        # tests, que usan compute_blowout_chains() puro con fecha fija).
        real_today = datetime.now(config.TZ).date().isoformat()
        self._insert("m1", 0, "A", "X", 3, 0, d=real_today)
        self._insert("m2", 10, "X", "Y", 3, 0, d=real_today)
        self._insert("m3", 20, "A", "Y", None, None, completed=False, d=real_today)
        self.conn.commit()

        result = scan_blowout_chain(self.conn, days_back=1)
        self.assertEqual(result["found"], 1)
        row = self.conn.execute("SELECT detected_at, match_completed FROM blowout_chain_signals").fetchone()
        first_seen = row["detected_at"]
        self.assertEqual(row["match_completed"], 0)

        # El partido pendiente se resuelve (A gana 3-2); re-escanear debe
        # actualizar el resultado y el veredicto pero conservar detected_at
        # (primera vez que se vio).
        self.conn.execute(
            "UPDATE raw_matches SET completed=1, s1=3, s2=2 WHERE match_uid='m3'"
        )
        self.conn.commit()
        scan_blowout_chain(self.conn, days_back=1)
        row2 = self.conn.execute(
            "SELECT detected_at, match_completed, a_score, y_score, theory_holds FROM blowout_chain_signals"
        ).fetchone()
        self.assertEqual(row2["detected_at"], first_seen)
        self.assertEqual(row2["match_completed"], 1)
        self.assertEqual(row2["a_score"], 3)
        self.assertEqual(row2["y_score"], 2)
        self.assertEqual(row2["theory_holds"], 1)

    def test_different_sessions_are_not_mixed(self):
        self._insert("m1", 0, "A", "X", 3, 0, session_url=SESSION_URL)
        self._insert("m2", 10, "X", "Y", 0, 3, session_url="https://example.test/other-session")
        self._insert("m3", 20, "A", "Y", 3, 1, session_url=SESSION_URL)
        self.conn.commit()

        signals = compute_blowout_chains(self.conn, date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual(signals, [])


if __name__ == "__main__":
    unittest.main()
