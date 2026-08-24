"""Cliente HTTP con cache persistente en SQLite y rate-limiting para BetsAPI.

BetsAPI documenta ~3600 req/hora. El backtest original en Colab ya sufria la
cuota diaria de UrlFetch de Apps Script; aqui cacheamos CADA respuesta cruda
para que re-correr un `collect` (por ejemplo tras un fallo a mitad de mes) no
vuelva a gastar requests en dias ya descargados.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone

import requests

from .. import config

USER_AGENT = "TTEliteApp/1.0"


class ApiClient:
    def __init__(self, conn: sqlite3.Connection, betsapi_token: str, min_interval: float = 1.05):
        self.conn = conn
        self.token = betsapi_token
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.min_interval = min_interval  # segundos entre llamadas a BetsAPI (< 3600/h)
        self._last_bets_call = 0.0

    @staticmethod
    def _cache_key(url: str, params: dict) -> str:
        key = url + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
        return hashlib.sha1(key.encode()).hexdigest()

    def get_json(self, url: str, params: dict | None = None, *, prefix: str = "http",
                 bets: bool = False, use_cache: bool = True, max_retries: int = 6) -> dict:
        params = dict(params or {})
        key = self._cache_key(url, params)

        if use_cache:
            row = self.conn.execute(
                "SELECT body FROM http_cache WHERE cache_key = ?", (key,)
            ).fetchone()
            if row:
                return json.loads(row["body"])

        if bets:
            wait = self.min_interval - (time.time() - self._last_bets_call)
            if wait > 0:
                time.sleep(wait)

        last_exc = None
        last_status = None
        last_body = None
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=45)
            except requests.RequestException as exc:
                last_exc = exc
                print(f"[http_cache] {url} intento {attempt + 1}/{max_retries}: excepcion de red: {exc!r}", flush=True)
                time.sleep(min(30, 2 ** attempt))
                continue
            if bets:
                self._last_bets_call = time.time()

            last_status = resp.status_code
            if resp.status_code == 429:
                reset = resp.headers.get("X-RateLimit-Reset")
                delay = max(2, int(reset) - int(time.time()) + 2) if reset and str(reset).isdigit() else min(60, 5 * (attempt + 1))
                last_body = resp.text[:500]
                print(f"[http_cache] {url} intento {attempt + 1}/{max_retries}: HTTP 429, esperando {delay}s. Cuerpo: {last_body!r}", flush=True)
                time.sleep(delay)
                continue
            if resp.status_code >= 500:
                last_body = resp.text[:500]
                delay = min(30, 2 ** attempt)
                print(f"[http_cache] {url} intento {attempt + 1}/{max_retries}: HTTP {resp.status_code}, esperando {delay}s. Cuerpo: {last_body!r}", flush=True)
                time.sleep(delay)
                continue
            if resp.status_code >= 400:
                # Error de cliente que no es 429 (401/403/404/etc.) -- reintentar no lo
                # arregla, asi que fallamos ya con el cuerpo de la respuesta en vez de
                # dejar que raise_for_status() tire un traceback crudo sin contexto.
                last_body = resp.text[:500]
                raise RuntimeError(
                    f"No se pudo obtener {url} ({params}): HTTP {resp.status_code} - {last_body!r}"
                )
            resp.raise_for_status()
            data = resp.json()
            if use_cache:
                self.conn.execute(
                    "INSERT OR REPLACE INTO http_cache(cache_key, prefix, fetched_at, body) VALUES (?, ?, ?, ?)",
                    (key, prefix, datetime.now(timezone.utc).isoformat(), json.dumps(data, ensure_ascii=False)),
                )
                self.conn.commit()
            return data
        raise RuntimeError(
            f"No se pudo obtener {url} ({params}) tras {max_retries} intentos: "
            f"ultimo status HTTP={last_status}, ultimo cuerpo={last_body!r}, ultima excepcion de red={last_exc!r}"
        )

    def bets(self, path: str, params: dict, *, prefix: str, use_cache: bool = True) -> dict:
        if not self.token:
            raise RuntimeError("Falta BETSAPI_TOKEN (variable de entorno / secret).")
        q = dict(params)
        q["token"] = self.token
        return self.get_json(f"{config.BETSAPI_BASE}{path}", q, prefix=prefix, bets=True, use_cache=use_cache)
