import { getBlowoutChainSignals, getBlowoutChainStats, getBlowoutChainStreakBreakdown, DEFAULT_MIN_Y_LOSS_STREAK } from "../../../lib/db";
import { AutoRefresh } from "../../components/AutoRefresh";

export const dynamic = "force-dynamic";

// Mismo huso que usa tt_elite (Europe/Warsaw, ver tt_elite/config.py::TZ) --
// para que "hoy" en esta pagina sea el mismo "hoy" que usa el scanner.
function warsawToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Warsaw" }).format(new Date());
}

function OddsCell({ a_odds, y_odds, odds_book }: { a_odds: number | null; y_odds: number | null; odds_book: string | null }) {
  if (a_odds == null || y_odds == null) {
    return <span style={{ color: "var(--muted)" }}>—</span>;
  }
  return (
    <span>
      @{a_odds.toFixed(2)} / @{y_odds.toFixed(2)}
      {odds_book && <span style={{ color: "var(--muted)" }}> ({odds_book})</span>}
    </span>
  );
}

export default async function CadenasPage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string; all?: string }>;
}) {
  const params = await searchParams;
  const date = params.date || warsawToday();
  const showAll = params.all === "1";
  const underdogOnly = !showAll;
  // Sistema "definitivo" fijado por el usuario el 2026-08-25: A underdog +
  // Y (el favorito) con al menos esta racha de derrotas antes de SU
  // barrida. --all quita ambos filtros (underdog Y racha).
  const minYLossStreak = showAll ? 0 : DEFAULT_MIN_Y_LOSS_STREAK;

  let signals, stats, streakBreakdown, loadError: string | null = null;
  try {
    [signals, stats, streakBreakdown] = await Promise.all([
      getBlowoutChainSignals(date, underdogOnly, minYLossStreak),
      getBlowoutChainStats(underdogOnly, minYLossStreak, "y_prior_loss_streak"),
      // El desglose de mas abajo usa solo el filtro de underdog (sin la
      // exigencia de racha de Y) para poder ver la progresion completa
      // 0/1/2/3 -- el desglose por racha de VICTORIAS de A antes de su
      // barrida perdia demasiado volumen sin mejorar el ROI; el usuario
      // pidio el opuesto: racha de DERROTAS de Y antes de SU barrida.
      getBlowoutChainStreakBreakdown(underdogOnly, "y_prior_loss_streak"),
    ]);
  } catch (err: any) {
    loadError = err?.message || String(err);
  }

  const pending = (signals || []).filter((s) => !s.match_completed);
  const played = (signals || []).filter((s) => s.match_completed);
  const statsPct = stats && stats.total ? Math.round((100 * stats.hits) / stats.total) : null;

  return (
    <>
      <AutoRefresh seconds={20} />

      <section>
        <h2>🔗 Cadenas de barridas transitivas</h2>
        <p className="hint">
          Sistema aparte del scanner principal -- <strong>sin señal de apuesta ni porcentaje de acierto</strong>,
          puramente observacional. Dentro de la misma sesión (torneo del día): si A goleó 3-0 a un rival X,
          y ese mismo X goleó 3-0 a un rival Y, y toca disputarse A vs Y, se muestra aquí (con las cuotas que
          tenía cada uno). Cuando el partido A vs Y termina, se indica si la teoría (A, transitivamente más
          fuerte, gana) se cumple o no.{" "}
          {underdogOnly
            ? "Filtrado a los casos donde A tiene cuota de UNDERDOG (el mercado lo ve menos probable que a Y) -- si A ya es favorito, la cadena no dice nada que la cuota no dijera ya."
            : "Mostrando TODAS las cadenas, incluidas las que A ya es favorito de mercado."}
        </p>
        {stats && stats.total > 0 && (
          <div className="stat-card">
            <p className="label">Histórico (todas las fechas{underdogOnly ? ", solo A underdog" : ""})</p>
            <p>
              La teoría se cumple en <strong>{stats.hits}/{stats.total}</strong> casos ya jugados ({statsPct}%).
              {statsPct !== null && statsPct <= 55 && statsPct >= 45 && " Con esta muestra, no se distingue de un 50/50 -- no es una señal fiable por sí sola."}
            </p>
          </div>
        )}
        {stats && stats.nWithOdds > 0 && (
          <div className="stat-grid">
            <div className="stat-card">
              <div className="label">Apuestas simuladas (1u a A, con cuota)</div>
              <div className="value">{stats.nWithOdds}</div>
            </div>
            <div className="stat-card">
              <div className="label">P&amp;L</div>
              <div className={`value ${stats.pnl >= 0 ? "win" : "loss"}`}>
                {stats.pnl >= 0 ? "+" : ""}{stats.pnl.toFixed(2)}u
              </div>
            </div>
            <div className="stat-card">
              <div className="label">ROI</div>
              <div className={`value ${(stats.roi || 0) >= 0 ? "win" : "loss"}`}>
                {stats.roi === null ? "—" : `${stats.roi >= 0 ? "+" : ""}${stats.roi.toFixed(1)}%`}
              </div>
            </div>
          </div>
        )}
        <p className="hint">
          Rentabilidad de apostar 1 unidad a A (la "selección" de la teoría) en cada cadena que tuvo cuota
          disponible, sin ningún criterio adicional de selección más allá del propio patrón{underdogOnly ? " y el filtro de underdog" : ""}.
          Muestra todavía pequeña -- no es una conclusión, es el dato tal cual está hoy.
        </p>

        {streakBreakdown && streakBreakdown.some((r) => r.total > 0) && (
          <>
            <p className="label" style={{ marginTop: 12 }}>
              Desglose por racha de DERROTAS de Y (el favorito) antes de su barrida (X vs Y){underdogOnly ? " (solo A underdog)" : ""}
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Racha derrotas ≥</th><th>Jugados</th><th>Cumple</th><th>Apuestas c/cuota</th><th>P&amp;L</th><th>ROI</th>
                  </tr>
                </thead>
                <tbody>
                  {streakBreakdown.map((r) => (
                    <tr key={r.minStreak}>
                      <td>{r.minStreak}</td>
                      <td>{r.total}</td>
                      <td>{r.total ? `${Math.round((100 * r.hits) / r.total)}%` : "—"}</td>
                      <td>{r.nWithOdds}</td>
                      <td style={r.nWithOdds ? { color: r.pnl >= 0 ? "var(--win)" : "var(--loss)" } : undefined}>
                        {r.nWithOdds ? `${r.pnl >= 0 ? "+" : ""}${r.pnl.toFixed(2)}u` : "—"}
                      </td>
                      <td style={r.roi !== null ? { color: r.roi >= 0 ? "var(--win)" : "var(--loss)", fontWeight: 600 } : undefined}>
                        {r.roi === null ? "—" : `${r.roi >= 0 ? "+" : ""}${r.roi.toFixed(1)}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="hint">
              "Racha derrotas ≥ N" = Y (el favorito) ya llegaba habiendo perdido sus últimos N partidos dentro de
              la misma sesión, justo antes de perder 0-3 contra X (la barrida en sí -- no antes de A vs Y).
              Fila 0 = sin exigir racha (igual que las tarjetas de arriba).
            </p>
          </>
        )}

        <form className="filter-form" action="/cadenas" method="GET">
          <label>
            Fecha
            <input type="date" name="date" defaultValue={date} />
          </label>
          {showAll && <input type="hidden" name="all" value="1" />}
          <button type="submit">Ver</button>
        </form>
        <p className="hint">
          {underdogOnly ? (
            <a href={`/cadenas?date=${date}&all=1`}>Ver todas (incluye A favorito)</a>
          ) : (
            <a href={`/cadenas?date=${date}`}>Ver solo A underdog</a>
          )}
        </p>
      </section>

      {loadError && (
        <section>
          <div className="stat-card"><p className="label">Error cargando datos</p><p>{loadError}</p></div>
        </section>
      )}

      <section>
        <h2>⏳ Pendientes -- por disputarse</h2>
        <div className="table-wrap" style={{ borderColor: "var(--accent)" }}>
          <table>
            <thead>
              <tr>
                <th>Hora</th><th>Sesión</th><th>A</th><th>Y</th>
                <th>A vs X</th><th>X vs Y</th><th>Cuotas (A / Y)</th><th>Racha A antes de A vs X</th><th>Racha derrotas Y antes de X vs Y</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((s) => (
                <tr key={s.id}>
                  <td>{s.time}</td>
                  <td>{s.session_title}</td>
                  <td>{s.player_a}</td>
                  <td>{s.player_y}</td>
                  <td>{s.player_a} 3-0 {s.common_x} ({s.ax_time})</td>
                  <td>{s.common_x} 3-0 {s.player_y} ({s.xy_time})</td>
                  <td><OddsCell a_odds={s.a_odds} y_odds={s.y_odds} odds_book={s.odds_book} /></td>
                  <td>{s.a_prior_win_streak ?? 0}</td>
                  <td>{s.y_prior_loss_streak ?? 0}</td>
                </tr>
              ))}
              {pending.length === 0 && !loadError && (
                <tr><td colSpan={9} style={{ color: "var(--muted)" }}>
                  Sin cadenas pendientes para {date}. Se actualiza cada 10 min junto al scanner en vivo.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>✅ Ya jugados -- ¿se cumplió la teoría?</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Hora</th><th>Sesión</th><th>A</th><th>Y</th>
                <th>A vs X</th><th>X vs Y</th><th>Cuotas (A / Y)</th><th>Racha A antes de A vs X</th><th>Racha derrotas Y antes de X vs Y</th><th>Resultado A vs Y</th><th>Teoría</th>
              </tr>
            </thead>
            <tbody>
              {played.map((s) => (
                <tr key={s.id}>
                  <td>{s.time}</td>
                  <td>{s.session_title}</td>
                  <td>{s.player_a}</td>
                  <td>{s.player_y}</td>
                  <td>{s.player_a} 3-0 {s.common_x} ({s.ax_time})</td>
                  <td>{s.common_x} 3-0 {s.player_y} ({s.xy_time})</td>
                  <td><OddsCell a_odds={s.a_odds} y_odds={s.y_odds} odds_book={s.odds_book} /></td>
                  <td>{s.a_prior_win_streak ?? 0}</td>
                  <td>{s.y_prior_loss_streak ?? 0}</td>
                  <td>{s.player_a} {s.a_score ?? "—"}-{s.y_score ?? "—"} {s.player_y}</td>
                  <td style={{ color: s.theory_holds ? "var(--win)" : "var(--loss)", fontWeight: 600 }}>
                    {s.theory_holds ? "SE CUMPLE" : "NO se cumple"}
                  </td>
                </tr>
              ))}
              {played.length === 0 && !loadError && (
                <tr><td colSpan={11} style={{ color: "var(--muted)" }}>Sin cadenas jugadas para {date}.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
