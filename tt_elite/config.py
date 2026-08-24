"""Configuracion global: se carga desde variables de entorno / .env.

Nunca pongas el token de BetsAPI ni la API key de SendGrid directamente en
este archivo -- siempre via entorno (.env local o GitHub Secrets en produccion).
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

# Envio de alertas por email via SendGrid (https://sendgrid.com) -- API HTTP
# simple con una sola API key. Requiere "Single Sender Verification" en el
# dashboard de SendGrid (confirmar con un clic que EMAIL_FROM es tuyo) --
# a diferencia de Resend en modo de pruebas, esto SI permite mandar a
# cualquier destinatario, sin necesitar verificar un dominio propio con DNS.
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "").strip()
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")

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
