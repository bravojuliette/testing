"""CLI del sistema de basketball. Fase actual: exploratoria -- descubrir
sport_id/league_id reales en BetsAPI y la forma del mercado de totales antes
de construir el collector/backtest definitivos (ver bball/sources/betsapi.py
para el porque). Se corre casi siempre via GitHub Actions (unico sitio con
salida a BetsAPI desde este repo ahora mismo), nunca desde esta sesion.

Uso:
    python -m bball.cli discover-leagues [--sport-ids 1,2,3] [--day YYYYMMDD]
    python -m bball.cli raw /v3/events/ended --params sport_id=18,day=20260827
    python -m bball.cli ended --sport-id 18 --league-id 12345 --day 20260827 [--full-first]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from . import config, db
from .sources.betsapi import discover_leagues, fetch_ended
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

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
