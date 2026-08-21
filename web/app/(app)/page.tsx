import Link from "next/link";
import { getSummary, getDataCoverage, getActiveStrategyJson } from "../../lib/db";
import { BASELINE_PARAMS, FIELD_INFO, TERMS, paramDiffs, parseParamsJson } from "../../lib/strategyMeta";
import { Info, Label } from "../components/Info";
import { ScanTrigger } from "../components/Triggers";
import { AutoRefresh } from "../components/AutoRefresh";

export const dynamic = "force-dynamic";

function pct(x: number | null, digits = 0): string {
  return x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`;
}
function num(x: number | null, digits = 2): string {
  return x === null || x === undefined ? "—" : x.toFixed(digits);
}

export default async function ResumenPage() {
  let summary, coverage;
  let activeJson: string | null = null;
  let loadError: string | null = null;
  try {
    [summary, coverage, activeJson] = await Promise.all([
      getSummary(30),
      getDataCoverage(),
      getActiveStrategyJson(),
    ]);
  } catch (err: any) {
    loadError = err?.message || String(err);
  }

  const activeParams = parseParamsJson(activeJson);
  const diffs = activeParams ? paramDiffs(activeParams) : [];
  const oddsCoveragePct = coverage && coverage.totalMatches
    ? (coverage.matchesWithOdds / coverage.totalMatches) * 100
    : null;

  return (
    <>
      <AutoRefresh seconds={20} />

      {loadError && (
        <section>
          <div className="stat-card">
            <p className="label">Error cargando datos</p>
            <p>{loadError}</p>
          </div>
        </section>
      )}

      <section>
        <h2>Picks en vivo, últimos 30 días <Info text={TERMS.hitRate} /></h2>
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
        <p className="hint">Detalle completo, filtros e histórico en <Link href="/picks">Picks en vivo</Link>.</p>
      </section>

      <section>
        <h2>Estrategia activa <Info text={TERMS.active} /></h2>
        <div className="card">
          {!activeParams && (
            <p>
              No se ha promovido ningún experimento todavía — el scanner en vivo está usando la configuración
              <strong> BASELINE</strong> (la que ya tenías validada en v7.1/v5).
            </p>
          )}
          {activeParams && (
            <>
              <p><strong>{activeParams.name}</strong></p>
              {diffs.length === 0 && <p className="hint">Es idéntica al BASELINE — ningún parámetro cambiado.</p>}
              {diffs.length > 0 && (
                <div className="chip-row">
                  {diffs.map((d) => (
                    <span key={d.key} className="chip" title={FIELD_INFO[d.key]?.tip}>
                      {d.label}: {d.value} <span className="chip-base">(base {d.baseValue})</span>
                    </span>
                  ))}
                </div>
              )}
            </>
          )}
          <p className="hint">Se cambia desde <Link href="/experimentos">Experimentos</Link>, con el botón "Promover".</p>
        </div>
      </section>

      <section>
        <h2>Dataset</h2>
        <div className="stat-grid">
          <div className="stat-card">
            <div className="label">Días con datos</div>
            <div className="value">{coverage?.daysWithData ?? "—"}</div>
          </div>
          <div className="stat-card">
            <div className="label">Rango</div>
            <div className="value" style={{ fontSize: 15 }}>
              {coverage?.minDate && coverage?.maxDate ? `${coverage.minDate} → ${coverage.maxDate}` : "—"}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">Partidos</div>
            <div className="value">{coverage?.totalMatches ?? "—"}</div>
          </div>
          <div className="stat-card">
            <div className="label">Con cuota <Info text="Porcentaje de partidos terminados que tienen cuota de apertura capturada -- son los únicos usables para backtesting." /></div>
            <div className="value">{oddsCoveragePct === null ? "—" : `${oddsCoveragePct.toFixed(0)}%`}</div>
          </div>
        </div>
        <p className="hint">Explora fila a fila en <Link href="/datos">Datos</Link>, o amplía el rango desde ahí mismo.</p>
      </section>

      <section>
        <h2>Acción rápida</h2>
        <div className="actions">
          <ScanTrigger />
        </div>
      </section>
    </>
  );
}
