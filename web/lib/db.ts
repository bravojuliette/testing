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
};

export type Experiment = {
  id: number;
  name: string;
  created_at: string;
  period_start: string;
  period_end: string;
  split_date: string;
  n_train: number | null;
  hit_rate_train: number | null;
  roi_train: number | null;
  n_test: number | null;
  hit_rate_test: number | null;
  roi_test: number | null;
  sharpe_test: number | null;
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

export async function getRecentExperiments(limit = 15): Promise<Experiment[]> {
  const db = client();
  const rs = await db.execute({
    sql: `SELECT id, name, created_at, period_start, period_end, split_date,
                 n_train, hit_rate_train, roi_train, n_test, hit_rate_test, roi_test, sharpe_test
          FROM experiments ORDER BY created_at DESC LIMIT ?`,
    args: [limit],
  });
  return rs.rows.map((r) => r as unknown as Experiment);
}
