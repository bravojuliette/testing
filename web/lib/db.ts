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
  match_completed: number;
  match_s1: number | null;
  match_s2: number | null;
  detected_at: string;
};

/** Sistema APARTE del scanner principal (sin señal/edge/ROI, puramente
 * observacional): cadenas A goleo 3-0 a X, X goleo 3-0 a Y, toca A vs Y --
 * dentro de la misma sesion. Ver tt_elite/live/blowout_chain.py. Por
 * defecto trae solo las de hoy (fecha del servidor). */
export async function getBlowoutChainSignals(date?: string): Promise<BlowoutChainSignal[]> {
  const db = client();
  const d = date || new Date().toISOString().slice(0, 10);
  const rs = await db.execute({
    sql: `SELECT id, match_uid, session_title, date, time, player_a, player_y, common_x,
                 match_completed, match_s1, match_s2, detected_at
          FROM blowout_chain_signals
          WHERE date = ?
          ORDER BY match_completed ASC, time ASC`,
    args: [d],
  });
  return rs.rows.map((r) => r as unknown as BlowoutChainSignal);
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
