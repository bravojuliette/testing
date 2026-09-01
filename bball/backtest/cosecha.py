"""Cosecha la serie de cuotas PROPIA DE CADA CASA (/v2/event/odds?source=...).

Por que existe: el scanner en vivo fotografiaba, para los partidos en juego,
la linea de cada casa desde /v2/event/odds/summary -> results[casa].odds.end.
Ese campo NO se refresca durante el partido: se queda clavado en el valor
pre-partido. Las "dispersiones de 20 puntos en vivo" que salian de ahi eran
lineas de apertura comparadas contra el marcador del cuarto 4 -- el usuario lo
cazo mirando los numeros, y los logs de Actions lo confirmaron (minimos
inmoviles en 157.0 / 145.5 / 173.5 mientras el marcador avanzaba).

La via buena: /v2/event/odds acepta `source`, y con ella devuelve la serie
historica COMPLETA de esa casa, con marcador (`ss`) en cada entrada -- es
decir, sus movimientos EN JUEGO, que es exactamente lo que el lead-lag
necesita. Y como es historico, una sola llamada por (partido, casa) trae el
partido entero: no hay que poner el scanner a sondear cada 10 minutos.

Se guarda en bball_odds_hist con la columna `source` rellena. `source IS NULL`
sigue siendo la serie agregada de siempre (backfill_hist), que no dice de
quien es cada movimiento y por eso no sirve para medir quien va primero.
"""
from __future__ import annotations

from ..sources.betsapi import fetch_odds_history_source
from .collect import _hist_rows, asegurar_columna_source

# Las tres que el sondeo de fuentes encontro con serie propia EN JUEGO sobre
# el mercado de totales. El resto de SOURCES_CANDIDATAS o no existe en la API
# o devuelve series sin marcador (solo pre-partido), y gastar llamadas en
# ellas no aporta al lead-lag.
FUENTES_VIVO = ("bet365", "1xbet", "bwin")


def cosechar(client, conn, event_ids, fuentes=FUENTES_VIVO, use_cache: bool = True) -> dict:
    """Una llamada por (evento, fuente). Resumible: salta los pares ya
    guardados, asi que repetir la orden no gasta cuota ni duplica filas."""
    asegurar_columna_source(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bball_odds_hist_event ON bball_odds_hist(event_id)")
    conn.commit()
    hechos = {(r[0], r[1]) for r in conn.execute(
        "SELECT DISTINCT event_id, source FROM bball_odds_hist WHERE source IS NOT NULL")}
    stats = {"pares": 0, "filas": 0, "vacios": 0, "errores": 0, "por_fuente": {}}
    for i, eid in enumerate(event_ids):
        for src in fuentes:
            if (eid, src) in hechos:
                continue
            stats["pares"] += 1
            try:
                js = fetch_odds_history_source(client, eid, src, use_cache=use_cache)
            except Exception as exc:
                stats["errores"] += 1
                if stats["errores"] <= 5:
                    print(f"  [WARN] {eid}/{src}: {str(exc)[:90]}", flush=True)
                continue
            if not js.get("success"):
                stats["vacios"] += 1
                continue
            filas = _hist_rows(eid, (js.get("results") or {}).get("odds") or {})
            if not filas:
                stats["vacios"] += 1
                continue
            conn.execute("DELETE FROM bball_odds_hist WHERE event_id = ? AND source = ?", (eid, src))
            conn.executemany(
                "INSERT INTO bball_odds_hist(event_id, market, add_time, ss, line, over_odds, "
                "under_odds, home_odds, away_odds, source) VALUES (?,?,?,?,?,?,?,?,?,?)",
                [f + (src,) for f in filas])
            stats["filas"] += len(filas)
            d = stats["por_fuente"].setdefault(src, {"eventos": 0, "filas": 0, "vivas": 0})
            d["eventos"] += 1
            d["filas"] += len(filas)
            # filas con marcador = movimientos EN JUEGO (el dato que se buscaba)
            d["vivas"] += sum(1 for f in filas if (f[3] or "").strip())
        if (i + 1) % 25 == 0:
            conn.commit()
            print(f"  {i + 1}/{len(event_ids)} eventos "
                  f"(filas={stats['filas']}, vacios={stats['vacios']}, err={stats['errores']})", flush=True)
    conn.commit()
    return stats


def cosechar_rango(client, conn, start: str, end: str, leagues=None, limit: int = 0,
                   fuentes=FUENTES_VIVO, use_cache: bool = True) -> dict:
    """Partidos COMPLETADOS entre start y end (YYYY-MM-DD), opcionalmente
    filtrados por nombre de liga."""
    q = "SELECT event_id FROM bball_games WHERE completed = 1 AND date >= ? AND date <= ?"
    params = [start, end]
    if leagues:
        q += " AND league_name IN (" + ",".join("?" * len(leagues)) + ")"
        params += list(leagues)
    q += " ORDER BY date"
    eids = [r[0] for r in conn.execute(q, params)]
    if limit:
        eids = eids[:limit]
    print(f"cosecha: {len(eids)} partidos x {len(fuentes)} fuentes "
          f"= hasta {len(eids) * len(fuentes)} llamadas", flush=True)
    return cosechar(client, conn, eids, fuentes=fuentes, use_cache=use_cache)
