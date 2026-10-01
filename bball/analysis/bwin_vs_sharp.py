"""¿Se equivoca BWin respecto al consenso afilado, y se puede cobrar?

IMPORTANTE sobre la restriccion del usuario: descarto Pinnacle como CASA
donde apostar (no tiene licencia española). Eso no impide usar su PRECIO
como informacion. Aqui no se apuesta ni un euro fuera de BWin: Pinnacle solo
aporta la mejor estimacion publica del total, igual que uno miraria un
termometro sin comprarlo. No es arbitraje: no se cubren las dos patas, se
apuesta una sola vez, en BWin, y se puede perder.

La idea, que es el metodo estandar de quien vive de esto: la linea de
Pinnacle al cierre es la prevision mas precisa que existe. Cuando BWin
cotiza una linea distinta, o la misma linea a mejor precio, esa diferencia
es ventaja medible -- y no depende de predecir el baloncesto mejor que
nadie, solo de detectar que una casa va por detras de la otra.
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball import config, db
from bball.backtest.replay import load_games

SHARP = "PinnacleSports"
MIA = "BWin"

with db.get_conn() as conn:
    games = {g.event_id: g for g in load_games(conn)}
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds FROM bball_odds "
        "WHERE market = ? AND snapshot = 'kickoff' AND book IN (?, ?)",
        (config.TOTALS_MARKET_KEY, SHARP, MIA)
    ).fetchall()

d = defaultdict(dict)
for r in rows:
    if r["over_odds"] and r["under_odds"] and r["over_odds"] > 1 and r["under_odds"] > 1:
        d[r["event_id"]][r["book"]] = r

m = []
for eid, bk in d.items():
    if SHARP not in bk or MIA not in bk or eid not in games:
        continue
    g = games[eid]
    s, b = bk[SHARP], bk[MIA]
    # probabilidad justa de Pinnacle, quitandole su margen
    io, iu = 1/s["over_odds"], 1/s["under_odds"]
    m.append(dict(
        date=g.date, lg=('NCAAB' if 'NCAA' in (g.league_name or '') else g.league_name),
        final=g.total, Ls=s["line"], Lb=b["line"],
        p_over=io/(io+iu), bo=b["over_odds"], bu=b["under_odds"],
    ))

print(f"Partidos con cierre en Pinnacle Y en BWin: {len(m)}")
if not m:
    sys.exit()
print(f"rango: {min(x['date'] for x in m)} .. {max(x['date'] for x in m)}\n")

print("¿Cuanto se desvia BWin de Pinnacle?")
dif = [x["Lb"] - x["Ls"] for x in m]
print(f"   diferencia de linea: mediana {statistics.median(dif):+.1f}, "
      f"|dif|>=1 en el {sum(1 for x in dif if abs(x)>=1)/len(dif)*100:.0f}% de los partidos\n")

def ev(sub, lado):
    pnl, ok, dec = [], 0, 0
    for x in sub:
        q = x["bo"] if lado == "O" else x["bu"]
        if x["final"] == x["Lb"]:
            pnl.append(0.0); continue
        gano = x["final"] > x["Lb"] if lado == "O" else x["final"] < x["Lb"]
        pnl.append(q - 1 if gano else -1.0); dec += 1; ok += gano
    n = len(pnl)
    if n == 0: return None
    sd = statistics.pstdev(pnl) if n > 1 else 0
    return dict(n=n, roi=sum(pnl)/n*100, hit=ok/dec*100 if dec else 0,
                t=(statistics.mean(pnl)/sd)*(n**0.5) if sd > 0 else 0)

print("ESTRATEGIA: apostar en BWin el lado que Pinnacle dice que esta barato.")
print("La ventaja = P(justa de Pinnacle) x cuota de BWin - 1\n")
print(f"{'ventaja exigida':<22} {'n':>5} {'acierto':>8} {'ROI':>8} {'t':>6} {'picks/dia':>10}")
dias = len({x["date"] for x in m})
for lo, hi in ((0.0, 0.02), (0.02, 0.04), (0.04, 0.07), (0.07, 0.12), (0.12, 9)):
    sub = []
    for x in m:
        # el lado apostable es el que da mas valor segun Pinnacle
        vo = x["p_over"] * x["bo"] - 1
        vu = (1 - x["p_over"]) * x["bu"] - 1
        v, lado = (vo, "O") if vo >= vu else (vu, "U")
        if lo <= v < hi:
            sub.append((x, lado))
    if len(sub) < 25:
        print(f"{f'{lo*100:.0f}% a {hi*100:.0f}%':<22} {len(sub):>5}   (muestra corta)")
        continue
    pnl, ok, dec = [], 0, 0
    for x, lado in sub:
        q = x["bo"] if lado == "O" else x["bu"]
        if x["final"] == x["Lb"]:
            pnl.append(0.0); continue
        gano = x["final"] > x["Lb"] if lado == "O" else x["final"] < x["Lb"]
        pnl.append(q - 1 if gano else -1.0); dec += 1; ok += gano
    sd = statistics.pstdev(pnl)
    print(f"{f'{lo*100:.0f}% a {hi*100:.0f}%':<22} {len(pnl):>5} {ok/dec*100:>7.1f}% "
          f"{sum(pnl)/len(pnl)*100:>+7.1f}% {statistics.mean(pnl)/sd*len(pnl)**0.5:>6.2f} "
          f"{len(pnl)/dias:>10.1f}")

print("\nReferencia sin filtro (todo lo que BWin cotiza):")
print(f"{'':<22} {'n':>5} {'acierto':>8} {'ROI':>8} {'t':>6}")
for lado, et in (("O", "siempre over"), ("U", "siempre under")):
    r = ev(m, lado)
    print(f"{et:<22} {r['n']:>5} {r['hit']:>7.1f}% {r['roi']:>+7.1f}% {r['t']:>6.2f}")
