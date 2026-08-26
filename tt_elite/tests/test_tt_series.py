"""tt_posts_for_date/load_sessions_for_date: use_cache debe poder desactivarse.

Bug real del 2026-08-26: el WordPress post de resultados de "hoy" en
TT-Series se va EDITANDO durante el dia segun se cierran partidos, pero la
URL/parametros de esta consulta no cambian en todo el dia (mismo
`search=dot`) -- con la cache por defecto de ApiClient.get_json (pensada
para backfill de dias YA cerrados, donde el contenido nunca cambia), el
scanner en vivo se quedaba pegado a la foto de la primera vez que la pidio
ese dia y nunca veia partidos nuevos como completados. Resultado: candidates
quedo en 0 durante horas (varias pasadas de live_scan.yml en produccion),
aunque de fondo si hubiera partidos jugandose y cerrandose con normalidad.
"""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from tt_elite import db as dbmod
from tt_elite.sources.http_cache import ApiClient
from tt_elite.sources.tt_series import tt_posts_for_date, load_sessions_for_date

D = date(2026, 8, 26)


def _fake_response(posts):
    resp = type("Resp", (), {})()
    resp.status_code = 200
    resp.json = lambda: posts
    resp.raise_for_status = lambda: None
    return resp


class TtSeriesCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.conn = dbmod.connect(Path(self.tmpdir.name) / "test.db")
        self.client = ApiClient(self.conn, betsapi_token="dummy")

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_use_cache_true_reuses_stale_response_across_calls(self):
        """Comportamiento pensado para backfill de dias ya cerrados: la
        segunda llamada NUNCA vuelve a tocar la red, aunque el contenido
        "real" haya cambiado -- correcto quando el dia ya esta cerrado."""
        first = [{"link": "x/26-08-2026-result-a/", "title": {"rendered": "t"}, "content": {"rendered": "v1"}}]
        second = [{"link": "x/26-08-2026-result-a/", "title": {"rendered": "t"}, "content": {"rendered": "v2"}}]
        with patch.object(self.client.session, "get", side_effect=[_fake_response(first), _fake_response(second)]) as m:
            r1 = tt_posts_for_date(self.client, D)
            r2 = tt_posts_for_date(self.client, D)
        self.assertEqual(m.call_count, 1)  # la segunda vino de cache, no de la red
        self.assertEqual(r1[0]["content"]["rendered"], "v1")
        self.assertEqual(r2[0]["content"]["rendered"], "v1")  # sigue viendo la version vieja

    def test_use_cache_false_always_fetches_fresh(self):
        """El caso real de "hoy" en el scanner en vivo: cada llamada debe ver
        el contenido mas reciente, ninguna se sirve de una respuesta vieja."""
        first = [{"link": "x/26-08-2026-result-a/", "title": {"rendered": "t"}, "content": {"rendered": "v1"}}]
        second = [{"link": "x/26-08-2026-result-a/", "title": {"rendered": "t"}, "content": {"rendered": "v2"}}]
        with patch.object(self.client.session, "get", side_effect=[_fake_response(first), _fake_response(second)]) as m:
            r1 = tt_posts_for_date(self.client, D, use_cache=False)
            r2 = tt_posts_for_date(self.client, D, use_cache=False)
        self.assertEqual(m.call_count, 2)  # las dos fueron a la red
        self.assertEqual(r1[0]["content"]["rendered"], "v1")
        self.assertEqual(r2[0]["content"]["rendered"], "v2")

    def test_load_sessions_for_date_threads_use_cache_through(self):
        post = [{
            "link": "x/26-08-2026-result-a/", "title": {"rendered": "t"},
            "content": {"rendered": "<table><tr><td>player</td><td>result</td><td>match</td></tr></table>"},
        }]
        with patch.object(self.client.session, "get", side_effect=[_fake_response(post), _fake_response(post)]) as m:
            load_sessions_for_date(self.client, D, use_cache=False)
            load_sessions_for_date(self.client, D, use_cache=False)
        self.assertEqual(m.call_count, 2)


if __name__ == "__main__":
    unittest.main()
