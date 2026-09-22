"""Correccion de local/visitante en NCAAB usando los estadios (bball_venues).

El feed de NCAAB de BetsAPI mezcla dos fuentes con ordenes opuestos y sin
marcador en el JSON (ver ENMIENDA 2 de PREREGISTRO_situacionales.md). La
unica verdad fisica por partido es su estadio. Metodo:

  1. El estadio MODAL de cada equipo (el mas frecuente en sus partidos) es
     su casa. Un equipo juega ~la mitad de sus partidos en casa, mas que en
     cualquier pabellon rival, asi que el modo identifica la casa sin
     circularidad -- no usa resultados ni cuotas, solo geografia.
  2. Partido en la casa del LOCAL listado -> correcto.
     Partido en la casa del VISITANTE listado -> INVERTIDO.
     Partido en la casa de ninguno -> NEUTRAL (torneos): se marca y queda
     fuera de los analisis de local/visitante y de los contadores de viaje.

No toca bball_games: devuelve un dict event_id -> 'ok'|'swap'|'neutral'|
'sin_dato' para que cada analisis corrija al vuelo. Exigimos que el equipo
tenga >=5 partidos con estadio y que el modo sea >=35% de ellos; si no, el
partido queda 'sin_dato' (mejor perder muestra que adivinar).
"""
from collections import Counter, defaultdict


def casas_por_equipo(conn, min_partidos: int = 5, min_frac: float = 0.35) -> dict:
    """equipo(key) -> nombre de su estadio modal, solo si es fiable."""
    partidos = conn.execute(
        "SELECT g.home_key, g.away_key, v.stadium FROM bball_games g "
        "JOIN bball_venues v ON v.event_id = g.event_id "
        "WHERE g.league_name LIKE '%NCAA%' AND v.stadium IS NOT NULL").fetchall()
    visto = defaultdict(Counter)
    for r in partidos:
        visto[r["home_key"]][r["stadium"]] += 1
        visto[r["away_key"]][r["stadium"]] += 1
    casas = {}
    for eq, cnt in visto.items():
        total = sum(cnt.values())
        if total < min_partidos:
            continue
        estadio, n = cnt.most_common(1)[0]
        if n / total >= min_frac:
            casas[eq] = estadio
    return casas


def clasificar_orientacion(conn) -> dict:
    """event_id -> 'ok' | 'swap' | 'neutral' | 'sin_dato' para NCAAB."""
    casas = casas_por_equipo(conn)
    filas = conn.execute(
        "SELECT g.event_id, g.home_key, g.away_key, v.stadium FROM bball_games g "
        "LEFT JOIN bball_venues v ON v.event_id = g.event_id "
        "WHERE g.league_name LIKE '%NCAA%'").fetchall()
    out = {}
    for r in filas:
        est = r["stadium"]
        if not est:
            out[r["event_id"]] = "sin_dato"
            continue
        ch, ca = casas.get(r["home_key"]), casas.get(r["away_key"])
        if est == ch and est != ca:
            out[r["event_id"]] = "ok"
        elif est == ca and est != ch:
            out[r["event_id"]] = "swap"
        elif ch is None and ca is None:
            out[r["event_id"]] = "sin_dato"
        else:
            out[r["event_id"]] = "neutral"
    return out
