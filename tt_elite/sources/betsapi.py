"""Cliente BetsAPI: resultados terminados/en vivo/proximos + cuotas de apertura.

Endpoints usados (los mismos que ya usaban tu Apps Script v7.1 y el backtest
Colab v5): /v3/events/ended, /v3/events/inplay, /v3/events/upcoming,
/v2/event/odds/summary.
"""
from __future__ import annotations

from datetime import date

from .. import config
from ..textutil import book_norm, parse_score, strong_name
from .http_cache import ApiClient


def fetch_ended(client: ApiClient, d: date, use_cache: bool = True) -> list[dict]:
    all_rows: list[dict] = []
    page = 1
    while True:
        js = client.bets(
            "/v3/events/ended",
            {"sport_id": config.SPORT_ID, "league_id": config.LEAGUE_ID, "day": d.strftime("%Y%m%d"), "page": page},
            prefix="ended", use_cache=use_cache,
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


def fetch_inplay(client: ApiClient) -> list[dict]:
    js = client.bets(
        "/v3/events/inplay", {"sport_id": config.SPORT_ID}, prefix="inplay", use_cache=False,
    )
    rows = js.get("results") or []
    league_ids = {str(config.LEAGUE_ID)}
    return [e for e in rows if str((e.get("league") or {}).get("id")) in league_ids]


def search_events_by_player(client: ApiClient, query: str, max_pages: int = 15) -> list[dict]:
    """Busca en /v3/events/upcoming (sport_id=92, SIN restringir a config.LEAGUE_ID)
    eventos cuyo home/away contenga `query` (case-insensitive). Pensado para
    descubrir el league_id real de un circuito nuevo (p.ej. otra liga de tenis
    de mesa en el mismo bookmaker) a partir de un nombre de jugador que veas en
    una casa de apuestas -- no para uso normal del scanner, que ya conoce su
    LEAGUE_ID. Cada evento devuelto trae su propio 'league': {'id', 'name'}."""
    q = query.lower()
    found: list[dict] = []
    for page in range(1, max_pages + 1):
        js = client.bets(
            "/v3/events/upcoming", {"sport_id": config.SPORT_ID, "page": page},
            prefix="discover_upcoming", use_cache=False,
        )
        rows = js.get("results") or []
        if not rows:
            break
        for e in rows:
            home = (e.get("home") or {}).get("name", "")
            away = (e.get("away") or {}).get("name", "")
            if q in home.lower() or q in away.lower():
                found.append(e)
        pager = js.get("pager") or {}
        total = int(pager.get("total") or 0)
        if page * len(rows) >= total:
            break
    return found


def fetch_upcoming(client: ApiClient, max_pages: int = 3) -> list[dict]:
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        js = client.bets(
            "/v3/events/upcoming",
            {"sport_id": config.SPORT_ID, "league_id": config.LEAGUE_ID, "page": page},
            prefix="upcoming", use_cache=False,
        )
        rows = js.get("results") or []
        out.extend(rows)
        pager = js.get("pager") or {}
        total = int(pager.get("total") or len(out))
        if not rows or len(out) >= total:
            break
    return out


def event_match(candidate_p1: str, candidate_p2: str, candidate_ts: int, e: dict) -> bool:
    home = (e.get("home") or {}).get("name", "")
    away = (e.get("away") or {}).get("name", "")
    direct = strong_name(home, candidate_p1) and strong_name(away, candidate_p2)
    reverse = strong_name(home, candidate_p2) and strong_name(away, candidate_p1)
    if not (direct or reverse):
        return False
    if not e.get("time"):
        return True
    return abs(int(e["time"]) - candidate_ts) <= config.EVENT_TIME_TOL_MIN * 60


def find_event(candidate_p1: str, candidate_p2: str, candidate_ts: int, events: list[dict]) -> dict | None:
    xs = [e for e in events if event_match(candidate_p1, candidate_p2, candidate_ts, e)]
    if not xs:
        return None
    return min(xs, key=lambda e: abs(int(e.get("time", 0)) - candidate_ts))


def best_opening_line(client: ApiClient, event: dict, use_cache: bool = True) -> dict | None:
    """Primera cuota disponible en la cadena de bookmakers (config.BOOKS), orientada
    home/away tal cual la entrega BetsAPI (el llamador la reorienta a p1/p2)."""
    js = client.bets("/v2/event/odds/summary", {"event_id": event["id"]}, prefix="odds_summary", use_cache=use_cache)
    results = js.get("results") or {}
    lookup = {book_norm(k): k for k in results}

    for source, label, is_fallback in config.BOOKS:
        candidates = [book_norm(source), book_norm(label)]
        k = next((lookup[x] for x in candidates if x in lookup), None)
        if not k:
            continue
        b = results[k] or {}
        start = (b.get("odds") or {}).get("start") or {}
        market = start.get(config.MARKET_KEY)
        if not market:
            market = next((v for kk, v in start.items() if str(kk).endswith("_1") and isinstance(v, dict)), None)
        if not market:
            continue
        try:
            h = float(market.get("home_od"))
            a = float(market.get("away_od"))
        except (TypeError, ValueError):
            continue
        try:
            draw = float(market.get("draw_od") or 0)
        except (TypeError, ValueError):
            draw = 0
        if not (h > 1 and a > 1) or draw > 1.01:
            continue
        add = int(float(market.get("add_time") or 0))
        ev_start = int(event.get("time") or 0)
        if add and ev_start and add >= ev_start:
            continue
        if int(b.get("matching_dir") or 1) == -1:
            h, a = a, h
        inv1, inv2 = 1 / h, 1 / a
        total = inv1 + inv2
        return {
            "event_id": str(event["id"]), "book": label, "source": source, "fallback": is_fallback,
            "odds1": h, "odds2": a, "mp1": inv1 / total, "mp2": inv2 / total,
            "add_time": add, "quality": "SUMMARY_OPENING",
        }
    return None


def current_best_line(client: ApiClient, event: dict) -> dict | None:
    """Como best_opening_line, pero toma el snapshot de cuota MAS RECIENTE (no la
    de apertura) -- lo que se usa en el scanner en vivo para decidir ahora mismo."""
    js = client.bets("/v2/event/odds/summary", {"event_id": event["id"]}, prefix="odds_summary", use_cache=False)
    results = js.get("results") or {}
    lookup = {book_norm(k): k for k in results}

    for source, label, is_fallback in config.BOOKS:
        candidates = [book_norm(source), book_norm(label)]
        k = next((lookup[x] for x in candidates if x in lookup), None)
        if not k:
            continue
        b = results[k] or {}
        odds_by_ts = (b.get("odds") or {})
        ts_keys = sorted((kk for kk in odds_by_ts if kk != "start" and str(kk).isdigit()), key=lambda x: int(x), reverse=True)
        ordered_keys = ts_keys + (["start"] if "start" in odds_by_ts else [])
        market = None
        for tk in ordered_keys:
            entry = odds_by_ts.get(tk) or {}
            market = entry.get(config.MARKET_KEY)
            if not market:
                market = next((v for kk, v in entry.items() if str(kk).endswith("_1") and isinstance(v, dict)), None)
            if market:
                break
        if not market:
            continue
        try:
            h = float(market.get("home_od"))
            a = float(market.get("away_od"))
        except (TypeError, ValueError):
            continue
        try:
            draw = float(market.get("draw_od") or 0)
        except (TypeError, ValueError):
            draw = 0
        if not (h > 1 and a > 1) or draw > 1.01:
            continue
        if int(b.get("matching_dir") or 1) == -1:
            h, a = a, h
        inv1, inv2 = 1 / h, 1 / a
        total = inv1 + inv2
        return {
            "event_id": str(event["id"]), "book": label, "source": source, "fallback": is_fallback,
            "odds1": h, "odds2": a, "mp1": inv1 / total, "mp2": inv2 / total,
            "add_time": None, "quality": "SUMMARY_CURRENT",
        }
    return None


def mark_inplay(sessions: list[dict], inplay_events: list[dict]) -> int:
    """Marca m['inplay']=True para partidos aun no completados que BetsAPI ya ve
    en juego -- se excluyen de la busqueda de candidatos "por empezar"."""
    marked = 0
    for sess in sessions:
        for m in sess["schedule"]:
            if m["completed"]:
                continue
            ts = int(m["dt"].timestamp()) if m.get("dt") else 0
            e = find_event(m["p1"], m["p2"], ts, inplay_events)
            if e:
                m["inplay"] = True
                marked += 1
    return marked


def fill_missing_results_from_events(sessions: list[dict], events: list[dict]) -> tuple[int, int]:
    """Rellena RESULT en blanco de TT-Series con resultados terminados de BetsAPI.
    Devuelve (rellenados, sin_resolver)."""
    filled = 0
    unresolved = 0
    for sess in sessions:
        for m in sess["schedule"]:
            if m["completed"]:
                continue
            ts = int(m["dt"].timestamp())
            e = find_event(m["p1"], m["p2"], ts, events)
            sc = parse_score(e.get("ss") if e else "")
            if sc:
                home = (e.get("home") or {}).get("name", "")
                away = (e.get("away") or {}).get("name", "")
                if strong_name(home, m["p1"]) and strong_name(away, m["p2"]):
                    s1, s2 = sc
                elif strong_name(home, m["p2"]) and strong_name(away, m["p1"]):
                    s1, s2 = sc[1], sc[0]
                else:
                    unresolved += 1
                    continue
                m["s1"], m["s2"], m["completed"] = s1, s2, True
                m["result_source"] = "BetsAPI ended"
                filled += 1
            else:
                unresolved += 1
    return filled, unresolved
