"""CLI unico para todo el flujo:

  python -m tt_elite.cli collect  --start 2025-08-01 --end 2026-08-01
  python -m tt_elite.cli sweep    --warmup-start 2025-06-01 --train-start 2025-08-01 \\
                                   --test-start 2026-02-01 --test-end 2026-08-01
  python -m tt_elite.cli promote  --experiment-id 42
  python -m tt_elite.cli scan
  python -m tt_elite.cli report   --days 30
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import date

from . import config
from . import db as dbmod
from .backtest.blowouts import compute_blowout_observations, print_blowout_table, summarize as summarize_blowouts
from .backtest.collect import collect_range
from .backtest.streaks import (
    compute_streak_observations,
    compute_streak_observations_full_model,
    print_streak_table,
    print_streak_table_full_model,
    summarize as summarize_streaks,
    summarize_full_model,
)
from .backtest.sweep import grid_sweep, print_leaderboard, run_experiment
from .model.active import load_active_params, save_active_params
from .model.params import BASELINE, StrategyParams
from .live.backfill import apply_backfill, compute_backfill
from .live.blowout_chain import scan_blowout_chain
from .live.scan import run_live_scan


def _d(s: str) -> date:
    return date.fromisoformat(s)


def cmd_collect(args: argparse.Namespace) -> None:
    collect_range(_d(args.start), _d(args.end), fetch_odds=not args.no_odds)


def cmd_sweep(args: argparse.Namespace) -> None:
    if args.grid_file:
        grid = json.loads(open(args.grid_file).read())
    else:
        # Grid por defecto: barre los 4 filtros de senal mas sensibles al ROI.
        grid = {
            "min_model": [0.52, 0.55, 0.58],
            "min_edge": [0.04, 0.06, 0.08, 0.10],
            "min_ev": [0.02, 0.03, 0.05],
        }
    with dbmod.get_conn() as conn:
        base = load_active_params(conn) if args.from_active else BASELINE
        results = grid_sweep(
            conn, base, grid,
            _d(args.warmup_start), _d(args.train_start), _d(args.test_start), _d(args.test_end),
            min_test_samples=args.min_test_samples,
        )
    print_leaderboard(results, top=args.top)
    if results:
        best = results[0]
        print(f"\nMejor por ROI de test: {best['name']} (hash={best['params'].hash()})")
        print("Para activarlo en el scanner en vivo:")
        print(f"  python -m tt_elite.cli promote --params-json '{best['params'].to_json()}'")


def cmd_run(args: argparse.Namespace) -> None:
    """Corre una sola configuracion (la activa, o BASELINE) y muestra metricas train/test."""
    with dbmod.get_conn() as conn:
        params = load_active_params(conn) if args.from_active else BASELINE
        res = run_experiment(
            conn, params, _d(args.warmup_start), _d(args.train_start), _d(args.test_start), _d(args.test_end),
            name=args.name or params.name,
        )
    print(json.dumps({"train": res["train"], "test": res["test"]}, indent=2, default=str))


def cmd_promote(args: argparse.Namespace) -> None:
    with dbmod.get_conn() as conn:
        if args.params_json:
            params = StrategyParams.from_json(args.params_json)
        elif args.experiment_id:
            row = conn.execute("SELECT params_json FROM experiments WHERE id = ?", (args.experiment_id,)).fetchone()
            if not row:
                print(f"No existe experiment id={args.experiment_id}", file=sys.stderr)
                sys.exit(1)
            params = StrategyParams.from_json(row["params_json"])
        else:
            print("Especifica --experiment-id o --params-json", file=sys.stderr)
            sys.exit(1)
        save_active_params(conn, params)
    print(f"Estrategia activa actualizada: {params.name} ({params.hash()})")


def cmd_scan(args: argparse.Namespace) -> None:
    summary = run_live_scan(dry_run_email=args.dry_run_email)
    print(json.dumps(summary, indent=2))


def cmd_test_email(args: argparse.Namespace) -> None:
    """Manda un email de prueba real via SendGrid -- util para verificar
    SENDGRID_API_KEY/EMAIL_FROM/EMAIL_TO sin depender de que haya un pick
    accionable ahora mismo."""
    from .notify.email import send_email
    send_email(
        "TT Elite: email de prueba",
        "<p>Si ves esto, el envio de email via SendGrid funciona correctamente.</p>",
        "Si ves esto, el envio de email via SendGrid funciona correctamente.",
    )
    print("Email de prueba enviado.")


def cmd_find_league(args: argparse.Namespace) -> None:
    """Busca en BetsAPI (sport_id=92, sin restringir a LEAGUE_ID) partidos
    proximos cuyo jugador coincida con --query -- para descubrir el league_id
    real de un circuito nuevo a partir de un nombre visto en una casa de
    apuestas. Diagnostico puntual, no forma parte del flujo normal."""
    from .sources.betsapi import search_events_by_player
    from .sources.http_cache import ApiClient
    with dbmod.get_conn() as conn:
        client = ApiClient(conn, config.BETSAPI_TOKEN)
        events = search_events_by_player(client, args.query, max_pages=args.max_pages)
    if not events:
        print(f"Sin resultados para {args.query!r} en /v3/events/upcoming (sport_id=92).")
        return
    for e in events:
        home = (e.get("home") or {}).get("name", "")
        away = (e.get("away") or {}).get("name", "")
        league = e.get("league") or {}
        print(f"event_id={e.get('id')} time={e.get('time')} league_id={league.get('id')} "
              f"league_name={league.get('name')!r} -- {home} vs {away}")


def cmd_player_stats(args: argparse.Namespace) -> None:
    """Consulta en BetsAPI (/v3/events/ended) el historial RECIENTE REAL de
    jugadores de un circuito nuevo -- pensado para Czech Liga Pro
    (league_id=22742, descubierta el 2026-08-24 via find-league), que no
    esta integrada ni validada en este proyecto.

    Da datos crudos (record, forma reciente, H2H) -- NUNCA una probabilidad
    o edge de modelo: no hay backtest detras para ningun circuito que no sea
    el ya validado (elo_scale=1800 + min_career_matches=12 + ... sobre
    TT-Series/league_id=29128). Pedido explicito del usuario tras entender
    esta distincion -- ver conversacion 2026-08-24."""
    from datetime import date, timedelta
    from .sources.betsapi import fetch_ended_for_league
    from .sources.http_cache import ApiClient
    from .textutil import parse_score, strong_name

    pairs: list[tuple[str, str]] = []
    for chunk in args.matchups.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        low = chunk.lower()
        if " vs " not in low:
            print(f"Aviso: no se pudo parsear {chunk!r} (falta ' vs '), se ignora.")
            continue
        idx = low.index(" vs ")
        p1, p2 = chunk[:idx].strip(), chunk[idx + 4:].strip()
        if p1 and p2:
            pairs.append((p1, p2))
    if not pairs:
        print("Ningun enfrentamiento valido en --matchups (formato: 'A vs B; C vs D').")
        return
    names = sorted({n for pair in pairs for n in pair})

    with dbmod.get_conn() as conn:
        client = ApiClient(conn, config.BETSAPI_TOKEN)
        today = date.today()
        events: list[dict] = []
        for i in range(args.days):
            d = today - timedelta(days=i)
            events.extend(fetch_ended_for_league(client, args.league_id, d, use_cache=False))

    per_player: dict[str, list[dict]] = {n: [] for n in names}
    for e in events:
        home = (e.get("home") or {}).get("name", "")
        away = (e.get("away") or {}).get("name", "")
        sc = parse_score(e.get("ss") or "")
        if not sc:
            continue
        for n in names:
            if strong_name(home, n):
                per_player[n].append({"time": e.get("time") or 0, "opp": away, "won": sc[0] > sc[1]})
            elif strong_name(away, n):
                per_player[n].append({"time": e.get("time") or 0, "opp": home, "won": sc[1] > sc[0]})

    print(f"Ventana: ultimos {args.days} dias, league_id={args.league_id}. "
          f"{len(events)} partidos terminados encontrados en total.")
    print("*** Datos crudos, SIN validar -- no es el modelo real, no hay backtest detras. ***\n")

    for p1, p2 in pairs:
        print(f"=== {p1} vs {p2} ===")
        for n in (p1, p2):
            ms = sorted(per_player[n], key=lambda m: m["time"], reverse=True)
            played = len(ms)
            if not played:
                print(f"  {n}: SIN PARTIDOS en la ventana consultada.")
                continue
            wins = sum(1 for m in ms if m["won"])
            recent = ms[:10]
            recent_wins = sum(1 for m in recent if m["won"])
            print(f"  {n}: {wins}/{played} ({100*wins/played:.0f}%) -- ultimos {len(recent)}: {recent_wins}/{len(recent)}")
        h2h = [m for m in per_player.get(p1, []) if strong_name(m["opp"], p2)]
        if h2h:
            h2h_wins = sum(1 for m in h2h if m["won"])
            print(f"  H2H en la ventana: {p1} {h2h_wins}-{len(h2h) - h2h_wins} {p2}")
        else:
            print("  Sin enfrentamientos directos en la ventana.")
        print()


def cmd_league_depth(args: argparse.Namespace) -> None:
    """Muestrea /v3/events/ended en unos pocos dias muy espaciados (no dia a
    dia -- eso ya vimos que tarda minutos con una liga de este volumen) para
    saber hasta cuando hay historico real en BetsAPI para un league_id --
    determina si merece la pena construir/validar un pipeline nuevo para ese
    circuito antes de invertir en ello."""
    from datetime import date, timedelta
    from .sources.betsapi import fetch_ended_for_league
    from .sources.http_cache import ApiClient

    offsets = [int(x) for x in args.sample_days.split(",") if x.strip()]
    with dbmod.get_conn() as conn:
        client = ApiClient(conn, config.BETSAPI_TOKEN)
        today = date.today()
        for off in offsets:
            d = today - timedelta(days=off)
            rows = fetch_ended_for_league(client, args.league_id, d, use_cache=False)
            print(f"hace {off:4d} dias ({d.isoformat()}): {len(rows)} partidos terminados encontrados")


def cmd_raw_events(args: argparse.Namespace) -> None:
    """Vuelca el JSON crudo de los primeros N eventos de /v3/events/ended para
    un league_id/dia -- para entender el esquema real (que campos trae,
    p.ej. algun identificador de "mesa"/ronda) antes de disenar como agrupar
    "sesiones" para un circuito que no tiene TT-Series detras."""
    import json as jsonmod
    from datetime import date
    from .sources.betsapi import fetch_ended_for_league
    from .sources.http_cache import ApiClient

    d = date.fromisoformat(args.day)
    with dbmod.get_conn() as conn:
        client = ApiClient(conn, config.BETSAPI_TOKEN)
        rows = fetch_ended_for_league(client, args.league_id, d, use_cache=False)
    print(f"{len(rows)} eventos encontrados el {d.isoformat()} (league_id={args.league_id}). Primeros {args.limit}:\n")
    for e in rows[: args.limit]:
        print(jsonmod.dumps(e, indent=2, ensure_ascii=False))
        print()


def cmd_backfill_state(args: argparse.Namespace) -> None:
    """Reconstruye elo_state/h2h_state/career_state desde CERO recorriendo
    todo el historico de raw_matches (ver live/backfill.py). Necesario tras
    el descubrimiento de que career_state (2026-08-24) nunca se habia
    inicializado: sin esto, min_career_matches tardaria semanas en
    satisfacerse solo con partidos nuevos vistos en vivo."""
    with dbmod.get_conn() as conn:
        params = load_active_params(conn)
        result = compute_backfill(conn, params)
        print(f"Sesiones completas encontradas: {result['sessions_folded']}/{result['sessions_total']}")
        print(f"Jugadores con Elo/carrera: {len(result['names'])}")
        print(f"Partidos aplicados (elo_applied=1): {len(result['applied_uids'])}")
        if args.dry_run:
            print("--dry-run: no se escribe nada.")
            return
        apply_backfill(conn, result)
    print("Backfill aplicado.")


def cmd_scan_blowout_chain(args: argparse.Namespace) -> None:
    """Sistema APARTE (sin picks, sin probabilidad de acierto -- puramente
    observacional): detecta "cadenas de barridas transitivas" dentro de una
    misma sesion (A goleo 3-0 a X, X goleo 3-0 a Y, toca A vs Y) y las
    guarda en blowout_chain_signals. La deteccion en si solo lee
    raw_matches ya recolectado; ademas, si hay BETSAPI_TOKEN (y no se paso
    --no-odds), consulta la cuota de cada uno (A/Y) en el partido -- solo
    una vez por senal, no se repite en pasadas siguientes. Pensado para
    correr cada 10 min junto al scanner principal (ver live_scan.yml) y
    para uso puntual con --show para ver lo encontrado hoy."""
    with dbmod.get_conn() as conn:
        result = scan_blowout_chain(conn, days_back=args.days_back, fetch_odds=not args.no_odds)
        print(f"Cadenas encontradas/actualizadas: {result['found']}")
        if args.show:
            _print_blowout_chain_today(conn, underdog_only=not args.all)


def _print_blowout_chain_today(conn, underdog_only: bool = True) -> None:
    """underdog_only (default True, pedido explicito del usuario): solo
    cadenas donde A -- la "seleccion" que favorece la teoria -- tiene cuota
    de UNDERDOG (a_odds > y_odds). Si A ya es favorito de mercado, la cadena
    no aporta nada que la cuota no dijera ya."""
    from datetime import date as _date
    today = _date.today().isoformat()
    underdog_filter = "AND a_odds IS NOT NULL AND a_odds > y_odds" if underdog_only else ""
    rows = conn.execute(
        f"""SELECT session_title, date, time, player_a, player_y, common_x,
                   ax_date, ax_time, xy_date, xy_time,
                   match_completed, a_score, y_score, theory_holds,
                   a_odds, y_odds, odds_book
            FROM blowout_chain_signals
            WHERE date = ? {underdog_filter}
            ORDER BY match_completed ASC, time ASC""",
        (today,),
    ).fetchall()
    tag = " (A underdog)" if underdog_only else ""
    if not rows:
        print(f"\nSin cadenas{tag} encontradas hoy ({today}).")
    else:
        print(f"\nCadenas de hoy{tag} ({today}), {len(rows)} encontradas:")
        for r in rows:
            print(f"\n  {r['date']} {r['time']} ({r['session_title']}): {r['player_a']} vs {r['player_y']}")
            print(f"      {r['player_a']} goleo 3-0 a {r['common_x']} el {r['ax_date']} {r['ax_time']}")
            print(f"      {r['common_x']} goleo 3-0 a {r['player_y']} el {r['xy_date']} {r['xy_time']}")
            if r["a_odds"] is not None:
                print(f"      Cuotas ({r['odds_book']}): {r['player_a']} @{r['a_odds']:.2f} -- {r['player_y']} @{r['y_odds']:.2f}")
            else:
                print("      Cuotas: sin encontrar en BetsAPI")
            if r["match_completed"]:
                veredicto = "SE CUMPLE (gano A)" if r["theory_holds"] else "NO se cumple (gano Y)"
                print(f"      Resultado: {r['player_a']} {r['a_score']}-{r['y_score']} {r['player_y']} -> teoria: {veredicto}")
            else:
                print("      PENDIENTE de jugarse")

    stats = conn.execute(
        f"""SELECT
                SUM(theory_holds) as hits,
                COUNT(*) as n,
                SUM(CASE WHEN a_odds IS NOT NULL THEN 1 ELSE 0 END) as n_odds,
                SUM(CASE WHEN a_odds IS NULL THEN 0 WHEN theory_holds = 1 THEN a_odds - 1 ELSE -1 END) as pnl
            FROM blowout_chain_signals
            WHERE match_completed = 1 {underdog_filter}"""
    ).fetchone()
    if stats and stats["n"]:
        print(f"\nHistorico (todas las fechas{tag}, {stats['n']} casos ya jugados): "
              f"la teoria se cumple en {stats['hits']}/{stats['n']} ({100 * stats['hits'] / stats['n']:.0f}%).")
        if stats["n_odds"]:
            pnl = stats["pnl"]
            roi = 100 * pnl / stats["n_odds"]
            print(f"Rentabilidad (apostando 1u a A en cada cadena con cuota, {stats['n_odds']} apuestas): "
                  f"pnl={pnl:+.2f}u, ROI={roi:+.1f}%. Muestra pequeña -- no es una conclusion.")


def cmd_status(args: argparse.Namespace) -> None:
    """Foto rapida de que hay en la base de datos ahora mismo -- sin lanzar
    nada, solo lee. Util para decidir sobre que rango de fechas correr un
    sweep sin tener que esperar a leer logs de un collect en marcha."""
    with dbmod.get_conn() as conn:
        m = conn.execute(
            """SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(DISTINCT date) as days,
                      COUNT(*) as total, SUM(CASE WHEN completed=1 THEN 1 ELSE 0 END) as completed
               FROM raw_matches"""
        ).fetchone()
        o = conn.execute("SELECT COUNT(*) as n, COUNT(DISTINCT match_uid) as matches FROM raw_odds").fetchone()
        n_exp = conn.execute("SELECT COUNT(*) as n FROM experiments").fetchone()
        active = load_active_params(conn)

        # Partidos completados por dia, para ver de un vistazo donde hay huecos.
        by_day = conn.execute(
            """SELECT date, COUNT(*) as n, SUM(CASE WHEN completed=1 THEN 1 ELSE 0 END) as done
               FROM raw_matches GROUP BY date ORDER BY date"""
        ).fetchall()

    print(f"Rango: {m['min_date']} -> {m['max_date']} ({m['days']} dias con datos)")
    print(f"Partidos: {m['total']} totales, {m['completed']} terminados")
    print(f"Cuotas: {o['n']} filas, {o['matches']} partidos con cuota")
    print(f"Experimentos guardados: {n_exp['n']}")
    print(f"Estrategia activa: {active.name} ({active.hash()})")
    print("\nPor dia:")
    for r in by_day:
        print(f"  {r['date']}: {r['done']}/{r['n']} completados")


def cmd_streaks(args: argparse.Namespace) -> None:
    """Rachas de victorias/derrotas dentro de una sesion: ¿el resultado del
    siguiente partido se desvia de lo que ya predice el Elo pre-sesion segun
    la racha con la que llega el jugador? Si la desviacion crece con la
    longitud de la racha, hay señal que el modelo actual no esta usando."""
    with dbmod.get_conn() as conn:
        if args.full_model:
            obs = compute_streak_observations_full_model(conn, _d(args.start), _d(args.end))
            rows = summarize_full_model(obs, max_bucket=args.max_bucket)
            print_streak_table_full_model(rows)
        else:
            obs = compute_streak_observations(conn, _d(args.start), _d(args.end))
            rows = summarize_streaks(obs, max_bucket=args.max_bucket)
            print_streak_table(rows)


def cmd_blowouts(args: argparse.Namespace) -> None:
    """Jugadores con alta tasa historica de resultados 0-3/3-0 (barrida):
    cuando dos de esos jugadores se enfrentan, ¿el partido en si termina en
    barrida mas de lo normal? Tasa acumulada en orden cronologico, solo con
    lo visto ANTES de cada partido (sin mirar el resultado del propio
    partido ni partidos futuros)."""
    with dbmod.get_conn() as conn:
        obs = compute_blowout_observations(conn, _d(args.start), _d(args.end), min_prior_matches=args.min_prior)
    result = summarize_blowouts(obs)
    print_blowout_table(result)


def cmd_report(args: argparse.Namespace) -> None:
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=args.days)).isoformat()
    with dbmod.get_conn() as conn:
        rows = conn.execute(
            """SELECT date, time, underdog, favorito, book, odds_underdog, signal, result, pnl_1u
               FROM picks WHERE source = 'live' AND date >= ? ORDER BY date DESC, time DESC LIMIT ?""",
            (cutoff, args.limit),
        ).fetchall()
        settled = conn.execute(
            "SELECT result, COUNT(*) n, SUM(pnl_1u) pnl FROM picks WHERE source='live' AND result != 'PENDING' AND date >= ? GROUP BY result",
            (cutoff,),
        ).fetchall()
    for r in rows:
        print(f"{r['date']} {r['time']} {r['underdog']:20s} vs {r['favorito']:20s} @{r['odds_underdog']:.2f} "
              f"[{r['signal']}] -> {r['result']} pnl={r['pnl_1u']}")
    print("\nResumen liquidado:")
    for r in settled:
        print(f"  {r['result']}: n={r['n']} pnl={r['pnl']}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tt_elite")
    sub = p.add_subparsers(required=True)

    c = sub.add_parser("collect", help="Descarga y cachea historico TT-Series + BetsAPI en SQLite")
    c.add_argument("--start", required=True)
    c.add_argument("--end", required=True)
    c.add_argument("--no-odds", action="store_true", help="Solo partidos/resultados, sin cuotas (mas rapido)")
    c.set_defaults(func=cmd_collect)

    s = sub.add_parser("sweep", help="Barre una grilla de parametros con split train/test")
    s.add_argument("--warmup-start", required=True)
    s.add_argument("--train-start", required=True)
    s.add_argument("--test-start", required=True)
    s.add_argument("--test-end", required=True)
    s.add_argument("--grid-file", help="JSON {campo: [valores]}. Por defecto barre min_model/min_edge/min_ev.")
    s.add_argument("--min-test-samples", type=int, default=20)
    s.add_argument("--top", type=int, default=15)
    s.add_argument("--from-active", action="store_true", help="Usa la estrategia activa como base en vez de BASELINE")
    s.set_defaults(func=cmd_sweep)

    r = sub.add_parser("run", help="Corre una sola configuracion (BASELINE o la activa) y muestra sus metricas")
    r.add_argument("--warmup-start", required=True)
    r.add_argument("--train-start", required=True)
    r.add_argument("--test-start", required=True)
    r.add_argument("--test-end", required=True)
    r.add_argument("--from-active", action="store_true")
    r.add_argument("--name")
    r.set_defaults(func=cmd_run)

    pr = sub.add_parser("promote", help="Activa una configuracion de parametros para el scanner en vivo")
    pr.add_argument("--experiment-id", type=int)
    pr.add_argument("--params-json")
    pr.set_defaults(func=cmd_promote)

    sc = sub.add_parser("scan", help="Una pasada del scanner en vivo (picks + email)")
    sc.add_argument("--dry-run-email", action="store_true", help="No envia email, solo calcula y guarda")
    sc.set_defaults(func=cmd_scan)

    te = sub.add_parser("test-email", help="Manda un email de prueba real via SendGrid (verifica SENDGRID_API_KEY/EMAIL_TO)")
    te.set_defaults(func=cmd_test_email)

    bf = sub.add_parser("backfill-state", help="Reconstruye elo_state/h2h_state/career_state desde todo el historico de raw_matches")
    bf.add_argument("--dry-run", action="store_true", help="Solo muestra cuanto se aplicaria, no escribe nada")
    bf.set_defaults(func=cmd_backfill_state)

    fl = sub.add_parser("find-league", help="Busca el league_id real de BetsAPI a partir de un nombre de jugador (diagnostico puntual)")
    fl.add_argument("--query", required=True, help="Substring de nombre de jugador a buscar")
    fl.add_argument("--max-pages", type=int, default=15)
    fl.set_defaults(func=cmd_find_league)

    ps = sub.add_parser("player-stats", help="Datos crudos (record/H2H/forma) de jugadores de un circuito NO validado -- nunca da un edge de modelo")
    ps.add_argument("--matchups", required=True, help="'Jugador A vs Jugador B; Jugador C vs Jugador D; ...'")
    ps.add_argument("--league-id", type=int, default=22742, help="Por defecto Czech Liga Pro")
    ps.add_argument("--days", type=int, default=30, help="Dias hacia atras a consultar en /v3/events/ended")
    ps.set_defaults(func=cmd_player_stats)

    ld = sub.add_parser("league-depth", help="Muestrea /v3/events/ended en fechas espaciadas para saber cuanto historico real hay de un league_id")
    ld.add_argument("--league-id", type=int, default=22742, help="Por defecto Czech Liga Pro")
    ld.add_argument("--sample-days", default="0,7,30,60,90,180,365,540,730",
                     help="Dias hacia atras a muestrear, separados por coma")
    ld.set_defaults(func=cmd_league_depth)

    re_ = sub.add_parser("raw-events", help="Vuelca el JSON crudo de eventos de /v3/events/ended (diagnostico de esquema)")
    re_.add_argument("--league-id", type=int, default=22742, help="Por defecto Czech Liga Pro")
    re_.add_argument("--day", required=True, help="YYYY-MM-DD")
    re_.add_argument("--limit", type=int, default=5)
    re_.set_defaults(func=cmd_raw_events)

    rp = sub.add_parser("report", help="Ultimos picks en vivo y su resultado")
    rp.add_argument("--limit", type=int, default=50)
    rp.add_argument("--days", type=int, default=30)
    rp.set_defaults(func=cmd_report)

    st = sub.add_parser("status", help="Foto rapida de la cobertura de datos (sin lanzar nada)")
    st.set_defaults(func=cmd_status)

    sk = sub.add_parser("streaks", help="Rachas de W/L dentro de sesion vs lo que ya predice el Elo")
    sk.add_argument("--start", required=True)
    sk.add_argument("--end", required=True)
    sk.add_argument("--max-bucket", type=int, default=6, help="Longitud de racha desde la que se agrupa como 'N+'")
    sk.add_argument("--full-model", action="store_true",
                     help="Compara tambien contra el modelo completo (Elo+session_delta+h2h+rivales comunes), no solo Elo puro")
    sk.set_defaults(func=cmd_streaks)

    bo = sub.add_parser("blowouts", help="Jugadores con alta tasa de 0-3/3-0: ¿se dan mas barridas entre ellos?")
    bo.add_argument("--start", required=True)
    bo.add_argument("--end", required=True)
    bo.add_argument("--min-prior", type=int, default=5, help="Partidos previos minimos por jugador para contar")
    bo.set_defaults(func=cmd_blowouts)

    bc = sub.add_parser("scan-blowout-chain",
                         help="Sistema APARTE: detecta cadenas A-goleo-3-0-a-X-que-goleo-3-0-a-Y dentro de una sesion")
    bc.add_argument("--days-back", type=int, default=2, help="Dias hacia atras a re-escanear (incluye hoy)")
    bc.add_argument("--show", action="store_true", help="Imprime las cadenas encontradas hoy")
    bc.add_argument("--no-odds", action="store_true", help="No consultar BetsAPI para las cuotas (mas rapido, no requiere BETSAPI_TOKEN)")
    bc.add_argument("--all", action="store_true", help="Con --show, incluye tambien las cadenas donde A ya es favorito de mercado (por defecto solo A underdog)")
    bc.set_defaults(func=cmd_scan_blowout_chain)

    return p


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
