"""PRE-REGISTRO: ¿tiene valor el LOCAL / el FAVORITO que pierde de mucho
tras el Q1, comprado en vivo al ganador (moneyline)?

Hipotesis del usuario (2026-08-30): "partidos donde el local va perdiendo
de mucho en el primer cuarto -- solo locales, o bien el favorito; ¿ahi no
hay ventaja de alguna forma?". Primer test del proyecto sobre el mercado de
GANADOR en vivo. Commiteado antes de correrlo.

DATOS: data_local/bball_local.db, serie 18_1 del historial (fuente por
defecto de BetsAPI = Bet365) con marcador `ss` por entrada.

ORIENTACION (reglas preexistentes de config, no elegidas ahora):
- Bet365 publica sus cuotas siguiendo el ORDEN DEL EVENTO de BetsAPI.
- En NBA (AWAY_FIRST) el evento lista "visitante @ local": en la serie
  cruda, home_od = cuota del VISITANTE real y el ss va (visitante:local).
  En Euroliga el orden del evento es el real.
- WNBA EXCLUIDA: su orden 2026 se invierte a mitad de temporada (config).
- PUERTA DE VALIDACION (se aborta el veredicto si falla): el favorito de
  cierre segun este mapeo debe ganar 58-78% en cada liga usada.

PROCEDIMIENTO:
- Favorito = lado con menor cuota en la ultima entrada 18_1 PRE-partido
  (add_time < inicio-60s, sin ss).
- Momento de compra: entradas 18_1 con suma de ss == P1 (fin del Q1),
  ventana [inicio+8min, inicio+80min], cuotas ambas en [1.01, 30].
  PRIMARIA: ultima entrada del tramo. SENSIBILIDAD: primera entrada (el
  sesgo de anticipacion descubierto hoy obliga a exigir que la conclusion
  sea la misma con ambas; si el signo depende del extremo, NO hay señal).
- Deficit tras Q1 (margen del lado comprado): umbral PRIMARIO >= 8 puntos
  (un cuarto muy malo); secundario informativo >= 12.
- Escenario A: LOCAL real perdiendo por >= umbral -> comprar su ML vivo.
- Escenario B: FAVORITO de cierre perdiendo por >= umbral -> comprar su ML.
  (Se solapan: los favoritos suelen ser locales; se reportan por separado.)
- Gana la apuesta si ese lado gana el partido (marcador final de
  bball_games, ya normalizado a local real).

CRITERIO (el de siempre): CONFIRMADA una celda solo con ROI > 0, t >= 2,
n >= 100, coherencia NBA y Euroliga (ambas positivas) y robustez
primera/ultima entrada. 2 escenarios x 2 ligas x 2 umbrales = 8 celdas
por captura: el azar espera ~0.5 con |t|>=2; una celda suelta es ruido.

RESULTADOS: se anexan tras correr, sin tocar lo de arriba.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball import config
from bball.analysis.sobre_reaccion_q1 import suma_ss, t_pnl

VENTANA = (8 * 60, 80 * 60)
LIGAS_ML = ("NBA", "Euroleague")


def partes_ss(ss):
    s = str(ss or "")
    sep = ":" if ":" in s else "-"
    a, _, b = s.partition(sep)
    try:
        return int(a), int(b)
    except ValueError:
        return None


def cargar(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    series: dict[str, list] = defaultdict(list)
    for r in conn.execute(
        "SELECT event_id, add_time, ss, home_odds, away_odds FROM bball_odds_hist "
        "WHERE market=? AND add_time IS NOT NULL", (config.MONEYLINE_MARKET_KEY,)):
        series[r["event_id"]].append(r)

    juegos = []
    for g in conn.execute(
        "SELECT event_id, league_name, time_ts, home_score, away_score, raw_json "
        "FROM bball_games WHERE completed=1"):
        lg = g["league_name"]
        if lg not in LIGAS_ML:
            continue
        try:
            sc = json.loads(g["raw_json"]).get("scores") or {}
            p1 = int(sc["1"]["home"]) + int(sc["1"]["away"])
        except (KeyError, TypeError, ValueError):
            continue
        ts = int(g["time_ts"] or 0)
        ser = series.get(g["event_id"]) or []
        pre = [e for e in ser if e["add_time"] < ts - 60 and not e["ss"]
               and e["home_odds"] and e["away_odds"]]
        if not pre:
            continue
        cierre = max(pre, key=lambda e: e["add_time"])
        vivo = [e for e in ser if suma_ss(e["ss"]) == p1
                and ts + VENTANA[0] <= e["add_time"] <= ts + VENTANA[1]
                and e["home_odds"] and e["away_odds"]
                and 1.01 <= e["home_odds"] <= 30 and 1.01 <= e["away_odds"] <= 30]
        if not vivo:
            continue
        # orientacion: en AWAY_FIRST el 'home' crudo de la serie es el
        # VISITANTE real y el ss va (visitante:local); en Euroliga es directo
        invertida = lg.upper() in {n.upper() for n in config.AWAY_FIRST_LEAGUES}
        juegos.append(dict(
            lg=lg, invertida=invertida, ts=ts,
            gano_local=(g["home_score"] or 0) > (g["away_score"] or 0),
            cierre=cierre, ult=max(vivo, key=lambda e: e["add_time"]),
            pri=min(vivo, key=lambda e: e["add_time"]),
            sc1=sc["1"],
        ))
    conn.close()
    return juegos


def lado_real(entry, invertida, lado):
    """cuota del LOCAL real ('local') o del visitante real ('visit')."""
    if lado == "local":
        return entry["away_odds"] if invertida else entry["home_odds"]
    return entry["home_odds"] if invertida else entry["away_odds"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data_local/bball_local.db")
    args = ap.parse_args()
    juegos = cargar(args.db)

    for lg in LIGAS_ML:
        js = [j for j in juegos if j["lg"] == lg]
        # PUERTA: favorito de cierre (mapeado) gana 58-78%
        fav_ok = 0
        for j in js:
            fav_local = lado_real(j["cierre"], j["invertida"], "local") < lado_real(j["cierre"], j["invertida"], "visit")
            if fav_local == j["gano_local"]:
                fav_ok += 1
        pct = fav_ok / len(js) * 100 if js else 0
        gate = "PASA" if 58 <= pct <= 78 else "FALLA -> VEREDICTO ABORTADO EN ESTA LIGA"
        print(f"\n===== {lg}: n={len(js)} | puerta favorito gana {pct:.1f}% [{gate}]")
        if not (58 <= pct <= 78):
            continue
        for captura in ("ult", "pri"):
            print(f"  captura={'ultima' if captura=='ult' else 'primera'} entrada:")
            for esc in ("A_local", "B_favorito"):
                for umbral in (8, 12):
                    pnls = []
                    for j in js:
                        h1 = int(j["sc1"]["home"]); a1 = int(j["sc1"]["away"])
                        margen_local = h1 - a1  # sc1 viene de bball_games, ya normalizado
                        if esc == "A_local":
                            objetivo_local = True
                        else:
                            objetivo_local = lado_real(j["cierre"], j["invertida"], "local") < lado_real(j["cierre"], j["invertida"], "visit")
                        deficit = -margen_local if objetivo_local else margen_local
                        if deficit < umbral:
                            continue
                        od = lado_real(j[captura], j["invertida"], "local" if objetivo_local else "visit")
                        gana = j["gano_local"] == objetivo_local
                        pnls.append((od - 1.0) if gana else -1.0)
                    if pnls:
                        cuota = statistics.mean(p + 1 for p in pnls if p > 0) if any(p > 0 for p in pnls) else 0
                        print(f"    {esc} deficit>={umbral:2d}: n={len(pnls):4d} ROI={statistics.mean(pnls)*100:+6.1f}% "
                              f"t={t_pnl(pnls):+.2f} acierto={sum(1 for p in pnls if p>0)/len(pnls)*100:.1f}%")


if __name__ == "__main__":
    main()
