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

SPORT_ID = 18  # basketball -- confirmado empiricamente (bball.cli discover-leagues), unico
               # sport_id que este token no rechaza con PERMISSION_DENIED.

# league_id descubiertos con `python -m bball.cli leagues-on-day` contra un dia real de
# temporada (20260115) + `discover-leagues` (WNBA, via /v3/events/upcoming). NBA All-Star
# Game (league_id=3877) es una liga DISTINTA -- no confundir.
LEAGUES = {
    "NBA": 2274,
    "WNBA": 244,
    "EUROLEAGUE": 1923,
    # Añadidas por VOLUMEN (descubiertas con `leagues-on-day --day 20260115`,
    # antes de mirar ningun resultado -- ver PREREGISTRO_rachas_over.md). El
    # baloncesto universitario de EEUU tiene ~13x los partidos de la NBA:
    # ese dia hubo NCAAB 106 y WNCAAB 57 frente a NBA 8 y Euroliga 6.
    # NO incluir 'Ebasketball H2H GG League' (id 25067, 201 partidos ese dia):
    # es baloncesto SIMULADO por videojuego, no deporte real.
    "NCAAB": 2638,
    "WNCAAB": 2675,
}

# Mercado de total de puntos (Over/Under) en la respuesta de BetsAPI -- confirmado
# empiricamente: "{sport_id}_3", con campos handicap/over_od/under_od. "{sport_id}_1" es
# ganador (home_od/away_od), "{sport_id}_2" es handicap/spread.
TOTALS_MARKET_KEY = f"{SPORT_ID}_3"
MONEYLINE_MARKET_KEY = f"{SPORT_ID}_1"
SPREAD_MARKET_KEY = f"{SPORT_ID}_2"

# BetsAPI lista las ligas AMERICANAS en convencion "visitante @ local": su campo
# 'home' es en realidad el equipo VISITANTE. Verificado contra la realidad
# (PHI 76ers 117-116 BOS Celtics, 2025-10-22: BetsAPI lo da como home=PHI, pero
# se jugo en Boston -- basketball-reference 202510220BOS) y confirmado por dos
# senales internas independientes en todo el dataset: nuestro 'local' anotaba
# MENOS que el visitante (NBA -1.82, WNBA -1.08 puntos) y ganaba solo el 45.0%
# (NBA) / 48.9% (WNBA), cuando la ventaja de campo real va en sentido contrario.
# La Euroliga viene bien (local +3.43 puntos, gana el 62.8%) y NO se toca.
# collect.py normaliza al ingest: en estas ligas se intercambian local/visitante
# para que 'home' signifique siempre el equipo que juega en casa.
# El mercado de totales (18_3) es simetrico y no le afecta; ganador (18_1) y
# handicap (18_2) SI, y se intercambian con el mismo criterio al parsearlos.
AWAY_FIRST_LEAGUES = {"NBA", "WNBA"}

# CUIDADO -- datos de origen no fiables: en la temporada 2026 de WNBA el
# ORDEN de los equipos que da BetsAPI es INCONSISTENTE dentro de la propia
# temporada, no una convencion fija. Evidencia (todo medido en el JSON
# NATIVO de BetsAPI, marcador y cuotas del mismo evento, sin transformarlo):
#   - el favorito segun la cuota de cierre gana el 65-70% en NBA, Euroliga y
#     en WNBA 2022/2023/2025, pero solo el 52.4% en WNBA 2026;
#   - por meses: 2026-05 58.7%, 2026-06 75.6%, 2026-07 35.7%, 2026-08 37.0%
#     -- se invierte a mitad de temporada;
#   - la ventaja del equipo listado primero es estable y negativa en
#     2022/2023/2025 (-0.9 a -4.8 puntos) pero salta de signo en 2026
#     (+0.90 / -0.66 / -0.39 / +3.16).
# NO es un fallo de nuestro mapeo: se verifico evento a evento contra la
# clave directa de la cache y coincide al 100% en todas las ligas y años.
# El mercado de TOTALES no se ve afectado (la suma es simetrica), pero
# ganador (18_1) y handicap (18_2) de este tramo son inutilizables.
# En las ligas 'visitante @ local' (AWAY_FIRST_LEAGUES) NO todas las casas
# publican sus cuotas igual: la mayoria las da con el local de verdad, pero
# BWin y Bet365 las dan siguiendo el orden (invertido) del propio evento de
# BetsAPI, asi que a ESAS hay que intercambiarlas.
#
# Determinado empiricamente con el invariante 'el favorito de cierre gana
# entre el 60% y el 75%', sobre 2625 partidos de NBA y 626 de WNBA:
# Barrido completo sobre NBA+WNBA (22 casas con n>=150): 19 dan 64-70% y tres
# daban ~31% -- BWin, Bet365 y Everygame. Marathonbet daba 51.3%, ni bien ni
# invertida, y va aparte en UNRELIABLE_ODDS_BOOKS.
# En Euroliga (que no es 'visitante @ local') las seis dan 60-66%, correctas.
# Betway no tiene cuotas de ganador en NBA/WNBA, asi que queda sin verificar:
# si aparecen, el test de bball/tests/test_orientacion_cuotas.py lo detectara
# -- ese test barre TODAS las casas, que es como se encontro Everygame.
# Casas cuyas cuotas de ganador/handicap NO son fiables ni intercambiando:
# la orientacion parece mezclada dentro de la propia casa. Medido con el
# mismo invariante del favorito: Marathonbet da NBA 57.5%, WNBA 39.7% y
# Euroliga 59.5%, cuando el resto de casas dan 60-70% en las tres. Queda
# fuera de cualquier analisis de ganador o handicap.
UNRELIABLE_ODDS_BOOKS = {"Marathonbet"}


def book_odds_reliable(book: str | None) -> bool:
    return (book or "") not in UNRELIABLE_ODDS_BOOKS


ODDS_FEED_FOLLOWS_EVENT_ORDER = {"BWin", "Bet365", "Everygame"}


def odds_need_swap(league_name: str | None, book: str | None) -> bool:
    """¿Hay que intercambiar local/visitante en las cuotas de esta casa?"""
    return (swaps_home_away(league_name)
            and (book or "") in ODDS_FEED_FOLLOWS_EVENT_ORDER)


UNRELIABLE_ORIENTATION = [("WNBA", "2026-01-01", "2026-12-31")]


def orientation_is_reliable(league_name: str | None, date: str) -> bool:
    """False si el orden local/visitante de ese partido no es de fiar --
    excluir de cualquier analisis de ganador o handicap."""
    lg = (league_name or "").strip().upper()
    return not any(lg == l.upper() and lo <= date <= hi
                   for l, lo, hi in UNRELIABLE_ORIENTATION)



def swaps_home_away(league_name: str | None) -> bool:
    """True si BetsAPI lista esta liga como 'visitante @ local' y hay que
    intercambiar los campos para que 'home' sea de verdad el local."""
    return (league_name or "").strip().upper() in {n.upper() for n in AWAY_FIRST_LEAGUES}

