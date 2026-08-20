"""Configuracion global: se carga desde variables de entorno / .env.

Nunca pongas el token de BetsAPI ni credenciales SMTP directamente en este
archivo -- siempre via entorno (.env local o GitHub Secrets en produccion).
"""
from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()  # no-op si no existe .env (p.ej. en GitHub Actions, que usa env vars reales)

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.environ.get("TT_ELITE_DB", str(DATA_DIR / "tt_elite.db")))

BETSAPI_TOKEN = os.environ.get("BETSAPI_TOKEN", "").strip()

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", SMTP_USER)
EMAIL_TO = os.environ.get("EMAIL_TO", SMTP_USER)

# ----------------------------- Fuentes de datos ------------------------------
TT_BASE = "https://www.tt-series.com"
TT_RANKING_URL = f"{TT_BASE}/ranking/"
BETSAPI_BASE = "https://api.b365api.com"
SPORT_ID = 92
LEAGUE_ID = 29128
TZ = ZoneInfo("Europe/Warsaw")
MARKET_KEY = "92_1"  # Match Winner para deportes no-friccion "_1" segun docs BetsAPI

# Cadena de casas de apuestas: Interwetten primero (mercado "de referencia" en tus
# scripts originales), luego fallbacks en orden de prioridad.
BOOKS = [
    ("interwetten", "Interwetten", False),
    ("bet365", "Bet365", True), ("betclic", "Betclic", True),
    ("bwin", "Bwin", True), ("betfair", "Betfair", True),
    ("betway", "Betway", True), ("188bet", "188Bet", True),
    ("ladbrokes", "Ladbrokes", True), ("cloudbet", "CloudBet", True),
    ("williamhill", "WilliamHill", True), ("betfred", "BetFred", True),
    ("betathome", "BetAtHome", True), ("intertops", "Intertops", True),
    ("nitrogensports", "NitrogenSports", True), ("ggbet", "GGBet", True),
    ("polymarket", "PolyMarket", True), ("10bet", "10Bet", True),
    ("ysb88", "YSB88", True), ("spreadex", "Spreadex", True),
    ("virginbet", "VirginBet", True), ("draftkings", "DraftKings", True),
    ("fanduel", "FanDuel", True), ("duelbits", "Duelbits", True),
    ("fonbet", "Fonbet", True),
]

EVENT_TIME_TOL_MIN = 120

# Ventana de elegibilidad del scanner en vivo: candidatos entre "ya deberia haber
# empezado hace STALE_GRACE_MINUTES" y "empieza en LOOKAHEAD_MINUTES".
STALE_GRACE_MINUTES = 20
LOOKAHEAD_MINUTES = 150

# Data-gap policy (igual que el backtest V5 de Colab): huecos aislados de
# resultados no abortan el dia completo si son pequenos.
MAX_UNRESOLVED_MATCHES_PER_DAY = 12
MAX_UNRESOLVED_RATIO_PER_DAY = 0.03
