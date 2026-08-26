"""Job del scanner en vivo: una pasada = revisar sesiones de hoy, actualizar
Elo/H2H persistente, evaluar candidatos elegibles contra la estrategia activa,
guardar picks y mandar email si hay algo nuevo accionable.

Pensado para correr cada 5-15 min via GitHub Actions (ver
.github/workflows/live_scan.yml) o cron local: `python -m tt_elite.cli scan`.
"""
from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timedelta, timezone

from .. import config
from .. import db as dbmod
from ..backtest.collect import _upsert_match
from ..model.active import load_active_params
from ..model.elo import compute_model, update_rolling
from ..model.strategy import evaluate_pick
from ..notify.email import render_picks_email, send_email
from ..sources.betsapi import (
    current_best_line, fetch_ended, fetch_inplay, fetch_upcoming,
    fill_missing_results_from_events, find_event, mark_inplay,
)
from ..sources.http_cache import ApiClient
from ..sources.tt_series import load_sessions_for_date, title_date
from ..textutil import strong_name


def _load_elo_state(conn) -> dict[str, float]:
    return {r["player_key"]: r["elo"] for r in conn.execute("SELECT player_key, elo FROM elo_state")}


def _save_elo_state(conn, elo: dict[str, float], names: dict[str, str]) -> None:
    if not elo:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        """INSERT INTO elo_state(player_key, player_name, elo, updated_at) VALUES (?,?,?,?)
           ON CONFLICT(player_key) DO UPDATE SET elo=excluded.elo, updated_at=excluded.updated_at,
             player_name=COALESCE(excluded.player_name, elo_state.player_name)""",
        [(k, names.get(k), v, now) for k, v in elo.items()],
    )


def _load_h2h_state(conn, maxlen: int) -> dict[str, deque]:
    out = {}
    for r in conn.execute("SELECT pair_key, history_json FROM h2h_state"):
        out[r["pair_key"]] = deque(json.loads(r["history_json"]), maxlen=maxlen)
    return out


def _save_h2h_state(conn, h2h: dict[str, deque]) -> None:
    if not h2h:
        return
    conn.executemany(
        """INSERT INTO h2h_state(pair_key, history_json) VALUES (?,?)
           ON CONFLICT(pair_key) DO UPDATE SET history_json=excluded.history_json""",
        [(k, json.dumps(list(arr))) for k, arr in h2h.items()],
    )


def _load_career_state(conn) -> tuple[dict[str, int], dict[str, int]]:
    played: dict[str, int] = {}
    wins: dict[str, int] = {}
    for r in conn.execute("SELECT player_key, played, wins FROM career_state"):
        played[r["player_key"]] = r["played"]
        wins[r["player_key"]] = r["wins"]
    return played, wins


def _save_career_state(conn, career_played: dict[str, int], career_wins: dict[str, int]) -> None:
    if not career_played:
        return
    conn.executemany(
        """INSERT INTO career_state(player_key, played, wins) VALUES (?,?,?)
           ON CONFLICT(player_key) DO UPDATE SET played=excluded.played, wins=excluded.wins""",
        [(k, played, career_wins.get(k, 0)) for k, played in career_played.items()],
    )


def run_live_scan(db_path=None, *, dry_run_email: bool = False) -> dict:
    now = datetime.now(config.TZ)
    today = now.date()

    summary = {
        "sessions": 0, "candidates": 0, "new_picks": 0, "emailed": 0, "results_updated": 0,
        # Diagnostico (2026-08-26): visibilidad directa de cuantos partidos
        # de hoy/ayer estan completados vs pendientes en esta pasada, para
        # distinguir "no hay nada que evaluar todavia" (dia ya cerrado o muy
        # al principio) de un fallo real en la carga de datos sin tener que
        # ir a mirar http_cache a mano cada vez.
        "matches_seen": 0, "matches_completed": 0, "matches_pending": 0,
    }

    with dbmod.get_conn(db_path) as conn:
        params = load_active_params(conn)
        client = ApiClient(conn, config.BETSAPI_TOKEN)

        # use_cache=False: "hoy"/"ayer" siguen editandose en TT-Series segun
        # se cierran partidos, pero la URL/parametros de la consulta no
        # cambian en todo el dia -- con la cache por defecto (pensada para
        # backfill de dias YA cerrados) el scanner se quedaba pegado a la
        # foto de la primera vez que la pidio ese dia y nunca veia partidos
        # nuevos como completados (candidates=0 durante horas, bug real del
        # 2026-08-26 -- ver tt_series.tt_posts_for_date).
        sessions = []
        for d in (today - timedelta(days=1), today):
            sessions.extend(load_sessions_for_date(client, d, use_cache=False))
        summary["sessions"] = len(sessions)
        all_matches = [m for s in sessions for m in s["schedule"]]
        summary["matches_seen"] = len(all_matches)
        summary["matches_completed"] = sum(1 for m in all_matches if m["completed"])
        summary["matches_pending"] = summary["matches_seen"] - summary["matches_completed"]
        if not sessions:
            return summary

        # fetch_inplay no es critico (solo sirve para excluir partidos ya
        # empezados de los candidatos y como pool extra para localizar cuotas):
        # si BetsAPI falla en ESTE endpoint concreto (visto en produccion: 500
        # con cuerpo vacio, mientras /v3/events/ended respondia normal -- ver
        # EXPERIMENTS_LOG.md), no tiene sentido tirar todo el scan por eso.
        # Se sigue sin marcar partidos en vivo en vez de perder la pasada entera.
        try:
            inplay_events = fetch_inplay(client)
        except Exception as exc:
            print(f"[scan] fetch_inplay fallo, se continua sin marcar partidos en vivo: {exc}", flush=True)
            inplay_events = []
        # Mismo patron que fetch_inplay: se ha visto en produccion que
        # /v3/events/ended tambien puede devolver 500 con cuerpo vacio para un
        # dia concreto (el "manana" de este bucle estructuralmente casi siempre
        # esta vacio -- ningun partido puede haber terminado todavia -- y un dia
        # que aun no cerro del todo puede tener el mismo problema). Solo rellena
        # resultados que faltan de TT-Series (fill_missing_results_from_events)
        # y marca partidos en vivo -- no es critico, asi que un fallo en UN dia
        # no debe tirar la pasada entera; se sigue sin ese dia.
        ended_events = []
        for d in (today - timedelta(days=1), today, today + timedelta(days=1)):
            try:
                ended_events.extend(fetch_ended(client, d, use_cache=False))
            except Exception as exc:
                print(f"[scan] fetch_ended({d}) fallo, se continua sin ese dia: {exc}", flush=True)
        by_id = {str(e.get("id")): e for e in ended_events if e.get("id")}
        ended_events = list(by_id.values())

        fill_missing_results_from_events(sessions, ended_events)
        mark_inplay(sessions, inplay_events)

        # Persistir todos los partidos de hoy (completos o no) en raw_matches.
        # match_uid queda identico al que usaria un `collect` posterior de este
        # mismo dia, asi que el historico "en vivo" se reutiliza directo en backtest.
        uid_map: dict[str, tuple[dict, dict]] = {}
        for sess in sessions:
            day = title_date(sess, today)
            for m in sess["schedule"]:
                uid = _upsert_match(conn, sess, m, day)
                m["uid"] = uid
                uid_map[uid] = (sess, m)
        conn.commit()

        # Partidos ya plegados al Elo/H2H persistente en una corrida anterior
        # -- nunca se vuelven a aplicar (evitaria inflar el rating cada scan).
        applied_uids = {r["match_uid"] for r in conn.execute("SELECT match_uid FROM raw_matches WHERE elo_applied = 1")}
        newly_applied: list[str] = []

        elo = _load_elo_state(conn)
        h2h = _load_h2h_state(conn, params.h2h_max_matches)
        career_played, career_wins = _load_career_state(conn)
        names: dict[str, str] = {}

        candidates = []
        upcoming_events = fetch_upcoming(client)
        odds_pool_events = upcoming_events + inplay_events

        # Orden cronologico entre sesiones (igual que el motor de backtest), para
        # que el Elo de una sesion ya cerrada se plegue antes de evaluar la siguiente.
        sessions_sorted = sorted(
            sessions, key=lambda s: min((m.get("rel_min") or 0) for m in s["schedule"]) if s["schedule"] else 0
        )

        for sess in sessions_sorted:
            schedule = sorted(sess["schedule"], key=lambda x: x.get("rel_min") or 0)
            fully_closed = all(m["completed"] for m in schedule) if schedule else False

            # Estadisticas de sesion (solo con lo ya jugado en ESTA sesion, igual
            # que el backtest): sirven tanto para elegibilidad como para el ajuste
            # por rivales comunes.
            stats: dict[str, dict] = {}
            tainted: set[str] = set()

            def get_stat(key, name):
                if key not in stats:
                    stats[key] = {"name": name, "played": 0, "wins": 0, "losses": 0, "sf": 0, "sa": 0, "matches": []}
                    names[key] = name
                return stats[key]

            ranking_snapshot = dict(elo)  # elo tal cual antes de que esta sesion empezara
            # Carrera COMPLETA del jugador (cruzando sesiones) tal cual antes de que
            # esta sesion empezara -- sin look-ahead, mismo criterio que el Elo.
            # Alimenta min_career_matches/min_career_win_rate (ver StrategyParams).
            career_snapshot = dict(career_played)
            career_wins_snapshot = dict(career_wins)

            # Un solo recorrido cronologico -- igual que backtest/replay.py --
            # para que un partido pendiente NUNCA se contamine a si mismo. Antes
            # esto eran dos bucles separados: uno marcaba 'tainted' recorriendo
            # TODA la sesion (pasado Y futuro), y el de candidatos lo consultaba
            # despues -- asi que el propio candidato (por definicion, un partido
            # "no completado") siempre habia contaminado a sus dos jugadores un
            # instante antes en el primer bucle. Resultado real en produccion:
            # candidates=0 en TODAS las pasadas de live_scan desde que se
            # promovio candidata_elo_scale_v1 (2026-08-24), pese a haber ~150
            # partidos pendientes en la ventana de hoy/ayer en cada pasada --
            # ver matches_seen/matches_completed/matches_pending en el summary.
            # Ahora, para cada partido, la elegibilidad como candidato se mira
            # ANTES de contaminar por su propia pendencia -- 'tainted' solo
            # refleja huecos de partidos ESTRICTAMENTE anteriores en la sesion,
            # tal cual hace el motor de backtest.
            for m in schedule:
                p1k, p2k = m["p1k"], m["p2k"]

                if not m["completed"] and not m.get("inplay"):
                    dt = m.get("dt")
                    if dt:
                        delta_min = (dt - now).total_seconds() / 60
                        if -config.STALE_GRACE_MINUTES <= delta_min <= config.LOOKAHEAD_MINUTES:
                            st1 = stats.get(p1k); st2 = stats.get(p2k)
                            if (
                                st1 and st2
                                and st1["played"] >= params.min_matches_played
                                and st2["played"] >= params.min_matches_played
                                and p1k not in tainted and p2k not in tainted
                            ):
                                # min_career_matches/min_career_win_rate -- mismo criterio
                                # que backtest/replay.py, sin look-ahead (snapshot de antes
                                # de esta sesion). Otros filtros de StrategyParams
                                # (min_session_size, min_avg_games_won, min_hour_of_day,
                                # min_weekday, min_career_win_rate_gap, min_blowout_rate,
                                # min_h2h_matches...) todavia NO estan portados al scanner
                                # en vivo -- solo importa ahora mismo porque son los dos
                                # unicos que usa la estrategia activa candidata_elo_scale_v1
                                # (ver EXPERIMENTS_LOG.md).
                                career_p1 = career_snapshot.get(p1k, 0)
                                career_p2 = career_snapshot.get(p2k, 0)
                                if career_p1 >= params.min_career_matches and career_p2 >= params.min_career_matches:
                                    career_wr_p1 = (career_wins_snapshot.get(p1k, 0) / career_p1) if career_p1 else 0.0
                                    career_wr_p2 = (career_wins_snapshot.get(p2k, 0) / career_p2) if career_p2 else 0.0
                                    if (
                                        params.min_career_win_rate <= career_wr_p1 <= params.max_career_win_rate
                                        and params.min_career_win_rate <= career_wr_p2 <= params.max_career_win_rate
                                    ):
                                        candidates.append((sess, m, st1, st2, dict(ranking_snapshot)))

                if not m["completed"]:
                    tainted.add(p1k)
                    tainted.add(p2k)
                    continue
                st1 = get_stat(p1k, m["p1"])
                st2 = get_stat(p2k, m["p2"])
                aw = m["s1"] > m["s2"]
                st1["played"] += 1; st2["played"] += 1
                st1["sf"] += m["s1"]; st1["sa"] += m["s2"]
                st2["sf"] += m["s2"]; st2["sa"] += m["s1"]
                if aw:
                    st1["wins"] += 1; st2["losses"] += 1
                else:
                    st2["wins"] += 1; st1["losses"] += 1
                st1["matches"].append({"oppKey": p2k, "sf": m["s1"], "sa": m["s2"], "win": aw})
                st2["matches"].append({"oppKey": p1k, "sf": m["s2"], "sa": m["s1"], "win": not aw})

            # Solo se pliega la sesion al Elo/H2H/carrera persistentes cuando esta
            # COMPLETA -- igual que el backtest, que nunca actualiza el rating a
            # mitad de sesion -- y solo una vez (elo_applied evita repetirlo en el
            # siguiente scan).
            if fully_closed and schedule and any(m["uid"] not in applied_uids for m in schedule):
                for m in schedule:
                    p1k, p2k = m["p1k"], m["p2k"]
                    hk = "|".join(sorted((p1k, p2k)))
                    arr = h2h.setdefault(hk, deque(maxlen=params.h2h_max_matches))
                    arr.append(p1k if m["s1"] > m["s2"] else p2k)
                    update_rolling(elo, p1k, p2k, m["s1"], m["s2"], params)
                    p1_won = m["s1"] > m["s2"]
                    career_played[p1k] = career_played.get(p1k, 0) + 1
                    career_played[p2k] = career_played.get(p2k, 0) + 1
                    winner_key = p1k if p1_won else p2k
                    career_wins[winner_key] = career_wins.get(winner_key, 0) + 1
                    newly_applied.append(m["uid"])

        summary["candidates"] = len(candidates)

        new_actionable = []
        for sess, m, st1, st2, ranking in candidates:
            ts = int(m["dt"].timestamp())
            event = find_event(m["p1"], m["p2"], ts, odds_pool_events)
            if not event:
                continue
            line = current_best_line(client, event)
            if not line:
                continue
            home = (event.get("home") or {}).get("name", "")
            if strong_name(home, m["p2"]):
                line["odds1"], line["odds2"] = line["odds2"], line["odds1"]
                line["mp1"], line["mp2"] = line["mp2"], line["mp1"]

            p1k, p2k = m["p1k"], m["p2k"]
            e1 = ranking.get(p1k, params.initial_elo)
            e2 = ranking.get(p2k, params.initial_elo)
            hk = "|".join(sorted((p1k, p2k)))
            h_arr = h2h.get(hk, deque())
            model = compute_model(e1, e2, st1["matches"], st2["matches"], len(h_arr),
                                   sum(1 for w in h_arr if w == p1k), ranking, params)
            ev = evaluate_pick(line["mp1"], line["mp2"], model["p1"], model["p2"],
                                line["odds1"], line["odds2"], bool(line["fallback"]), params)

            match_uid = m["uid"]
            pick_id = f"live|{match_uid}"
            underdog = m["p1"] if ev.underdog_is_p1 else m["p2"]
            favorito = m["p2"] if ev.underdog_is_p1 else m["p1"]
            created_at = datetime.now(timezone.utc).isoformat()

            existing = conn.execute("SELECT emailed FROM picks WHERE id = ?", (pick_id,)).fetchone()
            match_day = title_date(sess, today)
            row_values = {
                "id": pick_id, "source": "live", "strategy_name": params.name, "params_hash": params.hash(),
                "created_at": created_at, "match_uid": match_uid, "date": match_day.isoformat(),
                "session_title": sess["title"], "time": m["time"], "p1": m["p1"], "p2": m["p2"],
                "favorito": favorito, "underdog": underdog, "book": line["book"],
                "odds_underdog": ev.odds_underdog, "market_prob_underdog": ev.market_prob_underdog,
                "model_prob_underdog": ev.model_prob_underdog, "edge_pp": ev.edge_pp, "ev_pct": ev.ev_pct,
                "fair_odds": ev.fair_odds, "signal": ev.signal, "result": "PENDING", "pnl_1u": None,
                "emailed": 1 if (existing and existing["emailed"]) else 0,
            }
            cols = list(row_values.keys())
            conn.execute(
                f"""INSERT INTO picks ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})
                    ON CONFLICT(id) DO UPDATE SET
                      book=excluded.book, odds_underdog=excluded.odds_underdog,
                      market_prob_underdog=excluded.market_prob_underdog, model_prob_underdog=excluded.model_prob_underdog,
                      edge_pp=excluded.edge_pp, ev_pct=excluded.ev_pct, fair_odds=excluded.fair_odds,
                      signal=excluded.signal""",
                row_values,
            )

            if ev.actionable and not (existing and existing["emailed"]):
                new_actionable.append({
                    "id": pick_id, "time": m["time"], "underdog": underdog, "favorito": favorito,
                    "odds_underdog": ev.odds_underdog, "model_prob_underdog": ev.model_prob_underdog,
                    "edge_pp": ev.edge_pp, "ev_pct": ev.ev_pct, "signal": ev.signal, "book": line["book"],
                })

        _save_elo_state(conn, elo, names)
        _save_h2h_state(conn, h2h)
        _save_career_state(conn, career_played, career_wins)
        if newly_applied:
            conn.executemany(
                "UPDATE raw_matches SET elo_applied = 1 WHERE match_uid = ?",
                [(u,) for u in newly_applied],
            )
        conn.commit()

        summary["new_picks"] = len(new_actionable)
        if new_actionable and not dry_run_email:
            subject, html = render_picks_email(new_actionable)
            send_email(subject, html)
            ids = [p["id"] for p in new_actionable]
            conn.executemany("UPDATE picks SET emailed = 1 WHERE id = ?", [(i,) for i in ids])
            conn.commit()
            summary["emailed"] = len(new_actionable)

        summary["results_updated"] = _settle_pending_live_picks(conn)
        conn.commit()

    return summary


def _settle_pending_live_picks(conn) -> int:
    """Cierra picks 'live' cuyo partido ya termino: marca WIN/LOSS y pnl_1u."""
    rows = conn.execute(
        """SELECT p.id, p.underdog, p.odds_underdog, m.p1, m.p2, m.s1, m.s2, m.p1_key, m.p2_key
           FROM picks p JOIN raw_matches m ON p.match_uid = m.match_uid
           WHERE p.source = 'live' AND p.result = 'PENDING' AND m.completed = 1"""
    ).fetchall()
    n = 0
    for r in rows:
        underdog_is_p1 = r["underdog"] == r["p1"]
        won = (r["s1"] > r["s2"]) == underdog_is_p1
        pnl = (r["odds_underdog"] - 1) if won else -1.0
        conn.execute(
            "UPDATE picks SET result = ?, pnl_1u = ? WHERE id = ?",
            ("WIN" if won else "LOSS", pnl, r["id"]),
        )
        n += 1
    return n
