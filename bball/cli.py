"""CLI del sistema de basketball. Fase actual: exploratoria -- descubrir
sport_id/league_id reales en BetsAPI y la forma del mercado de totales antes
de construir el collector/backtest definitivos (ver bball/sources/betsapi.py
para el porque). Se corre casi siempre via GitHub Actions (unico sitio con
salida a BetsAPI desde este repo ahora mismo), nunca desde esta sesion.

Uso:
    python -m bball.cli discover-leagues [--sport-ids 1,2,3] [--day YYYYMMDD]
    python -m bball.cli leagues-on-day --sport-id 18 --day 20260115
    python -m bball.cli raw /v3/events/ended --params sport_id=18,day=20260827
    python -m bball.cli ended --sport-id 18 --league-id 12345 --day 20260827 [--full-first]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

from datetime import date as date_cls

from . import config, db
from .backtest.collect import collect_range
from .backtest.replay import load_games, load_totals_odds, run_backtest, summarize
from .backtest.risk import drawdown_curve, max_losing_streak, simulate_bankroll
from .backtest.sweep import print_split_leaderboard, run_split_sweep, t_stat
from .live.active import load_active_params, params_label, save_active_params
from .live.scan import run_live_scan
from .sources.betsapi import discover_leagues, fetch_ended, fetch_ended_all_leagues
from .sources.http_cache import ApiClient


def _client(conn) -> ApiClient:
    return ApiClient(conn, config.BETSAPI_TOKEN)


def _parse_params(s: str | None) -> dict:
    if not s:
        return {}
    out = {}
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        out[k.strip()] = v.strip()
    return out


def cmd_discover_leagues(args: argparse.Namespace) -> None:
    sport_ids = [int(x) for x in args.sport_ids.split(",")] if args.sport_ids else None
    with db.get_conn() as conn:
        client = _client(conn)
        found = discover_leagues(client, sport_ids=sport_ids)
        if not found:
            print("Sin matches -- ninguna liga probada coincidio con las keywords NBA/WNBA/Euroleague/etc.")
            return
        print(f"\n{len(found)} liga(s) encontradas:\n")
        for row in found:
            print(
                f"  sport_id={row['sport_id']:>3}  league_id={row['league_id']:>8}  "
                f"tag={row['tag']:<16} name={row['league_name']!r}  "
                f"muestra: {row['sample_home']!r} vs {row['sample_away']!r} (event_id={row['sample_event_id']})"
            )
            conn.execute(
                "INSERT INTO bball_leagues(league_id, sport_id, name, tag, discovered_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(league_id) DO UPDATE SET sport_id=excluded.sport_id, name=excluded.name, "
                "tag=excluded.tag, discovered_at=excluded.discovered_at",
                (row["league_id"], row["sport_id"], row["league_name"], row["tag"],
                 datetime.now(timezone.utc).isoformat()),
            )
        print("\n(persistido en bball_leagues)")


def cmd_raw(args: argparse.Namespace) -> None:
    params = _parse_params(args.params)
    with db.get_conn() as conn:
        client = _client(conn)
        js = client.bets(args.path, params, prefix="raw", use_cache=not args.no_cache)
        out = json.dumps(js, ensure_ascii=False, indent=2)
        if len(out) > args.max_chars:
            print(out[: args.max_chars])
            print(f"\n... [truncado, {len(out)} caracteres en total, usa --max-chars para ver mas]")
        else:
            print(out)


def cmd_ended(args: argparse.Namespace) -> None:
    with db.get_conn() as conn:
        client = _client(conn)
        rows = fetch_ended(client, args.sport_id, args.league_id, args.day)
        print(f"{len(rows)} partido(s) terminados el {args.day} (sport_id={args.sport_id}, league_id={args.league_id})\n")
        for e in rows[: args.limit]:
            home = (e.get("home") or {}).get("name", "?")
            away = (e.get("away") or {}).get("name", "?")
            print(f"  event_id={e.get('id')}  {home} vs {away}  ss={e.get('ss')!r}  time={e.get('time')}")
        if args.full_first and rows:
            print("\n--- evento completo (primero de la lista), crudo ---\n")
            print(json.dumps(rows[0], ensure_ascii=False, indent=2))


def cmd_leagues_on_day(args: argparse.Namespace) -> None:
    """Resumen COMPACTO (no JSON crudo) de que ligas de basketball tuvieron
    partidos terminados un dia dado -- para encontrar league_id de NBA/
    Euroliga/etc sin tener que adivinarlos, eligiendo un dia de temporada
    real (evitar All-Star break / pretemporada)."""
    with db.get_conn() as conn:
        client = _client(conn)
        rows = fetch_ended_all_leagues(client, args.sport_id, args.day)
        print(f"{len(rows)} partido(s) terminados el {args.day} (sport_id={args.sport_id}) en total\n")
        by_league: dict[str, dict] = {}
        for e in rows:
            league = e.get("league") or {}
            lid = str(league.get("id"))
            info = by_league.setdefault(lid, {"name": league.get("name"), "count": 0, "sample": None})
            info["count"] += 1
            if info["sample"] is None:
                home = (e.get("home") or {}).get("name", "?")
                away = (e.get("away") or {}).get("name", "?")
                info["sample"] = f"{home} vs {away}  ss={e.get('ss')!r}  event_id={e.get('id')}"
        for lid, info in sorted(by_league.items(), key=lambda kv: -kv[1]["count"]):
            print(f"  league_id={lid:>8}  n={info['count']:>3}  name={info['name']!r}")
            print(f"      muestra: {info['sample']}")


def cmd_collect(args: argparse.Namespace) -> None:
    names = [n.strip().upper() for n in args.leagues.split(",")] if args.leagues else list(config.LEAGUES)
    unknown = [n for n in names if n not in config.LEAGUES]
    if unknown:
        raise SystemExit(f"Liga(s) desconocida(s): {unknown}. Conocidas: {list(config.LEAGUES)}")
    league_ids = {n: config.LEAGUES[n] for n in names}
    start = date_cls.fromisoformat(args.start)
    end = date_cls.fromisoformat(args.end)
    with db.get_conn() as conn:
        client = _client(conn)
        collect_range(client, conn, league_ids, start, end, use_cache=not args.no_cache)


def cmd_backtest(args: argparse.Namespace) -> None:
    leagues = [n.strip().upper() for n in args.leagues.split(",")] if args.leagues else None
    windows = [int(x) for x in args.windows.split(",")]
    thresholds = [float(x) for x in args.thresholds.split(",")]
    with db.get_conn() as conn:
        games = load_games(conn, leagues=leagues)
        odds_by_event = load_totals_odds(conn)
    print(f"{len(games)} partido(s) cargados"
          f"{' (' + ','.join(leagues) + ')' if leagues else ''}, "
          f"{sum(1 for e in odds_by_event)} con al menos una cuota de totales pre-partido\n")
    if not games:
        print("Sin partidos -- corre primero 'collect'.")
        return
    print(f"{'N':>4} {'umbral':>7} {'n':>5} {'hit%':>6} {'ROI%':>7} {'odds_media':>10}")
    for n_window in windows:
        for threshold in thresholds:
            picks = run_backtest(games, odds_by_event, n_window, threshold)
            s = summarize(picks)
            print(f"{n_window:>4} {threshold:>7.1f} {s.n:>5} {s.hit_rate*100:>6.1f} {s.roi_pct:>7.1f} {s.mean_odds:>10.2f}")


def cmd_backtest_split(args: argparse.Namespace) -> None:
    leagues = [n.strip().upper() for n in args.leagues.split(",")] if args.leagues else None
    windows = [int(x) for x in args.windows.split(",")]
    thresholds = [float(x) for x in args.thresholds.split(",")]
    with db.get_conn() as conn:
        games = load_games(conn, leagues=leagues)
        odds_by_event = load_totals_odds(conn)
    if not games:
        print("Sin partidos -- corre primero 'collect'.")
        return
    print(f"{len(games)} partido(s) cargados. Reserva = picks con fecha >= {args.holdout_start} (nunca usar para elegir N/umbral).\n")
    results = run_split_sweep(games, odds_by_event, windows, thresholds, args.holdout_start)
    print_split_leaderboard(results, min_holdout_n=args.min_holdout_n)


def cmd_risk(args: argparse.Namespace) -> None:
    leagues = [n.strip().upper() for n in args.leagues.split(",")] if args.leagues else None
    with db.get_conn() as conn:
        games = load_games(conn, leagues=leagues)
        odds_by_event = load_totals_odds(conn)
    picks = run_backtest(games, odds_by_event, args.window, args.threshold)
    s = summarize(picks)
    print(f"n={s.n} hit={s.hit_rate*100:.1f}% ROI={s.roi_pct:+.1f}% (N={args.window}, umbral={args.threshold})\n")
    if s.n == 0:
        print("Sin picks -- nada que analizar.")
        return

    dd = drawdown_curve(picks)
    streak = max_losing_streak(picks)
    print(f"Racha de perdidas mas larga: {streak}")
    print(f"Drawdown maximo (apostando 1u fija): {dd.max_drawdown_units:.1f}u sobre {dd.final_pnl_units:+.1f}u de PnL final\n")

    mc = simulate_bankroll(picks, n_sims=args.sims, stake_fraction=args.stake_fraction, ruin_threshold_pct=args.ruin_threshold)
    print(f"Monte Carlo ({mc.n_sims} secuencias, apostando {mc.stake_fraction*100:.1f}% de banca actual por pick, {mc.n_bets} apuestas por secuencia):")
    print(f"  Probabilidad de ruina (banca cae por debajo del {mc.ruin_threshold_pct*100:.0f}% de la inicial en algun momento): {mc.prob_ruin*100:.1f}%")
    print(f"  Banca final -- percentil 1%: {mc.p1*100:.0f}%  percentil 5%: {mc.p5*100:.0f}%  mediana: {mc.p50*100:.0f}%  percentil 95%: {mc.p95*100:.0f}%  (100% = banca inicial)")


def cmd_scan(args: argparse.Namespace) -> None:
    summary = run_live_scan()
    print(summary)


def cmd_promote(args: argparse.Namespace) -> None:
    leagues = [n.strip().upper() for n in args.leagues.split(",")] if args.leagues else ["NBA", "WNBA", "EUROLEAGUE"]
    params = {"n_window": args.window, "threshold": args.threshold, "leagues": leagues}
    with db.get_conn() as conn:
        save_active_params(conn, params)
    print(f"Promovido: {params_label(params)}")


def cmd_active(args: argparse.Namespace) -> None:
    with db.get_conn() as conn:
        params = load_active_params(conn)
    print(params_label(params))
    print(params)


def cmd_backtest_summary(args: argparse.Namespace) -> None:
    """Corre la estrategia activa (o la que se pase por flags) sobre TODO el
    historico ya cargado y guarda un resumen en bball_meta -- el dashboard
    web lo lee de ahi (no puede correr este motor en Vercel). Mismo patron
    que tt_elite.cli backtest-summary / getFullHistoryBacktestSummary()."""
    with db.get_conn() as conn:
        active = load_active_params(conn)
    n_window = args.window if args.window is not None else int(active["n_window"])
    threshold = args.threshold if args.threshold is not None else float(active["threshold"])
    leagues = [n.strip().upper() for n in args.leagues.split(",")] if args.leagues else list(active["leagues"])

    with db.get_conn() as conn:
        games = load_games(conn, leagues=leagues)
        odds_by_event = load_totals_odds(conn)

    if not games:
        print("Sin partidos -- corre 'collect' primero.")
        return

    picks = run_backtest(games, odds_by_event, n_window, threshold)
    s = summarize(picks)

    max_date = max(g.date for g in games)
    holdout_start = args.holdout_start or (date_cls.fromisoformat(max_date) - timedelta(days=args.holdout_days)).isoformat()
    search_picks = [p for p in picks if p.date < holdout_start]
    holdout_picks = [p for p in picks if p.date >= holdout_start]
    s_search, s_holdout = summarize(search_picks), summarize(holdout_picks)
    holdout_t = t_stat(holdout_picks)

    dd = drawdown_curve(picks)
    streak = max_losing_streak(picks)
    mc = simulate_bankroll(picks, n_sims=args.sims) if s.n_decided >= 10 else None

    points = []
    cum = 0.0
    for p in picks:
        cum += p.pnl_1u
        points.append({
            "date": p.date, "homeTeam": p.home_team, "awayTeam": p.away_team,
            "expTotal": round(p.exp_total, 1), "line": p.line, "underOdds": p.under_odds,
            "cushion": round(p.cushion, 1), "finalTotal": p.final_total, "result": p.result,
            "pnl": round(p.pnl_1u, 3), "cumPnl": round(cum, 3),
        })

    summary = {
        "params": {"n_window": n_window, "threshold": threshold, "leagues": leagues},
        "n": s.n, "hits": s.wins, "hitRate": s.hit_rate, "roi": s.roi_pct, "pnlTotal": s.pnl,
        "search": {"n": s_search.n, "hitRate": s_search.hit_rate, "roi": s_search.roi_pct},
        "holdout": {"n": s_holdout.n, "hitRate": s_holdout.hit_rate, "roi": s_holdout.roi_pct, "start": holdout_start, "t": holdout_t},
        "maxLosingStreak": streak,
        "maxDrawdownUnits": dd.max_drawdown_units,
        "monteCarlo": None if mc is None else {
            "probRuin": mc.prob_ruin, "p1": mc.p1, "p5": mc.p5, "p50": mc.p50, "p95": mc.p95,
            "stakeFraction": mc.stake_fraction,
        },
        "evalStart": min(g.date for g in games) if picks else None,
        "evalEnd": max_date,
        "gamesLoaded": len(games),
        "points": points,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }

    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO bball_meta(key, value) VALUES ('full_history_backtest_summary', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(summary, ensure_ascii=False),),
        )
        conn.commit()

    t_str = f"{holdout_t:.2f}" if holdout_t is not None else "-"
    print(f"n={s.n} hit={s.hit_rate*100:.1f}% ROI={s.roi_pct:+.1f}% "
          f"(reserva: n={s_holdout.n} ROI={s_holdout.roi_pct:+.1f}% t={t_str} desde {holdout_start}) -- guardado en bball_meta.")


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m bball.cli")
    sub = p.add_subparsers(dest="command", required=True)

    p_disc = sub.add_parser("discover-leagues", help="Busca NBA/WNBA/Euroliga/etc barriendo sport_id candidatos")
    p_disc.add_argument("--sport-ids", help="Lista separada por comas, p.ej. 18,19,20 (por defecto 1..40)")
    p_disc.set_defaults(func=cmd_discover_leagues)

    p_raw = sub.add_parser("raw", help="Llamada cruda a cualquier endpoint de BetsAPI (pega token automaticamente)")
    p_raw.add_argument("path", help="p.ej. /v3/events/ended")
    p_raw.add_argument("--params", help="k=v,k2=v2 (sin el token, se añade solo)")
    p_raw.add_argument("--max-chars", type=int, default=20000)
    p_raw.add_argument("--no-cache", action="store_true")
    p_raw.set_defaults(func=cmd_raw)

    p_ended = sub.add_parser("ended", help="Partidos terminados de una liga en un dia, con marcador")
    p_ended.add_argument("--sport-id", type=int, required=True)
    p_ended.add_argument("--league-id", required=True)
    p_ended.add_argument("--day", required=True, help="YYYYMMDD")
    p_ended.add_argument("--limit", type=int, default=20)
    p_ended.add_argument("--full-first", action="store_true", help="Ademas, vuelca el JSON crudo del primer evento")
    p_ended.set_defaults(func=cmd_ended)

    p_lod = sub.add_parser("leagues-on-day", help="Resumen compacto de ligas con partidos ese dia (sin necesitar league_id)")
    p_lod.add_argument("--sport-id", type=int, required=True)
    p_lod.add_argument("--day", required=True, help="YYYYMMDD")
    p_lod.set_defaults(func=cmd_leagues_on_day)

    p_collect = sub.add_parser("collect", help="Descarga partidos+cuotas de totales para un rango de fechas")
    p_collect.add_argument("--start", required=True, help="YYYY-MM-DD")
    p_collect.add_argument("--end", required=True, help="YYYY-MM-DD")
    p_collect.add_argument("--leagues", help="NBA,WNBA,EUROLEAGUE (por defecto todas)")
    p_collect.add_argument("--no-cache", action="store_true")
    p_collect.set_defaults(func=cmd_collect)

    p_bt = sub.add_parser("backtest", help="Corre la teoria de totales sobre lo ya recolectado (sin red)")
    p_bt.add_argument("--leagues", help="NBA,WNBA,EUROLEAGUE (por defecto todas)")
    p_bt.add_argument("--windows", default="5,10,15,20", help="Valores de N a barrer")
    p_bt.add_argument("--thresholds", default="3,5,8,10,12,15", help="Valores de colchon minimo a barrer")
    p_bt.set_defaults(func=cmd_backtest)

    p_bts = sub.add_parser("backtest-split", help="Como backtest, pero separando busqueda (elegir) de reserva (comprobar, nunca elegir)")
    p_bts.add_argument("--leagues", help="NBA,WNBA,EUROLEAGUE (por defecto todas)")
    p_bts.add_argument("--windows", default="5,10,15,20")
    p_bts.add_argument("--thresholds", default="3,5,8,10,12,15")
    p_bts.add_argument("--holdout-start", required=True, help="YYYY-MM-DD -- todo desde aqui es reserva, nunca se usa para elegir")
    p_bts.add_argument("--min-holdout-n", type=int, default=5)
    p_bts.set_defaults(func=cmd_backtest_split)

    p_risk = sub.add_parser("risk", help="Racha de perdidas, drawdown y Monte Carlo de banca para un (N, umbral) concreto")
    p_risk.add_argument("--leagues", help="NBA,WNBA,EUROLEAGUE (por defecto todas)")
    p_risk.add_argument("--window", type=int, required=True)
    p_risk.add_argument("--threshold", type=float, required=True)
    p_risk.add_argument("--sims", type=int, default=5000)
    p_risk.add_argument("--stake-fraction", type=float, default=0.02, help="Fraccion de la banca actual apostada por pick (0.02 = 2%%)")
    p_risk.add_argument("--ruin-threshold", type=float, default=0.5, help="Fraccion de la banca inicial que cuenta como 'ruina' (0.5 = cae a la mitad)")
    p_risk.set_defaults(func=cmd_risk)

    p_scan = sub.add_parser("scan", help="Una pasada del scanner en vivo (collect reciente + liquida + busca picks nuevos)")
    p_scan.set_defaults(func=cmd_scan)

    p_promote = sub.add_parser("promote", help="Fija la estrategia activa (N, umbral, ligas) que usa el scanner en vivo")
    p_promote.add_argument("--window", type=int, required=True)
    p_promote.add_argument("--threshold", type=float, required=True)
    p_promote.add_argument("--leagues", help="NBA,WNBA,EUROLEAGUE (por defecto todas)")
    p_promote.set_defaults(func=cmd_promote)

    p_active = sub.add_parser("active", help="Muestra la estrategia activa actual")
    p_active.set_defaults(func=cmd_active)

    p_bsum = sub.add_parser("backtest-summary", help="Corre la estrategia activa sobre todo el historico y cachea el resumen para el dashboard web")
    p_bsum.add_argument("--window", type=int, help="Por defecto, el de la estrategia activa")
    p_bsum.add_argument("--threshold", type=float, help="Por defecto, el de la estrategia activa")
    p_bsum.add_argument("--leagues", help="Por defecto, las de la estrategia activa")
    p_bsum.add_argument("--holdout-start", help="YYYY-MM-DD; por defecto, ultimos --holdout-days del historico cargado")
    p_bsum.add_argument("--holdout-days", type=int, default=30)
    p_bsum.add_argument("--sims", type=int, default=3000)
    p_bsum.set_defaults(func=cmd_backtest_summary)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
