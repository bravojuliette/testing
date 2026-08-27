"""Scanner en vivo de basketball: una pasada = (1) recolecta resultados de
ayer/hoy para las ligas activas (asienta bball_games con lo recien
terminado), (2) liquida picks PENDING cuyo partido ya tiene marcador final,
(3) busca partidos que arrancan pronto, calcula la señal con la estrategia
activa (bball/live/active.py) y guarda los que cumplan el umbral como picks
nuevos.

Pensado para correr cada 10-15 min via GitHub Actions (ver
.github/workflows/bball_live_scan.yml) o `python -m bball.cli scan` en local.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .. import config
from .. import db as dbmod
from ..backtest.collect import collect_day
from ..sources.betsapi import extract_pre_match_totals, fetch_odds_summary
from ..sources.http_cache import ApiClient
from .active import load_active_params, params_label


def fetch_upcoming(client: ApiClient, league_id: int, max_pages: int = 3) -> list[dict]:
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        js = client.bets(
            "/v3/events/upcoming", {"sport_id": config.SPORT_ID, "league_id": league_id, "page": page},
            prefix=f"upcoming_{league_id}", use_cache=False,
        )
        rows = js.get("results") or []
        out.extend(rows)
        pager = js.get("pager") or {}
        total = int(pager.get("total") or len(out))
        if not rows or len(out) >= total:
            break
    return out


def _team_recent_pf(conn, team_key: str, before_ts: int, n: int) -> float | None:
    """Media de puntos anotados por `team_key` en sus ultimos `n` partidos
    COMPLETADOS con time_ts < before_ts -- nunca el propio partido ni
    ninguno posterior. None si todavia no hay `n` partidos previos."""
    rows = conn.execute(
        """SELECT CASE WHEN home_key = :tk THEN home_score ELSE away_score END as pf
           FROM bball_games
           WHERE completed = 1 AND (home_key = :tk OR away_key = :tk) AND time_ts < :before_ts
           ORDER BY time_ts DESC LIMIT :n""",
        {"tk": team_key, "before_ts": before_ts, "n": n},
    ).fetchall()
    if len(rows) < n:
        return None
    return sum(r["pf"] for r in rows) / n


def _settle_pending(conn) -> int:
    rows = conn.execute(
        """SELECT p.id, p.line, p.under_odds, g.home_score, g.away_score
           FROM bball_picks p JOIN bball_games g ON p.event_id = g.event_id
           WHERE p.result = 'PENDING' AND g.completed = 1"""
    ).fetchall()
    n = 0
    for r in rows:
        final_total = r["home_score"] + r["away_score"]
        if final_total < r["line"]:
            result, pnl = "WIN", r["under_odds"] - 1
        elif final_total > r["line"]:
            result, pnl = "LOSS", -1.0
        else:
            result, pnl = "PUSH", 0.0
        conn.execute(
            "UPDATE bball_picks SET result = :result, pnl_1u = :pnl, final_total = :ft WHERE id = :id",
            {"result": result, "pnl": pnl, "ft": final_total, "id": r["id"]},
        )
        n += 1
    return n


def run_live_scan(db_path=None) -> dict:
    summary = {"games_collected": 0, "settled": 0, "upcoming_seen": 0, "candidates": 0, "new_picks": 0}

    with dbmod.get_conn(db_path) as conn:
        client = ApiClient(conn, config.BETSAPI_TOKEN)
        params = load_active_params(conn)
        n_window = int(params["n_window"])
        threshold = float(params["threshold"])
        league_names = list(params["leagues"])
        book_filter = params.get("book")  # None = mejor cuota entre todas; si no, restringe a una sola casa
        strategy_label = params_label(params)
        print(f"[scan] estrategia activa: {strategy_label}", flush=True)

        today = datetime.now(timezone.utc).date()
        # "ayer" ya esta cerrado -- una vez cacheado (primera pasada del dia
        # que lo ve), no vuelve a cambiar, asi que usa cache normal. Solo "hoy"
        # necesita use_cache=False (partidos terminando a cada rato). Sin esta
        # distincion, cada pasada (cada 10-15 min) volvia a pegarle a BetsAPI
        # por CADA partido de ayer para siempre, aunque ya estuviera liquidado.
        for d, use_cache in ((today - timedelta(days=1), True), (today, False)):
            for name in league_names:
                counts = collect_day(client, conn, config.LEAGUES[name], d.strftime("%Y%m%d"), use_cache=use_cache)
                summary["games_collected"] += counts["games"]

        summary["settled"] = _settle_pending(conn)
        conn.commit()

        created_at = datetime.now(timezone.utc).isoformat()
        for name in league_names:
            events = fetch_upcoming(client, config.LEAGUES[name])
            summary["upcoming_seen"] += len(events)
            for e in events:
                eid = str(e.get("id"))
                ts = int(e.get("time") or 0)
                if not ts:
                    continue
                home = e.get("home") or {}
                away = e.get("away") or {}
                home_key, away_key = str(home.get("id")), str(away.get("id"))

                avg_home = _team_recent_pf(conn, home_key, ts, n_window)
                avg_away = _team_recent_pf(conn, away_key, ts, n_window)
                if avg_home is None or avg_away is None:
                    continue  # todavia no hay N partidos previos de alguno de los dos en los datos ya cargados
                exp_total = avg_home + avg_away

                odds_js = fetch_odds_summary(client, eid, use_cache=False)
                qualifying = [
                    r for r in extract_pre_match_totals(odds_js, ts)
                    if (r["line"] - exp_total) >= threshold and (not book_filter or r["book"] == book_filter)
                ]
                if not qualifying:
                    continue
                summary["candidates"] += 1
                # Mismo desempate deterministico que backtest/replay.py: a
                # igual cuota, la linea mas alta (mas colchon al mismo precio).
                best = max(qualifying, key=lambda r: (r["under_odds"], r["line"]))

                pick_id = f"live|{eid}"
                existing = conn.execute("SELECT id FROM bball_picks WHERE id = :id", {"id": pick_id}).fetchone()
                conn.execute(
                    """INSERT INTO bball_picks
                       (id, source, params_hash, created_at, event_id, league_name, date, time_ts,
                        home_team, away_team, exp_total, book, line, under_odds, cushion, result)
                       VALUES (:id, 'live', :params_hash, :created_at, :event_id, :league_name, :date, :time_ts,
                               :home_team, :away_team, :exp_total, :book, :line, :under_odds, :cushion, 'PENDING')
                       ON CONFLICT(id) DO UPDATE SET
                         book = excluded.book, line = excluded.line, under_odds = excluded.under_odds,
                         cushion = excluded.cushion, exp_total = excluded.exp_total""",
                    {
                        "id": pick_id, "params_hash": strategy_label, "created_at": created_at,
                        "event_id": eid, "league_name": name, "date": date.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                        "time_ts": ts, "home_team": home.get("name"), "away_team": away.get("name"),
                        "exp_total": exp_total, "book": best["book"], "line": best["line"],
                        "under_odds": best["under_odds"], "cushion": best["line"] - exp_total,
                    },
                )
                if not existing:
                    summary["new_picks"] += 1

        conn.commit()

    return summary
