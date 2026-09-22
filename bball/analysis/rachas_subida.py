"""Teoria del usuario: cuando un equipo lleva X partidos seguidos AUMENTANDO
su puntuacion (anotacion propia), en el siguiente 'suele bajarla'. ¿Cual es
X? ¿Y si los DOS equipos del partido llegan en esa dinamica, sube mucho la
probabilidad de under?

Tres medidas, separando el fenomeno de lo apostable:
1. P(baja su puntuacion) segun la longitud de la racha -- OJO: esto sale
   alto para cualquier racha por pura regresion a la media (tras subir
   varias veces, el ultimo valor esta alto). Se reporta junto al caso base
   (racha 0) para ver si la racha añade algo mas alla del artefacto.
2. Lo apostable: P(total < linea de CIERRE) segun rachas, y el sesgo de la
   linea (media de final - cierre). Si la casa ya descuenta la racha, aqui
   no habra nada.
3. Apuesta real: under al cierre de casas legales cuando 1 o 2 equipos
   llegan en racha >= k, split 2025-26 / 2024-25 (y su contrario over,
   por simetria).
"""
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")  # correr desde la raiz del repo

from bball import db
from bball.backtest.replay import load_games

SPLIT = "2025-10-01"
LEGAL_BOOKS = ["Bet365", "Betway", "BWin"]
MIN_N = 25

with db.get_conn() as conn:
    games = load_games(conn)
    rows = conn.execute(
        "SELECT event_id, book, line, over_odds, under_odds, snapshot FROM bball_odds "
        "WHERE market='18_3' AND snapshot='kickoff'"
    ).fetchall()

kick = defaultdict(dict)
for r in rows:
    kick[r["event_id"]][r["book"]] = r


def streak_up(hist: list) -> int:
    """Numero de subidas estrictas consecutivas al final del historial:
    hist[-1] > hist[-2] > ... (racha 1 = el ultimo partido subio)."""
    k = 0
    for i in range(len(hist) - 1, 0, -1):
        if hist[i] > hist[i - 1]:
            k += 1
        else:
            break
    return k


pts = defaultdict(list)
team_events = []   # (racha_previa, ¿bajo su puntuacion?) por equipo-partido
samples = []
for g in sorted(games, key=lambda x: x.time_ts):
    ks = kick.get(g.event_id, {})
    lines = [r["line"] for r in ks.values()]
    consensus = statistics.median(lines) if lines else None
    h_hist, a_hist = pts[g.home_key], pts[g.away_key]
    if len(h_hist) >= 2 and len(a_hist) >= 2:
        sh, sa = streak_up(h_hist), streak_up(a_hist)
        team_events.append((sh, g.home_score < h_hist[-1]))
        team_events.append((sa, g.away_score < a_hist[-1]))
        if consensus is not None:
            s = dict(date=g.date, league=g.league_name, final=g.total,
                     consensus=consensus, sh=sh, sa=sa,
                     smax=max(sh, sa), smin=min(sh, sa))
            for b in LEGAL_BOOKS:
                r = ks.get(b)
                s[b] = None if r is None else dict(L=r["line"], under=r["under_odds"], over=r["over_odds"])
            samples.append(s)
    pts[g.home_key].append(g.home_score)
    pts[g.away_key].append(g.away_score)

print(f"Equipo-partidos evaluables: {len(team_events)}; partidos con cierre: {len(samples)}\n")

# ---------- 1. el fenomeno: ¿baja la puntuacion tras una racha de k subidas? ----------
print("1. P(el equipo anota MENOS que en su partido anterior) segun racha de subidas:")
print(f"{'racha previa':<16} {'n':>6} {'P(baja)':>8}")
byk = defaultdict(list)
for k, dropped in team_events:
    byk[min(k, 4)].append(dropped)
for k in sorted(byk):
    lab = f"k = {k}" if k < 4 else "k >= 4"
    v = byk[k]
    print(f"{lab:<16} {len(v):>6} {sum(v)/len(v)*100:>7.1f}%")
print("(k=0 es el caso base: su ultimo partido NO subio -- la diferencia con k>=1")
print(" mide el fenomeno; ojo, gran parte es regresion a la media, no 'cansancio')\n")

# ---------- 2. ¿lo sabe la linea? total vs cierre segun rachas ----------
print("2. ¿Va el TOTAL under la linea de cierre cuando hay racha? (lo apostable)")
print(f"{'condicion':<38} {'n':>5} {'P(under)':>9} {'media final-cierre':>19}")
conds = [
    ("ningun equipo en racha (max k<=1)", lambda s: s["smax"] <= 1),
    ("algun equipo racha >= 2", lambda s: s["smax"] >= 2),
    ("algun equipo racha >= 3", lambda s: s["smax"] >= 3),
    ("algun equipo racha >= 4", lambda s: s["smax"] >= 4),
    ("LOS DOS en racha >= 2", lambda s: s["smin"] >= 2),
    ("LOS DOS en racha >= 3", lambda s: s["smin"] >= 3),
]
for name, cond in conds:
    sub = [s for s in samples if cond(s)]
    dec = [s for s in sub if s["final"] != s["consensus"]]
    if not dec:
        print(f"{name:<38} {len(sub):>5}  (sin muestra)")
        continue
    p = sum(1 for s in dec if s["final"] < s["consensus"]) / len(dec) * 100
    bias = statistics.mean(s["final"] - s["consensus"] for s in sub)
    print(f"{name:<38} {len(sub):>5} {p:>8.1f}% {bias:>+18.2f}")

# ---------- 3. apuesta real al cierre ----------
SIGNALS = []
for k in (2, 3, 4):
    SIGNALS.append((f"U: algun equipo racha >= {k}", "U", lambda s, k=k: s["smax"] >= k))
    SIGNALS.append((f"O: algun equipo racha >= {k}", "O", lambda s, k=k: s["smax"] >= k))
for k in (2, 3):
    SIGNALS.append((f"U: LOS DOS racha >= {k}", "U", lambda s, k=k: s["smin"] >= k))
    SIGNALS.append((f"O: LOS DOS racha >= {k}", "O", lambda s, k=k: s["smin"] >= k))

LEAGUES = [None, "NBA", "WNBA", "Euroleague"]

def evaluate(cond, side, book, league, subset):
    pnls, wins, dec = [], 0, 0
    for s in subset:
        if league is not None and s["league"] != league:
            continue
        bk = s[book]
        if bk is None or not cond(s):
            continue
        odds = bk["under"] if side == "U" else bk["over"]
        if not odds or odds <= 1:
            continue
        if s["final"] == bk["L"]:
            pnls.append(0.0)
            continue
        won = s["final"] < bk["L"] if side == "U" else s["final"] > bk["L"]
        pnls.append(odds - 1 if won else -1.0)
        dec += 1
        wins += won
    n = len(pnls)
    if n == 0:
        return None
    roi = sum(pnls) / n * 100
    sd = statistics.pstdev(pnls) if n > 1 else 0
    t = (statistics.mean(pnls) / sd) * (n ** 0.5) if sd > 0 else None
    return dict(n=n, roi=roi, t=t, hit=wins / dec * 100 if dec else 0)

search = [s for s in samples if s["date"] >= SPLIT]
hold = [s for s in samples if s["date"] < SPLIT]
results = []
for name, side, cond in SIGNALS:
    for book in LEGAL_BOOKS:
        for lg in LEAGUES:
            r = evaluate(cond, side, book, lg, search)
            if r is None or r["n"] < MIN_N:
                continue
            h = evaluate(cond, side, book, lg, hold)
            results.append(dict(name=name, book=book, lg=lg or "todas", s=r, h=h))

results.sort(key=lambda x: -x["s"]["roi"])
print(f"\n3. APUESTA AL CIERRE REAL -- combinaciones con n>={MIN_N}: {len(results)}. Top 12 por ROI busqueda:")
print(f"{'señal':<30} {'casa':<8} {'liga':<11} | {'n':>4} {'hit%':>5} {'ROI%':>7} {'t':>5} | {'n24':>4} {'ROI24%':>7} {'t24':>5}")
for x in results[:12]:
    s, h = x["s"], x["h"]
    t_s = f"{s['t']:.2f}" if s["t"] is not None else "-"
    if h is None:
        h_str = f"{'--':>4} {'--':>7} {'--':>5}"
    else:
        t_h = f"{h['t']:.2f}" if h["t"] is not None else "-"
        h_str = f"{h['n']:>4} {h['roi']:>+7.1f} {t_h:>5}"
    print(f"{x['name']:<30} {x['book']:<8} {x['lg']:<11} | {s['n']:>4} {s['hit']:>5.1f} {s['roi']:>+7.1f} {t_s:>5} | {h_str}")

print("\nROBUSTOS (positivo y t>=1.5 en ambas temporadas, n24>=15):")
found = False
for x in results:
    s, h = x["s"], x["h"]
    if h is None or h["n"] < 15:
        continue
    if s["roi"] > 0 and h["roi"] > 0 and s["t"] and h["t"] and s["t"] >= 1.5 and h["t"] >= 1.5:
        found = True
        print(f"  {x['name']} @ {x['book']} [{x['lg']}]: "
              f"25-26 n={s['n']} ROI{s['roi']:+.1f}% t={s['t']:.2f} | "
              f"24-25 n={h['n']} ROI{h['roi']:+.1f}% t={h['t']:.2f}")
if not found:
    print("  (ninguno)")
