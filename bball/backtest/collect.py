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


MIN_COINCIDENCIAS = 5   # casas que deben coincidir para dar por bueno un emparejamiento


def reparse_moneyline_spread(conn, batch: int = 200) -> dict:
    """Extrae de bball_http_cache los mercados de GANADOR (18_1) y HANDICAP
    (18_2) al cierre ('kickoff'), que el parser original ignoraba, sin una
    sola llamada nueva a BetsAPI. Mismo mapeo por huella digital que
    reparse_kickoff.

    Convencion de almacenamiento (bball_odds no tiene columnas home/away):
        over_odds  = cuota del LOCAL
        under_odds = cuota del VISITANTE
        line       = handicap aplicado al LOCAL (0 en el 1X2)
    El intercambio local/visitante NO se aplica por liga sino POR CASA: ver
    config.odds_need_swap. BetsAPI invierte los equipos en el feed de
    PARTIDOS de las ligas 'visitante @ local' (de ahi fix_home_away), pero en
    el de CUOTAS solo lo hacen algunas casas (BWin y Bet365); el resto ya da
    el local de verdad. Aplicarlo a todas dejaba a Pinnacle, Betsson, UniBet
    y DafaBet con el favorito de cierre ganando el 31% en NBA.
    El mercado de totales es simetrico y nada de esto le afecta.
    """
    ts_by_event, league_by_event = {}, {}
    for r in conn.execute("SELECT event_id, time_ts, league_name FROM bball_games").fetchall():
        ts_by_event[r["event_id"]] = r["time_ts"]
        league_by_event[r["event_id"]] = r["league_name"]

    # Emparejar cada body de la cache con SU partido. La cache se indexa por
    # sha1(url+params+token) y aqui no hay token, asi que hay que deducirlo de
    # las cuotas. Se usa el CONJUNTO COMPLETO de tuplas (casa, hora, linea) del
    # mercado de totales 'start', que en la ingesta se escribio desde este
    # mismo body con su event_id correcto -- un body trae ~15 casas, asi que
    # el conjunto identifica al partido sin ambigüedad.
    #
    # Antes se votaba tupla a tupla y bastaban 2 votos. Con NBA (8 partidos al
    # dia) funcionaba; con NCAAB (100+ al dia, muchos con la misma linea y
    # horas parecidas) colisionaba, y el resultado fue que las cuotas de
    # ganador se pegaban a partidos EQUIVOCADOS: el favorito de cierre solo
    # ganaba el 41% en NCAAB, y casas distintas señalaban favoritos distintos
    # en el 60% de los partidos.
    huella_por_evento: dict[str, frozenset] = {}
    acum: dict[str, set] = {}
    for r in conn.execute(
        "SELECT event_id, book, line, captured_at FROM bball_odds "
        "WHERE market = ? AND snapshot = 'start' AND captured_at IS NOT NULL",
        (config.TOTALS_MARKET_KEY,),
    ).fetchall():
        acum.setdefault(r["event_id"], set()).add(
            (r["book"], str(r["captured_at"]), float(r["line"])))
    # indice tupla -> partidos, para puntuar por tamaño de la interseccion
    por_tupla: dict[tuple, set] = {}
    for eid, tuplas in acum.items():
        if len(tuplas) < MIN_COINCIDENCIAS:
            continue          # muy pocas casas: no identifica nada
        huella_por_evento[eid] = frozenset(tuplas)
        for t in tuplas:
            por_tupla.setdefault(t, set()).add(eid)

    stats = {"bodies": 0, "mapped": 0, "moneyline_rows": 0, "spread_rows": 0}
    offset = 0
    while True:
        rows = conn.execute(
            "SELECT body FROM bball_http_cache WHERE prefix='odds_summary' LIMIT ? OFFSET ?",
            (batch, offset),
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
            results = js.get("results") or {}
            tuplas = set()
            for book, b in results.items():
                if not isinstance(b, dict):
                    continue
                e = ((b.get("odds") or {}).get("start") or {}).get(config.TOTALS_MARKET_KEY)
                if not isinstance(e, dict) or e.get("add_time") is None:
                    continue
                try:
                    tuplas.add((book, str(int(e["add_time"])), float(e["handicap"])))
                except (KeyError, TypeError, ValueError):
                    continue
            puntos: dict[str, int] = {}
            for t in tuplas:
                for cand in por_tupla.get(t, ()):
                    puntos[cand] = puntos.get(cand, 0) + 1
            if not puntos:
                stats["sin_mapear"] = stats.get("sin_mapear", 0) + 1
                continue
            orden = sorted(puntos.items(), key=lambda kv: -kv[1])
            eid, mejor = orden[0]
            segundo = orden[1][1] if len(orden) > 1 else 0
            # exigente a proposito: bastantes casas coincidiendo Y el segundo
            # candidato muy por detras. Con 2 votos (el criterio anterior) las
            # cuotas se pegaban a partidos equivocados en NCAAB.
            if mejor < MIN_COINCIDENCIAS or mejor < 2 * segundo:
                stats["ambiguos"] = stats.get("ambiguos", 0) + 1
                continue
            ts = ts_by_event.get(eid)
            if ts is None:
                continue
            stats["mapped"] += 1
            out = []
            for book, b in results.items():
                if not isinstance(b, dict):
                    continue
                for snap in ("kickoff", "start"):
                  ko = (b.get("odds") or {}).get(snap) or {}
                  for mkey, has_hcap in ((config.MONEYLINE_MARKET_KEY, False),
                                         (config.SPREAD_MARKET_KEY, True)):
                    e = ko.get(mkey)
                    if not isinstance(e, dict) or e.get("ss"):
                        continue
                    try:
                        loc, vis = float(e["home_od"]), float(e["away_od"])
                        hcap = float(e["handicap"]) if has_hcap else 0.0
                    except (KeyError, TypeError, ValueError):
                        continue
                    if loc <= 1 or vis <= 1:
                        continue
                    add = e.get("add_time")
                    try:
                        add_i = int(add) if add is not None else None
                    except (TypeError, ValueError):
                        add_i = None
                    if add_i is not None and ts and add_i > ts + 900:
                        continue
                    if config.odds_need_swap(league_by_event.get(eid), book):
                        loc, vis = vis, loc
                        hcap = -hcap
                    out.append((eid, book, mkey, hcap, loc, vis, snap, add_i, None))
                    stats["spread_rows" if has_hcap else "moneyline_rows"] += 1
            if out:
                conn.executemany(
                    "INSERT INTO bball_odds(event_id, book, market, line, over_odds, under_odds, "
                    "snapshot, captured_at, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(event_id, book, market, line, snapshot) DO UPDATE SET "
                    "over_odds=excluded.over_odds, under_odds=excluded.under_odds, "
                    "captured_at=excluded.captured_at",
                    out,
                )
        conn.commit()
        print(f"  {stats['bodies']} bodies -- ganador {stats['moneyline_rows']}, "
              f"handicap {stats['spread_rows']}", flush=True)
    return stats

def collect_venues(client, conn, league_like: str = "%NCAA%", batch: int = 10) -> dict:
    """Baja estadio/ciudad de los partidos que aun no lo tienen, en lotes de
    10 (limite del endpoint). Resumible via cache HTTP igual que collect."""
    from ..sources.betsapi import fetch_event_view

    pendientes = [r["event_id"] for r in conn.execute(
        "SELECT g.event_id FROM bball_games g LEFT JOIN bball_venues v "
        "ON v.event_id = g.event_id WHERE g.league_name LIKE ? AND v.event_id IS NULL "
        "ORDER BY g.date", (league_like,)).fetchall()]
    stats = {"pendientes": len(pendientes), "guardados": 0, "sin_estadio": 0}
    print(f"partidos sin estadio: {len(pendientes)}", flush=True)
    for i in range(0, len(pendientes), batch):
        lote = pendientes[i:i + batch]
        js = fetch_event_view(client, lote)
        res = js.get("results") or []
        if isinstance(res, dict):
            res = [res]
        filas = []
        ahora = datetime.now(timezone.utc).isoformat()
        vistos = set()
        for ev in res:
            if not isinstance(ev, dict):
                continue
            eid = str(ev.get("id"))
            vistos.add(eid)
            std = ((ev.get("extra") or {}).get("stadium_data") or {})
            filas.append((eid, std.get("name"), std.get("city"), ahora))
            if not std.get("city"):
                stats["sin_estadio"] += 1
        # los ids pedidos que no vinieron en la respuesta se marcan sin datos,
        # para no pedirlos en bucle en cada corrida
        for eid in lote:
            if eid not in vistos:
                filas.append((eid, None, None, ahora))
                stats["sin_estadio"] += 1
        conn.executemany(
            "INSERT INTO bball_venues(event_id, stadium, city, fetched_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(event_id) DO UPDATE SET stadium=excluded.stadium, city=excluded.city",
            filas)
        stats["guardados"] += len(filas)
        if (i // batch) % 50 == 0:
            conn.commit()
            print(f"  {i + len(lote)}/{len(pendientes)}", flush=True)
    conn.commit()
    return stats


# ------------------- Backfill del historial de cuotas -------------------------
# /v2/event/odds devuelve la SERIE temporal de cuotas de un evento (cada
# cambio, incluidos los EN VIVO) -- el descubrimiento que hace innecesario
# esperar semanas de scanner prospectivo: los partidos ya jugados tienen su
# historial en vivo guardado en BetsAPI. Se vuelca a bball_odds_hist SIN
# normalizar orientacion (18_1/18_2 vienen en el orden del evento de BetsAPI,
# con todas las trampas documentadas en config.py -- corregir al analizar,
# nunca al ingerir).

HIST_DDL = (
    "CREATE TABLE IF NOT EXISTS bball_odds_hist("
    " event_id TEXT NOT NULL, market TEXT NOT NULL, add_time INTEGER, ss TEXT,"
    " line REAL, over_odds REAL, under_odds REAL, home_odds REAL, away_odds REAL,"
    " source TEXT)"
)


def asegurar_columna_source(conn) -> None:
    """`source` NULL = serie agregada de /v2/event/odds sin parametro (lo
    que baja backfill_hist); `source` = 'bet365'/'bwin'/... = la serie
    PROPIA de esa casa. Son datos distintos y no deben mezclarse: la
    agregada no dice de quien es cada movimiento, que es justo lo que el
    lead-lag necesita saber. ALTER idempotente para no perder lo ya bajado."""
    conn.execute(HIST_DDL)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(bball_odds_hist)")}
    except Exception:
        cols = set()
    if "source" not in cols:
        conn.execute("ALTER TABLE bball_odds_hist ADD COLUMN source TEXT")
    conn.commit()


def _flt(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _hist_rows(eid: str, odds: dict) -> list[tuple]:
    """Filas de bball_odds_hist a partir de results.odds de /v2/event/odds.
    TODOS los mercados 18_* (peticion del usuario: cuartos y mitades ademas
    del partido completo -- 18_4..18_9 vienen gratis en la misma respuesta;
    su semantica exacta se determinara en el analisis, p.ej. un total de
    cuarto se delata por handicap ~ linea/4). El esquema de columnas cubre
    las dos formas: over/under para totales, home/away para ganador/handicap."""
    rows: list[tuple] = []
    prefijo = f"{config.SPORT_ID}_"
    for mk, serie in (odds or {}).items():
        if not str(mk).startswith(prefijo) or not isinstance(serie, list):
            continue
        for e in serie:
            if not isinstance(e, dict):
                continue
            try:
                add_t = int(e.get("add_time") or 0) or None
            except (TypeError, ValueError):
                add_t = None
            rows.append((eid, mk, add_t, e.get("ss"),
                         _flt(e.get("handicap")), _flt(e.get("over_od")), _flt(e.get("under_od")),
                         _flt(e.get("home_od")), _flt(e.get("away_od"))))
    return rows


def backfill_hist(client: ApiClient, conn, league_ids=None, limit: int = 0, use_cache: bool = True) -> dict:
    """Baja el historial de cuotas de cada partido completado que aun no lo
    tenga (resumible: salta los event_id ya presentes). Una llamada por
    partido. Pensado para correr contra la base LOCAL (workflow bball_local):
    contra Turso este bucle lee bball_games y bball_odds_hist en cada arranque."""
    from ..sources.betsapi import fetch_odds_history

    asegurar_columna_source(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bball_odds_hist_event ON bball_odds_hist(event_id)")
    conn.commit()
    hechos = {r["event_id"] for r in conn.execute("SELECT DISTINCT event_id FROM bball_odds_hist WHERE source IS NULL").fetchall()}
    filas = conn.execute(
        "SELECT event_id, league_id FROM bball_games WHERE completed = 1 ORDER BY date"
    ).fetchall()
    if league_ids:
        keep = {str(x) for x in league_ids}
        filas = [r for r in filas if str(r["league_id"]) in keep]
    pend = [r["event_id"] for r in filas if r["event_id"] not in hechos]
    if limit:
        pend = pend[:limit]
    print(f"backfill-hist: {len(filas)} partidos en ambito, {len(pend)} pendientes", flush=True)
    stats = {"eventos": 0, "filas": 0, "vacios": 0}
    for i, eid in enumerate(pend):
        js = fetch_odds_history(client, eid, use_cache=use_cache)
        rows = _hist_rows(eid, (js.get("results") or {}).get("odds") or {})
        conn.execute("DELETE FROM bball_odds_hist WHERE event_id = ? AND source IS NULL", (eid,))
        if rows:
            conn.executemany(
                "INSERT INTO bball_odds_hist(event_id, market, add_time, ss, line, over_odds, under_odds, home_odds, away_odds) "
                "VALUES (?,?,?,?,?,?,?,?,?)", rows)
            stats["filas"] += len(rows)
        else:
            stats["vacios"] += 1
        stats["eventos"] += 1
        if (i + 1) % 50 == 0:
            conn.commit()
            print(f"  {i + 1}/{len(pend)} (filas={stats['filas']}, vacios={stats['vacios']})", flush=True)
    conn.commit()
    return stats


def reparse_hist(conn, batch: int = 200) -> dict:
    """Reconstruye bball_odds_hist desde la cache local de /v2/event/odds SIN
    llamadas nuevas -- para ensanchar a TODOS los mercados (cuartos/mitades)
    los partidos bajados cuando el parser solo guardaba 18_1/18_2/18_3.

    Mapeo body -> partido:
    - prefix nuevo 'odds_hist_<event_id>': directo.
    - prefix viejo 'odds_hist' a secas: el body no trae event_id, se deduce
      por huella EXACTA del mercado de totales -- el conjunto (add_time,
      linea, over_od) de su serie 18_3 debe coincidir con las filas 18_3 ya
      guardadas para ese evento por backfill_hist (que si sabia el id).
      Sin coincidencia unica se salta y se cuenta, nunca se adivina (leccion
      del emparejamiento votado de reparse_moneyline_spread)."""
    asegurar_columna_source(conn)
    conn.commit()

    huella_por_evento: dict[frozenset, str] = {}
    acum: dict[str, set] = {}
    for r in conn.execute(
        "SELECT event_id, add_time, line, over_odds FROM bball_odds_hist WHERE market = ?",
        (config.TOTALS_MARKET_KEY,),
    ).fetchall():
        acum.setdefault(r["event_id"], set()).add(
            (r["add_time"], r["line"], r["over_odds"]))
    repetidas = set()
    for eid, tuplas in acum.items():
        fp = frozenset(tuplas)
        if fp in huella_por_evento:
            repetidas.add(fp)
        huella_por_evento[fp] = eid
    for fp in repetidas:
        huella_por_evento.pop(fp, None)  # huella compartida: no identifica

    claves = [r["cache_key"] for r in conn.execute(
        "SELECT cache_key FROM bball_http_cache WHERE prefix LIKE 'odds_hist%'"
    ).fetchall()]
    stats = {"bodies": len(claves), "directos": 0, "por_huella": 0,
             "sin_mapear": 0, "filas": 0}
    import json as _json
    for k in claves:
        row = conn.execute(
            "SELECT prefix, body FROM bball_http_cache WHERE cache_key = ?", (k,)
        ).fetchone()
        if not row:
            continue
        odds = ((_json.loads(row["body"]).get("results") or {}).get("odds")) or {}
        pref = row["prefix"] or ""
        eid = None
        if pref.startswith("odds_hist_") and pref[len("odds_hist_"):].isdigit():
            eid = pref[len("odds_hist_"):]
            stats["directos"] += 1
        else:
            serie = odds.get(config.TOTALS_MARKET_KEY) or []
            fp = frozenset(
                ((int(e.get("add_time") or 0) or None), _flt(e.get("handicap")), _flt(e.get("over_od")))
                for e in serie if isinstance(e, dict))
            eid = huella_por_evento.get(fp)
            if eid:
                stats["por_huella"] += 1
        if not eid:
            stats["sin_mapear"] += 1
            continue
        rows = _hist_rows(eid, odds)
        conn.execute("DELETE FROM bball_odds_hist WHERE event_id = ? AND source IS NULL", (eid,))
        if rows:
            conn.executemany(
                "INSERT INTO bball_odds_hist(event_id, market, add_time, ss, line, over_odds, under_odds, home_odds, away_odds) "
                "VALUES (?,?,?,?,?,?,?,?,?)", rows)
            stats["filas"] += len(rows)
        if (stats["directos"] + stats["por_huella"]) % batch == 0:
            conn.commit()
    conn.commit()
    return stats


def collect_all_range(client: ApiClient, conn, start: date, end: date, use_cache: bool = True) -> dict:
    """Barrido de LIGAS CHICAS: todos los partidos reales de basket de un
    rango de dias, SIN filtrar por liga -- el territorio que el veredicto de
    las ligas grandes dejo explicitamente abierto (peticion del usuario:
    'algo tiene que haber'). Por evento: partido + resumen de cuotas + serie
    historica completa (3 llamadas/partido aprox: 1 de dia compartida + 2).

    Se excluyen las ligas grandes ya recolectadas (por league_id) y el
    basket no-real (videojuego, 3x3). Resumible: salta eventos que ya tengan
    historial."""
    from ..sources.betsapi import (fetch_ended_all_leagues, fetch_odds_history,
                                   fetch_odds_summary, parse_score)

    MALAS = ("ebasketball", "h2h gg", "esports", "3x3")
    GRANDES = {str(v) for v in config.LEAGUES.values()}
    asegurar_columna_source(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bball_odds_hist_event ON bball_odds_hist(event_id)")
    conn.commit()
    hechos = {r["event_id"] for r in conn.execute("SELECT DISTINCT event_id FROM bball_odds_hist WHERE source IS NULL").fetchall()}
    stats = {"dias": 0, "partidos": 0, "con_cuotas": 0, "filas_hist": 0}
    day = start
    while day <= end:
        ds = day.strftime("%Y%m%d")
        eventos = fetch_ended_all_leagues(client, config.SPORT_ID, ds, use_cache=use_cache)
        n_dia = 0
        fetched_at = datetime.now(timezone.utc).isoformat()
        for e in eventos:
            league = e.get("league") or {}
            lid = str(league.get("id"))
            lname = str(league.get("name") or "")
            if lid in GRANDES or any(x in lname.lower() for x in MALAS):
                continue
            sc = parse_score(e.get("ss"))
            if not sc:
                continue
            eid = str(e.get("id"))
            if eid in hechos:
                continue
            home = e.get("home") or {}
            away = e.get("away") or {}
            if config.swaps_home_away(lname):
                home, away = away, home
                sc = (sc[1], sc[0])
            ts = int(e.get("time") or 0)
            game_date = (datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
                         if ts else f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}")
            conn.execute(
                "INSERT INTO bball_games(event_id, sport_id, league_id, league_name, date, time_ts, "
                "home_team, away_team, home_key, away_key, home_score, away_score, completed, raw_json, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?) "
                "ON CONFLICT(event_id) DO UPDATE SET home_score=excluded.home_score, away_score=excluded.away_score, "
                "raw_json=excluded.raw_json, fetched_at=excluded.fetched_at",
                (eid, str(config.SPORT_ID), lid, lname, game_date, ts,
                 home.get("name"), away.get("name"), str(home.get("id")), str(away.get("id")),
                 sc[0], sc[1], json.dumps(e, ensure_ascii=False), fetched_at))
            odds_js = fetch_odds_summary(client, eid, use_cache=use_cache)
            rows = extract_pre_match_totals(odds_js, ts)
            if rows:
                conn.executemany(
                    "INSERT INTO bball_odds(event_id, book, market, line, over_odds, under_odds, snapshot, captured_at, raw_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(event_id, book, market, line, snapshot) DO UPDATE SET "
                    "over_odds=excluded.over_odds, under_odds=excluded.under_odds, captured_at=excluded.captured_at",
                    [(eid, r["book"], config.TOTALS_MARKET_KEY, r["line"], r["over_odds"], r["under_odds"],
                      r["snapshot"], r["captured_at"], None) for r in rows])
                stats["con_cuotas"] += 1
            js = fetch_odds_history(client, eid, use_cache=use_cache)
            hrows = _hist_rows(eid, (js.get("results") or {}).get("odds") or {})
            conn.execute("DELETE FROM bball_odds_hist WHERE event_id = ? AND source IS NULL", (eid,))
            if hrows:
                conn.executemany(
                    "INSERT INTO bball_odds_hist(event_id, market, add_time, ss, line, over_odds, under_odds, home_odds, away_odds) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", hrows)
                stats["filas_hist"] += len(hrows)
            hechos.add(eid)
            n_dia += 1
        conn.commit()
        stats["dias"] += 1
        stats["partidos"] += n_dia
        print(f"{day.isoformat()} chicas: {n_dia} partidos nuevos", flush=True)
        day += timedelta(days=1)
    return stats
