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


def cmd_collect_venues(args: argparse.Namespace) -> None:
    """Baja estadio/ciudad (event/view) de los partidos que no lo tengan."""
    from .backtest.collect import collect_venues

    with db.get_conn() as conn:
        client = _client(conn)
        print(f"Listo: {collect_venues(client, conn, league_like=args.league_like)}")


def cmd_dump_local(args: argparse.Namespace) -> None:
    """Vuelca la base remota (Turso) a un SQLite local, tabla a tabla, para
    que TODO el analisis corra en local y la remota quede solo para
    recolectar y servir el dashboard. Razon: dos dias de barridos analiticos
    contra la remota fundieron la cuota mensual de lecturas del plan.

    Por defecto omite bball_http_cache (gigante y solo necesaria para
    reparses); --with-cache la incluye."""
    import sqlite3 as sq

    tablas = ["bball_games", "bball_odds", "bball_leagues", "bball_meta",
              "bball_venues", "bball_picks", "bball_live_snapshots"]
    if args.with_cache:
        tablas.append("bball_http_cache")
    destino = sq.connect(args.out)
    with db.get_conn() as remota:
        for t in tablas:
            filas = remota.execute(f"SELECT * FROM {t}").fetchall()
            if not filas:
                print(f"  {t}: vacia")
                continue
            cols = list(filas[0].keys())
            ddl = ", ".join(f'"{c}"' for c in cols)
            destino.execute(f'DROP TABLE IF EXISTS {t}')
            destino.execute(f'CREATE TABLE {t} ({ddl})')
            destino.executemany(
                f'INSERT INTO {t} VALUES ({",".join("?" * len(cols))})',
                [tuple(r[c] for c in cols) for r in filas])
            destino.commit()
            print(f"  {t}: {len(filas)} filas")
    destino.close()
    print(f"volcado en {args.out}")


def cmd_collect_chicas(args: argparse.Namespace) -> None:
    """Barrido de LIGAS CHICAS (todas las ligas reales de basket de un rango
    de dias, con resumen + historial en vivo por partido). Correr --local."""
    from .backtest.collect import collect_all_range

    with db.get_conn() as conn:
        client = _client(conn)
        print(f"Listo: {collect_all_range(client, conn, date_cls.fromisoformat(args.start), date_cls.fromisoformat(args.end), use_cache=not args.no_cache)}")


def cmd_backfill_hist(args: argparse.Namespace) -> None:
    """Historial de cuotas (/v2/event/odds, serie completa con cambios en
    vivo) de los partidos ya recolectados -> bball_odds_hist. Una llamada por
    partido; resumible. Correr en el workflow bball_local (sin Turso)."""
    from .backtest.collect import backfill_hist

    lids = None
    if args.leagues:
        names = [n.strip().upper() for n in args.leagues.split(",")]
        unknown = [n for n in names if n not in config.LEAGUES]
        if unknown:
            raise SystemExit(f"Liga(s) desconocida(s): {unknown}. Conocidas: {list(config.LEAGUES)}")
        lids = [config.LEAGUES[n] for n in names]
    with db.get_conn() as conn:
        client = _client(conn)
        print(f"Listo: {backfill_hist(client, conn, league_ids=lids, limit=args.limit, use_cache=not args.no_cache)}")


def cmd_reparse_hist(args: argparse.Namespace) -> None:
    """Reconstruye bball_odds_hist con TODOS los mercados (cuartos y mitades
    incluidos) desde la cache local de /v2/event/odds -- cero llamadas."""
    from .backtest.collect import reparse_hist

    with db.get_conn() as conn:
        print(f"Listo: {reparse_hist(conn)}")


def cmd_export_compact(args: argparse.Namespace) -> None:
    """Volcado compacto de la base de recoleccion actual a otro SQLite: las
    tablas de analisis sin la cache HTTP cruda y sin raw_json en bball_odds.
    Es el canal de vuelta hacia la sesion de trabajo (se commitea .gz en la
    rama; la sesion no puede bajar artefactos de Actions)."""
    import sqlite3 as sq

    drop_cols = {"bball_odds": {"raw_json"}}
    tablas = ["bball_games", "bball_odds", "bball_leagues", "bball_venues", "bball_odds_hist"]
    dst = sq.connect(args.out)
    with db.get_conn() as src:
        for t in tablas:
            try:
                filas = src.execute(f"SELECT * FROM {t}").fetchall()
            except Exception as exc:
                print(f"  {t}: no legible ({str(exc)[:60]})")
                continue
            if not filas:
                print(f"  {t}: vacia")
                continue
            cols = [c for c in filas[0].keys() if c not in drop_cols.get(t, set())]
            ddl = ", ".join(f'"{c}"' for c in cols)
            dst.execute(f'DROP TABLE IF EXISTS {t}')
            dst.execute(f'CREATE TABLE {t} ({ddl})')
            dst.executemany(
                f'INSERT INTO {t} VALUES ({",".join("?" * len(cols))})',
                [tuple(r[c] for c in cols) for r in filas])
            dst.commit()
            print(f"  {t}: {len(filas)} filas")
    dst.close()
    print(f"volcado compacto en {args.out}")


def cmd_event_finals(args: argparse.Namespace) -> None:
    """Baja el estado/resultado final de event_ids concretos (event/view en
    lotes de 10). A diferencia de 'raw', los ids van separados por ':' para
    esquivar al parser de --params, que trocea por comas."""
    from .sources.betsapi import fetch_event_view

    ids = [x for x in args.ids.split(":") if x]
    with db.get_conn() as conn:
        client = _client(conn)
        for i in range(0, len(ids), 10):
            js = fetch_event_view(client, ids[i:i + 10], use_cache=not args.no_cache)
            res = js.get("results") or []
            if isinstance(res, dict):
                res = [res]
            for ev in res:
                print(f"{ev.get('id')} status={ev.get('time_status')} ss={ev.get('ss')!r} "
                      f"{(ev.get('home') or {}).get('name','?')} vs {(ev.get('away') or {}).get('name','?')}")


def cmd_probe_hist(args: argparse.Namespace) -> None:
    """Sonda de /v2/event/odds sobre partidos TERMINADOS: mide cuantas
    entradas devuelve por mercado, si la serie llega hasta antes del pitido
    inicial o viene truncada a lo mas reciente, y si since_time/source
    cambian la ventana. De esto depende cuantas llamadas cuesta reconstruir
    el historial en vivo de un partido ya jugado (backfill local)."""
    from .sources.betsapi import fetch_ended_all_leagues

    with db.get_conn() as conn:
        client = _client(conn)
        rows = fetch_ended_all_leagues(client, config.SPORT_ID, args.day, use_cache=False, max_pages=1)
        malas = ("ebasketball", "h2h gg", "esports")
        rows = [e for e in rows if e.get("ss")
                and not any(x in ((e.get("league") or {}).get("name") or "").lower() for x in malas)]
        print(f"{len(rows)} terminados reales el {args.day} (pagina 1); sondeo {args.n}")
        for e in rows[: args.n]:
            eid = str(e.get("id"))
            ts = int(e.get("time") or 0)
            lg = (e.get("league") or {}).get("name")
            print(f"\n== {eid} [{lg}] {(e.get('home') or {}).get('name')} vs "
                  f"{(e.get('away') or {}).get('name')} ss={e.get('ss')!r} start_ts={ts}")
            js = client.bets("/v2/event/odds", {"event_id": eid}, prefix="probe_hist", use_cache=False)
            odds = (js.get("results") or {}).get("odds") or {}
            for mk, serie in sorted(odds.items()):
                if not isinstance(serie, list) or not serie:
                    continue
                ats = [int(x.get("add_time") or 0) for x in serie]
                pre = sum(1 for a in ats if ts and a < ts)
                con_ss = sum(1 for x in serie if x.get("ss"))
                print(f"  {mk}: {len(serie)} entradas, rel_inicio {min(ats) - ts}..{max(ats) - ts}s, "
                      f"pre_partido={pre}, con_marcador={con_ss}")
            js2 = client.bets("/v2/event/odds", {"event_id": eid, "since_time": ts}, prefix="probe_hist", use_cache=False)
            s2 = ((js2.get("results") or {}).get("odds") or {}).get(config.TOTALS_MARKET_KEY) or []
            if s2:
                a2 = [int(x.get("add_time") or 0) for x in s2]
                print(f"  since_time=inicio -> totales: {len(s2)} entradas, rel {min(a2) - ts}..{max(a2) - ts}s")
            else:
                print("  since_time=inicio -> totales: vacio")
            js3 = client.bets("/v2/event/odds", {"event_id": eid, "source": "bwin"}, prefix="probe_hist", use_cache=False)
            s3 = ((js3.get("results") or {}).get("odds") or {}).get(config.TOTALS_MARKET_KEY) or []
            print(f"  source=bwin -> totales: {len(s3)} entradas")


def cmd_probe_sources(args: argparse.Namespace) -> None:
    """¿Que fuentes acepta /v2/event/odds y que mercados trae cada una EN
    VIVO? Decide si el lead-lag en juego es medible (hacen falta >=2 fuentes
    con el mismo mercado y entradas con marcador)."""
    from .sources.betsapi import SOURCES_CANDIDATAS, fetch_odds_history_source

    fuentes = args.sources.split(",") if args.sources else list(SOURCES_CANDIDATAS)
    with db.get_conn() as conn:
        client = _client(conn)
        for eid in args.events.split(":"):
            print(f"\n===== evento {eid} =====")
            print(f"{'fuente':14s}{'estado':22s}{'mercado':8s}{'entradas':>9s}{'en_vivo':>9s}{'span_min':>9s}")
            for src in fuentes:
                try:
                    js = fetch_odds_history_source(client, eid, src, use_cache=False)
                except Exception as exc:
                    print(f"{src:14s}{('EXC ' + str(exc)[:16]):22s}"); continue
                if not js.get("success"):
                    print(f"{src:14s}{('ERROR ' + str(js.get('error'))[:14]):22s}"); continue
                odds = ((js.get("results") or {}).get("odds") or {})
                if not odds:
                    print(f"{src:14s}{'OK (sin mercados)':22s}"); continue
                for mk in sorted(odds):
                    ent = odds[mk] or []
                    vivo = [e for e in ent if e.get("ss")]
                    ts = [int(e["add_time"]) for e in ent if e.get("add_time")]
                    span = (max(ts) - min(ts)) / 60 if len(ts) > 1 else 0
                    print(f"{src:14s}{'OK':22s}{mk:8s}{len(ent):9d}{len(vivo):9d}{span:9.0f}")


def cmd_cosecha_src(args: argparse.Namespace) -> None:
    """Baja la serie PROPIA de cada casa (source=...) para partidos ya
    terminados. Una llamada por (partido, casa) trae el partido entero, asi
    que no hace falta sondear en vivo: esto es historico y resumible."""
    from .backtest.cosecha import FUENTES_VIVO, cosechar_rango

    from .backtest.cosecha import cosechar

    fuentes = tuple(args.sources.split(",")) if args.sources else FUENTES_VIVO
    ligas = args.leagues.split(",") if args.leagues else None
    with db.get_conn() as conn:
        client = _client(conn)
        if args.events_file:
            # Con las lecturas de Turso bloqueadas, la base del runner arranca
            # vacia y no puede decir que partidos existen: la lista de ids se
            # calcula aqui fuera, contra el volcado local, y se commitea.
            eids = [ln.strip() for ln in open(args.events_file) if ln.strip()
                    and not ln.startswith("#")]
            # el fichero va en orden de fecha ascendente; --offset permite
            # trocear la cosecha en runs encadenados sin repetir llamadas
            if args.offset:
                eids = eids[args.offset:]
            if args.limit:
                eids = eids[:args.limit]
            print(f"cosecha: {len(eids)} partidos de {args.events_file} x "
                  f"{len(fuentes)} fuentes = hasta {len(eids) * len(fuentes)} llamadas", flush=True)
            st = cosechar(client, conn, eids, fuentes=fuentes, use_cache=not args.no_cache)
        else:
            st = cosechar_rango(client, conn, args.start, args.end, leagues=ligas,
                                limit=args.limit, fuentes=fuentes,
                                use_cache=not args.no_cache)
    print(f"cosecha: {st}")
    for src, d in sorted(st["por_fuente"].items()):
        cob = d["eventos"]
        print(f"  {src:10s} eventos_con_serie={cob:5d} filas={d['filas']:8d} "
              f"filas_EN_JUEGO={d['vivas']:8d}")


def cmd_scan_q1(args: argparse.Namespace) -> None:
    """Scanner de lineas en vivo. Sin --loop-minutes hace UNA pasada; con el,
    repite cada --every segundos hasta agotar el tiempo (pensado para un job
    de Actions lanzado antes de una ventana de partidos)."""
    import time as _t

    from .live.q1 import scan_inplay

    fin = _t.time() + args.loop_minutes * 60 if args.loop_minutes else 0
    with db.get_conn() as conn:
        client = _client(conn)
        while True:
            print(f"{datetime.now(timezone.utc).isoformat()} {scan_inplay(client, conn)}", flush=True)
            if _t.time() + args.every >= fin:
                break
            _t.sleep(args.every)


def cmd_reparse_kickoff(args: argparse.Namespace) -> None:
    """Re-extrae de la cache HTTP el snapshot 'kickoff' (linea de cierre) que
    el parser original ignoraba. Sin red a BetsAPI -- solo lee bball_http_cache
    y upserta en bball_odds."""
    from .backtest.collect import reparse_kickoff

    with db.get_conn() as conn:
        stats = reparse_kickoff(conn)
    print(f"Listo: {stats}")


def cmd_reparse_markets(args: argparse.Namespace) -> None:
    """Extrae de la cache los mercados de ganador (18_1) y handicap (18_2)
    al cierre, ya normalizados local/visitante. Sin red."""
    from .backtest.collect import reparse_moneyline_spread

    with db.get_conn() as conn:
        print(f"Listo: {reparse_moneyline_spread(conn)}")


def cmd_fix_home_away(args: argparse.Namespace) -> None:
    """Migracion de una vez: normaliza local/visitante en NBA/WNBA."""
    from .backtest.collect import fix_home_away

    with db.get_conn() as conn:
        print(f"Resultado: {fix_home_away(conn)}")


def cmd_backtest(args: argparse.Namespace) -> None:
    leagues = [n.strip().upper() for n in args.leagues.split(",")] if args.leagues else None
    windows = [int(x) for x in args.windows.split(",")]
    thresholds = [float(x) for x in args.thresholds.split(",")]
    with db.get_conn() as conn:
        games = load_games(conn, leagues=leagues)
        odds_by_event = load_totals_odds(conn, book=getattr(args, "book", None))
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
        odds_by_event = load_totals_odds(conn, book=getattr(args, "book", None))
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
        odds_by_event = load_totals_odds(conn, book=getattr(args, "book", None))
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
    params = {"n_window": args.window, "threshold": args.threshold, "leagues": leagues, "book": args.book or None}
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
    book = args.book if getattr(args, "book", None) is not None else active.get("book")

    with db.get_conn() as conn:
        games = load_games(conn, leagues=leagues)
        odds_by_event = load_totals_odds(conn, book=book)

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
        "params": {"n_window": n_window, "threshold": threshold, "leagues": leagues, "book": book},
        "n": s.n, "hits": s.wins, "hitRate": s.hit_rate, "roi": s.roi_pct, "pnlTotal": s.pnl, "meanOdds": s.mean_odds,
        "search": {"n": s_search.n, "hitRate": s_search.hit_rate, "roi": s_search.roi_pct, "meanOdds": s_search.mean_odds},
        "holdout": {"n": s_holdout.n, "hitRate": s_holdout.hit_rate, "roi": s_holdout.roi_pct, "start": holdout_start, "t": holdout_t, "meanOdds": s_holdout.mean_odds},
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

    # Clave distinta por casa -- asi el dashboard puede guardar/mostrar a la
    # vez el resumen "mejor cuota entre todas" y el de una casa concreta
    # (p.ej. Bwin), sin que uno pise al otro cada vez que se recalcula.
    meta_key = "full_history_backtest_summary" if not book else f"full_history_backtest_summary__{book}"
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO bball_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (meta_key, json.dumps(summary, ensure_ascii=False)),
        )
        conn.commit()

    t_str = f"{holdout_t:.2f}" if holdout_t is not None else "-"
    book_str = f" book={book}" if book else " (mejor cuota entre todas)"
    print(f"n={s.n} hit={s.hit_rate*100:.1f}% ROI={s.roi_pct:+.1f}%{book_str} "
          f"(reserva: n={s_holdout.n} ROI={s_holdout.roi_pct:+.1f}% t={t_str} desde {holdout_start}) -- guardado en bball_meta['{meta_key}'].")


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m bball.cli")
    p.add_argument("--local", action="store_true",
                   help="Fuerza SQLite local (data/bball.db) aunque TURSO_DATABASE_URL este definida -- "
                        "para recolectar sin gastar cuota de Turso (va ANTES del subcomando)")
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

    p_cv = sub.add_parser("collect-venues", help="Baja estadio/ciudad de event/view para partidos sin ellos")
    p_cv.add_argument("--league-like", default="%NCAA%", help="filtro SQL LIKE sobre league_name")
    p_cv.set_defaults(func=cmd_collect_venues)

    p_dl = sub.add_parser("dump-local", help="Vuelca la base remota a un SQLite local para analizar sin gastar lecturas de Turso")
    p_dl.add_argument("--out", default="bball_local.db")
    p_dl.add_argument("--with-cache", action="store_true")
    p_dl.set_defaults(func=cmd_dump_local)

    p_cch = sub.add_parser("collect-chicas", help="Barrido de todas las ligas chicas (partidos + cuotas + historial en vivo)")
    p_cch.add_argument("--start", required=True, help="YYYY-MM-DD")
    p_cch.add_argument("--end", required=True, help="YYYY-MM-DD")
    p_cch.add_argument("--no-cache", action="store_true")
    p_cch.set_defaults(func=cmd_collect_chicas)

    p_bh = sub.add_parser("backfill-hist", help="Serie historica de cuotas (con cambios en vivo) por partido -> bball_odds_hist")
    p_bh.add_argument("--leagues", help="NBA,WNBA,... (por defecto todas las recolectadas)")
    p_bh.add_argument("--limit", type=int, default=0, help="tope de partidos en esta corrida (0 = todos)")
    p_bh.add_argument("--no-cache", action="store_true")
    p_bh.set_defaults(func=cmd_backfill_hist)

    p_rh = sub.add_parser("reparse-hist", help="Reconstruye bball_odds_hist con todos los mercados desde la cache local (sin red)")
    p_rh.set_defaults(func=cmd_reparse_hist)

    p_ec = sub.add_parser("export-compact", help="Volcado compacto (sin cache cruda) de la base actual a otro SQLite")
    p_ec.add_argument("--out", default="compact.db")
    p_ec.set_defaults(func=cmd_export_compact)

    p_ef = sub.add_parser("event-finals", help="Estado/resultado de event_ids concretos (separados por ':')")
    p_ef.add_argument("--ids", required=True)
    p_ef.add_argument("--no-cache", action="store_true")
    p_ef.set_defaults(func=cmd_event_finals)

    p_ph = sub.add_parser("probe-hist", help="Sonda: profundidad real de /v2/event/odds en partidos terminados")
    p_ph.add_argument("--day", default=(datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y%m%d"))
    p_ph.add_argument("--n", type=int, default=3)
    p_ph.set_defaults(func=cmd_probe_hist)

    p_ps = sub.add_parser("probe-sources", help="Que fuentes acepta /v2/event/odds y que mercados trae cada una (decide si el lead-lag EN VIVO es medible)")
    p_ps.add_argument("--events", required=True, help="event_ids separados por ':'")
    p_ps.add_argument("--sources", help="lista separada por comas; por defecto SOURCES_CANDIDATAS")
    p_ps.set_defaults(func=cmd_probe_sources)

    p_cs = sub.add_parser("cosecha-src", help="Serie historica POR CASA (/v2/event/odds?source=) de partidos terminados -- el dato real para el lead-lag en juego")
    p_cs.add_argument("--start", help="YYYY-MM-DD (no hace falta con --events-file)")
    p_cs.add_argument("--end", help="YYYY-MM-DD (no hace falta con --events-file)")
    p_cs.add_argument("--events-file", help="fichero con un event_id por linea (evita leer bball_games)")
    p_cs.add_argument("--leagues", help="nombres de liga separados por comas (por defecto, todas)")
    p_cs.add_argument("--sources", help="lista separada por comas; por defecto FUENTES_VIVO")
    p_cs.add_argument("--limit", type=int, default=0)
    p_cs.add_argument("--offset", type=int, default=0, help="salta los N primeros ids de --events-file")
    p_cs.add_argument("--no-cache", action="store_true")
    p_cs.set_defaults(func=cmd_cosecha_src)

    p_sq = sub.add_parser("scan-q1", help="Foto de las lineas de total EN VIVO de los partidos en juego")
    p_sq.add_argument("--loop-minutes", type=int, default=0, help="repetir durante N minutos (0 = una pasada)")
    p_sq.add_argument("--every", type=int, default=600, help="segundos entre pasadas en modo bucle")
    p_sq.set_defaults(func=cmd_scan_q1)

    p_rk = sub.add_parser("reparse-kickoff", help="Re-extrae de la cache el snapshot kickoff (linea de cierre) ignorado por el parser original")
    p_rk.set_defaults(func=cmd_reparse_kickoff)

    p_rm = sub.add_parser("reparse-markets", help="Extrae de la cache ganador (18_1) y handicap (18_2) al cierre, normalizados")
    p_rm.set_defaults(func=cmd_reparse_markets)

    p_fha = sub.add_parser("fix-home-away", help="Migracion: normaliza local/visitante en las ligas listadas como 'visitante @ local' (NBA/WNBA)")
    p_fha.set_defaults(func=cmd_fix_home_away)


    p_bt = sub.add_parser("backtest", help="Corre la teoria de totales sobre lo ya recolectado (sin red)")
    p_bt.add_argument("--leagues", help="NBA,WNBA,EUROLEAGUE (por defecto todas)")
    p_bt.add_argument("--windows", default="5,10,15,20", help="Valores de N a barrer")
    p_bt.add_argument("--thresholds", default="3,5,8,10,12,15", help="Valores de colchon minimo a barrer")
    p_bt.add_argument("--book", help="Restringe a una sola casa (p.ej. BWin) en vez de la mejor cuota entre todas")
    p_bt.set_defaults(func=cmd_backtest)

    p_bts = sub.add_parser("backtest-split", help="Como backtest, pero separando busqueda (elegir) de reserva (comprobar, nunca elegir)")
    p_bts.add_argument("--leagues", help="NBA,WNBA,EUROLEAGUE (por defecto todas)")
    p_bts.add_argument("--windows", default="5,10,15,20")
    p_bts.add_argument("--thresholds", default="3,5,8,10,12,15")
    p_bts.add_argument("--holdout-start", required=True, help="YYYY-MM-DD -- todo desde aqui es reserva, nunca se usa para elegir")
    p_bts.add_argument("--min-holdout-n", type=int, default=5)
    p_bts.add_argument("--book", help="Restringe a una sola casa (p.ej. BWin) en vez de la mejor cuota entre todas")
    p_bts.set_defaults(func=cmd_backtest_split)

    p_risk = sub.add_parser("risk", help="Racha de perdidas, drawdown y Monte Carlo de banca para un (N, umbral) concreto")
    p_risk.add_argument("--leagues", help="NBA,WNBA,EUROLEAGUE (por defecto todas)")
    p_risk.add_argument("--window", type=int, required=True)
    p_risk.add_argument("--threshold", type=float, required=True)
    p_risk.add_argument("--sims", type=int, default=5000)
    p_risk.add_argument("--stake-fraction", type=float, default=0.02, help="Fraccion de la banca actual apostada por pick (0.02 = 2%%)")
    p_risk.add_argument("--ruin-threshold", type=float, default=0.5, help="Fraccion de la banca inicial que cuenta como 'ruina' (0.5 = cae a la mitad)")
    p_risk.add_argument("--book", help="Restringe a una sola casa (p.ej. BWin) en vez de la mejor cuota entre todas")
    p_risk.set_defaults(func=cmd_risk)

    p_scan = sub.add_parser("scan", help="Una pasada del scanner en vivo (collect reciente + liquida + busca picks nuevos)")
    p_scan.set_defaults(func=cmd_scan)

    p_promote = sub.add_parser("promote", help="Fija la estrategia activa (N, umbral, ligas) que usa el scanner en vivo")
    p_promote.add_argument("--window", type=int, required=True)
    p_promote.add_argument("--threshold", type=float, required=True)
    p_promote.add_argument("--leagues", help="NBA,WNBA,EUROLEAGUE (por defecto todas)")
    p_promote.add_argument("--book", help="Restringe el scanner en vivo a una sola casa (p.ej. BWin) en vez de la mejor cuota entre todas")
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
    p_bsum.add_argument("--book", help="Por defecto, la de la estrategia activa (ninguna = mejor cuota entre todas)")
    p_bsum.set_defaults(func=cmd_backtest_summary)

    args = p.parse_args()
    if args.local:
        # db.connect() consulta el entorno en cada llamada: vaciarlo aqui
        # desvia TODO el proceso a data/bball.db sin tocar ninguna otra ruta.
        import os as _os
        _os.environ.pop("TURSO_DATABASE_URL", None)
        _os.environ.pop("TURSO_AUTH_TOKEN", None)
    args.func(args)


if __name__ == "__main__":
    main()
