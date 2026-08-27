"""Configuracion del sistema de basketball (teoria de totales por debajo de
la media de scoring de cada equipo). Deliberadamente independiente de
tt_elite/: token de BetsAPI propio (es un producto/tier distinto al de tenis
de mesa) y tablas de base de datos propias con prefijo `bball_`, aunque
reutiliza la MISMA cuenta Turso ya configurada en este repo (TURSO_DATABASE_URL
/ TURSO_AUTH_TOKEN) -- así no hace falta una base de datos nueva, y los datos
de un sistema nunca se mezclan con los del otro.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # no-op si no existe .env (p.ej. en GitHub Actions)

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.environ.get("BBALL_DB", str(DATA_DIR / "bball.db")))

# El usuario confirmo que su token de basketball es el MISMO valor que el
# BETSAPI_TOKEN ya configurado para tt_elite (una sola suscripcion de BetsAPI
# cubre ambos deportes) -- BETSAPI_TOKEN_BBALL existe solo por si en el
# futuro pasan a tokens distintos por producto; mientras no se defina, cae en
# BETSAPI_TOKEN. Nunca lo pongas en codigo: .env local o secret de GitHub
# Actions.
BETSAPI_TOKEN = (os.environ.get("BETSAPI_TOKEN_BBALL") or os.environ.get("BETSAPI_TOKEN") or "").strip()
BETSAPI_BASE = "https://api.b365api.com"
