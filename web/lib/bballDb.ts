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
  params: { n_window: number; threshold: number; leagues: string[]; book: string | null };
  n: number;
  hits: number;
  hitRate: number | null;
  roi: number | null;
  pnlTotal: number;
  meanOdds: number;
  search: { n: number; hitRate: number | null; roi: number | null; meanOdds: number };
  holdout: { n: number; hitRate: number | null; roi: number | null; start: string; t: number | null; meanOdds: number };
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
 * ese comando ni una vez (o, con `book`, no se corrio `--book <book>`).
 * Sin `book`: el resumen "mejor cuota entre todas las casas" (clave
 * 'full_history_backtest_summary'). Con `book`: el resumen restringido a
 * esa unica casa (clave 'full_history_backtest_summary__<book>') -- cada
 * uno se guarda aparte, uno no pisa al otro. */
export async function getBballFullHistorySummary(book?: string): Promise<BballFullHistorySummary | null> {
  const db = client();
  const key = book ? `full_history_backtest_summary__${book}` : "full_history_backtest_summary";
  const rs = await db.execute({
    sql: `SELECT value FROM bball_meta WHERE key = ?`,
    args: [key],
  });
  const row = rs.rows[0] as unknown as { value: string } | undefined;
  if (!row?.value) return null;
  return JSON.parse(row.value) as BballFullHistorySummary;
}

/** Casas de apuestas con al menos una cuota de totales cargada -- para
 * poblar el selector "ver el backtest restringido a esta casa" del
 * dashboard, sin hardcodear nombres. */
export async function getBballBooks(): Promise<string[]> {
  const db = client();
  const rs = await db.execute({
    sql: `SELECT DISTINCT book FROM bball_odds ORDER BY book`,
    args: [],
  });
  return rs.rows.map((r) => (r as unknown as { book: string }).book);
}

export type BballBackfillStatus = {
  totalGames: number;
  lastFetchedAt: string | null;
  secondsSinceLastFetch: number | null;
  byLeague: { league: string; n: number; minDate: string | null; maxDate: string | null }[];
};

/** Estado de la recoleccion de datos, para que el dashboard muestre el
 * progreso del backfill sin que haya que preguntar -- cuantos partidos hay
 * cargados por liga (completados o no, a diferencia de getBballCoverage que
 * solo cuenta completados) y hace cuanto se escribio el ultimo, como señal
 * de que el job de GitHub Actions sigue vivo. Con el auto-refresh de la
 * pagina esto se actualiza solo cada vez que se recarga. */
export async function getBballBackfillStatus(): Promise<BballBackfillStatus> {
  const db = client();
  const [totals, byLeague] = await Promise.all([
    db.execute({
      sql: `SELECT COUNT(*) as totalGames, MAX(fetched_at) as lastFetchedAt FROM bball_games`,
      args: [],
    }),
    db.execute({
      sql: `SELECT league_name as league, COUNT(*) as n, MIN(date) as minDate, MAX(date) as maxDate
            FROM bball_games GROUP BY league_name ORDER BY n DESC`,
      args: [],
    }),
  ]);
  const t = totals.rows[0] as unknown as { totalGames: number; lastFetchedAt: string | null };
  const lastFetchedAt = t?.lastFetchedAt ?? null;
  return {
    totalGames: Number(t?.totalGames || 0),
    lastFetchedAt,
    secondsSinceLastFetch: lastFetchedAt ? Math.max(0, (Date.now() - new Date(lastFetchedAt).getTime()) / 1000) : null,
    byLeague: byLeague.rows.map((r) => {
      const row = r as unknown as { league: string; n: number; minDate: string | null; maxDate: string | null };
      return { league: row.league, n: Number(row.n), minDate: row.minDate, maxDate: row.maxDate };
    }),
  };
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
  pushes: number;
  hitRate: number | null;
  totalPnl: number;
  roi: number | null;
  meanOdds: number | null;
};

export async function getBballPicksSummary(days = 30): Promise<BballPicksSummary> {
  const db = client();
  const cutoff = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
  const [pending, settled, oddsAvg] = await Promise.all([
    db.execute({
      sql: `SELECT COUNT(*) as n FROM bball_picks WHERE result = 'PENDING' AND date >= ?`,
      args: [cutoff],
    }),
    db.execute({
      sql: `SELECT result, COUNT(*) as n, SUM(pnl_1u) as pnl FROM bball_picks
            WHERE result != 'PENDING' AND date >= ? GROUP BY result`,
      args: [cutoff],
    }),
    // Cuota media de TODOS los picks de la ventana (pendientes + liquidados)
    // -- "a que cuota se esta apostando", no solo los ya resueltos.
    db.execute({
      sql: `SELECT AVG(under_odds) as avg FROM bball_picks WHERE date >= ?`,
      args: [cutoff],
    }),
  ]);
  let wins = 0, losses = 0, pushes = 0, totalPnl = 0;
  for (const row of settled.rows) {
    const r = row as unknown as { result: string; n: number; pnl: number | null };
    if (r.result === "WIN") wins = r.n;
    if (r.result === "LOSS") losses = r.n;
    if (r.result === "PUSH") pushes = r.n;
    totalPnl += r.pnl || 0;
  }
  // "Liquidados" incluye PUSH (no es ni acierto ni fallo, pero ya se resolvio)
  // -- para que cuadre con la tabla de historial de abajo, que lista los tres.
  // hitRate SI excluye PUSH del denominador (no fue ni acierto ni fallo);
  // roi usa el total liquidado, igual convencion que Summary.roi_pct en
  // bball/backtest/replay.py (pnl / n, con n incluyendo los push en 0).
  const decidedCount = wins + losses;
  const settledCount = decidedCount + pushes;
  const avgOdds = (oddsAvg.rows[0] as unknown as { avg: number | null })?.avg;
  return {
    pendingCount: Number((pending.rows[0] as unknown as { n: number })?.n || 0),
    settledCount,
    wins,
    losses,
    pushes,
    hitRate: decidedCount ? wins / decidedCount : null,
    totalPnl,
    roi: settledCount ? (totalPnl / settledCount) * 100 : null,
    meanOdds: avgOdds === null || avgOdds === undefined ? null : Number(avgOdds),
  };
}
