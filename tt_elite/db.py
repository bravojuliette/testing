"""Capa de datos. Una sola base de datos para: cache de datos crudos (para que
un sweep de parametros no vuelva a pegarle a las APIs), picks generados
(tanto de backtest como en vivo), experimentos y el estado persistente del
Elo/H2H que usa el scanner en vivo.

Dos backends, misma interfaz (execute/executemany/executescript/commit/close,
filas indexables por nombre de columna como sqlite3.Row):

- **SQLite local** (por defecto): un archivo en `data/tt_elite.db`. Sirve para
  desarrollo/tests, sin dependencias externas.
- **Turso** (si `TURSO_DATABASE_URL` esta en el entorno): base de datos remota
  compatible con SQLite. Se usa cuando el mismo estado tiene que ser
  accesible desde varios sitios a la vez -- p.ej. GitHub Actions escribiendo
  los picks y el dashboard en Vercel leyendolos.

El resto del codigo (`backtest/`, `live/`, `cli.py`) nunca sabe cual de los
dos esta usando: solo llama a `db.get_conn()`.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_matches (
    match_uid TEXT PRIMARY KEY,
    session_url TEXT NOT NULL,
    session_title TEXT,
    date TEXT NOT NULL,          -- YYYY-MM-DD del dia de sesion asignado
    time TEXT NOT NULL,          -- HH:MM tal cual TT-Series
    dt TEXT,                     -- ISO datetime con tz, si se pudo resolver
    rel_min INTEGER,
    p1 TEXT NOT NULL, p2 TEXT NOT NULL,
    p1_key TEXT NOT NULL, p2_key TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    s1 INTEGER, s2 INTEGER,
    result_source TEXT,
    elo_applied INTEGER NOT NULL DEFAULT 0   -- ya se aplico al elo_state persistente (scanner en vivo)
);
CREATE INDEX IF NOT EXISTS idx_raw_matches_date ON raw_matches(date);

CREATE TABLE IF NOT EXISTS raw_odds (
    match_uid TEXT NOT NULL,
    book TEXT NOT NULL,
    source TEXT,
    is_fallback INTEGER NOT NULL DEFAULT 0,
    event_id TEXT,
    odds1 REAL, odds2 REAL,
    mp1 REAL, mp2 REAL,
    add_time INTEGER,
    quality TEXT,
    captured_at TEXT,
    PRIMARY KEY (match_uid, book)
);

CREATE TABLE IF NOT EXISTS picks (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,        -- 'backtest' | 'live'
    strategy_name TEXT,
    params_hash TEXT,
    created_at TEXT,
    match_uid TEXT,
    date TEXT, session_title TEXT, time TEXT,
    p1 TEXT, p2 TEXT,
    favorito TEXT, underdog TEXT,
    book TEXT, odds_underdog REAL,
    market_prob_underdog REAL, model_prob_underdog REAL,
    edge_pp REAL, ev_pct REAL, fair_odds REAL,
    signal TEXT,
    result TEXT DEFAULT 'PENDING',   -- PENDING | WIN | LOSS
    pnl_1u REAL,
    emailed INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_picks_params ON picks(params_hash);
CREATE INDEX IF NOT EXISTS idx_picks_date ON picks(date);

CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    params_hash TEXT,
    params_json TEXT,
    created_at TEXT,
    period_start TEXT, period_end TEXT,
    split_date TEXT,
    n_train INTEGER, hit_rate_train REAL, roi_train REAL, pnl_train REAL,
    n_test INTEGER, hit_rate_test REAL, roi_test REAL, pnl_test REAL, sharpe_test REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS elo_state (
    player_key TEXT PRIMARY KEY,
    player_name TEXT,
    elo REAL NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS h2h_state (
    pair_key TEXT PRIMARY KEY,
    history_json TEXT NOT NULL   -- lista JSON de player_key ganador, mas reciente al final
);

-- Contadores de carrera COMPLETA del jugador (cruzando sesiones), persistentes
-- entre pasadas del scanner en vivo -- igual patron que elo_state/h2h_state.
-- Alimenta min_career_matches/min_career_win_rate (ver StrategyParams), que
-- el motor de backtest (backtest/replay.py) ya aplicaba pero el scanner en
-- vivo no comprobaba (bug encontrado el 2026-08-24, ver EXPERIMENTS_LOG.md).
CREATE TABLE IF NOT EXISTS career_state (
    player_key TEXT PRIMARY KEY,
    played INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0
);

-- Sistema APARTE del scanner principal (picks/edge/ROI): detector de
-- "cadenas de barridas transitivas". Dentro de una misma sesion, si A goleo
-- 3-0 a X, y X goleo 3-0 a Y, y toca A vs Y -- se marca aqui. Puramente
-- observacional (sin backtest, sin probabilidad de acierto): lo pidio el
-- usuario el 2026-08-24 como herramienta separada, no como sustituto de la
-- estrategia ya validada. Se alimenta solo de raw_matches ya recolectado
-- (sin llamadas nuevas a BetsAPI/TT-Series). id = match_uid + par (A,X) para
-- que un mismo partido pueda registrar mas de una cadena si aplica en ambos
-- sentidos o con mas de un X comun. INSERT ... ON CONFLICT conserva
-- detected_at (primera vez que se vio) y solo refresca el resultado del
-- partido segun se va completando.
-- ax_*/xy_* identifican los DOS partidos de barrida que forman la cadena
-- (A goleo 3-0 a X el ax_date/ax_time, X goleo 3-0 a Y el xy_date/xy_time),
-- para poder mostrarlos. a_score/y_score son el resultado del propio
-- partido A vs Y ya REORIENTADO (a_score siempre es el marcador de A, sin
-- importar si A fue home o away en raw_matches) -- theory_holds (NULL
-- mientras no termine el partido) es 1 si A gano (confirma la teoria de que
-- A > Y por transitividad) o 0 si gano Y (la refuta).
CREATE TABLE IF NOT EXISTS blowout_chain_signals (
    id TEXT PRIMARY KEY,
    match_uid TEXT NOT NULL,
    session_url TEXT, session_title TEXT,
    date TEXT, time TEXT, dt TEXT, rel_min INTEGER,
    player_a TEXT, player_a_key TEXT,
    player_y TEXT, player_y_key TEXT,
    common_x TEXT, common_x_key TEXT,
    ax_match_uid TEXT, ax_date TEXT, ax_time TEXT,
    xy_match_uid TEXT, xy_date TEXT, xy_time TEXT,
    match_completed INTEGER NOT NULL DEFAULT 0,
    a_score INTEGER, y_score INTEGER,
    theory_holds INTEGER,
    detected_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_blowout_chain_date ON blowout_chain_signals(date);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Cache de respuestas HTTP crudas (TT-Series + BetsAPI). Clave = url+params.
-- Evita volver a gastar cuota/rate-limit al re-correr un collect ya hecho.
CREATE TABLE IF NOT EXISTS http_cache (
    cache_key TEXT PRIMARY KEY,
    prefix TEXT,
    fetched_at TEXT,
    body TEXT NOT NULL
);
"""

SCHEMA_STATEMENTS = [s.strip() for s in SCHEMA.split(";") if s.strip()]

# Migraciones aditivas (ALTER TABLE ADD COLUMN) para bases ya existentes con
# una version anterior de blowout_chain_signals (Turso en produccion ya
# tenia filas con el esquema viejo -- match_s1/match_s2 sin reorientar --
# cuando se descubrio que hacia falta guardar los dos partidos de barrida, el
# marcador reorientado y las cuotas). En una base nueva (tests, SQLite local)
# estas columnas ya existen via CREATE TABLE de arriba. Cada entrada es
# (tabla, columna, sentencia ALTER) -- _apply_migrations() comprueba con
# PRAGMA table_info si la columna ya existe antes de correr el ALTER, en vez
# de intentarlo y descartar el error: el cliente HTTP de Turso (libsql_client)
# no propaga el mensaje de error real de "duplicate column" (revienta con un
# KeyError generico), asi que detectarlo por texto de excepcion no es fiable.
MIGRATIONS = [
    ("blowout_chain_signals", "ax_match_uid", "ALTER TABLE blowout_chain_signals ADD COLUMN ax_match_uid TEXT"),
    ("blowout_chain_signals", "ax_date", "ALTER TABLE blowout_chain_signals ADD COLUMN ax_date TEXT"),
    ("blowout_chain_signals", "ax_time", "ALTER TABLE blowout_chain_signals ADD COLUMN ax_time TEXT"),
    ("blowout_chain_signals", "xy_match_uid", "ALTER TABLE blowout_chain_signals ADD COLUMN xy_match_uid TEXT"),
    ("blowout_chain_signals", "xy_date", "ALTER TABLE blowout_chain_signals ADD COLUMN xy_date TEXT"),
    ("blowout_chain_signals", "xy_time", "ALTER TABLE blowout_chain_signals ADD COLUMN xy_time TEXT"),
    ("blowout_chain_signals", "a_score", "ALTER TABLE blowout_chain_signals ADD COLUMN a_score INTEGER"),
    ("blowout_chain_signals", "y_score", "ALTER TABLE blowout_chain_signals ADD COLUMN y_score INTEGER"),
    ("blowout_chain_signals", "theory_holds", "ALTER TABLE blowout_chain_signals ADD COLUMN theory_holds INTEGER"),
    ("blowout_chain_signals", "a_odds", "ALTER TABLE blowout_chain_signals ADD COLUMN a_odds REAL"),
    ("blowout_chain_signals", "y_odds", "ALTER TABLE blowout_chain_signals ADD COLUMN y_odds REAL"),
    ("blowout_chain_signals", "odds_book", "ALTER TABLE blowout_chain_signals ADD COLUMN odds_book TEXT"),
    # Racha de victorias de A justo ANTES de LA BARRIDA (A goleando 3-0 a X)
    # -- no antes de A vs Y. 0 si el partido inmediatamente anterior de A
    # fue una derrota, o si A no jugo nada mas antes en esa sesion. Pedido
    # del usuario el 2026-08-25 para filtrar a los casos donde la propia
    # barrida ya venia respaldada por 1/2/3 victorias previas.
    ("blowout_chain_signals", "a_prior_win_streak", "ALTER TABLE blowout_chain_signals ADD COLUMN a_prior_win_streak INTEGER"),
]


def _apply_migrations(conn) -> None:
    cols_by_table: dict[str, set[str]] = {}
    for table, col, ddl in MIGRATIONS:
        if table not in cols_by_table:
            cols_by_table[table] = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in cols_by_table[table]:
            conn.execute(ddl)
            cols_by_table[table].add(col)


# ----------------------------- Backend: Turso (remoto) -------------------------
class _TursoRow:
    """Envuelve una Row de libsql_client para que se comporte como
    sqlite3.Row: indexable por columna o posicion, y sobre todo con .keys()
    -- sin eso, dict(row) no usa el protocolo de mapeo y en su lugar intenta
    trocear cada VALOR de la fila como si fuera un par (clave, valor), lo que
    revienta en cuanto una columna de texto no mide exactamente 2 caracteres."""

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
    """Imita lo minimo de un cursor sqlite3 que usa el resto del codigo:
    fetchone/fetchall/iteracion + lastrowid."""

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


class TursoConnection:
    """Adaptador sobre libsql_client que expone la misma superficie que usa el
    resto del codigo (execute/executemany/executescript/commit/close, filas
    accesibles por nombre de columna) -- para que backtest/live/cli no sepan
    si estan hablando con SQLite local o con Turso."""

    def __init__(self, url: str, auth_token: str):
        import libsql_client  # import perezoso: solo hace falta si se usa Turso
        self._client = libsql_client.create_client_sync(url=url, auth_token=auth_token)

    def execute(self, sql: str, params: Any = None) -> _TursoCursor:
        rs = self._client.execute(sql, _coerce_params(params))
        return _TursoCursor(rs)

    def executemany(self, sql: str, seq_of_params) -> None:
        stmts = [(sql, _coerce_params(p)) for p in seq_of_params]
        if stmts:
            self._client.batch(stmts)

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
    """libsql_client interpreta el esquema 'libsql://' (el que da el dashboard
    de Turso) como WebSocket -- que en la practica falla el handshake contra
    el endpoint de Turso. 'https://' con el mismo host usa el transporte HTTP
    normal (mas simple y mas apto para entornos efimeros tipo GitHub Actions
    / serverless), y es el mismo backend."""
    if url.startswith("libsql://"):
        return "https://" + url[len("libsql://"):]
    return url


# ----------------------------- Conexion --------------------------------------
def connect(db_path: Path | None = None):
    turso_url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    if turso_url:
        conn = TursoConnection(_normalize_turso_url(turso_url), os.environ.get("TURSO_AUTH_TOKEN", "").strip())
        try:
            for stmt in SCHEMA_STATEMENTS:
                conn.execute(stmt)
            _apply_migrations(conn)
        except Exception:
            # Sin esto, un fallo aqui deja vivo el hilo en segundo plano de
            # libsql_client (nunca se llama a conn.close()) y el proceso se
            # queda colgado en vez de fallar limpio.
            conn.close()
            raise
        return conn

    path = db_path or config.DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(SCHEMA)
    _apply_migrations(conn)
    return conn


@contextmanager
def get_conn(db_path: Path | None = None):
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_meta(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
