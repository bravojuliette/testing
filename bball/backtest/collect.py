"""Collector: descarga partidos terminados + cuotas de totales pre-partido
para un rango de fechas, y los cachea en bball_games/bball_odds. Resumible
como el de tt_elite -- bball_http_cache evita repetir llamadas a dias ya
descargados; los UPSERT hacen que volver a correr el mismo rango sea barato
(no vuelve a pegarle a la red salvo por dias/eventos nuevos)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from datetime import datetime, timezone

from .. import config
from ..sources.betsapi import extract_pre_match_totals, fetch_ended, fetch_odds_summary, parse_score
from ..sources.http_cache import ApiClient


def collect_day(client: ApiClient, conn, league_id: int, day: str, use_cache: bool = True) -> dict:
    events = fetch_ended(client, config.SPORT_ID, str(league_id), day, use_cache=use_cache)
    n_games = 0
    n_with_odds = 0
    n_unresolved = 0
    fetched_at = datetime.now(timezone.utc).isoformat()
    for e in events:
        sc = parse_score(e.get("ss"))
        if not sc:
            n_unresolved += 1
            continue
        eid = str(e.get("id"))
        home = e.get("home") or {}
        away = e.get("away") or {}
        league = e.get("league") or {}
        ts = int(e.get("time") or 0)
        game_date = date.fromtimestamp(ts).isoformat() if ts else day[:4] + "-" + day[4:6] + "-" + day[6:8]
        conn.execute(
            "INSERT INTO bball_games(event_id, sport_id, league_id, league_name, date, time_ts, "
            "home_team, away_team, home_key, away_key, home_score, away_score, completed, raw_json, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?) "
            "ON CONFLICT(event_id) DO UPDATE SET home_score=excluded.home_score, away_score=excluded.away_score, "
            "completed=excluded.completed, raw_json=excluded.raw_json, fetched_at=excluded.fetched_at",
            (eid, str(config.SPORT_ID), str(league_id), league.get("name"), game_date, ts,
             home.get("name"), away.get("name"), str(home.get("id")), str(away.get("id")),
             sc[0], sc[1], json.dumps(e, ensure_ascii=False), fetched_at),
        )
        n_games += 1

        odds_js = fetch_odds_summary(client, eid, use_cache=use_cache)
        rows = extract_pre_match_totals(odds_js, ts)
        if rows:
            # executemany -> UN solo viaje de red a Turso para todas las filas de
            # este partido (hasta ~50, una por casa/snapshot) en vez de uno por
            # fila -- sin esto, la latencia de Turso (no la de BetsAPI) es el
            # cuello de botella real del collect (~10s/partido medido en la
            # primera corrida de prueba).
            conn.executemany(
                "INSERT INTO bball_odds(event_id, book, market, line, over_odds, under_odds, snapshot, captured_at, raw_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(event_id, book, market, line, snapshot) DO UPDATE SET "
                "over_odds=excluded.over_odds, under_odds=excluded.under_odds, captured_at=excluded.captured_at",
                [
                    (eid, r["book"], config.TOTALS_MARKET_KEY, r["line"], r["over_odds"], r["under_odds"],
                     r["snapshot"], r["captured_at"], None)
                    for r in rows
                ],
            )
        if rows:
            n_with_odds += 1
    conn.commit()
    return {"games": n_games, "with_odds": n_with_odds, "unresolved": n_unresolved}


def collect_range(client: ApiClient, conn, league_ids: dict[str, int], start: date, end: date, use_cache: bool = True):
    day = start
    while day <= end:
        day_str = day.strftime("%Y%m%d")
        for name, lid in league_ids.items():
            counts = collect_day(client, conn, lid, day_str, use_cache=use_cache)
            print(f"{day.isoformat()} {name}: {counts}", flush=True)
        day += timedelta(days=1)
