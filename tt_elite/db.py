"""Capa SQLite. Una sola base de datos para: cache de datos crudos (para que
un sweep de parametros no vuelva a pegarle a las APIs), picks generados
(tanto de backtest como en vivo), experimentos y el estado persistente del
Elo/H2H que usa el scanner en vivo.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

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


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
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


def get_meta(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
