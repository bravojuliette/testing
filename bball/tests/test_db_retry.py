"""Una recoleccion de horas contra Turso se topa antes o despues con un corte
de red (paso: run 33205631811 murio a los 68 minutos con
`aiohttp ServerDisconnectedError`). El reintento debe cubrir ESO y solo eso:
un SQL invalido tiene que fallar a la primera."""
import unittest
from unittest import mock

from bball import db


class _FakeClient:
    """Falla las primeras `fallos` llamadas con `exc`, luego devuelve algo."""

    def __init__(self, fallos, exc):
        self.fallos = fallos
        self.exc = exc
        self.llamadas = 0

    def execute(self, sql, params=None):
        self.llamadas += 1
        if self.llamadas <= self.fallos:
            raise self.exc
        return mock.Mock(rows=[], last_insert_rowid=None, rows_affected=0)

    def batch(self, stmts):
        return self.execute("batch")

    def close(self):
        pass


def _conn(fallos, exc):
    c = db.TursoConnection.__new__(db.TursoConnection)
    c._url, c._auth_token = "libsql://x", "t"
    c._client = _FakeClient(fallos, exc)
    c._reconnect = lambda: None    # no hay red que reabrir en el test
    return c


class TursoRetryTests(unittest.TestCase):
    def test_reintenta_tras_corte_de_red_y_acaba_bien(self):
        c = _conn(2, Exception("Server disconnected"))
        with mock.patch("time.sleep"):
            c.execute("SELECT 1")
        self.assertEqual(c._client.llamadas, 3)

    def test_sql_invalido_no_se_reintenta(self):
        c = _conn(99, ValueError("no such table: bball_nope"))
        with mock.patch("time.sleep"), self.assertRaises(ValueError):
            c.execute("SELECT * FROM bball_nope")
        self.assertEqual(c._client.llamadas, 1)

    def test_se_rinde_tras_agotar_los_reintentos(self):
        c = _conn(99, Exception("Connection reset by peer"))
        with mock.patch("time.sleep"), self.assertRaises(Exception):
            c.execute("SELECT 1")
        self.assertEqual(c._client.llamadas, db.TURSO_RETRIES)

    def test_executemany_tambien_reintenta(self):
        c = _conn(1, Exception("503 Service Unavailable"))
        with mock.patch("time.sleep"):
            c.executemany("INSERT INTO t VALUES (?)", [(1,), (2,)])
        self.assertEqual(c._client.llamadas, 2)

    def test_clasificacion_de_errores(self):
        for msg in ("Server disconnected", "Cannot connect to host",
                    "504 Gateway Timeout", "Connection closed"):
            self.assertTrue(db._is_retryable(Exception(msg)), msg)
        for msg in ("no such column: foo", "UNIQUE constraint failed"):
            self.assertFalse(db._is_retryable(Exception(msg)), msg)


if __name__ == "__main__":
    unittest.main()


class SchemaSplitterTests(unittest.TestCase):
    def test_ningun_trozo_es_solo_comentario(self):
        """Un ';' dentro de un comentario del esquema no debe generar
        trozos-basura (rompio el connect() contra Turso dos veces)."""
        for stmt in db.SCHEMA_STATEMENTS:
            self.assertTrue(stmt.upper().startswith("CREATE"),
                            f"trozo sospechoso: {stmt[:80]!r}")

    def test_los_comentarios_no_llegan_a_turso(self):
        for stmt in db.SCHEMA_STATEMENTS:
            self.assertNotIn("--", stmt)
