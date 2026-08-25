"""Detector de "cadenas de barridas transitivas" -- sistema APARTE del
scanner principal (tt_elite/live/scan.py), pedido explicito del usuario el
2026-08-24:

    "Si en una misma sesion (dia de torneo), existe alguien que haya quedado
    3-0 contra un rival X, y toque disputar su encuentro con un rival Y, que
    ha perdido 0-3 contra ese rival X, quiero que se me muestre."

Y el 2026-08-24 (mismo dia), pidio ademas que se muestre como quedo cada uno
contra el rival comun X, y que -- una vez terminado el partido A vs Y -- se
indique si se CUMPLE la teoria (A, transitivamente mas fuerte, gana) o NO
(gana Y).

Y el mismo dia, mas tarde, pidio tambien ver las cuotas que tenia cada uno
(A y Y) en el partido de la cadena -- ver _attach_odds() --, y despues
filtrar a los casos donde A tiene cuota de underdog, y la rentabilidad de
apostarle (ver cli.py/db.ts).

Y el 2026-08-25 pidio poder analizar esto en el pasado ("todos los dias un
mes atras") para tener una rentabilidad mas realista (mas muestra). Como
raw_matches ya tiene ~2 anios de historico (recolectado por el backtest
original) y raw_odds YA tiene cuotas de apertura para la mayoria de esos
dias (recolectadas en su momento con collect_range --fetch-odds, antes de
que existiera este sistema), un backfill NO necesita repetir consultas a
BetsAPI en vivo: _attach_odds_from_raw_odds() reutiliza esas cuotas ya
guardadas. Solo faltan por consultar en vivo los dias mas recientes que el
scanner en vivo no llegó a recolectar con cuota (normalmente unos pocos
dias). Para un backfill de un mes: `scan-blowout-chain --days-back 31`.

Y el mismo dia, mas tarde, pidio añadir como criterio que A hubiera ganado
tambien 1, 2 o 3 partidos anteriores. OJO: la primera implementacion de
esto media la racha de A justo antes de A VS Y -- el usuario aclaro que no
era eso: el criterio va sobre LA BARRIDA en si (A venciendo a X 3-0), es
decir cuantas victorias consecutivas traia A justo ANTES de esa barrida
concreta. a_prior_win_streak se captura en el momento en que la barrida
A-vs-X se registra en `wins` (no en el momento de detectar la señal A-Y),
leyendo el estado de `streaks[A]` ANTES de que ese mismo partido lo
actualice.

Resultado (backfill completo, 2026-08-25): exigir racha de A perdia
demasiado volumen (de 279 casos A-underdog a solo 7 exigiendo racha>=3) sin
mejorar el ROI de forma fiable -- el usuario descarto ese filtro y pidio el
opuesto: en vez de exigir que el underdog (A) haya GANADO 1/2/3 partidos
antes de SU barrida, exigir que el FAVORITO (Y, el que pierde 0-3 contra X)
haya PERDIDO 1/2/3 partidos antes de ESA barrida (X venciendo a Y 3-0).
Mismo patron, mirror exacto: y_prior_loss_streak se captura igual que
a_prior_win_streak pero del lado del PERDEDOR de la barrida (rachas de
DERROTA en vez de victoria), leido de `streaks[loser]` justo antes de que
esa barrida lo actualice.

No genera picks ni probabilidad de acierto -- es puramente observacional,
sin backtest ni validacion detras (a diferencia del sistema principal). La
deteccion en si se alimenta solo de raw_matches ya recolectado (sin
llamadas nuevas a BetsAPI ni TT-Series); las cuotas se resuelven primero
desde raw_odds ya recolectado (gratis, sin llamadas) y solo si ahi no estan
se consulta BetsAPI en vivo -- pero solo una vez por senal, una vez
guardada una cuota no se vuelve a pedir en pasadas siguientes.

Algoritmo, por sesion (session_url), en orden cronologico (rel_min):
  Se mantiene un diccionario "wins[winner_key][loser_key] = {match_uid,
  date, time}" de barridas 3-0/0-3 YA RESUELTAS antes del partido actual
  (sin mirar al futuro). Para cada partido A vs B se comprueba, en ambos
  sentidos (A=p1,Y=p2) y (A=p2,Y=p1), si existe un X tal que A goleo 3-0 a X
  y X goleo 3-0 a Y -- si lo hay, se registra la senal (con el detalle de
  ambos partidos de barrida). Solo DESPUES de comprobar el partido actual se
  anade su propio resultado (si fue barrida) al diccionario, para partidos
  posteriores de la misma sesion.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .. import config

# Limite de parametros por sentencia SQL (clausulas IN, executemany) --
# tanto SQLite (variable_number, tipicamente 999) como Turso via HTTP tienen
# un techo. Con un backfill de TODO el historico (~2 anios, miles de
# senales) una sola consulta/lote sin trocear reventaria; 400 es
# conservador para ambos backends.
_SQL_CHUNK = 400


def _chunked(seq: list, size: int = _SQL_CHUNK):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def compute_blowout_chains(conn, start: date, end: date) -> list[dict]:
    """Recorre raw_matches entre `start` y `end` (inclusive) y devuelve la
    lista de senales encontradas, jugadas o pendientes. Pura (sin depender
    de la hora actual) para que sea facil de testear con fechas fijas."""
    rows = conn.execute(
        """SELECT match_uid, session_url, session_title, date, time, dt, rel_min,
                  p1, p2, p1_key, p2_key, completed, s1, s2
           FROM raw_matches
           WHERE date >= ? AND date <= ?
           ORDER BY session_url, rel_min""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()

    by_session: dict[str, list[dict]] = {}
    for r in rows:
        by_session.setdefault(r["session_url"], []).append(dict(r))

    signals: list[dict] = []
    for session_url, matches in by_session.items():
        matches = sorted(matches, key=lambda m: m["rel_min"] if m["rel_min"] is not None else 0)
        name_by_key: dict[str, str] = {}
        # winner_key -> {loser_key: {match_uid, date, time}} de barridas 3-0
        # ya resueltas antes del partido actual.
        wins: dict[str, dict[str, dict]] = {}
        # player_key -> ('W'|'L', longitud) de la racha de resultados DENTRO
        # de esta sesion, hasta antes del partido actual (sin look-ahead) --
        # mismo patron que backtest/streaks.py. Se usa para anotar, en cada
        # barrida 3-0 registrada en `wins`, cuantas victorias consecutivas
        # traia el que goleo justo ANTES de esa barrida (ver mas abajo).
        streaks: dict[str, tuple[str | None, int]] = {}

        for m in matches:
            p1k, p2k, p1n, p2n = m["p1_key"], m["p2_key"], m["p1"], m["p2"]
            name_by_key[p1k] = p1n
            name_by_key[p2k] = p2n

            for a, y, an, yn, a_is_p1 in (
                (p1k, p2k, p1n, p2n, True),
                (p2k, p1k, p2n, p1n, False),
            ):
                for x, ax_info in wins.get(a, {}).items():
                    xy_info = wins.get(x, {}).get(y)
                    if not xy_info:
                        continue
                    completed = bool(m["completed"]) and m["s1"] is not None and m["s2"] is not None
                    a_score = y_score = theory_holds = None
                    if completed:
                        a_score, y_score = (m["s1"], m["s2"]) if a_is_p1 else (m["s2"], m["s1"])
                        theory_holds = 1 if a_score > y_score else 0
                    signals.append({
                        "id": f"{m['match_uid']}|{a}|{x}",
                        "match_uid": m["match_uid"],
                        "session_url": session_url,
                        "session_title": m["session_title"],
                        "date": m["date"], "time": m["time"],
                        "dt": m["dt"], "rel_min": m["rel_min"],
                        "player_a": an, "player_a_key": a,
                        "player_y": yn, "player_y_key": y,
                        "common_x": name_by_key.get(x, x), "common_x_key": x,
                        "ax_match_uid": ax_info["match_uid"], "ax_date": ax_info["date"], "ax_time": ax_info["time"],
                        "xy_match_uid": xy_info["match_uid"], "xy_date": xy_info["date"], "xy_time": xy_info["time"],
                        "match_completed": completed,
                        "a_score": a_score, "y_score": y_score,
                        "theory_holds": theory_holds,
                        # Racha de victorias de A EN LA SESION justo ANTES de
                        # LA BARRIDA (A goleando 3-0 a X) -- no antes de A vs
                        # Y. 0 si el partido inmediatamente anterior de A fue
                        # una derrota, o si A no jugo nada mas antes.
                        "a_prior_win_streak": ax_info["prior_streak"],
                        # Racha de DERROTAS de Y justo ANTES de esa OTRA
                        # barrida (X goleando 3-0 a Y) -- 0 si el partido
                        # inmediatamente anterior de Y fue una victoria, o si
                        # Y no jugo nada mas antes en la sesion.
                        "y_prior_loss_streak": xy_info["loser_prior_loss_streak"],
                        # Se rellenan en _attach_odds_from_raw_odds() /
                        # _attach_odds() -- None aqui = "todavia sin cuota".
                        "a_odds": None, "y_odds": None, "odds_book": None,
                        # Interno (no se persiste): que lado de raw_matches
                        # es A, para reorientar raw_odds.odds1/odds2 -- ver
                        # _attach_odds_from_raw_odds().
                        "_a_is_p1": a_is_p1,
                    })

            if m["completed"] and m["s1"] is not None and m["s2"] is not None:
                p1_won = m["s1"] > m["s2"]

                def _next(type_, len_, won):
                    outcome = "W" if won else "L"
                    return (outcome, len_ + 1) if type_ == outcome else (outcome, 1)

                # Racha de CADA jugador justo ANTES de este partido (para
                # anotarla en la barrida, si lo es) -- se lee antes de
                # actualizar `streaks` con el resultado de este partido.
                # prior_streak = victorias consecutivas (para el que gana la
                # barrida); prior_loss_streak = derrotas consecutivas (para
                # el que la pierde) -- mismo dato, leido en direccion opuesta.
                s1_type, s1_len = streaks.get(p1k, (None, 0))
                s2_type, s2_len = streaks.get(p2k, (None, 0))
                p1_prior_win_streak = s1_len if s1_type == "W" else 0
                p2_prior_win_streak = s2_len if s2_type == "W" else 0
                p1_prior_loss_streak = s1_len if s1_type == "L" else 0
                p2_prior_loss_streak = s2_len if s2_type == "L" else 0

                if m["s1"] == 3 and m["s2"] == 0:
                    wins.setdefault(p1k, {})[p2k] = {
                        "match_uid": m["match_uid"], "date": m["date"], "time": m["time"],
                        "prior_streak": p1_prior_win_streak,
                        "loser_prior_loss_streak": p2_prior_loss_streak,
                    }
                elif m["s1"] == 0 and m["s2"] == 3:
                    wins.setdefault(p2k, {})[p1k] = {
                        "match_uid": m["match_uid"], "date": m["date"], "time": m["time"],
                        "prior_streak": p2_prior_win_streak,
                        "loser_prior_loss_streak": p1_prior_loss_streak,
                    }

                streaks[p1k] = _next(s1_type, s1_len, p1_won)
                streaks[p2k] = _next(s2_type, s2_len, not p1_won)

    return signals


def upsert_blowout_chain_signals(conn, signals: list[dict]) -> int:
    """Guarda las senales encontradas. INSERT ... ON CONFLICT conserva
    detected_at (primera vez que se vio esta cadena) y solo refresca el
    estado del partido (completed/marcador/veredicto/cuota) segun se va
    resolviendo."""
    if not signals:
        return 0
    now_iso = datetime.now(config.TZ).isoformat()
    rows = [
        (
            s["id"], s["match_uid"], s["session_url"], s["session_title"],
            s["date"], s["time"], s.get("dt"), s.get("rel_min"),
            s["player_a"], s["player_a_key"], s["player_y"], s["player_y_key"],
            s["common_x"], s["common_x_key"],
            s["ax_match_uid"], s["ax_date"], s["ax_time"],
            s["xy_match_uid"], s["xy_date"], s["xy_time"],
            1 if s["match_completed"] else 0, s.get("a_score"), s.get("y_score"), s.get("theory_holds"),
            s.get("a_odds"), s.get("y_odds"), s.get("odds_book"),
            s.get("a_prior_win_streak"), s.get("y_prior_loss_streak"),
            now_iso,
        )
        for s in signals
    ]
    sql = """INSERT INTO blowout_chain_signals
               (id, match_uid, session_url, session_title, date, time, dt, rel_min,
                player_a, player_a_key, player_y, player_y_key,
                common_x, common_x_key,
                ax_match_uid, ax_date, ax_time, xy_match_uid, xy_date, xy_time,
                match_completed, a_score, y_score, theory_holds,
                a_odds, y_odds, odds_book, a_prior_win_streak, y_prior_loss_streak, detected_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
               match_completed = excluded.match_completed,
               a_score = excluded.a_score,
               y_score = excluded.y_score,
               theory_holds = excluded.theory_holds,
               ax_match_uid = excluded.ax_match_uid,
               ax_date = excluded.ax_date, ax_time = excluded.ax_time,
               xy_match_uid = excluded.xy_match_uid,
               xy_date = excluded.xy_date, xy_time = excluded.xy_time,
               a_prior_win_streak = excluded.a_prior_win_streak,
               y_prior_loss_streak = excluded.y_prior_loss_streak,
               a_odds = excluded.a_odds, y_odds = excluded.y_odds, odds_book = excluded.odds_book"""
    # Trocear el batch: un backfill de todo el historico puede juntar miles
    # de filas, y un solo batch() gigante contra Turso (una request HTTP con
    # todas las sentencias) es fragil -- ver _SQL_CHUNK.
    for chunk in _chunked(rows):
        conn.executemany(sql, chunk)
    return len(rows)


def _load_existing_odds(conn, signals: list[dict]) -> None:
    """Rellena a_odds/y_odds/odds_book desde lo ya guardado en pasadas
    anteriores (in-place sobre `signals`), para no volver a consultar
    BetsAPI por una senal que ya tiene cuota."""
    ids = [s["id"] for s in signals]
    if not ids:
        return
    existing: dict[str, tuple] = {}
    for chunk in _chunked(ids):
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT id, a_odds, y_odds, odds_book FROM blowout_chain_signals WHERE id IN ({placeholders})",
            chunk,
        ).fetchall()
        existing.update({r["id"]: (r["a_odds"], r["y_odds"], r["odds_book"]) for r in rows})
    for s in signals:
        hit = existing.get(s["id"])
        if hit and hit[0] is not None:
            s["a_odds"], s["y_odds"], s["odds_book"] = hit


def _attach_odds_from_raw_odds(conn, signals: list[dict]) -> None:
    """Rellena a_odds/y_odds/odds_book desde raw_odds YA recolectado (por
    backtest/collect.py, para dias historicos anteriores a este sistema) --
    sin ninguna llamada a BetsAPI. Se ejecuta siempre (gratis) antes de
    _attach_odds(), que solo consulta BetsAPI en vivo para lo que aqui no
    se encuentre (normalmente solo los dias mas recientes)."""
    todo = [s for s in signals if s.get("a_odds") is None]
    if not todo:
        return
    uids = list({s["match_uid"] for s in todo})
    # Por match_uid, se prefiere el libro "principal" (is_fallback=0) sobre
    # cualquier fallback -- mismo criterio que best_opening_line().
    best_by_uid: dict[str, dict] = {}
    for chunk in _chunked(uids):
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT match_uid, book, is_fallback, odds1, odds2 FROM raw_odds WHERE match_uid IN ({placeholders})",
            chunk,
        ).fetchall()
        for r in rows:
            cur = best_by_uid.get(r["match_uid"])
            if cur is None or r["is_fallback"] < cur["is_fallback"]:
                best_by_uid[r["match_uid"]] = dict(r)
    for s in todo:
        hit = best_by_uid.get(s["match_uid"])
        if not hit:
            continue
        a_odds, y_odds = (hit["odds1"], hit["odds2"]) if s["_a_is_p1"] else (hit["odds2"], hit["odds1"])
        s["a_odds"], s["y_odds"], s["odds_book"] = a_odds, y_odds, hit["book"]


def _attach_odds(conn, signals: list[dict]) -> None:
    """Consulta BetsAPI (solo el partido A vs Y de cada senal, no los dos de
    barrida) para rellenar a_odds/y_odds/odds_book de las senales que
    todavia no la tienen guardada. No es critico -- si BetsAPI falla o no
    hay token, se deja sin cuota y se reintenta en la siguiente pasada.

    Un backfill grande (p.ej. 735 dias) puede necesitar decenas de miles de
    llamadas a /v2/event/odds/summary (una por partido A-vs-Y, BetsAPI no
    tiene un endpoint por lotes) -- a ~1 req/s por el rate-limit de la
    cuenta, eso son HORAS reales, mas de lo que cabe en un solo job de
    Github Actions. Por eso aqui se hace UPSERT incremental (por fecha, o
    tras el lote de pendientes) en vez de esperar a que _attach_odds()
    entero termine: si el job se corta a mitad de camino (timeout), lo ya
    resuelto queda guardado y una relanzada solo tiene que cubrir el resto
    (ademas de que get_json() ya cachea cada respuesta cruda en http_cache,
    asi que ni siquiera repite la llamada HTTP)."""
    if not config.BETSAPI_TOKEN:
        return
    from ..sources.betsapi import (
        best_opening_line, current_best_line, fetch_ended, fetch_inplay, fetch_upcoming, find_event,
    )
    from ..sources.http_cache import ApiClient
    from ..textutil import strong_name

    pending_lookup = [s for s in signals if s.get("a_odds") is None and not s["match_completed"] and s.get("dt")]
    completed_lookup = [s for s in signals if s.get("a_odds") is None and s["match_completed"] and s.get("dt")]
    if not pending_lookup and not completed_lookup:
        return

    client = ApiClient(conn, config.BETSAPI_TOKEN)

    def _fill(group: list[dict], events: list[dict], *, completed: bool) -> None:
        for s in group:
            ts = int(datetime.fromisoformat(s["dt"]).timestamp())
            event = find_event(s["player_a"], s["player_y"], ts, events)
            if not event:
                continue
            try:
                line = best_opening_line(client, event) if completed else current_best_line(client, event)
            except Exception as exc:
                print(f"[blowout_chain] consulta de cuota fallo para {s['id']}: {exc}", flush=True)
                continue
            if not line:
                continue
            home = (event.get("home") or {}).get("name", "")
            if strong_name(home, s["player_y"]):
                line["odds1"], line["odds2"] = line["odds2"], line["odds1"]
            s["a_odds"], s["y_odds"], s["odds_book"] = line["odds1"], line["odds2"], line["book"]

    if pending_lookup:
        try:
            upcoming_events = fetch_upcoming(client) + fetch_inplay(client)
        except Exception as exc:
            print(f"[blowout_chain] fetch_upcoming/fetch_inplay fallo, se sigue sin cuotas de pendientes: {exc}", flush=True)
            upcoming_events = []
        _fill(pending_lookup, upcoming_events, completed=False)
        upsert_blowout_chain_signals(conn, pending_lookup)

    dates = sorted({date.fromisoformat(s["date"]) for s in completed_lookup})
    for d in dates:
        try:
            events = fetch_ended(client, d)
        except Exception as exc:
            print(f"[blowout_chain] fetch_ended({d}) fallo, se sigue sin esas cuotas: {exc}", flush=True)
            events = []
        day_signals = [s for s in completed_lookup if s["date"] == d.isoformat()]
        _fill(day_signals, events, completed=True)
        upsert_blowout_chain_signals(conn, day_signals)


def scan_blowout_chain(conn, days_back: int = 2, fetch_odds: bool = True) -> dict:
    """Envoltorio "de produccion": ancla la ventana a hoy (hora real,
    config.TZ) y persiste lo encontrado. `days_back` grande (p.ej. 31) sirve
    para un backfill historico -- la mayoria de esas cuotas ya estan en
    raw_odds (gratis, ver _attach_odds_from_raw_odds), asi que no dispara un
    aluvion de llamadas a BetsAPI. fetch_odds=False salta la consulta EN
    VIVO a BetsAPI (util en tests o si no hay BETSAPI_TOKEN) -- pero la
    reutilizacion de raw_odds ya recolectado sigue activa siempre."""
    today = datetime.now(config.TZ).date()
    start = today - timedelta(days=days_back - 1)
    signals = compute_blowout_chains(conn, start, today)
    if signals:
        _load_existing_odds(conn, signals)
        _attach_odds_from_raw_odds(conn, signals)
        if fetch_odds:
            _attach_odds(conn, signals)
    n = upsert_blowout_chain_signals(conn, signals)
    return {"found": n}
