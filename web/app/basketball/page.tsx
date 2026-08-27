import Link from "next/link";
import { getBballActiveParams, getBballBackfillStatus, getBballBooks, getBballCoverage, getBballFullHistorySummary, getBballPicksSummary } from "../../lib/bballDb";
import { BballEquityChart } from "../components/BballEquityChart";
import { AutoRefresh } from "../components/AutoRefresh";

export const dynamic = "force-dynamic";

function pct(x: number | null | undefined, digits = 0): string {
  return x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`;
}
function signedPct(x: number | null | undefined, digits = 1): string {
  return x === null || x === undefined ? "—" : `${x >= 0 ? "+" : ""}${x.toFixed(digits)}%`;
}
function num(x: number | null | undefined, digits = 2): string {
  return x === null || x === undefined ? "—" : x.toFixed(digits);
}
function ago(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 90) return `hace ${Math.round(seconds)}s`;
  if (seconds < 3600) return `hace ${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `hace ${(seconds / 3600).toFixed(1)} h`;
  return `hace ${(seconds / 86400).toFixed(1)} días`;
}

export default async function BasketballDashboard({
  searchParams,
}: {
  searchParams: Promise<{ book?: string }>;
}) {
  const { book } = await searchParams;

  let coverage, picksSummary, fullHistory, activeParams, books, backfill;
  let loadError: string | null = null;
  try {
    [coverage, picksSummary, fullHistory, activeParams, books, backfill] = await Promise.all([
      getBballCoverage(),
      getBballPicksSummary(30),
      getBballFullHistorySummary(book),
      getBballActiveParams(),
      getBballBooks(),
      getBballBackfillStatus(),
    ]);
  } catch (err: any) {
    loadError = err?.message || String(err);
  }

  return (
    <>
      <AutoRefresh seconds={30} />

      {loadError && (
        <section>
          <div className="stat-card">
            <p className="label">Error cargando datos</p>
            <p>{loadError}</p>
          </div>
        </section>
      )}

      <section>
        <div className="card">
          <p style={{ margin: 0 }}>
            <strong>La teoría:</strong> si la línea de totales de un partido supera lo que ambos equipos
            anotan de media en sus últimos partidos por un colchón suficiente, apostar UNDER debería ser rentable.
          </p>
          <p className="hint" style={{ marginBottom: 0 }}>
            Sin escalera de líneas alternativas de un mismo libro con el plan actual de BetsAPI -- se usa la mejor
            línea disponible entre las casas cubiertas (~26) que cumplan el umbral en cada partido.
          </p>
        </div>
      </section>

      <section>
        <h2>Recolección en curso</h2>
        <div className="card">
          {backfill ? (
            <>
              <p style={{ margin: 0 }}>
                <span
                  style={{
                    display: "inline-block",
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    marginRight: 8,
                    background:
                      backfill.secondsSinceLastFetch !== null && backfill.secondsSinceLastFetch < 1200
                        ? "#22c55e"
                        : backfill.secondsSinceLastFetch !== null && backfill.secondsSinceLastFetch < 4200
                        ? "#eab308"
                        : "#9ca3af",
                  }}
                />
                <strong>{backfill.totalGames}</strong> partidos cargados en total -- última escritura{" "}
                {ago(backfill.secondsSinceLastFetch)}.
              </p>
              <div className="chip-row" style={{ marginTop: 10 }}>
                {backfill.byLeague.map((l) => (
                  <span key={l.league} className="chip">
                    {l.league}: {l.n} ({l.minDate ?? "?"} → {l.maxDate ?? "?"})
                  </span>
                ))}
              </div>
              <p className="hint" style={{ marginBottom: 0 }}>
                Esta página se auto-refresca cada 30s -- si el punto está verde, el job de backfill sigue escribiendo
                ahora mismo. Estos totales incluyen partidos aún no finalizados; el backtest de arriba solo usa
                los completados.
              </p>
            </>
          ) : (
            <p style={{ margin: 0 }}>Sin datos todavía.</p>
          )}
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
            <div className="value">{coverage?.totalGames ?? "—"}</div>
          </div>
          <div className="stat-card">
            <div className="label">Con cuota de totales</div>
            <div className="value">
              {coverage && coverage.totalGames
                ? `${((coverage.gamesWithOdds / coverage.totalGames) * 100).toFixed(0)}%`
                : "—"}
            </div>
          </div>
        </div>
        {coverage && coverage.byLeague.length > 0 && (
          <div className="chip-row">
            {coverage.byLeague.map((l) => (
              <span key={l.league} className="chip">{l.league}: {l.n}</span>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2>Backtest sobre todo el histórico</h2>
        <form className="filter-form" action="/basketball" method="GET">
          <label>
            Casa de apuestas
            <select name="book" defaultValue={book || ""}>
              <option value="">Mejor cuota entre todas</option>
              {(books || []).map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          </label>
          <button type="submit">Ver</button>
        </form>
        {!fullHistory && (
          <div className="card">
            <p style={{ margin: 0 }}>
              Todavía no se corrió <code>python -m bball.cli backtest-summary{book ? ` --book ${book}` : ""}</code>{" "}
              -- no hay nada que mostrar aquí hasta la primera vez que se genere para
              {book ? ` ${book}` : " esta vista"}.
            </p>
          </div>
        )}
        {fullHistory && (
          <>
            <p className="hint">
              Estrategia evaluada: N={fullHistory.params.n_window} (media de los últimos N partidos), umbral de
              colchón={fullHistory.params.threshold}, ligas: {fullHistory.params.leagues.join(", ")}, casa:{" "}
              {fullHistory.params.book ?? "mejor cuota entre todas"}.
              Calculado {new Date(fullHistory.generatedAt).toLocaleString("es-ES")}.
            </p>
            <div className="kpi-row">
              <div className="kpi kpi-highlight">
                <div className="kpi-label">Total (n={fullHistory.n})</div>
                <div className={`kpi-value ${(fullHistory.roi || 0) >= 0 ? "win" : "loss"}`}>
                  {signedPct(fullHistory.roi)} ROI
                </div>
                <div className="hint" style={{ margin: 0 }}>
                  hit rate {pct(fullHistory.hitRate)} -- cuota media {num(fullHistory.meanOdds)}
                </div>
              </div>
              <div className="kpi">
                <div className="kpi-label">Búsqueda (n={fullHistory.search.n})</div>
                <div className={`kpi-value ${(fullHistory.search.roi || 0) >= 0 ? "win" : "loss"}`}>
                  {signedPct(fullHistory.search.roi)}
                </div>
                <div className="hint" style={{ margin: 0 }}>
                  hit rate {pct(fullHistory.search.hitRate)} -- cuota media {num(fullHistory.search.meanOdds)}
                </div>
              </div>
              <div className="kpi">
                <div className="kpi-label">Reserva (n={fullHistory.holdout.n}, desde {fullHistory.holdout.start})</div>
                <div className={`kpi-value ${(fullHistory.holdout.roi || 0) >= 0 ? "win" : "loss"}`}>
                  {signedPct(fullHistory.holdout.roi)}
                </div>
                <div className="hint" style={{ margin: 0 }}>
                  hit rate {pct(fullHistory.holdout.hitRate)} -- cuota media {num(fullHistory.holdout.meanOdds)}
                  {fullHistory.holdout.t !== null && ` -- t=${fullHistory.holdout.t.toFixed(2)}${fullHistory.holdout.t >= 2 ? " ✓" : ""}`}
                </div>
              </div>
            </div>
            <p className="hint">
              La <strong>reserva</strong> es la única cifra que importa para decidir si esto funciona -- la de
              búsqueda pudo elegirse mirando esos mismos datos. t≥2 es la convención informal de este proyecto
              para &quot;probablemente no es ruido&quot; (no es un test riguroso).
            </p>

            <div style={{ marginTop: 20 }}>
              <BballEquityChart points={fullHistory.points} />
            </div>

            <div className="kpi-row" style={{ marginTop: 16 }}>
              <div className="kpi">
                <div className="kpi-label">Racha de pérdidas más larga</div>
                <div className="kpi-value">{fullHistory.maxLosingStreak}</div>
              </div>
              <div className="kpi">
                <div className="kpi-label">Drawdown máximo (1u fija)</div>
                <div className="kpi-value loss">-{fullHistory.maxDrawdownUnits.toFixed(1)}u</div>
              </div>
              {fullHistory.monteCarlo && (
                <>
                  <div className="kpi">
                    <div className="kpi-label">Prob. de ruina (Monte Carlo, {(fullHistory.monteCarlo.stakeFraction * 100).toFixed(0)}% banca/pick)</div>
                    <div className={`kpi-value ${fullHistory.monteCarlo.probRuin > 0.05 ? "loss" : "win"}`}>
                      {pct(fullHistory.monteCarlo.probRuin, 1)}
                    </div>
                  </div>
                  <div className="kpi">
                    <div className="kpi-label">Banca final -- percentil 5% / mediana</div>
                    <div className="kpi-value">
                      {(fullHistory.monteCarlo.p5 * 100).toFixed(0)}% / {(fullHistory.monteCarlo.p50 * 100).toFixed(0)}%
                    </div>
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </section>

      <section>
        <h2>Picks en vivo, últimos 30 días</h2>
        <div className="stat-grid">
          <div className="stat-card">
            <div className="label">Pendientes</div>
            <div className="value">{picksSummary?.pendingCount ?? "—"}</div>
          </div>
          <div className="stat-card">
            <div className="label">Liquidados</div>
            <div className="value">{picksSummary?.settledCount ?? "—"}</div>
          </div>
          <div className="stat-card">
            <div className="label">Hit rate</div>
            <div className="value">{pct(picksSummary?.hitRate ?? null)}</div>
          </div>
          <div className="stat-card">
            <div className="label">ROI</div>
            <div className={`value ${(picksSummary?.roi || 0) >= 0 ? "win" : "loss"}`}>
              {signedPct(picksSummary?.roi ?? null)}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">Cuota media</div>
            <div className="value">{num(picksSummary?.meanOdds ?? null)}</div>
          </div>
        </div>
        <p className="hint">Detalle completo en <Link href="/basketball/picks">Picks en vivo</Link>.</p>
      </section>

      <section>
        <h2>Estrategia activa del scanner en vivo</h2>
        <div className="card">
          {activeParams ? (
            <p style={{ margin: 0 }}>
              N={activeParams.n_window}, umbral={activeParams.threshold}, ligas: {activeParams.leagues.join(", ")}
            </p>
          ) : (
            <p style={{ margin: 0 }}>Sin promover todavía -- el scanner usaría un valor por defecto sin validar.</p>
          )}
          <p className="hint" style={{ marginBottom: 0 }}>
            Se cambia con <code>python -m bball.cli promote --window N --threshold T</code> -- solo hazlo después de
            confirmar el ROI de reserva arriba, nunca por el de búsqueda.
          </p>
        </div>
      </section>
    </>
  );
}
