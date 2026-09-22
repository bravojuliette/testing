"""Alineacion del par del moneyline entre casas -- POR (casa, LIGA).

Por que existe, y por que la version global estaba mal
------------------------------------------------------
En `bball_odds` el par (over_odds, under_odds) del mercado 18_1 guarda las dos
cuotas del moneyline en el orden en que las devolvio BetsAPI para esa casa, y
ese orden NO es el mismo en todas. Eso ya se sabia. Lo que se descubrio el
2026-09-03 es que **tampoco es el mismo en todas las ligas para una misma
casa**: en NCAAB practicamente todas las casas van INVERTIDAS respecto a
Bet365, mientras que en NBA/WNBA/Euroliga esas mismas casas van alineadas, con
consistencias del 96-99% DENTRO de cada liga.

Una alineacion global por casa promedia esas dos convenciones opuestas y sale a
cara o cruz (consistencias del 50-54%), lo que orienta los pares al azar y
hunde el acierto de cualquier consenso hasta el ~50%. Asi se corrompio la
primera version de `orden_apertura.py` y la de `pinnacle_referencia.py`.

Metodo: se vota por PRECIOS contra Bet365 (jamas por resultados) dentro de cada
(casa, liga). Se exige un minimo de votos; sin ellos la casa queda fuera para
esa liga, que es preferible a adivinar.
"""
from collections import Counter, defaultdict

REF = "Bet365"
LIGAS = ("NBA", "NCAA", "WNBA", "Euroleague")


def liga_de(nombre: str | None) -> str | None:
    if not nombre:
        return None
    if "NCAA" in nombre:
        return "NCAA"
    return nombre if nombre in LIGAS else None


def votar(eventos: dict, liga_por_evento: dict, min_votos: int = 30) -> dict:
    """(casa, liga) -> (invertir: bool, consistencia: float, n: int).

    `eventos`: event_id -> {casa: (cuota_a, cuota_b)}.
    """
    votos = defaultdict(Counter)
    for ev, porcasa in eventos.items():
        ref = porcasa.get(REF)
        lg = liga_por_evento.get(ev)
        if not ref or lg is None:
            continue
        for casa, par in porcasa.items():
            if casa == REF:
                continue
            recto = abs(par[0] - ref[0]) + abs(par[1] - ref[1])
            vuelta = abs(par[1] - ref[0]) + abs(par[0] - ref[1])
            if recto == vuelta:
                continue
            votos[(casa, lg)]["inv" if vuelta < recto else "ok"] += 1
    out = {}
    for clave, c in votos.items():
        n = c["ok"] + c["inv"]
        if n >= min_votos:
            out[clave] = (c["inv"] > c["ok"], max(c["ok"], c["inv"]) / n, n)
    return out


def alinear_par(par, casa, liga, tabla):
    """Devuelve el par en el mismo orden que Bet365, o None si no hay voto."""
    if casa == REF:
        return par
    v = tabla.get((casa, liga))
    if v is None:
        return None
    return (par[1], par[0]) if v[0] else par
