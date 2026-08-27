"""Que (N, umbral, ligas) usa el scanner en vivo de basketball ahora mismo.
Mismo patron que tt_elite/model/active.py: se guarda en la base de datos
(tabla bball_meta), no en un archivo -- asi el dashboard puede "promover"
una configuracion escribiendo directo en Turso, sin depender de un commit
a git, y el scanner la recoge en la siguiente pasada.
"""
from __future__ import annotations

import json

META_KEY = "active_bball_params"

# Placeholder razonable hasta que el backtest-split de una configuracion
# validada contra reserva para promover -- NUNCA se debe apostar dinero real
# contra este default sin antes correr `backtest-split` + `risk` sobre el
# historico ya recolectado.
DEFAULT_PARAMS = {"n_window": 10, "threshold": 8.0, "leagues": ["NBA", "WNBA", "EUROLEAGUE"], "book": None}


def load_active_params(conn) -> dict:
    row = conn.execute("SELECT value FROM bball_meta WHERE key = ?", (META_KEY,)).fetchone()
    if row and row["value"]:
        return json.loads(row["value"])
    return dict(DEFAULT_PARAMS)


def save_active_params(conn, params: dict) -> None:
    conn.execute(
        "INSERT INTO bball_meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (META_KEY, json.dumps(params)),
    )


def params_label(params: dict) -> str:
    leagues = "+".join(params.get("leagues", []))
    book = params.get("book")
    book_str = f" book={book}" if book else " (mejor cuota entre todas las casas)"
    return f"N={params.get('n_window')} umbral={params.get('threshold')} [{leagues}]{book_str}"
