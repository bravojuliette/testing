import { createClient } from "@libsql/client";

// Mismo normalizador que lib/db.ts -- 'libsql://' falla el handshake contra
// Turso en produccion, 'https://' con el mismo host usa transporte HTTP normal.
function normalizeTursoUrl(url: string): string {
  return url.startsWith("libsql://") ? "https://" + url.slice("libsql://".length) : url;
}

function client() {
  const url = process.env.TURSO_DATABASE_URL;
  const authToken = process.env.TURSO_AUTH_TOKEN;
  if (!url) throw new Error("Falta TURSO_DATABASE_URL en las variables de entorno.");
  return createClient({ url: normalizeTursoUrl(url), authToken });
}

export type BballCoverage = {
  minDate: string | null;
  maxDate: string | null;
  daysWithData: number;
  totalGames: number;
  totalOddsRows: number;
  gamesWithOdds: number;
  byLeague: { league: string; n: number }[];
};

export async function getBballCoverage(): Promise<BballCoverage> {
  const db = client();
  const [games, odds, byLeague] = await Promise.all([
    db.execute({
      sql: `SELECT MIN(date) as minDate, MAX(date) as maxDate, COUNT(DISTINCT date) as daysWithData,
                   COUNT(*) as totalGames
            FROM bball_games WHERE completed = 1`,
      args: [],
    }),
    db.execute({
      sql: `SELECT COUNT(*) as totalOddsRows, COUNT(DISTINCT event_id) as gamesWithOdds FROM bball_odds`,
      args: [],
    }),
    db.execute({
      sql: `SELECT league_name as league, COUNT(*) as n FROM bball_games WHERE completed = 1
            GROUP BY league_name ORDER BY n DESC`,
      args: [],
    }),
  ]);
  const g = games.rows[0] as unknown as {
    minDate: string | null; maxDate: string | null; daysWithData: number; totalGames: number;
  };
  const o = odds.rows[0] as unknown as { totalOddsRows: number; gamesWithOdds: number };
  return {
    minDate: g?.minDate ?? null,
    maxDate: g?.maxDate ?? null,
    daysWithData: Number(g?.daysWithData || 0),
    totalGames: Number(g?.totalGames || 0),
    totalOddsRows: Number(o?.totalOddsRows || 0),
    gamesWithOdds: Number(o?.gamesWithOdds || 0),
    byLeague: byLeague.rows.map((r) => {
      const row = r as unknown as { league: string; n: number };
      return { league: row.league, n: Number(row.n) };
    }),
  };
}

export type BballEquityPoint = {
  date: string;
  homeTeam: string;
  awayTeam: string;
  expTotal: number;
  line: number;
  underOdds: number;
  cushion: number;
  finalTotal: number | null;
  result: string;
  pnl: number;
  cumPnl: number;
};

export type BballFullHistorySummary = {
  params: { n_window: number; threshold: number; leagues: string[] };
  n: number;
  hits: number;
  hitRate: number | null;
  roi: number | null;
  pnlTotal: number;
  search: { n: number; hitRate: number | null; roi: number | null };
  holdout: { n: number; hitRate: number | null; roi: number | null; start: string; t: number | null };
  maxLosingStreak: number;
  maxDrawdownUnits: number;
  monteCarlo: { probRuin: number; p1: number; p5: number; p50: number; p95: number; stakeFraction: number } | null;
  evalStart: string | null;
  evalEnd: string;
  gamesLoaded: number;
  points: BballEquityPoint[];
  generatedAt: string;
};

/** Resultado de `python -m bball.cli backtest-summary`, cacheado en
 * bball_meta -- este dashboard no puede correr el motor de backtest en
 * Vercel, asi que lee el JSON ya calculado. null si todavia no se corrio
 * ese comando ni una vez. */
export async function getBballFullHistorySummary(): Promise<BballFullHistorySummary | null> {
  const db = client();
  const rs = await db.execute({
    sql: `SELECT value FROM bball_meta WHERE key = 'full_history_backtest_summary'`,
    args: [],
  });
  const row = rs.rows[0] as unknown as { value: string } | undefined;
  if (!row?.value) return null;
  return JSON.parse(row.value) as BballFullHistorySummary;
}

export type BballActiveParams = { n_window: number; threshold: number; leagues: string[] };

export async function getBballActiveParams(): Promise<BballActiveParams | null> {
  const db = client();
  const rs = await db.execute({
    sql: `SELECT value FROM bball_meta WHERE key = 'active_bball_params'`,
    args: [],
  });
  const row = rs.rows[0] as unknown as { value: string } | undefined;
  return row?.value ? (JSON.parse(row.value) as BballActiveParams) : null;
}

export type BballPick = {
  id: string;
  event_id: string;
  league_name: string;
  date: string;
  home_team: string;
  away_team: string;
  exp_total: number;
  book: string;
  line: number;
  under_odds: number;
  cushion: number;
  result: string;
  final_total: number | null;
  pnl_1u: number | null;
};

export async function getBballPicks(opts: { days?: number; limit?: number } = {}): Promise<BballPick[]> {
  const db = client();
  const days = opts.days ?? 30;
  const cutoff = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
  const rs = await db.execute({
    sql: `SELECT id, event_id, league_name, date, home_team, away_team, exp_total, book, line,
                 under_odds, cushion, result, final_total, pnl_1u
          FROM bball_picks WHERE date >= ? ORDER BY time_ts DESC LIMIT ?`,
    args: [cutoff, opts.limit ?? 200],
  });
  return rs.rows.map((r) => r as unknown as BballPick);
}

export type BballPicksSummary = {
  pendingCount: number;
  settledCount: number;
  wins: number;
  losses: number;
  hitRate: number | null;
  totalPnl: number;
  roi: number | null;
};

export async function getBballPicksSummary(days = 30): Promise<BballPicksSummary> {
  const db = client();
  const cutoff = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
  const [pending, settled] = await Promise.all([
    db.execute({
      sql: `SELECT COUNT(*) as n FROM bball_picks WHERE result = 'PENDING' AND date >= ?`,
      args: [cutoff],
    }),
    db.execute({
      sql: `SELECT result, COUNT(*) as n, SUM(pnl_1u) as pnl FROM bball_picks
            WHERE result != 'PENDING' AND date >= ? GROUP BY result`,
      args: [cutoff],
    }),
  ]);
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
