import { getRecentExperiments, getActiveStrategyJson } from "../../../lib/db";
import { FIELD_INFO, TERMS, paramDiffs, parseParamsJson, paramsEqualIgnoringName } from "../../../lib/strategyMeta";
import { Info } from "../../components/Info";
import { SweepTrigger } from "../../components/Triggers";
import { PromoteButton } from "../../components/PromoteButton";

export const dynamic = "force-dynamic";

function pct(x: number | null, digits = 0): string {
  return x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`;
}
function roiStr(x: number | null): string {
  return x === null || x === undefined ? "—" : `${x >= 0 ? "+" : ""}${x.toFixed(1)}%`;
}

export default async function ExperimentosPage() {
  let experiments;
  let activeJson: string | null = null;
  let loadError: string | null = null;
  try {
    [experiments, activeJson] = await Promise.all([getRecentExperiments(100), getActiveStrategyJson()]);
  } catch (err: any) {
    loadError = err?.message || String(err);
  }

  const activeParams = parseParamsJson(activeJson);

  return (
    <>
      {loadError && (
        <section>
          <div className="stat-card"><p className="label">Error cargando datos</p><p>{loadError}</p></div>
        </section>
      )}

      <section>
        <h2>Lanzar experimento</h2>
        <div className="actions">
          <SweepTrigger />
        </div>
      </section>

      <section>
        <h2>
          Experimentos <Info text="Cada fila es una configuración de parámetros evaluada sobre el histórico ya descargado, con un split train/test para evitar sobreajuste." />
        </h2>
        <p className="hint" style={{ marginBottom: 16 }}>
          {TERMS.warmupTrainTest} <strong>Fíjate solo en las columnas de Test</strong> para decidir si una
          configuración vale — el rendimiento en Train no garantiza nada fuera de esa muestra.
        </p>

        <div className="exp-list">
          {(experiments || []).map((e) => {
            const params = parseParamsJson(e.params_json);
            const diffs = params ? paramDiffs(params) : [];
            const isActive = paramsEqualIgnoringName(params, activeParams) || (activeParams === null && diffs.length === 0);
            return (
              <div className="exp-card" key={e.id}>
                <div className="exp-card-head">
                  <div>
                    <strong>{e.name.split("[")[0]}</strong>
                    <span className="hint" style={{ marginLeft: 8 }}>
                      #{e.id} · {e.created_at?.slice(0, 16).replace("T", " ")}
                    </span>
                  </div>
                  <PromoteButton experimentId={e.id} isActive={isActive} />
                </div>

                <p className="hint">
                  Warmup desde <strong>{e.period_start}</strong>, test entre <strong>{e.split_date}</strong> y{" "}
                  <strong>{e.period_end}</strong>.
                  {e.notes && <> — {e.notes}</>}
                </p>

                {diffs.length === 0 ? (
                  <p className="hint">Configuración idéntica al BASELINE.</p>
                ) : (
                  <div className="chip-row">
                    {diffs.map((d) => (
                      <span key={d.key} className="chip" title={FIELD_INFO[d.key]?.tip}>
                        {d.label}: {d.value} <span className="chip-base">(base {d.baseValue})</span>
                      </span>
                    ))}
                  </div>
                )}

                <div className="kpi-row">
                  <div className="kpi">
                    <div className="kpi-label">Train — n / hit / ROI</div>
                    <div className="kpi-value">
                      {e.n_train ?? "—"} / {pct(e.hit_rate_train)} / {roiStr(e.roi_train)}
                    </div>
                  </div>
                  <div className="kpi kpi-highlight">
                    <div className="kpi-label">
                      Test — n / hit / ROI <Info text={`${TERMS.hitRate} ${TERMS.roi}`} />
                    </div>
                    <div className={`kpi-value ${(e.roi_test || 0) >= 0 ? "win" : "loss"}`}>
                      {e.n_test ?? "—"} / {pct(e.hit_rate_test)} / {roiStr(e.roi_test)}
                    </div>
                  </div>
                  <div className="kpi">
                    <div className="kpi-label">Sharpe test <Info text={TERMS.sharpe} /></div>
                    <div className="kpi-value">{e.sharpe_test === null || e.sharpe_test === undefined ? "—" : e.sharpe_test.toFixed(2)}</div>
                  </div>
                </div>
              </div>
            );
          })}

          {(!experiments || experiments.length === 0) && !loadError && (
            <p className="hint">Sin experimentos todavía — lanza uno arriba (necesitas datos en la sección Datos primero).</p>
          )}
        </div>
      </section>
    </>
  );
}
