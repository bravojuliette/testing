"""La correccion por estadio modal no usa resultados ni cuotas: solo el
pabellon. Estos tests fijan la mecanica con datos sinteticos."""
import unittest

from bball import db
from bball.backtest.orientacion import casas_por_equipo, clasificar_orientacion


def _mk(conn):
    juegos = []
    # equipo A juega 6 en 'Casa A', equipo B 6 en 'Casa B'; luego:
    #   e_ok      A local en Casa A -> ok
    #   e_swap    A 'local' pero en Casa B -> invertido
    #   e_neutral A vs B en 'Pabellon Feria' -> neutral
    for i in range(6):
        juegos.append((f"h{i}", "A", f"rivalA{i}", "Casa A"))
        juegos.append((f"g{i}", "B", f"rivalB{i}", "Casa B"))
    juegos += [("e_ok", "A", "B", "Casa A"), ("e_swap", "A", "B", "Casa B"),
               ("e_neutral", "A", "B", "Pabellon Feria")]
    for eid, h, a, st in juegos:
        conn.execute(
            "INSERT INTO bball_games(event_id, league_name, home_team, away_team, "
            "home_key, away_key, home_score, away_score, completed, date) "
            "VALUES (?, 'NCAAB', ?, ?, ?, ?, 70, 60, 1, '2026-01-01')",
            (eid, h, a, h, a))
        conn.execute("INSERT INTO bball_venues(event_id, stadium) VALUES (?, ?)", (eid, st))


class OrientacionPorEstadio(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        _mk(self.conn)

    def test_casa_modal(self):
        casas = casas_por_equipo(self.conn)
        self.assertEqual(casas["A"], "Casa A")
        self.assertEqual(casas["B"], "Casa B")
        self.assertNotIn("rivalA0", casas)   # 1 partido: sin fiabilidad

    def test_clasificacion(self):
        c = clasificar_orientacion(self.conn)
        self.assertEqual(c["e_ok"], "ok")
        self.assertEqual(c["e_swap"], "swap")
        self.assertEqual(c["e_neutral"], "neutral")


if __name__ == "__main__":
    unittest.main()
