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
        # En NBA/WNBA BetsAPI lista "visitante @ local": su 'home' es el
        # visitante real. Se normaliza aqui para que en bball_games 'home'
        # signifique siempre el equipo que juega en casa (ver config.py).
        if config.swaps_home_away(league.get("name")):
            home, away = away, home
            sc = (sc[1], sc[0])
        ts = int(e.get("time") or 0)
        # UTC explicito -- date.fromtimestamp() NO acepta tz (solo
        # datetime.fromtimestamp() lo acepta); sin esto usa la zona horaria
        # local del proceso, que en GitHub Actions es UTC pero en cualquier
        # otro entorno puede no serlo. bball_picks (live/scan.py) ya calcula
        # esta misma fecha en UTC; con date local aqui, un partido cerca de
        # medianoche UTC podia terminar en dias distintos segun donde
        # corriera, descuadrando el corte busqueda/reserva de sweep.py
        # (compara p.date como string). Atrapado por bball/tests/test_collect.py.
        game_date = (
            datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
            if ts else day[:4] + "-" + day[4:6] + "-" + day[6:8]
        )
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


def reparse_kickoff(conn, batch: int = 100) -> dict:
    """Re-extrae de bball_http_cache el snapshot 'kickoff' (cuota al pitido
    inicial = linea de CIERRE real) que el parser original ignoraba -- sin
    una sola llamada nueva a BetsAPI. La respuesta de odds/summary no trae
    el event_id, asi que cada body se mapea a su partido por huella digital:
    sus entradas 'start' (book, add_time, linea) deben coincidir con las
    filas snapshot='start' que ya guardamos para ese evento. Se exige
    coincidencia mayoritaria (>=2 casas, o candidato unico) para no upsertar
    cuotas en el partido equivocado."""
    ts_by_event = {
        r["event_id"]: r["time_ts"]
        for r in conn.execute("SELECT event_id, time_ts FROM bball_games").fetchall()
    }
    fp_index: dict[tuple, set] = {}
    for r in conn.execute(
        "SELECT event_id, book, line, captured_at FROM bball_odds "
        "WHERE market = ? AND snapshot = 'start' AND captured_at IS NOT NULL",
        (config.TOTALS_MARKET_KEY,),
    ).fetchall():
        fp = (r["book"], str(r["captured_at"]), float(r["line"]))
        fp_index.setdefault(fp, set()).add(r["event_id"])

    stats = {"bodies": 0, "mapped": 0, "ambiguous": 0, "kickoff_rows": 0}
    offset = 0
    while True:
        rows = conn.execute(
            "SELECT body FROM bball_http_cache WHERE prefix='odds_summary' "
            "LIMIT ? OFFSET ?", (batch, offset),
        ).fetchall()
        if not rows:
            break
        offset += len(rows)
        for row in rows:
            stats["bodies"] += 1
            try:
                js = json.loads(row["body"])
            except (TypeError, ValueError):
                continue
            votes: dict[str, int] = {}
            for book, b in (js.get("results") or {}).items():
                if not isinstance(b, dict):
                    continue
                entry = ((b.get("odds") or {}).get("start") or {}).get(config.TOTALS_MARKET_KEY)
                if not isinstance(entry, dict) or entry.get("add_time") is None:
                    continue
                try:
                    fp = (book, str(int(entry["add_time"])), float(entry["handicap"]))
                except (KeyError, TypeError, ValueError):
                    continue
                for eid in fp_index.get(fp, ()):
                    votes[eid] = votes.get(eid, 0) + 1
            if not votes:
                continue
            ranked = sorted(votes.items(), key=lambda kv: -kv[1])
            eid, top = ranked[0]
            second = ranked[1][1] if len(ranked) > 1 else 0
            if (top < 2 and len(ranked) > 1) or top == second:
                stats["ambiguous"] += 1
                continue
            ts = ts_by_event.get(eid)
            if ts is None:
                continue
            stats["mapped"] += 1
            kicks = [r for r in extract_pre_match_totals(js, ts) if r["snapshot"] == "kickoff"]
            if kicks:
                conn.executemany(
                    "INSERT INTO bball_odds(event_id, book, market, line, over_odds, under_odds, snapshot, captured_at, raw_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(event_id, book, market, line, snapshot) DO UPDATE SET "
                    "over_odds=excluded.over_odds, under_odds=excluded.under_odds, captured_at=excluded.captured_at",
                    [
                        (eid, k["book"], config.TOTALS_MARKET_KEY, k["line"], k["over_odds"],
                         k["under_odds"], "kickoff", k["captured_at"], None)
                        for k in kicks
                    ],
                )
                stats["kickoff_rows"] += len(kicks)
        conn.commit()
        print(f"  procesados {stats['bodies']} bodies -- mapeados {stats['mapped']}, "
              f"filas kickoff {stats['kickoff_rows']}", flush=True)
    return stats


def fix_home_away(conn) -> dict:
    """Migracion de una sola vez: intercambia local/visitante en las filas ya
    guardadas de las ligas que BetsAPI lista como 'visitante @ local'
    (config.AWAY_FIRST_LEAGUES). Es NO idempotente por naturaleza -- correrla
    dos veces volveria a invertir -- asi que deja una marca en bball_meta y se
    niega a repetirse. El mercado de totales (18_3) es simetrico y no se toca."""
    marker = conn.execute(
        "SELECT value FROM bball_meta WHERE key = 'home_away_normalized'"
    ).fetchone()
    if marker and marker["value"] == "1":
        return {"skipped": "ya normalizado"}

    names = sorted(config.AWAY_FIRST_LEAGUES)
    placeholders = ",".join("?" for _ in names)
    out = {}
    for table, cols in (
        ("bball_games", [("home_team", "away_team"), ("home_key", "away_key"),
                         ("home_score", "away_score")]),
        ("bball_picks", [("home_team", "away_team")]),
    ):
        try:
            # SQLite/Turso evaluan el SET con los valores ORIGINALES de la
            # fila, asi que el intercambio directo a = b, b = a es seguro.
            sets = ", ".join(f"{a} = {b}, {b} = {a}" for a, b in cols)
            cur = conn.execute(
                f"UPDATE {table} SET {sets} WHERE UPPER(league_name) IN ({placeholders})",
                [n.upper() for n in names],
            )
            out[table] = getattr(cur, "rowcount", None)
        except Exception as exc:  # tabla puede no existir todavia
            out[table] = f"omitida ({exc})"

    conn.execute(
        "INSERT INTO bball_meta(key, value) VALUES ('home_away_normalized', '1') "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    )
    conn.commit()
    return out
