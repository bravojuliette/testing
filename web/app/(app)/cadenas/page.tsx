import { getBlowoutChainSignals } from "../../../lib/db";
import { AutoRefresh } from "../../components/AutoRefresh";

export const dynamic = "force-dynamic";

// Mismo huso que usa tt_elite (Europe/Warsaw, ver tt_elite/config.py::TZ) --
// para que "hoy" en esta pagina sea el mismo "hoy" que usa el scanner.
function warsawToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Warsaw" }).format(new Date());
}

export default async function CadenasPage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const params = await searchParams;
  const date = params.date || warsawToday();

  let signals, loadError: string | null = null;
  try {
    signals = await getBlowoutChainSignals(date);
  } catch (err: any) {
    loadError = err?.message || String(err);
  }

  const pending = (signals || []).filter((s) => !s.match_completed);
  const played = (signals || []).filter((s) => s.match_completed);

  return (
    <>
      <AutoRefresh seconds={20} />

      <section>
        <h2>🔗 Cadenas de barridas transitivas</h2>
        <p className="hint">
          Sistema aparte del scanner principal -- <strong>sin señal de apuesta ni porcentaje de acierto</strong>,
          puramente observacional. Dentro de la misma sesión (torneo del día): si A goleó 3-0 a un rival X,
          y ese mismo X goleó 3-0 a un rival Y, y toca disputarse A vs Y, se muestra aquí.
        </p>
        <form className="filter-form" action="/cadenas" method="GET">
          <label>
            Fecha
            <input type="date" name="date" defaultValue={date} />
          </label>
          <button type="submit">Ver</button>
        </form>
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
                <th>Hora</th><th>Sesión</th><th>A</th><th>Y</th><th>Rival común (X)</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((s) => (
                <tr key={s.id}>
                  <td>{s.time}</td>
                  <td>{s.session_title}</td>
                  <td>{s.player_a}</td>
                  <td>{s.player_y}</td>
                  <td>{s.common_x}</td>
                </tr>
              ))}
              {pending.length === 0 && !loadError && (
                <tr><td colSpan={5} style={{ color: "var(--muted)" }}>
                  Sin cadenas pendientes para {date}. Se actualiza cada 10 min junto al scanner en vivo.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>✅ Ya jugados</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Hora</th><th>Sesión</th><th>A</th><th>Y</th><th>Rival común (X)</th><th>Resultado A vs Y</th>
              </tr>
            </thead>
            <tbody>
              {played.map((s) => (
                <tr key={s.id}>
                  <td>{s.time}</td>
                  <td>{s.session_title}</td>
                  <td>{s.player_a}</td>
                  <td>{s.player_y}</td>
                  <td>{s.common_x}</td>
                  <td>{s.match_s1 ?? "—"}-{s.match_s2 ?? "—"}</td>
                </tr>
              ))}
              {played.length === 0 && !loadError && (
                <tr><td colSpan={6} style={{ color: "var(--muted)" }}>Sin cadenas jugadas para {date}.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
