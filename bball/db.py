"""Capa de datos del sistema de basketball. Mismo patron que tt_elite/db.py
(SQLite local por defecto, Turso remota si TURSO_DATABASE_URL esta en el
entorno) pero con sus PROPIAS tablas (prefijo `bball_`) -- reutiliza la misma
cuenta/instancia Turso que ya usa tt_elite en produccion (cero configuracion
nueva), sin tocar ni una tabla de ese sistema.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import config

SCHEMA = """
-- Cache de respuestas HTTP crudas de BetsAPI. Clave = url+params. Evita
-- volver a gastar cuota/rate-limit al re-correr un collect ya hecho.
CREATE TABLE IF NOT EXISTS bball_http_cache (
    cache_key TEXT PRIMARY KEY,
    prefix TEXT,
    fetched_at TEXT,
    body TEXT NOT NULL
);

-- Ligas descubiertas (sport_id + league_id de BetsAPI) y como las
-- clasificamos nosotros (NBA/WNBA/EUROLEAGUE/...) -- alimentada por
-- `bball.cli discover-leagues`, para no tener que re-descubrir cada vez.
CREATE TABLE IF NOT EXISTS bball_leagues (
    league_id TEXT PRIMARY KEY,
    sport_id TEXT NOT NULL,
    name TEXT,
    tag TEXT,
    discovered_at TEXT
);

-- Partidos terminados (resultado final) + metadatos minimos para poder
-- calcular medias moviles de puntos por equipo sin llamar de nuevo a la API.
CREATE TABLE IF NOT EXISTS bball_games (
    event_id TEXT PRIMARY KEY,
    sport_id TEXT,
    league_id TEXT,
    league_name TEXT,
    date TEXT,              -- YYYY-MM-DD (dia del partido)
    time_ts INTEGER,        -- unix timestamp de inicio programado
    home_team TEXT, away_team TEXT,
    home_key TEXT, away_key TEXT,   -- nombre normalizado (para agrupar historico por equipo)
    home_score INTEGER, away_score INTEGER,
    completed INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT,           -- evento crudo de BetsAPI, por si hace falta re-parsear
    fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_bball_games_date ON bball_games(date);
CREATE INDEX IF NOT EXISTS idx_bball_games_home ON bball_games(home_key, date);
CREATE INDEX IF NOT EXISTS idx_bball_games_away ON bball_games(away_key, date);

-- Cuotas de total de puntos (Over/Under), una fila por linea+casa+snapshot
-- disponible -- un partido puede tener varias lineas simultaneas (la
-- "principal" y alternativas), cada una con su propia cuota.
CREATE TABLE IF NOT EXISTS bball_odds (
    event_id TEXT NOT NULL,
    book TEXT NOT NULL,
    market TEXT NOT NULL,   -- market_key crudo de BetsAPI, tal cual, hasta confirmar su significado
    line REAL,
    over_odds REAL,
    under_odds REAL,
    snapshot TEXT,           -- 'opening' | 'closing' | timestamp crudo de BetsAPI
    captured_at TEXT,
    raw_json TEXT,
    PRIMARY KEY (event_id, book, market, line, snapshot)
);

-- Estadio y ciudad de cada partido (de /v1/event/view). La razon de que
-- exista: el feed de NCAAB mezcla fuentes con local/visitante en ordenes
-- opuestos y sin marcador -- el estadio es la unica verdad fisica por
-- partido (ver PREREGRO/ENMIENDA 2 de situacionales).
CREATE TABLE IF NOT EXISTS bball_venues (
    event_id TEXT PRIMARY KEY,
    stadium TEXT,
    city TEXT,
    fetched_at TEXT
);

-- Estado clave-valor (estrategia activa del scanner en vivo) -- mismo patron
-- que la tabla `meta` de tt_elite, con su propio nombre para no compartir
-- fila con ese sistema.
CREATE TABLE IF NOT EXISTS bball_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Picks del scanner en vivo (y, mas adelante, de un backtest si hiciera
-- falta guardarlos). Un pick = un partido + la mejor cuota disponible entre
-- las casas que cumplian el umbral de la estrategia activa en el momento de
-- evaluarlo. result se actualiza a WIN/LOSS/PUSH cuando bball_games ya tiene
-- el marcador final de ese event_id (ver live/scan.py::_settle_pending).
CREATE TABLE IF NOT EXISTS bball_picks (
    id TEXT PRIMARY KEY,          -- 'live|<event_id>'
    source TEXT NOT NULL,         -- 'live' (por ahora el unico)
    params_hash TEXT,             -- resume n_window+threshold+leagues activos al crearlo
    created_at TEXT,
    event_id TEXT NOT NULL,
    league_name TEXT,
    date TEXT,
    time_ts INTEGER,
    home_team TEXT, away_team TEXT,
    exp_total REAL,
    book TEXT, line REAL, under_odds REAL,
    cushion REAL,
    result TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | WIN | LOSS | PUSH
    final_total INTEGER,
    pnl_1u REAL
);
CREATE INDEX IF NOT EXISTS idx_bball_picks_date ON bball_picks(date);
"""

SCHEMA_STATEMENTS = [s.strip() for s in SCHEMA.split(";") if s.strip()]


# ----------------------------- Backend: Turso (remoto) -------------------------
class _TursoRow:
    """Envuelve una Row de libsql_client para que se comporte como
    sqlite3.Row: indexable por columna o posicion, y sobre todo con .keys()
    -- sin eso, dict(row) no usa el protocolo de mapeo y en su lugar intenta
    trocear cada VALOR de la fila como si fuera un par (clave, valor)."""

    __slots__ = ("_row",)

    def __init__(self, row):
        self._row = row

    def __getitem__(self, key):
        return self._row[key]

    def keys(self):
        return self._row._fields

    def __iter__(self):
        return iter(self._row.astuple())

    def __len__(self):
        return len(self._row)

    def __repr__(self):
        return repr(self._row)


class _TursoCursor:
    def __init__(self, result_set):
        self._rows = [_TursoRow(r) for r in result_set.rows]
        self._pos = 0
        self.lastrowid = result_set.last_insert_rowid
        self.rowcount = result_set.rows_affected

    def fetchone(self):
        if self._pos >= len(self._rows):
            return None
        row = self._rows[self._pos]
        self._pos += 1
        return row

    def fetchall(self):
        rest = list(self._rows[self._pos:])
        self._pos = len(self._rows)
        return rest

    def __iter__(self):
        return iter(self._rows[self._pos:])


def _coerce_params(params):
    if params is None:
        return None
    if isinstance(params, dict):
        return params
    return tuple(params)


# Errores de RED contra Turso (HTTP sobre aiohttp). No indican que la
# sentencia sea invalida, solo que la conexion se cayo: reintentar es
# correcto. Una recoleccion larga (horas) se topa con esto tarde o temprano;
# sin reintento, un `ServerDisconnectedError` suelto tira el run entero.
_RETRYABLE = (
    "server disconnected",
    "connection reset",
    "connection closed",
    "cannot connect",
    "timeout",
    "temporarily unavailable",
    "502", "503", "504",
)
TURSO_RETRIES = 5


def _is_retryable(exc: BaseException) -> bool:
    msg = f"{type(exc).__name__}: {exc}".lower()
    return any(needle in msg for needle in _RETRYABLE)


class TursoConnection:
    def __init__(self, url: str, auth_token: str):
        import libsql_client  # import perezoso: solo hace falta si se usa Turso
        self._url = url
        self._auth_token = auth_token
        self._client = libsql_client.create_client_sync(url=url, auth_token=auth_token)

    def _reconnect(self) -> None:
        import libsql_client
        try:
            self._client.close()
        except Exception:
            pass
        self._client = libsql_client.create_client_sync(
            url=self._url, auth_token=self._auth_token)

    def _retrying(self, fn):
        """Ejecuta fn(), reintentando solo ante caidas de red, con espera
        creciente (1s, 2s, 4s, 8s). Cualquier otro error sube tal cual: un
        SQL malo debe fallar rapido, no reintentarse cinco veces."""
        import time
        last = None
        for intento in range(TURSO_RETRIES):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 -- se re-lanza si no es de red
                if not _is_retryable(exc) or intento == TURSO_RETRIES - 1:
                    raise
                last = exc
                time.sleep(2 ** intento)
                self._reconnect()
        raise last  # pragma: no cover -- inalcanzable

    def execute(self, sql: str, params: Any = None) -> _TursoCursor:
        p = _coerce_params(params)
        rs = self._retrying(lambda: self._client.execute(sql, p))
        return _TursoCursor(rs)

    def executemany(self, sql: str, seq_of_params) -> None:
        stmts = [(sql, _coerce_params(p)) for p in seq_of_params]
        if stmts:
            self._retrying(lambda: self._client.batch(stmts))

    def executescript(self, sql: str) -> None:
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                self._client.execute(stmt)

    def commit(self) -> None:
        pass  # Turso via HTTP hace autocommit por sentencia fuera de una transaction()

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _normalize_turso_url(url: str) -> str:
    if url.startswith("libsql://"):
        return "https://" + url[len("libsql://"):]
    return url


# ----------------------------- Conexion --------------------------------------
def connect(db_path: Path | None = None):
    """Un `db_path` explicito gana siempre sobre TURSO_DATABASE_URL -- igual
    fix que tt_elite/db.py (ver EXPERIMENTS_LOG.md, 2026-08-24): sin esto, un
    test que pide SQLite local de usar y tirar acaba escribiendo en silencio
    contra Turso en cuanto el entorno tiene TURSO_DATABASE_URL definido."""
    if db_path is not None:
        return _connect_sqlite(db_path)

    turso_url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    if turso_url:
        conn = TursoConnection(_normalize_turso_url(turso_url), os.environ.get("TURSO_AUTH_TOKEN", "").strip())
        try:
            for stmt in SCHEMA_STATEMENTS:
                conn.execute(stmt)
        except Exception:
            conn.close()
            raise
        return conn

    return _connect_sqlite(config.DB_PATH)


def _connect_sqlite(db_path: Path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def get_conn(db_path: Path | None = None):
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
