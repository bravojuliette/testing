"""Tanda de teorias NUEVAS -- angulos nunca probados con estos datos.

Todo al cierre real, primera casa entre Bet365/Betway/BWin (normalizadas por
el reparse; ligas de orientacion fiable para handicap). Se cuentan las
casillas miradas: con ~15, UN t>=2 por azar es lo esperado.

HANDICAP (nunca barrido):
  1. ¿Cubre el local mas o menos del 50%?
  2. ¿Cubren los favoritos GRANDES? (la sabiduria popular dice que no)
  3. Back-to-back: ¿cubre menos el equipo sin descanso? ¿y el visitante b2b?
  4. Resaca de paliza: ¿cubre menos quien viene de ganar de 20+? ¿mas quien
     viene de perder de 20+? (rebote/relajacion)
  5. Steam: el handicap se movio >=2 pts de apertura a cierre -> ¿seguir el
     movimiento paga al cierre?

TOTALES (angulos finos no probados):
  6. Prorroga escondida: los partidos IGUALADOS (|handicap|<3) van a OT ~10%
     de las veces y la OT suma puntos. ¿Lo tiene la linea metido? (over en
     igualados vs desiguales)
  7. Playoffs: 'en playoffs se defiende mas' -> ¿under sistematico?
  8. Resaca de prorroga: el partido SIGUIENTE de un equipo que jugo OT
     (cansancio) -> ¿under?
  9. Principio de temporada: ¿la linea se equivoca mas (|error| mayor) en
     los 2 primeros meses? ¿y con sesgo de lado?
"""
import json
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from bball import config, db
from bball.backtest.replay import load_games

BOOKS = ("Bet365", "Betway", "BWin")


def stat(v):
    if len(v) < 40:
        return None
    sd = statistics.pstdev(v)
    return dict(n=len(v), roi=statistics.mean(v) * 100,
                t=statistics.mean(v) / sd * len(v) ** 0.5 if sd else 0)


def linea(et, v):
    r = stat(v)
    if not r:
        print(f"  {et:<44} n={len(v):>4}  (muestra corta)")
        return
    marca = "  <-- t>=2" if abs(r["t"]) >= 2 else ""
    print(f"  {et:<44} n={r['n']:>5}  ROI {r['roi']:>+6.1f}%  t={r['t']:>+5.2f}{marca}")


with db.get_conn() as conn:
    games = sorted(load_games(conn), key=lambda x: x.time_ts)
    raw = {r["event_id"]: r["raw_json"] for r in conn.execute(
        "SELECT event_id, raw_json FROM bball_games WHERE completed=1").fetchall()}
    sp = defaultdict(dict)
    for r in conn.execute("SELECT event_id, book, line, over_odds h, under_odds a, snapshot "
                          "FROM bball_odds WHERE market='18_2'").fetchall():
        sp[(r["snapshot"], r["event_id"])][r["book"]] = r
    tot = defaultdict(dict)
    for r in conn.execute("SELECT event_id, book, line, over_odds o, under_odds u "
                          "FROM bball_odds WHERE market='18_3' AND snapshot='kickoff'").fetchall():
        tot[r["event_id"]][r["book"]] = r

last_ts, last_marg, last_ot = {}, {}, {}
muestras = []
for g in games:
    lg = g.league_name or ""
    fiable_hcap = ("NCAA" not in lg) and config.orientation_is_reliable(lg, g.date)
    rk = next((sp[("kickoff", g.event_id)][b] for b in BOOKS
               if b in sp.get(("kickoff", g.event_id), {})), None)
    ro = next((sp[("start", g.event_id)][b] for b in BOOKS
               if b in sp.get(("start", g.event_id), {})), None)
    rt = next((tot[g.event_id][b] for b in BOOKS if b in tot.get(g.event_id, {})), None)
    # OT: el final excede la suma de los 4 cuartos
    ot = False
    try:
        scz = json.loads(raw[g.event_id]).get("scores") or {}
        q4 = sum(int(scz[k]["home"]) + int(scz[k]["away"]) for k in ("1", "2", "4", "5"))
        ot = g.total > q4
    except Exception:
        pass
    m = dict(
        lg=lg, date=g.date, marg=g.home_score - g.away_score, total=g.total,
        hcap=rk["line"] if (rk and fiable_hcap) else None,
        h_od=rk["h"] if (rk and fiable_hcap) else None,
        a_od=rk["a"] if (rk and fiable_hcap) else None,
        hcap_open=ro["line"] if (ro and fiable_hcap) else None,
        L=rt["line"] if rt else None, o_od=rt["o"] if rt else None, u_od=rt["u"] if rt else None,
        desc_h=(g.time_ts - last_ts[g.home_key]) / 86400 if g.home_key in last_ts else 9,
        desc_a=(g.time_ts - last_ts[g.away_key]) / 86400 if g.away_key in last_ts else 9,
        prev_h=last_marg.get(g.home_key, 0), prev_a=last_marg.get(g.away_key, 0),
        ot_prev_h=last_ot.get(g.home_key, False), ot_prev_a=last_ot.get(g.away_key, False),
    )
    muestras.append(m)
    last_ts[g.home_key] = last_ts[g.away_key] = g.time_ts
    last_marg[g.home_key] = g.home_score - g.away_score
    last_marg[g.away_key] = g.away_score - g.home_score
    last_ot[g.home_key] = last_ot[g.away_key] = ot


def ats(m, lado):
    """pnl de apostar el handicap: lado 'H' = local con su handicap."""
    cubre = m["marg"] + m["hcap"]
    if cubre == 0:
        return 0.0
    if lado == "H":
        return m["h_od"] - 1 if cubre > 0 else -1.0
    return m["a_od"] - 1 if cubre < 0 else -1.0


def ou(m, lado):
    if m["total"] == m["L"]:
        return 0.0
    if lado == "O":
        return m["o_od"] - 1 if m["total"] > m["L"] else -1.0
    return m["u_od"] - 1 if m["total"] < m["L"] else -1.0


H = [m for m in muestras if m["hcap"] is not None and m["h_od"] and m["a_od"]
     and m["h_od"] > 1 and m["a_od"] > 1]
T = [m for m in muestras if m["L"] is not None and m["o_od"] and m["u_od"]
     and m["o_od"] > 1 and m["u_od"] > 1]
print(f"handicap apostable (ligas fiables): {len(H)} | totales apostables: {len(T)}\n")

print("HANDICAP:")
linea("1. local con su handicap, siempre", [ats(m, "H") for m in H])
linea("2. favorito GRANDE cubre (hcap<=-9, apostarlo)", [ats(m, "H") for m in H if m["hcap"] <= -9])
linea("   ...o apostar CONTRA el (el perro +9)", [ats(m, "A") for m in H if m["hcap"] <= -9])
linea("3. b2b: contra el equipo SIN descanso (local)", [ats(m, "A") for m in H if m["desc_h"] <= 1.1 < m["desc_a"]])
linea("   contra el visitante en b2b", [ats(m, "H") for m in H if m["desc_a"] <= 1.1 < m["desc_h"]])
linea("4. resaca: contra quien gano de 20+ (local)", [ats(m, "A") for m in H if m["prev_h"] >= 20])
linea("   a favor de quien perdio de 20+ (local)", [ats(m, "H") for m in H if m["prev_h"] <= -20])
mov = [m for m in H if m["hcap_open"] is not None and abs(m["hcap"] - m["hcap_open"]) >= 2]
linea("5. steam: seguir el movimiento del handicap", [ats(m, "H" if m["hcap"] < m["hcap_open"] else "A") for m in mov])

print("\nTOTALES:")
TH = [m for m in T if m["hcap"] is not None]
linea("6. over en partidos IGUALADOS (|hcap|<3)", [ou(m, "O") for m in TH if abs(m["hcap"]) < 3])
linea("   over en DESIGUALES (|hcap|>=9)", [ou(m, "O") for m in TH if abs(m["hcap"]) >= 9])
po = [m for m in T if (m["lg"] == "NBA" and m["date"][5:7] in ("04", "05", "06") and m["date"][8:] > "18")
      or (m["lg"] == "WNBA" and m["date"][5:7] in ("09", "10"))]
linea("7. under en playoffs (NBA abr18+/WNBA sep-oct)", [ou(m, "U") for m in po])
linea("8. under tras PRORROGA de cualquiera de los dos", [ou(m, "U") for m in T if m["ot_prev_h"] or m["ot_prev_a"]])
print("\n9. ¿Se equivoca mas la linea al principio de temporada? (|final-linea| medio)")
for lg, meses_ini in (("NBA", ("10", "11")), ("NCAAB", ("11", "12")), ("Euroleague", ("10", "11"))):
    sub = [m for m in T if (lg in m["lg"] if lg == "NCAAB" else m["lg"] == lg)]
    ini = [abs(m["total"] - m["L"]) for m in sub if m["date"][5:7] in meses_ini]
    resto = [abs(m["total"] - m["L"]) for m in sub if m["date"][5:7] not in meses_ini]
    if len(ini) > 100 and len(resto) > 100:
        pnl_o = [ou(m, "O") for m in sub if m["date"][5:7] in meses_ini]
        r = stat(pnl_o)
        print(f"  {lg:<11} inicio {statistics.mean(ini):.2f} vs resto {statistics.mean(resto):.2f}"
              f"  | over al inicio: ROI {r['roi']:+.1f}% t={r['t']:+.2f}" if r else "")
