import { getBlowoutChainSignals, getBlowoutChainStats } from "../../../lib/db";
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

  let signals, stats, loadError: string | null = null;
  try {
    [signals, stats] = await Promise.all([
      getBlowoutChainSignals(date, underdogOnly),
      getBlowoutChainStats(underdogOnly),
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
                <th>A vs X</th><th>X vs Y</th><th>Cuotas (A / Y)</th>
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
                </tr>
              ))}
              {pending.length === 0 && !loadError && (
                <tr><td colSpan={7} style={{ color: "var(--muted)" }}>
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
                <th>A vs X</th><th>X vs Y</th><th>Cuotas (A / Y)</th><th>Resultado A vs Y</th><th>Teoría</th>
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
                  <td>{s.player_a} {s.a_score ?? "—"}-{s.y_score ?? "—"} {s.player_y}</td>
                  <td style={{ color: s.theory_holds ? "var(--win)" : "var(--loss)", fontWeight: 600 }}>
                    {s.theory_holds ? "SE CUMPLE" : "NO se cumple"}
                  </td>
                </tr>
              ))}
              {played.length === 0 && !loadError && (
                <tr><td colSpan={9} style={{ color: "var(--muted)" }}>Sin cadenas jugadas para {date}.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
