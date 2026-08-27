"""Cliente BetsAPI para basketball -- exploratorio a proposito: no conocemos
todavia (bloqueado el acceso a la documentacion desde este entorno, ver
notas de la sesion) el sport_id exacto de basketball en BetsAPI, los
league_id de NBA/WNBA/Euroliga, ni la forma real del mercado de "total de
puntos" (una linea, o varias lineas alternativas con su propia cuota). Estas
funciones estan pensadas para descubrir eso contra datos reales (vía
GitHub Actions, que sí tiene salida a internet) antes de fijar nada.
"""
from __future__ import annotations

from .. import config
from .http_cache import ApiClient

# Candidatos de sport_id a probar en discover_leagues. BetsAPI numera sus
# sport_id por orden de incorporacion historica -- tt_elite ya establecio que
# tenis de mesa es 92 (un deporte nicho, ID alto); basketball es un deporte
# mayor y debería tener un ID bajo, pero no lo damos por sentado: se prueba
# un rango amplio y se deja que los datos reales decidan.
DEFAULT_SPORT_ID_CANDIDATES = list(range(1, 41))

# Substrings (case-insensitive) que esperamos ver en el nombre de liga que
# devuelve BetsAPI para basketball de interes. Los nombres de liga en BetsAPI
# suelen tener forma "PAIS - Competicion", p.ej. "USA - NBA".
DEFAULT_LEAGUE_KEYWORDS = {
    "nba": "NBA",
    "wnba": "WNBA",
    "euroleague": "EUROLEAGUE",
    "euroliga": "EUROLEAGUE",
    "eurocup": "EUROCUP",
    " acb": "ACB",
    "basketball": "BASKETBALL_OTHER",
}


def probe_sport_upcoming(client: ApiClient, sport_id: int, use_cache: bool = False) -> list[dict]:
    """Una sola pagina de /v3/events/upcoming para un sport_id candidato --
    barato, solo para ver que hay ahi (no pretende ser exhaustivo)."""
    js = client.bets(
        "/v3/events/upcoming", {"sport_id": sport_id, "page": 1},
        prefix=f"probe_upcoming_{sport_id}", use_cache=use_cache,
    )
    return js.get("results") or []


def discover_leagues(client: ApiClient, sport_ids=None, keywords=None) -> list[dict]:
    """Prueba cada sport_id candidato contra /v3/events/upcoming y se queda
    con los eventos cuyo nombre de liga matchea alguna de las keywords.
    Devuelve una fila por (sport_id, league_id) distinto encontrado, con un
    evento de muestra para poder verificar a ojo."""
    sport_ids = sport_ids if sport_ids is not None else DEFAULT_SPORT_ID_CANDIDATES
    keywords = keywords if keywords is not None else DEFAULT_LEAGUE_KEYWORDS

    seen: dict[tuple[str, str], dict] = {}
    for sid in sport_ids:
        try:
            events = probe_sport_upcoming(client, sid)
        except RuntimeError as exc:
            print(f"[discover_leagues] sport_id={sid}: {exc}", flush=True)
            continue
        if not events:
            continue
        print(f"[discover_leagues] sport_id={sid}: {len(events)} eventos en /v3/events/upcoming pagina 1", flush=True)
        for e in events:
            league = e.get("league") or {}
            lname = str(league.get("name") or "")
            lname_low = lname.lower()
            tag = next((t for kw, t in keywords.items() if kw in lname_low), None)
            if not tag:
                continue
            key = (str(sid), str(league.get("id")))
            if key not in seen:
                home = (e.get("home") or {}).get("name", "")
                away = (e.get("away") or {}).get("name", "")
                seen[key] = {
                    "sport_id": str(sid),
                    "league_id": str(league.get("id")),
                    "league_name": lname,
                    "tag": tag,
                    "sample_home": home,
                    "sample_away": away,
                    "sample_event_id": str(e.get("id")),
                }
    return list(seen.values())


def fetch_ended_all_leagues(client: ApiClient, sport_id: int, day: str, use_cache: bool = True, max_pages: int = 20) -> list[dict]:
    """Como fetch_ended(), pero SIN league_id -- /v3/events/ended lo acepta
    opcional y devuelve partidos de TODAS las ligas de ese sport_id ese dia.
    Pensado para descubrir league_id de NBA/Euroliga/etc en un dia de
    temporada real, igual que discover_leagues() hace con /v3/events/upcoming
    para lo que hay ahora mismo."""
    all_rows: list[dict] = []
    page = 1
    while page <= max_pages:
        js = client.bets(
            "/v3/events/ended",
            {"sport_id": sport_id, "day": day, "page": page},
            prefix=f"ended_all_{sport_id}", use_cache=use_cache,
        )
        rows = js.get("results") or []
        all_rows.extend(rows)
        pager = js.get("pager") or {}
        total = int(pager.get("total") or len(all_rows))
        per = int(pager.get("per_page") or 50)
        if not rows or len(all_rows) >= total or len(rows) < per:
            break
        page += 1
    return all_rows


def parse_score(ss: str | None) -> tuple[int, int] | None:
    """'111-118' -> (111, 118). BetsAPI ya da el marcador final total (incluye
    prorrogas si las hubo) en este campo para basketball -- confirmado
    empiricamente, no hay sufijos de periodo en `ss`."""
    if not ss or "-" not in ss:
        return None
    a, _, b = ss.partition("-")
    try:
        return int(a), int(b)
    except ValueError:
        return None


def fetch_odds_summary(client: ApiClient, event_id: str, use_cache: bool = True) -> dict:
    return client.bets("/v2/event/odds/summary", {"event_id": event_id}, prefix="odds_summary", use_cache=use_cache)


def extract_pre_match_totals(odds_js: dict, event_start_ts: int) -> list[dict]:
    """De la respuesta de /v2/event/odds/summary, saca UNA fila por
    (bookmaker, snapshot) para el mercado de totales (config.TOTALS_MARKET_KEY),
    descartando cualquier snapshot cuyo add_time sea posterior al inicio del
    partido -- evita fuga de informacion (cuota ya afectada por el partido en
    curso), mismo criterio que ya usa tt_elite/sources/betsapi.py
    (best_opening_line: 'if add and ev_start and add >= ev_start: continue').
    Puede haber dos filas por casa (start y end) si ambas son pre-partido."""
    results = odds_js.get("results") or {}
    out: list[dict] = []
    if not isinstance(results, dict):
        return out
    for book, b in results.items():
        if not isinstance(b, dict):
            continue
        odds = b.get("odds") or {}
        for snapshot in ("start", "end"):
            entry = (odds.get(snapshot) or {}).get(config.TOTALS_MARKET_KEY)
            if not isinstance(entry, dict):
                continue
            try:
                line = float(entry["handicap"])
                over_od = float(entry["over_od"])
                under_od = float(entry["under_od"])
            except (KeyError, TypeError, ValueError):
                continue
            add_time = entry.get("add_time")
            try:
                add_time_i = int(add_time) if add_time is not None else None
            except (TypeError, ValueError):
                add_time_i = None
            if add_time_i is not None and event_start_ts and add_time_i >= event_start_ts:
                continue  # ya en juego o posterior -- descartado
            out.append({
                "book": book, "snapshot": snapshot, "line": line,
                "over_odds": over_od, "under_odds": under_od,
                "captured_at": add_time_i,
            })
    return out


def fetch_ended(client: ApiClient, sport_id: int, league_id: str, day: str, use_cache: bool = True) -> list[dict]:
    """Partidos terminados de una liga en un dia dado (YYYYMMDD). Pagina
    igual que tt_elite/sources/betsapi.py: sigue mientras haya paginas."""
    all_rows: list[dict] = []
    page = 1
    while True:
        js = client.bets(
            "/v3/events/ended",
            {"sport_id": sport_id, "league_id": league_id, "day": day, "page": page},
            prefix=f"ended_{sport_id}_{league_id}", use_cache=use_cache,
        )
        rows = js.get("results") or []
        all_rows.extend(rows)
        pager = js.get("pager") or {}
        total = int(pager.get("total") or len(all_rows))
        per = int(pager.get("per_page") or 50)
        if not rows or len(all_rows) >= total or len(rows) < per:
            break
        page += 1
    return all_rows
