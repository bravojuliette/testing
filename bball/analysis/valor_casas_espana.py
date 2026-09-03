"""¿Hay valor en alguna casa con licencia española, en algun mercado?

CORRIGE un error del primer intento (bwin_vs_sharp.py): alli compare la
probabilidad justa de Pinnacle EN SU LINEA con la cuota de la otra casa EN
LA LINEA DE ESA CASA. Cuando las lineas difieren -- y difieren en el 30% de
los partidos -- eso compara cosas distintas. Aqui se exige MISMA LINEA para
totales y handicap; el ganador no tiene linea, asi que es directo.

Metodo: la cuota de cierre de la casa mas afilada, quitandole su margen, da
la probabilidad justa de cada lado. Valor en la casa objetivo =
p_justa x cuota_objetivo - 1. Se apuesta SOLO en la casa objetivo (una
pata, se puede perder); Pinnacle es termometro, no casa donde apostar.

Se excluye WNBA 2026 de ganador/handicap: la orientacion local/visitante
viene rota de origen (ver config.UNRELIABLE_ORIENTATION).
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball import config, db
from bball.backtest.replay import load_games

SHARP = "PinnacleSports"
OBJETIVO = ["BWin", "Bet365", "Betway", "Betsson", "UniBet", "BetClic"]
MERCADOS = [("18_3", "totales"), ("18_1", "ganador"), ("18_2", "handicap")]

with db.get_conn() as conn:
    games = {g.event_id: g for g in load_games(conn)}
    todo = conn.execute(
        "SELECT event_id, book, market, line, over_odds, under_odds FROM bball_odds "
        "WHERE snapshot = 'kickoff'"
    ).fetchall()

por_mkt = defaultdict(lambda: defaultdict(dict))
for r in todo:
    if not r["over_odds"] or not r["under_odds"]:
        continue
    if r["over_odds"] <= 1 or r["under_odds"] <= 1:
        continue
    # varias lineas por casa: se indexa por (casa, linea)
    por_mkt[r["market"]][r["event_id"]][(r["book"], r["line"])] = r


def resolver(mkt, casa):
    """Devuelve [(valor, cuota, gano)] de la mejor apuesta por partido."""
    out = []
    for eid, d in por_mkt[mkt].items():
        g = games.get(eid)
        if not g:
            continue
        if mkt in ("18_1", "18_2") and not config.orientation_is_reliable(g.league_name, g.date):
            continue
        for (bk, ln), r in d.items():
            if bk != casa:
                continue
            # el afilado, EN LA MISMA LINEA
            s = d.get((SHARP, ln))
            if not s:
                continue
            io, iu = 1 / s["over_odds"], 1 / s["under_odds"]
            p_o = io / (io + iu)
            if mkt == "18_3":
                if g.total == ln:
                    continue
                gan_o = g.total > ln
            elif mkt == "18_1":
                gan_o = g.home_score > g.away_score
            else:
                marg = g.home_score - g.away_score + (ln or 0)
                if marg == 0:
                    continue
                gan_o = marg > 0
            for p, q, gano in ((p_o, r["over_odds"], gan_o),
                               (1 - p_o, r["under_odds"], not gan_o)):
                out.append((p * q - 1, q, gano))
    return out


print(f"{'mercado':<9} {'casa':<9} {'apuestas':>9} {'con valor>0':>12} "
      f"{'n>=2%':>7} {'ROI de esas':>12} {'t':>6}")
for mkt, nombre in MERCADOS:
    for casa in OBJETIVO:
        v = resolver(mkt, casa)
        if len(v) < 200:
            continue
        pos = [x for x in v if x[0] > 0]
        sel = [x for x in v if x[0] >= 0.02]
        if len(sel) >= 30:
            pnl = [q - 1 if gano else -1.0 for _, q, gano in sel]
            sd = statistics.pstdev(pnl)
            roi = sum(pnl) / len(pnl) * 100
            t = statistics.mean(pnl) / sd * len(pnl) ** 0.5 if sd else 0
            extra = f"{roi:>+11.1f}% {t:>6.2f}"
        else:
            extra = f"{'(muestra corta)':>19}"
        print(f"{nombre:<9} {casa:<9} {len(v):>9} {len(pos):>11} "
              f"({len(pos)/len(v)*100:>3.0f}%) {len(sel):>6} {extra}")
