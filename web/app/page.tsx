import { getRecentPicks, getSummary, getRecentExperiments } from "../lib/db";
import { actionsRunsUrl } from "../lib/github";
import { ScanTrigger, SweepTrigger, CollectTrigger } from "./trigger-panel";

export const dynamic = "force-dynamic"; // siempre datos frescos, nunca cacheados

function pct(x: number | null, digits = 0): string {
  return x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`;
}

function num(x: number | null, digits = 2): string {
  return x === null || x === undefined ? "—" : x.toFixed(digits);
}

export default async function DashboardPage() {
  let summary, picks, experiments, loadError: string | null = null;
  try {
    [summary, picks, experiments] = await Promise.all([
      getSummary(30),
      getRecentPicks(30, 100),
      getRecentExperiments(15),
    ]);
  } catch (err: any) {
    loadError = err?.message || String(err);
  }

  return (
    <main className="page">
      <div className="page-header">
        <h1>TT Elite</h1>
        <form className="logout-form" action="/api/logout" method="POST">
          <button type="submit">Salir</button>
        </form>
      </div>

      {loadError && (
        <section>
          <div className="stat-card">
            <p className="label">Error cargando datos</p>
            <p>{loadError}</p>
          </div>
        </section>
      )}

      {summary && (
        <div className="stat-grid">
          <div className="stat-card">
            <div className="label">Pendientes</div>
            <div className="value">{summary.pendingCount}</div>
          </div>
          <div className="stat-card">
            <div className="label">Liquidados (30d)</div>
            <div className="value">{summary.settledCount}</div>
          </div>
          <div className="stat-card">
            <div className="label">Hit rate</div>
            <div className="value">{pct(summary.hitRate)}</div>
          </div>
          <div className="stat-card">
            <div className="label">PnL (1u/pick)</div>
            <div className={`value ${summary.totalPnl >= 0 ? "win" : "loss"}`}>
              {summary.totalPnl >= 0 ? "+" : ""}
              {num(summary.totalPnl)}u
            </div>
          </div>
          <div className="stat-card">
            <div className="label">ROI</div>
            <div className={`value ${(summary.roi || 0) >= 0 ? "win" : "loss"}`}>
              {summary.roi === null ? "—" : `${summary.roi >= 0 ? "+" : ""}${summary.roi.toFixed(1)}%`}
            </div>
          </div>
        </div>
      )}

      <section>
        <h2>Acciones</h2>
        <div className="actions">
          <ScanTrigger />
          <SweepTrigger />
          <CollectTrigger />
        </div>
        <p style={{ fontSize: 12 }}>
          Progreso real de cada corrida en{" "}
          <a href={actionsRunsUrl()} target="_blank" rel="noreferrer">
            GitHub Actions
          </a>
          .
        </p>
      </section>

      <section>
        <h2>Picks recientes (30 días)</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th><th>Hora</th><th>Underdog</th><th>Favorito</th><th>Casa</th>
                <th>Cuota</th><th>Prob. modelo</th><th>Edge</th><th>EV</th><th>Señal</th><th>Resultado</th><th>PnL</th>
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
                </tr>
              ))}
              {(!picks || picks.length === 0) && !loadError && (
                <tr><td colSpan={12} style={{ color: "var(--muted)" }}>Sin picks todavía.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>Experimentos recientes (sweeps)</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Nombre</th><th>Creado</th><th>Periodo</th>
                <th>Train n/hit/ROI</th><th>Test n/hit/ROI</th><th>Sharpe test</th>
              </tr>
            </thead>
            <tbody>
              {(experiments || []).map((e) => (
                <tr key={e.id}>
                  <td>{e.name}</td>
                  <td>{e.created_at?.slice(0, 16).replace("T", " ")}</td>
                  <td>{e.period_start} → {e.period_end}</td>
                  <td>{e.n_train ?? "—"} / {pct(e.hit_rate_train)} / {e.roi_train === null ? "—" : `${e.roi_train.toFixed(1)}%`}</td>
                  <td>{e.n_test ?? "—"} / {pct(e.hit_rate_test)} / {e.roi_test === null ? "—" : `${e.roi_test.toFixed(1)}%`}</td>
                  <td>{num(e.sharpe_test)}</td>
                </tr>
              ))}
              {(!experiments || experiments.length === 0) && !loadError && (
                <tr><td colSpan={6} style={{ color: "var(--muted)" }}>Sin experimentos todavía.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
