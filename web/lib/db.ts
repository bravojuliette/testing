import { createClient } from "@libsql/client";

// El equivalente Python de este cliente (usado en GitHub Actions) interpretaba
// 'libsql://' como WebSocket y el handshake fallaba contra Turso en produccion
// (ver tt_elite/db.py::_normalize_turso_url). 'https://' con el mismo host usa
// el transporte HTTP normal -- por seguridad, se normaliza igual aqui.
function normalizeTursoUrl(url: string): string {
  return url.startsWith("libsql://") ? "https://" + url.slice("libsql://".length) : url;
}

function client() {
  const url = process.env.TURSO_DATABASE_URL;
  const authToken = process.env.TURSO_AUTH_TOKEN;
  if (!url) throw new Error("Falta TURSO_DATABASE_URL en las variables de entorno.");
  return createClient({ url: normalizeTursoUrl(url), authToken });
}

export type Pick = {
  id: string;
  date: string;
  time: string;
  underdog: string;
  favorito: string;
  book: string;
  odds_underdog: number;
  model_prob_underdog: number;
  edge_pp: number;
  ev_pct: number;
  signal: string;
  result: string;
  pnl_1u: number | null;
  strategy_name?: string;
};

export type Experiment = {
  id: number;
  name: string;
  params_hash: string;
  params_json: string;
  created_at: string;
  period_start: string;
  period_end: string;
  split_date: string;
  n_train: number | null;
  hit_rate_train: number | null;
  roi_train: number | null;
  pnl_train: number | null;
  n_test: number | null;
  hit_rate_test: number | null;
  roi_test: number | null;
  pnl_test: number | null;
  sharpe_test: number | null;
  notes: string | null;
};

export type DataCoverage = {
  minDate: string | null;
  maxDate: string | null;
  daysWithData: number;
  totalMatches: number;
  completedMatches: number;
  totalOddsRows: number;
  matchesWithOdds: number;
  lastUpdated: string | null;
};

export type DatasetRow = {
  match_uid: string;
  date: string;
  time: string;
  session_title: string;
  p1: string;
  p2: string;
  completed: number;
  s1: number | null;
  s2: number | null;
  has_odds: number;
};

export type Summary = {
  pendingCount: number;
  settledCount: number;
  wins: number;
  losses: number;
  hitRate: number | null;
  totalPnl: number;
  roi: number | null;
};

export async function getRecentPicks(days = 30, limit = 100): Promise<Pick[]> {
  const db = client();
  const cutoff = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
  const rs = await db.execute({
    sql: `SELECT id, date, time, underdog, favorito, book, odds_underdog, model_prob_underdog,
                 edge_pp, ev_pct, signal, result, pnl_1u
          FROM picks WHERE source = 'live' AND date >= ? ORDER BY date DESC, time DESC LIMIT ?`,
    args: [cutoff, limit],
  });
  return rs.rows.map((r) => r as unknown as Pick);
}

export async function getSummary(days = 30): Promise<Summary> {
  const db = client();
  const cutoff = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);

  const pending = await db.execute({
    sql: `SELECT COUNT(*) as n FROM picks WHERE source='live' AND result='PENDING' AND date >= ?`,
    args: [cutoff],
  });
  const settled = await db.execute({
    sql: `SELECT result, COUNT(*) as n, SUM(pnl_1u) as pnl FROM picks
          WHERE source='live' AND result != 'PENDING' AND date >= ? GROUP BY result`,
    args: [cutoff],
  });

  let wins = 0, losses = 0, totalPnl = 0;
  for (const row of settled.rows) {
    const r = row as unknown as { result: string; n: number; pnl: number | null };
    if (r.result === "WIN") wins = r.n;
    if (r.result === "LOSS") losses = r.n;
    totalPnl += r.pnl || 0;
  }
  const settledCount = wins + losses;

  return {
    pendingCount: Number((pending.rows[0] as unknown as { n: number })?.n || 0),
    settledCount,
    wins,
    losses,
    hitRate: settledCount ? wins / settledCount : null,
    totalPnl,
    roi: settledCount ? (totalPnl / settledCount) * 100 : null,
  };
}

export async function getRecentExperiments(limit = 50): Promise<Experiment[]> {
  const db = client();
  const rs = await db.execute({
    sql: `SELECT id, name, params_hash, params_json, created_at, period_start, period_end, split_date,
                 n_train, hit_rate_train, roi_train, pnl_train,
                 n_test, hit_rate_test, roi_test, pnl_test, sharpe_test, notes
          FROM experiments ORDER BY created_at DESC LIMIT ?`,
    args: [limit],
  });
  return rs.rows.map((r) => r as unknown as Experiment);
}

export async function getExperiment(id: number): Promise<Experiment | null> {
  const db = client();
  const rs = await db.execute({
    sql: `SELECT id, name, params_hash, params_json, created_at, period_start, period_end, split_date,
                 n_train, hit_rate_train, roi_train, pnl_train,
                 n_test, hit_rate_test, roi_test, pnl_test, sharpe_test, notes
          FROM experiments WHERE id = ?`,
    args: [id],
  });
  return (rs.rows[0] as unknown as Experiment) || null;
}

/** null = no hay estrategia promovida todavia -> el scanner en vivo usa BASELINE. */
export async function getActiveStrategyJson(): Promise<string | null> {
  const db = client();
  const rs = await db.execute({
    sql: `SELECT value FROM meta WHERE key = 'active_strategy_params'`,
    args: [],
  });
  const row = rs.rows[0] as unknown as { value: string } | undefined;
  return row?.value ?? null;
}

export async function setActiveStrategyJson(paramsJson: string): Promise<void> {
  const db = client();
  await db.execute({
    sql: `INSERT INTO meta(key, value) VALUES ('active_strategy_params', ?)
          ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
    args: [paramsJson],
  });
}

export async function getDataCoverage(): Promise<DataCoverage> {
  const db = client();
  const [matches, odds] = await Promise.all([
    db.execute({
      sql: `SELECT MIN(date) as minDate, MAX(date) as maxDate,
                   COUNT(DISTINCT date) as daysWithData,
                   COUNT(*) as totalMatches,
                   SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completedMatches
            FROM raw_matches`,
      args: [],
    }),
    db.execute({
      sql: `SELECT COUNT(*) as totalOddsRows, COUNT(DISTINCT match_uid) as matchesWithOdds FROM raw_odds`,
      args: [],
    }),
  ]);
  const m = matches.rows[0] as unknown as {
    minDate: string | null; maxDate: string | null; daysWithData: number;
    totalMatches: number; completedMatches: number;
  };
  const o = odds.rows[0] as unknown as { totalOddsRows: number; matchesWithOdds: number };
  return {
    minDate: m?.minDate ?? null,
    maxDate: m?.maxDate ?? null,
    daysWithData: Number(m?.daysWithData || 0),
    totalMatches: Number(m?.totalMatches || 0),
    completedMatches: Number(m?.completedMatches || 0),
    totalOddsRows: Number(o?.totalOddsRows || 0),
    matchesWithOdds: Number(o?.matchesWithOdds || 0),
    lastUpdated: m?.maxDate ?? null,
  };
}

export async function getDataset(opts: {
  page?: number; pageSize?: number; dateFrom?: string; dateTo?: string;
}): Promise<{ rows: DatasetRow[]; total: number }> {
  const db = client();
  const page = Math.max(1, opts.page || 1);
  const pageSize = Math.min(200, Math.max(1, opts.pageSize || 50));
  const offset = (page - 1) * pageSize;

  const where: string[] = [];
  const args: (string | number)[] = [];
  if (opts.dateFrom) { where.push("m.date >= ?"); args.push(opts.dateFrom); }
  if (opts.dateTo) { where.push("m.date <= ?"); args.push(opts.dateTo); }
  const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";

  const [rows, count] = await Promise.all([
    db.execute({
      sql: `SELECT m.match_uid, m.date, m.time, m.session_title, m.p1, m.p2, m.completed, m.s1, m.s2,
                   (SELECT COUNT(*) FROM raw_odds o WHERE o.match_uid = m.match_uid) as has_odds
            FROM raw_matches m ${whereSql}
            ORDER BY m.date DESC, m.rel_min DESC
            LIMIT ? OFFSET ?`,
      args: [...args, pageSize, offset],
    }),
    db.execute({
      sql: `SELECT COUNT(*) as n FROM raw_matches m ${whereSql}`,
      args,
    }),
  ]);

  return {
    rows: rows.rows.map((r) => r as unknown as DatasetRow),
    total: Number((count.rows[0] as unknown as { n: number })?.n || 0),
  };
}

/** Picks todavia sin liquidar (result='PENDING') y con senal accionable
 * (SI/SI_FALLBACK) -- los mismos criterios que usa el scanner en vivo para
 * decidir si manda email (ver StrategyDecision.actionable en
 * tt_elite/model/strategy.py). Pensada para una vista "para apostar ahora",
 * sin filtro de dias: mientras siga PENDING, sigue siendo relevante. */
export async function getActionablePicks(limit = 50): Promise<Pick[]> {
  const db = client();
  const rs = await db.execute({
    sql: `SELECT id, date, time, underdog, favorito, book, odds_underdog, model_prob_underdog,
                 edge_pp, ev_pct, signal, result, pnl_1u, strategy_name
          FROM picks
          WHERE source = 'live' AND result = 'PENDING' AND signal IN ('SI', 'SI_FALLBACK')
          ORDER BY date DESC, time DESC
          LIMIT ?`,
    args: [limit],
  });
  return rs.rows.map((r) => r as unknown as Pick);
}

export type BlowoutChainSignal = {
  id: string;
  match_uid: string;
  session_title: string;
  date: string;
  time: string;
  player_a: string;
  player_y: string;
  common_x: string;
  ax_date: string | null;
  ax_time: string | null;
  xy_date: string | null;
  xy_time: string | null;
  match_completed: number;
  a_score: number | null;
  y_score: number | null;
  theory_holds: number | null;
  a_odds: number | null;
  y_odds: number | null;
  odds_book: string | null;
  a_prior_win_streak: number | null;
  y_prior_loss_streak: number | null;
  detected_at: string;
};

// Sistema "definitivo" fijado por el usuario el 2026-08-25, tras comparar
// sobre el historico completo: A con cuota de underdog + Y (el favorito)
// con al menos esta racha de derrotas consecutivas antes de SU barrida
// (X vs Y) -- ver tt_elite/cli.py::DEFAULT_MIN_Y_LOSS_STREAK y el README
// para los numeros. Se probo con 3, pero ese resultado (n=7) venia en
// gran parte de datos de test colados en produccion (bug de connect(),
// corregido y limpiado); con datos limpios, 3 se queda en n=4 y ROI
// negativo -- el usuario confirmo volver a 2 (n=29 limpio, ROI+16.1%).
export const DEFAULT_MIN_Y_LOSS_STREAK = 2;

/** Sistema APARTE del scanner principal (sin señal/edge/ROI, puramente
 * observacional): cadenas A goleo 3-0 a X, X goleo 3-0 a Y, toca A vs Y --
 * dentro de la misma sesion. Ver tt_elite/live/blowout_chain.py. Por
 * defecto trae solo las de hoy (fecha del servidor).
 *
 * underdogOnly (default true): solo cadenas donde A -- nuestra "seleccion",
 * el que la teoria favorece -- tiene cuota de UNDERDOG (a_odds > y_odds, es
 * decir el mercado lo ve MENOS probable que Y). Pedido explicito del
 * usuario: cuando A ya es favorito de mercado, la cadena no aporta nada que
 * la cuota no dijera ya -- solo interesa cuando la teoria discrepa del
 * mercado. Excluye tambien las cadenas sin cuota todavia (a_odds IS NULL).
 *
 * minYLossStreak (default DEFAULT_MIN_Y_LOSS_STREAK): exige que Y (el
 * favorito) ya llegara con al menos esa racha de derrotas consecutivas
 * justo antes de SU barrida (X goleando 3-0 a Y). Junto con underdogOnly,
 * este es el sistema "definitivo" -- pasa 0 para quitar el filtro.
 */
export async function getBlowoutChainSignals(
  date?: string, underdogOnly = true, minYLossStreak = DEFAULT_MIN_Y_LOSS_STREAK,
): Promise<BlowoutChainSignal[]> {
  const db = client();
  const d = date || new Date().toISOString().slice(0, 10);
  const conds: string[] = [];
  const args: (string | number)[] = [d];
  if (underdogOnly) conds.push("a_odds IS NOT NULL AND a_odds > y_odds");
  if (minYLossStreak > 0) {
    conds.push("y_prior_loss_streak >= ?");
    args.push(minYLossStreak);
  }
  const filter = conds.length ? `AND ${conds.join(" AND ")}` : "";
  const rs = await db.execute({
    sql: `SELECT id, match_uid, session_title, date, time, player_a, player_y, common_x,
                 ax_date, ax_time, xy_date, xy_time,
                 match_completed, a_score, y_score, theory_holds,
                 a_odds, y_odds, odds_book, a_prior_win_streak, y_prior_loss_streak, detected_at
          FROM blowout_chain_signals
          WHERE date = ? ${filter}
          ORDER BY match_completed ASC, time ASC`,
    args,
  });
  return rs.rows.map((r) => r as unknown as BlowoutChainSignal);
}

export type BlowoutChainStats = {
  hits: number;
  total: number;
  /** apuestas con cuota conocida (subconjunto de `total`) -- pnl/roi solo se calculan sobre estas. */
  nWithOdds: number;
  /** P&L en unidades de apostar 1u a A en cada cadena con cuota (a_odds - 1 si gana, -1 si pierde). */
  pnl: number;
  /** pnl / nWithOdds * 100, o null si nWithOdds es 0. */
  roi: number | null;
};

// Columnas de racha validas para filtrar en getBlowoutChainStats() --
// whitelist explicita porque el nombre se interpola en el SQL.
export type StreakColumn = "a_prior_win_streak" | "y_prior_loss_streak";

/** Cuantas veces se cumple la teoria (A gana) sobre TODAS las fechas ya
 * jugadas -- para dar contexto de fiabilidad, no solo el dia actual -- mas
 * la rentabilidad de apostar 1u a A en cada cadena con cuota conocida.
 * Mismo filtro underdogOnly que getBlowoutChainSignals(). minStreak (default
 * 0 = sin filtro) exige al menos esa racha en `streakColumn`:
 * a_prior_win_streak = victorias consecutivas de A justo ANTES de SU
 * barrida (A goleando 3-0 a X); y_prior_loss_streak = derrotas consecutivas
 * de Y (el favorito) justo antes de SU barrida (X goleando 3-0 a Y). Ninguna
 * de las dos se mide antes de A vs Y. Pedido explicito del usuario el
 * 2026-08-25 (primero probo con A, perdia demasiado volumen; luego pidio
 * el opuesto: Y en racha de derrotas). */
export async function getBlowoutChainStats(
  underdogOnly = true, minStreak = 0, streakColumn: StreakColumn = "a_prior_win_streak",
): Promise<BlowoutChainStats> {
  const db = client();
  const underdogFilter = underdogOnly ? "AND a_odds IS NOT NULL AND a_odds > y_odds" : "";
  const rs = await db.execute({
    sql: `SELECT
            SUM(theory_holds) as hits,
            COUNT(*) as total,
            SUM(CASE WHEN a_odds IS NOT NULL THEN 1 ELSE 0 END) as nWithOdds,
            SUM(CASE WHEN a_odds IS NULL THEN 0 WHEN theory_holds = 1 THEN a_odds - 1 ELSE -1 END) as pnl
          FROM blowout_chain_signals
          WHERE match_completed = 1 AND ${streakColumn} >= ? ${underdogFilter}`,
    args: [minStreak],
  });
  const r = rs.rows[0] as unknown as { hits: number | null; total: number | null; nWithOdds: number | null; pnl: number | null };
  const nWithOdds = Number(r?.nWithOdds || 0);
  const pnl = Number(r?.pnl || 0);
  return {
    hits: Number(r?.hits || 0),
    total: Number(r?.total || 0),
    nWithOdds,
    pnl,
    roi: nWithOdds ? (pnl / nWithOdds) * 100 : null,
  };
}

export type BlowoutChainStreakRow = BlowoutChainStats & { minStreak: number };

/** Desglose de getBlowoutChainStats() por una de las dos rachas previas a
 * una barrida (0/1/2/3+) -- pedido explicito del usuario el 2026-08-25:
 * ver como evoluciona el ROI/hit rate al exigir mas racha. */
export async function getBlowoutChainStreakBreakdown(
  underdogOnly = true, streakColumn: StreakColumn = "a_prior_win_streak",
): Promise<BlowoutChainStreakRow[]> {
  const rows = await Promise.all(
    [0, 1, 2, 3].map((minStreak) => getBlowoutChainStats(underdogOnly, minStreak, streakColumn))
  );
  return rows.map((r, i) => ({ ...r, minStreak: i }));
}

export type EquityCurvePoint = {
  date: string;
  time: string;
  playerA: string;
  playerY: string;
  won: boolean;
  odds: number;
  pnl: number;
  cumPnl: number;
};

export type BlowoutChainStrategySummary = {
  points: EquityCurvePoint[];
  hits: number;
  total: number;
  roi: number | null;
  finalPnl: number;
  /** Total de señales que cumplen el filtro (jugadas o no) -- para picks/dia. */
  totalSignals: number;
  /** Dias DISTINTOS con datos en raw_matches -- no el rango de calendario,
   * que en este histórico tiene un hueco de 559 días (dic-2024 a jun-2026)
   * y usar el rango completo infravaloraría muchísimo los picks/día reales. */
  daysWithData: number;
  avgPicksPerDay: number;
};

/** Curva de bankroll (equity curve) + resumen de la estrategia "definitiva"
 * (A underdog + Y racha de derrotas >= minYLossStreak antes de SU barrida),
 * apostando 1u a A en cada señal jugada con cuota conocida, en orden
 * cronológico -- para ver cómo habría evolucionado el bank si se hubiera
 * usado en todo el histórico. Pedido explícito del usuario el 2026-08-25. */
export async function getBlowoutChainStrategySummary(
  minYLossStreak = DEFAULT_MIN_Y_LOSS_STREAK,
): Promise<BlowoutChainStrategySummary> {
  const db = client();
  const [playedRs, totalRs, daysRs] = await Promise.all([
    db.execute({
      sql: `SELECT date, time, player_a, player_y, a_odds, theory_holds
            FROM blowout_chain_signals
            WHERE match_completed = 1 AND a_odds IS NOT NULL AND a_odds > y_odds
                  AND y_prior_loss_streak >= ?
            ORDER BY date, time`,
      args: [minYLossStreak],
    }),
    db.execute({
      sql: `SELECT COUNT(*) as n FROM blowout_chain_signals
            WHERE a_odds IS NOT NULL AND a_odds > y_odds AND y_prior_loss_streak >= ?`,
      args: [minYLossStreak],
    }),
    db.execute({ sql: `SELECT COUNT(DISTINCT date) as n FROM raw_matches`, args: [] }),
  ]);

  let cum = 0;
  let hits = 0;
  const points: EquityCurvePoint[] = playedRs.rows.map((row) => {
    const r = row as unknown as { date: string; time: string; player_a: string; player_y: string; a_odds: number; theory_holds: number };
    const won = r.theory_holds === 1;
    if (won) hits++;
    const pnl = won ? r.a_odds - 1 : -1;
    cum += pnl;
    return { date: r.date, time: r.time, playerA: r.player_a, playerY: r.player_y, won, odds: r.a_odds, pnl, cumPnl: cum };
  });

  const total = points.length;
  const totalSignals = Number((totalRs.rows[0] as unknown as { n: number | null })?.n || 0);
  const daysWithData = Number((daysRs.rows[0] as unknown as { n: number | null })?.n || 0);

  return {
    points,
    hits,
    total,
    roi: total ? (cum / total) * 100 : null,
    finalPnl: cum,
    totalSignals,
    daysWithData,
    avgPicksPerDay: daysWithData ? totalSignals / daysWithData : 0,
  };
}

export async function getPicksFiltered(opts: {
  days?: number; signal?: string; limit?: number;
}): Promise<Pick[]> {
  const db = client();
  const days = opts.days ?? 30;
  const cutoff = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
  const where = ["source = 'live'", "date >= ?"];
  const args: (string | number)[] = [cutoff];
  if (opts.signal) { where.push("signal = ?"); args.push(opts.signal); }
  args.push(opts.limit ?? 200);

  const rs = await db.execute({
    sql: `SELECT id, date, time, underdog, favorito, book, odds_underdog, model_prob_underdog,
                 edge_pp, ev_pct, signal, result, pnl_1u, strategy_name
          FROM picks WHERE ${where.join(" AND ")} ORDER BY date DESC, time DESC LIMIT ?`,
    args,
  });
  return rs.rows.map((r) => r as unknown as Pick);
}
