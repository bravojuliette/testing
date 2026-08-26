"""run_live_scan: un partido pendiente no debe contaminarse a si mismo.

Bug real de produccion (candidata_elo_scale_v1, promovida el 2026-08-24):
candidates=0 en TODAS las pasadas de live_scan.yml desde entonces, pese a
haber ~150 partidos pendientes en la ventana de hoy/ayer en cada pasada
(ver diagnostico matches_seen/completed/pending añadido al summary).

Causa: el calculo de 'tainted' recorria TODA la sesion (pasado y futuro) en
un primer bucle, y el bucle de candidatos lo consultaba despues -- asi que
el propio partido candidato (por definicion "no completado") siempre habia
contaminado a sus dos jugadores un instante antes, en el primer bucle.
Ningun partido pendiente podia pasar nunca el filtro.

Arreglo: un solo recorrido cronologico (igual que backtest/replay.py) donde
la elegibilidad de un candidato se mira ANTES de marcarlo a el mismo como
contaminado -- 'tainted' solo debe reflejar huecos ESTRICTAMENTE anteriores
en la sesion."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from tt_elite import config
from tt_elite import db as dbmod
from tt_elite.live.scan import run_live_scan


def _match(time_, p1, p2, rel_min, dt, completed=True, s1=3, s2=0):
    return {
        "time": time_, "p1": p1, "p2": p2, "p1k": p1.lower(), "p2k": p2.lower(),
        "completed": completed, "s1": s1 if completed else None, "s2": s2 if completed else None,
        "rel_min": rel_min, "dt": dt,
    }


class LiveScanCandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        self.now = datetime.now(config.TZ)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _run(self, schedule):
        session = {"title": "sesion de prueba", "url": "https://example.test/s1", "schedule": schedule}
        # load_sessions_for_date se llama una vez por dia (ayer, hoy) -- solo
        # "hoy" debe devolver la sesion de prueba, o quedaria duplicada (una
        # vez por cada dia consultado) y el conteo de candidatos saldria mal.
        today = self.now.date()

        def fake_load(client, d, use_cache=True):
            return [session] if d == today else []

        with patch("tt_elite.live.scan.load_sessions_for_date", side_effect=fake_load), \
             patch("tt_elite.live.scan.fetch_inplay", return_value=[]), \
             patch("tt_elite.live.scan.fetch_upcoming", return_value=[]), \
             patch("tt_elite.live.scan.fetch_ended", return_value=[]):
            return run_live_scan(self.db_path)

    def test_pending_candidate_is_not_tainted_by_its_own_pendingness(self):
        d0 = self.now - timedelta(hours=2)
        schedule = [
            # A y E acumulan 3 partidos completados cada uno ANTES del candidato.
            _match("10:00", "A", "X1", 0, d0),
            _match("10:10", "A", "X2", 10, d0 + timedelta(minutes=10)),
            _match("10:20", "A", "X3", 20, d0 + timedelta(minutes=20)),
            _match("10:05", "E", "Y1", 5, d0 + timedelta(minutes=5)),
            _match("10:15", "E", "Y2", 15, d0 + timedelta(minutes=15)),
            _match("10:25", "E", "Y3", 25, d0 + timedelta(minutes=25)),
            # El candidato: A vs E, todavia sin jugar, dentro de la ventana horaria.
            _match("10:30", "A", "E", 30, self.now, completed=False),
        ]
        summary = self._run(schedule)
        self.assertEqual(summary["candidates"], 1)

    def test_earlier_gap_for_same_player_still_taints_later_candidate(self):
        """El taint SI debe seguir aplicando cuando el hueco es de un partido
        estrictamente ANTERIOR al candidato (mismo criterio que el backtest) --
        el fix no debe volverse permisivo de mas."""
        d0 = self.now - timedelta(hours=2)
        schedule = [
            # A llega a los 3 partidos completados que exige min_matches_played
            # -- igual que en el otro test -- para aislar el efecto del taint.
            _match("10:00", "A", "X1", 0, d0),
            _match("10:10", "A", "X2", 10, d0 + timedelta(minutes=10)),
            _match("10:15", "A", "X3", 15, d0 + timedelta(minutes=15)),
            # Hueco ANTERIOR al candidato: A vs Z todavia sin resultado.
            _match("10:20", "A", "Z", 20, d0 + timedelta(minutes=20), completed=False),
            _match("10:05", "E", "Y1", 5, d0 + timedelta(minutes=5)),
            _match("10:16", "E", "Y2", 16, d0 + timedelta(minutes=16)),
            _match("10:25", "E", "Y3", 25, d0 + timedelta(minutes=25)),
            _match("10:30", "A", "E", 30, self.now, completed=False),
        ]
        summary = self._run(schedule)
        self.assertEqual(summary["candidates"], 0)


if __name__ == "__main__":
    unittest.main()
