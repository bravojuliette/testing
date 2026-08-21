import { getSummary, getPicksFiltered } from "../../../lib/db";
import { TERMS } from "../../../lib/strategyMeta";
import { Info } from "../../components/Info";
import { AutoRefresh } from "../../components/AutoRefresh";

export const dynamic = "force-dynamic";

function pct(x: number | null, digits = 0): string {
  return x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`;
}
function num(x: number | null, digits = 2): string {
  return x === null || x === undefined ? "—" : x.toFixed(digits);
}

const SIGNALS = ["", "SI", "SI_FALLBACK", "REVISAR"];

export default async function PicksPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string; signal?: string }>;
}) {
  const params = await searchParams;
  const days = Math.max(1, parseInt(params.days || "30", 10) || 30);
  const signal = params.signal || "";

  let summary, picks, loadError: string | null = null;
  try {
    [summary, picks] = await Promise.all([
      getSummary(days),
      getPicksFiltered({ days, signal: signal || undefined, limit: 300 }),
    ]);
  } catch (err: any) {
    loadError = err?.message || String(err);
  }

  return (
    <>
      <AutoRefresh seconds={20} />

      {loadError && (
        <section>
          <div className="stat-card"><p className="label">Error cargando datos</p><p>{loadError}</p></div>
        </section>
      )}

      <section>
        <h2>KPIs — últimos {days} días</h2>
        <div className="stat-grid">
          <div className="stat-card">
            <div className="label">Pendientes <Info text={TERMS.pending} /></div>
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
            <div className="label">Hit rate <Info text={TERMS.hitRate} /></div>
            <div className="value">{pct(summary?.hitRate ?? null)}</div>
          </div>
          <div className="stat-card">
            <div className="label">PnL <Info text={TERMS.pnl} /></div>
            <div className={`value ${(summary?.totalPnl ?? 0) >= 0 ? "win" : "loss"}`}>
              {summary ? `${summary.totalPnl >= 0 ? "+" : ""}${num(summary.totalPnl)}u` : "—"}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">ROI <Info text={TERMS.roi} /></div>
            <div className={`value ${(summary?.roi || 0) >= 0 ? "win" : "loss"}`}>
              {summary?.roi === null || summary?.roi === undefined ? "—" : `${summary.roi >= 0 ? "+" : ""}${summary.roi.toFixed(1)}%`}
            </div>
          </div>
        </div>
      </section>

      <section>
        <h2>Picks <Info text={TERMS.signal} /></h2>
        <form className="filter-form" action="/picks" method="GET">
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
            Señal
            <select name="signal" defaultValue={signal}>
              {SIGNALS.map((s) => (
                <option key={s} value={s}>{s || "Todas"}</option>
              ))}
            </select>
          </label>
          <button type="submit">Filtrar</button>
        </form>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th><th>Hora</th><th>Underdog</th><th>Favorito</th><th>Casa</th>
                <th>Cuota</th>
                <th>Prob. modelo</th>
                <th>Edge <Info text={TERMS.edge} /></th>
                <th>EV <Info text={TERMS.ev} /></th>
                <th>Señal</th><th>Resultado</th><th>PnL</th><th>Estrategia</th>
              </tr>
            </thead>
            <tbody>
              {(picks || []).map((p) => (
                <tr key={p.id}>
                  <td>{p.date}</td>
                  <td>{p.time}</td>
                  <td>{p.underdog}</td>
                  <td>{p.favorito}</td>
                  <td>{p.book}</td>
                  <td>{num(p.odds_underdog)}</td>
                  <td>{pct(p.model_prob_underdog, 1)}</td>
                  <td>{pct(p.edge_pp, 1)}</td>
                  <td>{pct(p.ev_pct, 1)}</td>
                  <td><span className={`badge ${p.signal}`}>{p.signal}</span></td>
                  <td className={`result-${p.result}`}>{p.result}</td>
                  <td>{p.pnl_1u === null ? "—" : num(p.pnl_1u)}</td>
                  <td className="hint">{p.strategy_name || "—"}</td>
                </tr>
              ))}
              {(!picks || picks.length === 0) && !loadError && (
                <tr><td colSpan={13} style={{ color: "var(--muted)" }}>Sin picks todavía en esta ventana.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
