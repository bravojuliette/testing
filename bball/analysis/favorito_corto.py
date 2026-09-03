"""H1 (descanso) y H2 (movimiento) sobre el favorito corto de Bet365.
Criterios y celdas fijados en PREREGISTRO_favorito_corto.md (commit anterior).

Uso: python3 bball/analysis/favorito_corto.py [ruta.db]
"""
import bisect
import datetime
import math
import random
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, ".")
from bball.backtest.orientacion import clasificar_orientacion

DB = sys.argv[1] if len(sys.argv) > 1 else "data_local/bball_turso.db"
LIGAS = ("NBA", "NCAA", "WNBA", "Euroleague")
UMBRALES = (1.20, 1.30, 1.40, 1.55)
CORTO = 1.40


def liga(nombre):
    if not nombre:
        return None
    if "NCAA" in nombre:
        return "NCAA"
    return nombre if nombre in LIGAS else None


def stats(apuestas):
    """apuestas = lista de (pnl,). Devuelve n, ROI%, t."""
    n = len(apuestas)
    if not n:
        return 0, 0.0, 0.0
    m = sum(apuestas) / n
    if n < 2:
        return n, m * 100, 0.0
    var = sum((x - m) ** 2 for x in apuestas) / (n - 1)
    t = m / math.sqrt(var / n) if var > 0 else 0.0
    return n, m * 100, t


def fmt(apuestas, minimo=300):
    n, roi, t = stats(apuestas)
    if n < minimo:
        return f"n={n:<5} (n<{minimo})".ljust(30)
    return f"n={n:<5} ROI {roi:+6.2f}%  t={t:+5.2f}".ljust(30)


def cargar(conn):
    orient = clasificar_orientacion(conn)
    filas = conn.execute(
        """SELECT g.event_id, g.date, g.league_name, g.home_key, g.away_key,
                  g.home_score, g.away_score,
                  s.over_odds sh, s.under_odds sa, k.over_odds kh, k.under_odds ka
           FROM bball_games g
           JOIN bball_odds s ON s.event_id=g.event_id AND s.book='Bet365'
                AND s.market='18_1' AND s.snapshot='start'
           LEFT JOIN bball_odds k ON k.event_id=g.event_id AND k.book='Bet365'
                AND k.market='18_1' AND k.snapshot='kickoff'
                AND k.over_odds>1 AND k.under_odds>1
           WHERE g.completed=1 AND g.date IS NOT NULL
             AND g.home_score IS NOT NULL AND g.home_score<>g.away_score
             AND s.over_odds>1 AND s.under_odds>1"""
    ).fetchall()

    # calendario para el descanso: SOLO fechas, ni cuotas ni resultados
    dias = defaultdict(set)
    for r in conn.execute("SELECT date, home_key, away_key FROM bball_games "
                          "WHERE completed=1 AND date IS NOT NULL"):
        dias[r["home_key"]].add(r["date"])
        dias[r["away_key"]].add(r["date"])
    cal = {k: sorted(v) for k, v in dias.items()}

    def descanso(eq, d):
        l = cal.get(eq, [])
        i = bisect.bisect_left(l, d)
        if i == 0:
            return None
        return (datetime.date.fromisoformat(d) - datetime.date.fromisoformat(l[i - 1])).days

    out = []
    for r in filas:
        lg = liga(r["league_name"])
        if lg is None:
            continue
        # Orientacion NCAAB: reetiquetar el SLOT, jamas tocar el marcador.
        eq_h, eq_a = r["home_key"], r["away_key"]
        o_h, o_a = r["sh"], r["sa"]
        kh, ka = r["kh"], r["ka"]
        if lg == "NCAA":
            cl = orient.get(r["event_id"], "sin_dato")
            if cl == "sin_dato":
                continue
            if cl == "swap":
                eq_h, eq_a = eq_a, eq_h
                o_h, o_a = o_a, o_h
                kh, ka = ka, kh
                gana_h = r["away_score"] > r["home_score"]
            else:
                gana_h = r["home_score"] > r["away_score"]
        else:
            gana_h = r["home_score"] > r["away_score"]

        fav_es_local = o_h < o_a
        cuota_ini = o_h if fav_es_local else o_a
        cuota_kick = (kh if fav_es_local else ka) if kh else None
        gana_fav = gana_h if fav_es_local else not gana_h
        eq_fav, eq_dog = (eq_h, eq_a) if fav_es_local else (eq_a, eq_h)
        df, dd = descanso(eq_fav, r["date"]), descanso(eq_dog, r["date"])
        out.append(dict(ev=r["event_id"], lg=lg, fecha=r["date"], cuota=cuota_ini,
                        cuota_kick=cuota_kick, gana_fav=gana_fav,
                        d_fav=df, d_dog=dd,
                        cuota_dog_kick=(ka if fav_es_local else kh) if kh else None))
    return out


def pnl(cuota, acierta):
    return (cuota - 1) if acierta else -1.0


def mitades(reg):
    fechas = sorted(x["fecha"] for x in reg)
    return fechas[len(fechas) // 2] if fechas else None


def h1(reg):
    print("\n" + "=" * 78)
    print("H1 -- DESCANSO en el favorito corto (apuesta a la cuota de APERTURA)")
    print("=" * 78)
    base = [x for x in reg if x["cuota"] < CORTO and x["d_fav"] is not None and x["d_dog"] is not None]
    print(f"favoritos cortos con descanso calculable: n={len(base)}")
    for lg in LIGAS:
        print(f"   {lg:<12} {sum(1 for x in base if x['lg']==lg)}")

    def D(x):
        return max(-3, min(3, x["d_fav"] - x["d_dog"]))

    print("\nEscalera de dosis-respuesta en D = descanso(fav) - descanso(dog):")
    for d in (-2, -1, 0, 1, 2):
        sel = [x for x in base if (D(x) <= -2 if d == -2 else D(x) >= 2 if d == 2 else D(x) == d)]
        etiqueta = {-2: "D <= -2", 2: "D >= +2"}.get(d, f"D  = {d:+d}")
        print(f"  {etiqueta:<10} {fmt([pnl(x['cuota'], x['gana_fav']) for x in sel])}")

    corte = mitades(base)
    print(f"\nCelda principal D >= +2, busqueda/reserva (corte {corte}):")
    prin = [x for x in base if D(x) >= 2]
    for nombre, sub in (("busqueda", [x for x in prin if x["fecha"] < corte]),
                        ("reserva ", [x for x in prin if x["fecha"] >= corte])):
        print(f"  {nombre}  {fmt([pnl(x['cuota'], x['gana_fav']) for x in sub], minimo=100)}")

    print("\nPLACEBO (descansos reasignados al azar, semillas 1/2/3):")
    for semilla in (1, 2, 3):
        rnd = random.Random(semilla)
        pares = [(x["d_fav"], x["d_dog"]) for x in base]
        rnd.shuffle(pares)
        falso = [x for x, (a, b) in zip(base, pares) if max(-3, min(3, a - b)) >= 2]
        print(f"  semilla {semilla}  {fmt([pnl(x['cuota'], x['gana_fav']) for x in falso])}")

    print("\nPor liga, celda D >= +2:")
    for lg in LIGAS:
        sel = [x for x in prin if x["lg"] == lg]
        print(f"  {lg:<12} {fmt([pnl(x['cuota'], x['gana_fav']) for x in sel], minimo=100)}")

    print("\nEscalera de umbral de cuota (celda D >= +2):")
    for u in UMBRALES:
        sel = [x for x in base if D(x) >= 2 and x["cuota"] < u]
        print(f"  cuota < {u:.2f}  {fmt([pnl(x['cuota'], x['gana_fav']) for x in sel], minimo=100)}")


def h2(reg):
    print("\n" + "=" * 78)
    print("H2 -- MOVIMIENTO apertura->kickoff (apuesta SIEMPRE a la cuota de KICKOFF)")
    print("=" * 78)
    base = [x for x in reg if x["cuota_kick"] and x["cuota_kick"] < CORTO]
    print(f"favoritos cortos al kickoff con apertura y kickoff: n={len(base)}")
    for umbral in (0.02, 0.05):
        print(f"\n  umbral |M| >= {umbral}")
        seguir = [x for x in base if x["cuota"] - x["cuota_kick"] >= umbral]
        contra = [x for x in base if x["cuota"] - x["cuota_kick"] >= umbral and x["cuota_dog_kick"]]
        alarga = [x for x in base if x["cuota_kick"] - x["cuota"] >= umbral]
        print(f"    SEGUIR   (fav se acorto -> al fav)  {fmt([pnl(x['cuota_kick'], x['gana_fav']) for x in seguir])}")
        print(f"    CONTRA   (fav se acorto -> al dog)  {fmt([pnl(x['cuota_dog_kick'], not x['gana_fav']) for x in contra])}")
        print(f"    fav se ALARGO -> al fav             {fmt([pnl(x['cuota_kick'], x['gana_fav']) for x in alarga])}")

    corte = mitades(base)
    seguir = [x for x in base if x["cuota"] - x["cuota_kick"] >= 0.02]
    print(f"\n  SEGUIR, busqueda/reserva (corte {corte}):")
    for nombre, sub in (("busqueda", [x for x in seguir if x["fecha"] < corte]),
                        ("reserva ", [x for x in seguir if x["fecha"] >= corte])):
        print(f"    {nombre}  {fmt([pnl(x['cuota_kick'], x['gana_fav']) for x in sub], minimo=100)}")


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    reg = cargar(conn)
    print(f"partidos cargados (Bet365, moneyline apertura, 4 ligas): {len(reg)}")
    base_corta = [x for x in reg if x["cuota"] < CORTO]
    print(f"favoritos cortos (<{CORTO}): {len(base_corta)}")
    print(f"  linea base sin filtro: {fmt([pnl(x['cuota'], x['gana_fav']) for x in base_corta])}")
    h1(reg)
    h2(reg)


if __name__ == "__main__":
    main()
