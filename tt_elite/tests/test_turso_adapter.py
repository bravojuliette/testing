"""Verifica el adaptador TursoConnection (tt_elite/db.py) sin red: se
sustituye libsql_client.create_client_sync por un cliente falso, pero se usan
los objetos reales ResultSet/Row de la libreria (instalada localmente) para
que la prueba refleje el comportamiento real de indexado/iteracion."""
import unittest
from unittest.mock import patch

from libsql_client.result import ResultSet, Row

from tt_elite.db import TursoConnection, SCHEMA_STATEMENTS, _normalize_turso_url, connect


def _row(cols, values):
    return Row({c: i for i, c in enumerate(cols)}, tuple(values))


class _FakeClient:
    """Sustituye a libsql_client.ClientSync: registra las sentencias recibidas
    y devuelve resultados prefabricados."""

    def __init__(self, script_result=None):
        self.calls = []
        self._script_result = script_result or ResultSet((), [], 0, None)

    def execute(self, sql, args=None):
        self.calls.append((sql, args))
        if "SELECT" in sql.upper():
            cols = ("a", "b")
            rows = [_row(cols, [1, "x"]), _row(cols, [2, "y"])]
            return ResultSet(cols, rows, 0, None)
        return ResultSet((), [], 1, 42)

    def batch(self, stmts):
        self.calls.append(("BATCH", stmts))
        return [ResultSet((), [], 1, None) for _ in stmts]

    def close(self):
        self.calls.append(("CLOSE", None))


class TursoAdapterTests(unittest.TestCase):
    def _make_conn(self, fake_client):
        with patch("libsql_client.create_client_sync", return_value=fake_client):
            # executescript en __init__ de connect() normal; aqui construimos
            # TursoConnection directo para no depender de variables de entorno.
            conn = TursoConnection("libsql://fake.turso.io", "token")
        return conn

    def test_execute_select_returns_rows_indexable_by_name_and_iterable(self):
        fake = _FakeClient()
        conn = self._make_conn(fake)
        cur = conn.execute("SELECT a, b FROM t")
        first = cur.fetchone()
        self.assertEqual(first["a"], 1)
        self.assertEqual(first["b"], "x")
        rest = cur.fetchall()
        self.assertEqual(len(rest), 1)
        self.assertEqual(rest[0]["a"], 2)

    def test_iterating_cursor_directly_like_a_for_loop(self):
        fake = _FakeClient()
        conn = self._make_conn(fake)
        rows = list(conn.execute("SELECT a, b FROM t"))
        self.assertEqual([r["a"] for r in rows], [1, 2])

    def test_insert_returns_lastrowid_from_result_set(self):
        fake = _FakeClient()
        conn = self._make_conn(fake)
        cur = conn.execute("INSERT INTO t(a) VALUES (?)", (1,))
        self.assertEqual(cur.lastrowid, 42)

    def test_executemany_uses_batch_with_coerced_params(self):
        fake = _FakeClient()
        conn = self._make_conn(fake)
        conn.executemany("UPDATE t SET a=? WHERE b=?", [(1, "x"), (2, "y")])
        self.assertEqual(len(fake.calls), 1)
        label, stmts = fake.calls[0]
        self.assertEqual(label, "BATCH")
        self.assertEqual(stmts, [("UPDATE t SET a=? WHERE b=?", (1, "x")), ("UPDATE t SET a=? WHERE b=?", (2, "y"))])

    def test_executescript_splits_into_individual_statements(self):
        fake = _FakeClient()
        conn = self._make_conn(fake)
        conn.executescript("CREATE TABLE a(x); CREATE TABLE b(y);")
        executed_sql = [c[0] for c in fake.calls]
        self.assertEqual(len(executed_sql), 2)
        self.assertIn("CREATE TABLE a(x)", executed_sql[0])
        self.assertIn("CREATE TABLE b(y)", executed_sql[1])

    def test_commit_is_a_noop_and_close_forwards(self):
        fake = _FakeClient()
        conn = self._make_conn(fake)
        conn.commit()  # no debe llamar al cliente
        conn.close()
        self.assertEqual(fake.calls[-1], ("CLOSE", None))

    def test_schema_statements_apply_cleanly_against_fake_client(self):
        fake = _FakeClient()
        conn = self._make_conn(fake)
        for stmt in SCHEMA_STATEMENTS:
            conn.execute(stmt)
        # Todas las sentencias del schema real deben poder mandarse una a una
        # sin que el split dependa de mas contexto que un simple ';'.
        self.assertEqual(len(fake.calls), len(SCHEMA_STATEMENTS))


class TursoUrlNormalizationTests(unittest.TestCase):
    """Regresion: 'libsql://' hace que libsql_client intente WebSocket (wss://),
    que en la practica fallo el handshake contra Turso (visto en produccion:
    WSServerHandshakeError 400). 'https://' usa el transporte HTTP normal."""

    def test_libsql_scheme_is_rewritten_to_https(self):
        self.assertEqual(
            _normalize_turso_url("libsql://mydb-myorg.turso.io"),
            "https://mydb-myorg.turso.io",
        )

    def test_https_url_is_left_unchanged(self):
        self.assertEqual(
            _normalize_turso_url("https://mydb-myorg.turso.io"),
            "https://mydb-myorg.turso.io",
        )


class TursoConnectFailureClosesClientTests(unittest.TestCase):
    """Regresion: si connect() falla aplicando el schema, el cliente debe
    cerrarse. Sin esto, el hilo en segundo plano de libsql_client se queda
    vivo para siempre y el proceso nunca termina (visto en produccion: un
    job de GitHub Actions colgado 10 minutos hasta el timeout, en vez de
    fallar en segundos)."""

    def test_connect_closes_client_and_reraises_when_schema_fails(self):
        fake = _FakeClient()
        fake.execute = lambda sql, args=None: (_ for _ in ()).throw(RuntimeError("boom"))

        with patch("libsql_client.create_client_sync", return_value=fake), \
             patch.dict("os.environ", {"TURSO_DATABASE_URL": "libsql://x.turso.io", "TURSO_AUTH_TOKEN": "t"}):
            with self.assertRaises(RuntimeError):
                connect()

        self.assertIn(("CLOSE", None), fake.calls)


if __name__ == "__main__":
    unittest.main()
