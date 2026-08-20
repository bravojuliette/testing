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

from . import db as dbmod
from .backtest.collect import collect_range
from .backtest.sweep import grid_sweep, print_leaderboard, run_experiment
from .model.active import load_active_params, save_active_params
from .model.params import BASELINE, StrategyParams
from .live.scan import run_live_scan


def _d(s: str) -> date:
    return date.fromisoformat(s)


def cmd_collect(args: argparse.Namespace) -> None:
    collect_range(_d(args.start), _d(args.end), fetch_odds=not args.no_odds)


def cmd_sweep(args: argparse.Namespace) -> None:
    base = load_active_params() if args.from_active else BASELINE
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
    params = load_active_params() if args.from_active else BASELINE
    with dbmod.get_conn() as conn:
        res = run_experiment(
            conn, params, _d(args.warmup_start), _d(args.train_start), _d(args.test_start), _d(args.test_end),
            name=args.name or params.name,
        )
    print(json.dumps({"train": res["train"], "test": res["test"]}, indent=2, default=str))


def cmd_promote(args: argparse.Namespace) -> None:
    if args.params_json:
        params = StrategyParams.from_json(args.params_json)
    elif args.experiment_id:
        with dbmod.get_conn() as conn:
            row = conn.execute("SELECT params_json FROM experiments WHERE id = ?", (args.experiment_id,)).fetchone()
        if not row:
            print(f"No existe experiment id={args.experiment_id}", file=sys.stderr)
            sys.exit(1)
        params = StrategyParams.from_json(row["params_json"])
    else:
        print("Especifica --experiment-id o --params-json", file=sys.stderr)
        sys.exit(1)
    save_active_params(params)
    print(f"Estrategia activa actualizada: {params.name} ({params.hash()})")


def cmd_scan(args: argparse.Namespace) -> None:
    summary = run_live_scan(dry_run_email=args.dry_run_email)
    print(json.dumps(summary, indent=2))


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

    rp = sub.add_parser("report", help="Ultimos picks en vivo y su resultado")
    rp.add_argument("--limit", type=int, default=50)
    rp.add_argument("--days", type=int, default=30)
    rp.set_defaults(func=cmd_report)

    return p


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
