"""Auditoria integral: invariantes que DEBEN cumplirse en datos sanos.
Cada uno cazo (o habria cazado) un bug real de esta base. Correr tras
cualquier recoleccion o migracion. Imprime PASS/FAIL por invariante.
"""
import json
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball import config, db
from bball.backtest.orientacion import clasificar_orientacion
from bball.backtest.replay import load_games

fallos = []


def check(nombre, ok, detalle=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {nombre}" + (f" -- {detalle}" if detalle else ""))
    if not ok:
        fallos.append(nombre)


with db.get_conn() as conn:
    games = load_games(conn)
    gd = {g.event_id: g for g in games}
    ml = conn.execute("SELECT event_id, book, over_odds h, under_odds a FROM bball_odds "
                      "WHERE snapshot='kickoff' AND market='18_1'").fetchall()
    tt = conn.execute("SELECT event_id, book, line, over_odds o, under_odds u, snapshot "
                      "FROM bball_odds WHERE market='18_3' AND snapshot IN ('start','kickoff')").fetchall()
    sp2 = conn.execute("SELECT event_id, line, snapshot FROM bball_odds WHERE market='18_2'").fetchall()
    ven = conn.execute("SELECT COUNT(*) c FROM bball_venues").fetchone()["c"]
    raws = conn.execute("SELECT event_id, raw_json FROM bball_games WHERE completed=1").fetchall()
    orient = clasificar_orientacion(conn)

print("1. PARTIDOS")
lgs = defaultdict(list)
for g in games:
    lgs["NCAAB" if "NCAA" in (g.league_name or "") else g.league_name].append(g)
check("marcadores sanos (0<puntos<200 en ambos)", all(0 < g.home_score < 200 and 0 < g.away_score < 200 for g in games),
      "load_games ya filtra los 0-0 suspendidos")
for lg, gs in sorted(lgs.items(), key=lambda kv: -len(kv[1])):
    if len(gs) < 300:
        continue
    if lg == "NCAAB":
        okg = [g for g in gs if orient.get(g.event_id) == "ok"]
        swg = [g for g in gs if orient.get(g.event_id) == "swap"]
        pl = (sum(1 for g in okg if g.home_score > g.away_score) +
              sum(1 for g in swg if g.away_score > g.home_score)) / max(1, len(okg) + len(swg))
        check(f"ventaja de campo {lg} (corregida por estadio)", 0.55 < pl < 0.75, f"{pl*100:.1f}%")
    else:
        pl = sum(1 for g in gs if g.home_score > g.away_score) / len(gs)
        check(f"ventaja de campo {lg}", 0.50 < pl < 0.70, f"{pl*100:.1f}%")

print("2. CUARTOS (raw_json)")
mal = tot = 0
for r in raws[:4000]:
    sc = json.loads(r["raw_json"]).get("scores") or {}
    g = gd.get(r["event_id"])
    if not g or not all(k in sc for k in ("1", "2", "4", "5")):
        continue
    tot += 1
    try:
        s4 = sum(int(sc[k]["home"]) + int(sc[k]["away"]) for k in ("1", "2", "4", "5"))
    except (TypeError, ValueError, KeyError):
        mal += 1
        continue
    if not (s4 <= g.total <= s4 + 45):     # el final = 4 cuartos (+ prorrogas)
        mal += 1
check("suma de cuartos <= final <= cuartos+OT", mal / max(1, tot) < 0.02, f"{mal}/{tot} raros")

print("3. CUOTAS DE GANADOR (el invariante que cazo 3 casas invertidas)")
st = defaultdict(lambda: [0, 0])
for r in ml:
    g = gd.get(r["event_id"])
    if not g or not r["h"] or not r["a"] or r["h"] <= 1 or r["a"] <= 1:
        continue
    if not config.book_odds_reliable(r["book"]) or r["book"] == "CloudBet":
        # CloudBet: cuotas blandas/rancias en NCAAB (su favorito implica 81.6%
        # y gana 88%) -- no es bug de orientacion, pero distorsiona el rango.
        continue
    lg = "NCAAB" if "NCAA" in (g.league_name or "") else g.league_name
    if lg == "NCAAB":
        o = orient.get(r["event_id"])
        if o not in ("ok", "swap"):
            continue
        fisico = r["book"] not in config.ODDS_FEED_FOLLOWS_EVENT_ORDER
        gana_h = (g.home_score > g.away_score) if (o == "ok" or not fisico) else (g.away_score > g.home_score)
        if not fisico and o == "swap":
            gana_h = g.home_score > g.away_score
    else:
        if not config.orientation_is_reliable(lg, g.date):
            continue
        gana_h = g.home_score > g.away_score
    st[(r["book"], lg)][1] += 1
    st[(r["book"], lg)][0] += (r["h"] < r["a"]) == gana_h
peor = None
for (bk, lg), (w, n) in st.items():
    if n < 400:
        continue
    p = w / n
    if peor is None or abs(p - 0.67) > abs(peor[2] - 0.67):
        peor = (bk, lg, p, n)
    if not 0.58 < p < 0.78:
        check(f"favorito 58-78%: {bk}/{lg}", False, f"{p*100:.1f}% (n={n})")
check("favorito de cierre 58-78% en todas las (casa, liga) con n>=400", not fallos or all("favorito" not in f for f in fallos),
      f"caso extremo: {peor[0]}/{peor[1]} {peor[2]*100:.1f}%")

print("4. TOTALES")
porlg = defaultdict(lambda: ([], []))
for r in tt:
    if r["snapshot"] != "kickoff" or not r["line"]:
        continue
    g = gd.get(r["event_id"])
    if not g:
        continue
    lg = "NCAAB" if "NCAA" in (g.league_name or "") else g.league_name
    porlg[lg][0].append(r["line"])
    porlg[lg][1].append(g.total)
for lg, (xs, ys) in sorted(porlg.items(), key=lambda kv: -len(kv[1][0])):
    if len(xs) < 500:
        continue
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** .5
    c = num / den
    # el maximo teorico depende de cuanto VARIAN las lineas en esa liga:
    # corr_max = sd(lineas) / sqrt(sd(lineas)^2 + sd(residuo)^2). Exigimos
    # llegar al 70% de ese maximo (medido: las 4 ligas rondan el 90%).
    sdl = statistics.pstdev(xs)
    cmax = sdl / (sdl ** 2 + 17.2 ** 2) ** 0.5
    check(f"corr(linea, total) {lg} >= 70% del max teorico ({cmax:.2f})", c >= 0.7 * cmax, f"{c:.3f}")
    check(f"sesgo |media(final-linea)| {lg} < 2.5", abs(my - mx) < 2.5, f"{my-mx:+.2f}")

print("5. COBERTURAS Y PROCESOS")
check("estadios para >=85% de NCAAB", ven / max(1, len(lgs['NCAAB'])) >= 0.85, f"{ven}/{len(lgs['NCAAB'])}")
ck = sum(1 for r in tt if r["snapshot"] == "kickoff")
op = sum(1 for r in tt if r["snapshot"] == "start")
check("cierres y aperturas de totales presentes", ck > 50000 and op > 50000, f"kickoff={ck} start={op}")
n_ml_start = 0
with db.get_conn() as conn:
    n_ml_start = conn.execute("SELECT COUNT(*) c FROM bball_odds WHERE market='18_2' AND snapshot='start'").fetchone()["c"]
print(f"  [info] aperturas de handicap reparseadas hasta ahora: {n_ml_start}")

print()
if fallos:
    print(f"AUDITORIA: {len(fallos)} FALLO(S): {fallos}")
    sys.exit(1)
print("AUDITORIA: todo PASS")
