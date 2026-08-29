"""El feed de PARTIDOS de BetsAPI invierte local/visitante en las ligas que
lista como 'visitante @ local' (NBA/WNBA); el de CUOTAS no. Confundir las dos
cosas costo un analisis entero: con las cuotas intercambiadas, el favorito de
cierre 'ganaba' el 31% en NBA y el 30% en WNBA, y el buscador de valor
encontraba un +212% de ROI que era puro artefacto del error.

El invariante que lo detecta, y que estos tests fijan: en cualquier liga y
mercado sano el favorito de cierre gana entre el 60% y el 75%.
"""
import unittest

from bball import config


class ConvencionDeOrientacion(unittest.TestCase):
    def test_ligas_visitante_primero(self):
        self.assertTrue(config.swaps_home_away("NBA"))
        self.assertTrue(config.swaps_home_away("WNBA"))
        self.assertFalse(config.swaps_home_away("Euroleague"))
        self.assertFalse(config.swaps_home_away("NCAAB"))

    def test_el_reparse_no_intercambia_las_cuotas(self):
        """Guardia contra la regresion concreta: si alguien vuelve a meter el
        intercambio en reparse_moneyline_spread, esto falla."""
        import inspect

        from bball.backtest import collect

        src = inspect.getsource(collect.reparse_moneyline_spread)
        self.assertNotIn("loc, vis = vis, loc", src)
        self.assertNotIn("hcap = -hcap", src)
        self.assertIn("NO se intercambian las cuotas", src)


class FavoritoGanaLoNormal(unittest.TestCase):
    """Invariante de cordura sobre datos reales. Si no hay base cargada el
    test se salta: en CI no siempre hay Turso."""

    def _favoritos(self):
        from collections import defaultdict

        from bball import db
        from bball.backtest.replay import load_games

        with db.get_conn() as conn:
            games = {g.event_id: g for g in load_games(conn)}
            if not games:
                return None
            rows = conn.execute(
                "SELECT event_id, over_odds, under_odds FROM bball_odds "
                "WHERE snapshot='kickoff' AND market=? AND book='PinnacleSports'",
                (config.MONEYLINE_MARKET_KEY,),
            ).fetchall()
        st = defaultdict(lambda: [0, 0])
        for r in rows:
            g = games.get(r["event_id"])
            if not g or not r["over_odds"] or not r["under_odds"]:
                continue
            if not config.orientation_is_reliable(g.league_name, g.date):
                continue
            lg = "NCAAB" if "NCAA" in (g.league_name or "") else g.league_name
            st[lg][1] += 1
            if (r["over_odds"] < r["under_odds"]) == (g.home_score > g.away_score):
                st[lg][0] += 1
        return st

    def test_entre_60_y_75_por_ciento_en_cada_liga(self):
        st = self._favoritos()
        if not st:
            self.skipTest("sin datos cargados")
        comprobadas = 0
        for lg, (ok, n) in st.items():
            if n < 300:
                continue
            comprobadas += 1
            pct = ok / n * 100
            self.assertGreater(pct, 60.0, f"{lg}: el favorito gana solo el {pct:.1f}% "
                                          f"-- orientacion invertida?")
            self.assertLess(pct, 75.0, f"{lg}: el favorito gana el {pct:.1f}% -- demasiado, "
                                       f"¿fuga de informacion?")
        if comprobadas == 0:
            self.skipTest("ninguna liga con muestra suficiente")

    def test_la_ventaja_de_campo_es_positiva(self):
        """Comprobacion independiente de las cuotas: si bball_games estuviera
        mal orientado, el local ganaria menos del 50%."""
        from collections import defaultdict

        from bball import db
        from bball.backtest.replay import load_games

        with db.get_conn() as conn:
            games = load_games(conn)
        if not games:
            self.skipTest("sin datos cargados")
        st = defaultdict(lambda: [0, 0])
        for g in games:
            lg = "NCAAB" if "NCAA" in (g.league_name or "") else (g.league_name or "?")
            st[lg][1] += 1
            if g.home_score > g.away_score:
                st[lg][0] += 1
        for lg, (ok, n) in st.items():
            if n < 500:
                continue
            self.assertGreater(ok / n, 0.50, f"{lg}: el local gana el {ok/n*100:.1f}%")


if __name__ == "__main__":
    unittest.main()
