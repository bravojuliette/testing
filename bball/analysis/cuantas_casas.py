"""Curva ROI(N) del mejor precio entre N casas, y el mismo test restringido a
las casas con licencia en España. Ver PREREGISTRO_cuantas_casas.md.

Dos partes, en este orden:

  1) ALINEACION. Las casas NO guardan el par del moneyline en el mismo orden.
     Se alinea cada casa contra Bet365 comparando SOLO PRECIOS (nunca
     resultados): para cada evento con ambas casas, se mide si el par casa
     esta mas cerca del par Bet365 tal cual o invertido, y se decide por
     mayoria. 16 de 19 casas salen invertidas con 95-99% de consistencia:
     es convencion por casa, no ruido.

  2) CURVA ROI(N) sobre el mejor precio de N casas, por cubos de cuota, y
     luego el mismo calculo sobre subconjuntos de casas LEGALES EN ESPAÑA
     (criterio externo, elegido por licencia y no por rendimiento).

Uso:  python3 bball/analysis/cuantas_casas.py [ruta.db]
"""
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict

DB = sys.argv[1] if len(sys.argv) > 1 else "data_local/bball_turso.db"
REF = "Bet365"            # casa de referencia para alinear (la mas fiable y con mas cobertura)
ESPANA = ["Bet365", "BWin", "Betsson", "Interwetten", "Betway", "888Sport", "WilliamHill"]
CUBOS = [(1.01, 1.40), (1.40, 2.20), (2.20, 20.0)]


def cargar(conn):
    """evento -> {casa: (cuota_home, cuota_away)} en apertura, + ganador."""
    filas = conn.execute(
        """SELECT o.event_id, o.book, o.over_odds AS a, o.under_odds AS b,
                  g.home_score, g.away_score
           FROM bball_odds o JOIN bball_games g ON g.event_id = o.event_id
           WHERE o.market='18_1' AND o.snapshot='start' AND g.completed=1
             AND g.league_name LIKE '%NCAA%'
             AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
             AND g.home_score <> g.away_score
             AND o.over_odds > 1 AND o.under_odds > 1"""
    ).fetchall()
    cuotas, gana_home = defaultdict(dict), {}
    for r in filas:
        cuotas[r["event_id"]][r["book"]] = (r["a"], r["b"])
        gana_home[r["event_id"]] = r["home_score"] > r["away_score"]
    return cuotas, gana_home


def alinear(cuotas):
    """casa -> True si hay que invertir su par para que case con Bet365."""
    votos = defaultdict(Counter)
    for ev, porcasa in cuotas.items():
        ref = porcasa.get(REF)
        if not ref:
            continue
        for casa, par in porcasa.items():
            if casa == REF:
                continue
            recto = abs(par[0] - ref[0]) + abs(par[1] - ref[1])
            vuelta = abs(par[1] - ref[0]) + abs(par[0] - ref[1])
            if recto == vuelta:
                continue
            votos[casa]["inv" if vuelta < recto else "ok"] += 1
    inv = {}
    for casa, c in votos.items():
        n = c["ok"] + c["inv"]
        if n < 30:
            continue
        inv[casa] = (c["inv"] > c["ok"], max(c["ok"], c["inv"]) / n, n)
    return inv


def normalizar(cuotas, inv):
    """Devuelve evento -> {casa: (home, away)} ya alineado; descarta casas sin voto."""
    out = {}
    for ev, porcasa in cuotas.items():
        d = {}
        for casa, par in porcasa.items():
            if casa == REF:
                d[casa] = par
            elif casa in inv:
                d[casa] = (par[1], par[0]) if inv[casa][0] else par
        if d:
            out[ev] = d
    return out


def ranking_cobertura(norm):
    """Casas ordenadas por cobertura -- el orden en que un apostante real
    abriria cuentas. No usa resultados ni rendimiento."""
    c = Counter()
    for porcasa in norm.values():
        c.update(porcasa.keys())
    return [k for k, _ in c.most_common()]


def roi_mejor_precio(norm, gana_home, casas=None, n_max=None, minimo=1, orden=None):
    """ROI por cubo apostando al favorito corto/medio/largo al mejor precio.

    Apuesta SIEMPRE a los dos lados por separado (cada lado es una apuesta
    distinta y cae en su cubo por su propia cuota), como en mejor_precio.py.
    """
    acc = {c: [0.0, 0] for c in CUBOS}
    for ev, porcasa in norm.items():
        sel = porcasa if casas is None else {k: v for k, v in porcasa.items() if k in casas}
        if len(sel) < minimo:
            continue
        libros = sorted(sel, key=orden.index) if orden else sorted(sel)
        if n_max is not None:
            libros = libros[:n_max]
            if len(libros) < n_max:
                continue
        mh = max(sel[k][0] for k in libros)
        ma = max(sel[k][1] for k in libros)
        for cuota, acierta in ((mh, gana_home[ev]), (ma, not gana_home[ev])):
            for c in CUBOS:
                if c[0] <= cuota < c[1]:
                    acc[c][0] += (cuota - 1) if acierta else -1
                    acc[c][1] += 1
                    break
    return acc


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cuotas, gana_home = cargar(conn)
    print(f"eventos NCAAB con apertura y resultado: {len(cuotas)}")

    inv = alinear(cuotas)
    print(f"\n== ALINEACION contra {REF} (solo precios, nunca resultados)")
    for casa, (flip, cons, n) in sorted(inv.items(), key=lambda kv: -kv[1][2]):
        print(f"  {casa:<18} {'INVERTIDA' if flip else 'alineada':<10} consistencia {cons*100:5.1f}%  n={n}")
    print(f"  -> {sum(1 for v in inv.values() if v[0])} de {len(inv)} invertidas")

    norm = normalizar(cuotas, inv)
    fav = sum(1 for ev, p in norm.items()
              for casa, par in p.items()
              if (par[0] < par[1]) == gana_home[ev])
    tot = sum(len(p) for p in norm.values())
    print(f"  sanidad: el favorito gana el {fav/tot*100:.1f}% (n={tot})")

    orden = ranking_cobertura(norm)
    print("\n== CURVA ROI(N), las N casas de mayor cobertura")
    print("  orden de apertura de cuentas: " + ", ".join(orden[:12]))
    print(f"{'N':>3} " + " ".join(f"{f'[{a},{b})':>22}" for a, b in CUBOS))
    for n in (1, 2, 3, 4, 6, 8, 12):
        acc = roi_mejor_precio(norm, gana_home, n_max=n, orden=orden)
        cel = []
        for c in CUBOS:
            pnl, k = acc[c]
            cel.append(f"{pnl/k*100:+7.2f}% n={k:<6}" if k >= 300 else f"{'(n<300)':>22}")
        print(f"{n:>3} " + " ".join(cel))

    print("\n== MARGEN Y CUOTA DE MEJOR PRECIO entre casas legales en España")
    margenes, cobertura = defaultdict(list), Counter()
    for ev, porcasa in norm.items():
        for casa, (h, a) in porcasa.items():
            if casa in ESPANA:
                cobertura[casa] += 1
                margenes[casa].append((1 / h + 1 / a - 1) * 100)
    for casa in ESPANA:
        if cobertura[casa]:
            print(f"  {casa:<14} n={cobertura[casa]:<6} margen {statistics.mean(margenes[casa]):5.2f}%")
        else:
            print(f"  {casa:<14} n=0   (sin cobertura en este dataset)")

    for etiqueta, universo in (("ESPAÑA", ESPANA), ("TODAS", None)):
        gana = Counter()
        for ev, porcasa in norm.items():
            sel = porcasa if universo is None else {k: v for k, v in porcasa.items() if k in universo}
            if len(sel) < 2:
                continue
            for lado in (0, 1):
                gana[max(sel, key=lambda k: sel[k][lado])] += 1
        n = sum(gana.values())
        print(f"\n  quien da el mejor precio ({etiqueta}, n={n}):")
        for casa, k in gana.most_common(8):
            print(f"    {casa:<16} {k/n*100:5.1f}%")

    print("\n== ROI del mejor precio segun que cuentas españolas se abran")
    conjuntos = [
        ("Bet365 sola", ["Bet365"]),
        ("Bet365+BWin", ["Bet365", "BWin"]),
        ("+Interwetten", ["Bet365", "BWin", "Interwetten"]),
        ("+Betsson", ["Bet365", "BWin", "Interwetten", "Betsson"]),
        ("las 7 de España", ESPANA),
    ]
    for etiqueta, casas in conjuntos:
        acc = roi_mejor_precio(norm, gana_home, casas=casas, minimo=min(2, len(casas)))
        cel = []
        for c in CUBOS:
            pnl, k = acc[c]
            cel.append(f"{pnl/k*100:+7.2f}% n={k:<6}" if k >= 300 else f"{'(n<300)':>22}")
        print(f"  {etiqueta:<18} " + " ".join(cel))

    # Lo de arriba NO es comparable entre filas: cada conjunto califica partidos
    # distintos (un partido entra si tiene >=2 casas del conjunto). Para saber si
    # abrir mas cuentas ESPAÑOLAS aporta algo hay que mirar LOS MISMOS partidos.
    cuatro = ["Bet365", "BWin", "Interwetten", "Betsson"]
    comun = {ev: p for ev, p in norm.items() if all(c in p for c in cuatro)}
    print(f"\n== MISMOS PARTIDOS (los {len(comun)} con las 4 casas españolas a la vez)")
    for etiqueta, casas in (("Bet365 sola", ["Bet365"]), ("Bet365+BWin", ["Bet365", "BWin"]),
                            ("+Interwetten", cuatro[:3]), ("las 4", cuatro)):
        acc = roi_mejor_precio(comun, gana_home, casas=casas, minimo=1)
        cel = []
        for c in CUBOS:
            pnl, k = acc[c]
            cel.append(f"{pnl/k*100:+7.2f}% n={k:<6}" if k >= 300 else f"{'(n<300)':>22}")
        print(f"  {etiqueta:<18} " + " ".join(cel))

    # Y el contraste que decide: sobre ESOS MISMOS partidos, que pasa si en vez
    # de casas españolas se añaden las mismas 4 casas pero SHARP (no jugables).
    sharp = ["Bet365", "PinnacleSports", "GGBet", "SBOBET"]
    if all(any(c in p for p in comun.values()) for c in sharp):
        acc = roi_mejor_precio(comun, gana_home, casas=sharp, minimo=1)
        cel = []
        for c in CUBOS:
            pnl, k = acc[c]
            cel.append(f"{pnl/k*100:+7.2f}% n={k:<6}" if k >= 300 else f"{'(n<300)':>22}")
        print(f"  {'4 sharp (no jugables)':<18} " + " ".join(cel))


if __name__ == "__main__":
    main()
