import { getBballPicksSummary, getBballPicks } from "../../../lib/bballDb";
import { AutoRefresh } from "../../components/AutoRefresh";

export const dynamic = "force-dynamic";

function pct(x: number | null | undefined, digits = 0): string {
  return x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`;
}
function num(x: number | null | undefined, digits = 2): string {
  return x === null || x === undefined ? "—" : x.toFixed(digits);
}

const RESULTS = ["", "PENDING", "WIN", "LOSS", "PUSH"];

export default async function BballPicksPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string; result?: string }>;
}) {
  const params = await searchParams;
  const days = Math.max(1, parseInt(params.days || "30", 10) || 30);
  const resultFilter = params.result || "";

  let summary, picks;
  let loadError: string | null = null;
  try {
    [summary, picks] = await Promise.all([
      getBballPicksSummary(days),
      getBballPicks({ days, limit: 300 }),
    ]);
  } catch (err: any) {
    loadError = err?.message || String(err);
  }

  const filteredPicks = resultFilter ? (picks || []).filter((p) => p.result === resultFilter) : picks;
  const pending = (picks || []).filter((p) => p.result === "PENDING");

  return (
    <>
      <AutoRefresh seconds={20} />

      {loadError && (
        <section>
          <div className="stat-card"><p className="label">Error cargando datos</p><p>{loadError}</p></div>
        </section>
      )}

      <section>
        <h2>🎯 Pendientes -- para apostar ahora</h2>
        <div className="table-wrap" style={{ borderColor: "var(--accent)" }}>
          <table>
            <thead>
              <tr>
                <th>Fecha</th><th>Liga</th><th>Partido</th><th>Total esperado</th>
                <th>Línea</th><th>Casa</th><th>Cuota UNDER</th><th>Colchón</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((p) => (
                <tr key={p.id}>
                  <td>{p.date}</td>
                  <td>{p.league_name}</td>
                  <td>{p.home_team} vs {p.away_team}</td>
                  <td>{num(p.exp_total, 1)}</td>
                  <td>{num(p.line, 1)}</td>
                  <td>{p.book}</td>
                  <td>{num(p.under_odds)}</td>
                  <td>{num(p.cushion, 1)}</td>
                </tr>
              ))}
              {pending.length === 0 && !loadError && (
                <tr><td colSpan={8} style={{ color: "var(--muted)" }}>
                  No hay picks pendientes ahora mismo. En cuanto el scanner en vivo encuentre uno, aparece aquí.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>KPIs -- últimos {days} días</h2>
        <div className="stat-grid">
          <div className="stat-card">
            <div className="label">Pendientes</div>
            <div className="value">{summary?.pendingCount ?? "—"}</div>
          </div>
          <div className="stat-card">
            <div className="label">Liquidados</div>
            <div className="value">{summary?.settledCount ?? "—"}</div>
          </div>
          <div className="stat-card">
            <div className="label">Aciertos</div>
            <div className="value win">{summary?.wins ?? "—"}</div>
          </div>
          <div className="stat-card">
            <div className="label">Fallos</div>
            <div className="value loss">{summary?.losses ?? "—"}</div>
          </div>
          <div className="stat-card">
            <div className="label">Push</div>
            <div className="value">{summary?.pushes ?? "—"}</div>
          </div>
          <div className="stat-card">
            <div className="label">Hit rate</div>
            <div className="value">{pct(summary?.hitRate ?? null)}</div>
          </div>
          <div className="stat-card">
            <div className="label">PnL</div>
            <div className={`value ${(summary?.totalPnl ?? 0) >= 0 ? "win" : "loss"}`}>
              {summary ? `${summary.totalPnl >= 0 ? "+" : ""}${num(summary.totalPnl)}u` : "—"}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">ROI</div>
            <div className={`value ${(summary?.roi || 0) >= 0 ? "win" : "loss"}`}>
              {summary?.roi === null || summary?.roi === undefined ? "—" : `${summary.roi >= 0 ? "+" : ""}${summary.roi.toFixed(1)}%`}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">Cuota media</div>
            <div className="value">{num(summary?.meanOdds ?? null)}</div>
          </div>
        </div>
        <p className="hint">
          Esto es lo que de verdad pasó apostando en vivo -- distinto del backtest histórico de{" "}
          <a href="/basketball">Resumen</a>, que reproduce la estrategia sobre datos ya pasados.
        </p>
      </section>

      <section>
        <h2>Historial de picks</h2>
        <form className="filter-form" action="/basketball/picks" method="GET">
          <label>
            Ventana
            <select name="days" defaultValue={String(days)}>
              <option value="7">7 días</option>
              <option value="14">14 días</option>
              <option value="30">30 días</option>
              <option value="90">90 días</option>
            </select>
          </label>
          <label>
            Resultado
            <select name="result" defaultValue={resultFilter}>
              {RESULTS.map((r) => (
                <option key={r} value={r}>{r || "Todos"}</option>
              ))}
            </select>
          </label>
          <button type="submit">Filtrar</button>
        </form>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th><th>Liga</th><th>Partido</th><th>Total esperado</th>
                <th>Línea</th><th>Casa</th><th>Cuota</th><th>Colchón</th>
                <th>Total real</th><th>Resultado</th><th>PnL</th>
              </tr>
            </thead>
            <tbody>
              {(filteredPicks || []).map((p) => (
                <tr key={p.id}>
                  <td>{p.date}</td>
                  <td>{p.league_name}</td>
                  <td>{p.home_team} vs {p.away_team}</td>
                  <td>{num(p.exp_total, 1)}</td>
                  <td>{num(p.line, 1)}</td>
                  <td>{p.book}</td>
                  <td>{num(p.under_odds)}</td>
                  <td>{num(p.cushion, 1)}</td>
                  <td>{p.final_total ?? "—"}</td>
                  <td className={`result-${p.result}`}>{p.result}</td>
                  <td>{p.pnl_1u === null || p.pnl_1u === undefined ? "—" : num(p.pnl_1u)}</td>
                </tr>
              ))}
              {(!filteredPicks || filteredPicks.length === 0) && !loadError && (
                <tr><td colSpan={11} style={{ color: "var(--muted)" }}>Sin picks todavía en esta ventana.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
