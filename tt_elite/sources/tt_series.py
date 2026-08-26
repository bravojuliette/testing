"""TT-Series: descubrir sesiones del dia y parsear el calendario/resultados.

Usa la API REST de WordPress (mas fiable para backtesting que el buscador
HTML del tema, tal como ya habias comprobado en tus scripts).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

from bs4 import BeautifulSoup

from .. import config
from ..textutil import clean_html, name_key, parse_score
from .http_cache import ApiClient


def tt_posts_for_date(client: ApiClient, d: date, *, use_cache: bool = True) -> list[dict]:
    """Posts de resultados de TT-Series que mencionan la fecha d (dd.mm.yyyy).

    `use_cache=True` (por defecto) es correcto para un dia YA CERRADO -- el
    contenido de ese post no vuelve a cambiar, asi que collect.py (backfill
    historico) lo reutiliza sin gastar requests. Pero el propio WordPress post
    de "hoy" se va EDITANDO durante el dia segun se van cerrando partidos --
    el body de ese post cambia, pero la URL/parametros de esta consulta NO
    (mismo `search=dot` durante todo el dia), asi que con cache activada el
    scanner en vivo se quedaria pegado a la foto de la primera vez que lo pidio
    ese dia. `live/scan.py` por eso pasa use_cache=False para "hoy"/"ayer" --
    ver el bug real del 2026-08-26: candidates=0 durante horas porque
    reutilizaba la misma respuesta cacheada de madrugada sin ver los
    resultados que se iban cerrando."""
    dot = d.strftime("%d.%m.%Y")
    slug = d.strftime("%d-%m-%Y")
    url = f"{config.TT_BASE}/wp-json/wp/v2/posts"
    data = client.get_json(
        url, {"search": dot, "per_page": 100, "page": 1, "_fields": "link,title,content"},
        prefix="tt", use_cache=use_cache,
    )
    return [x for x in data if slug in str(x.get("link", "")) and "-result-" in str(x.get("link", "")).lower()]


def parse_session(post: dict) -> dict:
    link = str(post.get("link", ""))
    title = clean_html((post.get("title") or {}).get("rendered", "")) or link
    content = (post.get("content") or {}).get("rendered", "")
    soup = BeautifulSoup(content, "html.parser")
    schedule = []

    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [clean_html(c) for c in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        joined = " ".join(" ".join(r) for r in rows).lower()
        if not ("player" in joined and "result" in joined and "match" in joined):
            continue
        for row in rows:
            if len(row) < 4 or not re.fullmatch(r"\d{1,2}:\d{2}", row[0].strip()):
                continue
            if len(row) >= 5:
                p1, p2, res = row[2], row[3], row[4]
            else:
                p1, p2, res = row[1], row[2], row[3]
            p1, p2 = p1.strip(), p2.strip()
            if not p1 or not p2 or name_key(p1) == name_key(p2):
                continue
            sc = parse_score(res)
            schedule.append({
                "time": row[0].strip(), "p1": p1, "p2": p2,
                "p1k": name_key(p1), "p2k": name_key(p2),
                "completed": bool(sc),
                "s1": sc[0] if sc else None, "s2": sc[1] if sc else None,
            })
        if schedule:
            break

    return {"title": title, "url": link, "schedule": schedule}


def title_date(session: dict, fallback: date) -> date:
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", session["title"])
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return fallback


def assign_datetimes(session: dict, fallback_day: date) -> dict:
    """Asigna datetime real a cada partido, manejando sesiones 'night' que cruzan
    medianoche (los horarios se reinician tras las 00:00 pero pertenecen al mismo
    bloque, asi que se les suma un dia si el reloj retrocede)."""
    base = title_date(session, fallback_day)
    prev = None
    offset = 0
    for m in session["schedule"]:
        h, mi = map(int, m["time"].split(":"))
        x = h * 60 + mi
        if prev is not None and x + offset < prev - 60:
            offset += 1440
        rel = x + offset
        prev = rel
        m["rel_min"] = rel
        m["dt"] = datetime(base.year, base.month, base.day, tzinfo=config.TZ) + timedelta(minutes=rel)
    return session


def load_sessions_for_date(client: ApiClient, d: date, *, use_cache: bool = True) -> list[dict]:
    posts = tt_posts_for_date(client, d, use_cache=use_cache)
    sessions = [assign_datetimes(parse_session(p), d) for p in posts]
    return [s for s in sessions if s["schedule"]]


def get_official_ranking(client: ApiClient) -> dict[str, dict]:
    """Ranking Elo oficial publicado por TT-Series (pagina HTML, no JSON)."""
    resp = client.session.get(config.TT_RANKING_URL, timeout=45)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    ranking: dict[str, dict] = {}
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [clean_html(c) for c in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        joined = " ".join(" ".join(r) for r in rows).lower()
        if "player" not in joined or "elo" not in joined:
            continue
        for row in rows:
            if len(row) < 3:
                continue
            try:
                elo = float(re.sub(r"[^0-9.\-]", "", row[-1]))
            except ValueError:
                continue
            if elo < 50:
                continue
            player = row[-2]
            key = name_key(player)
            if key:
                ranking[key] = {"name": player, "elo": elo}
        if ranking:
            break
    if len(ranking) < 50:
        raise RuntimeError(f"Tabla ELO de TT-Series parece incompleta ({len(ranking)} jugadores).")
    return ranking
