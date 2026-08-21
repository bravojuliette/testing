import { getDataCoverage, getDataset } from "../../../lib/db";
import { Info } from "../../components/Info";
import { CollectTrigger } from "../../components/Triggers";
import { AutoRefresh } from "../../components/AutoRefresh";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 50;

export default async function DatosPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string; from?: string; to?: string }>;
}) {
  const params = await searchParams;
  const page = Math.max(1, parseInt(params.page || "1", 10) || 1);
  const dateFrom = params.from || undefined;
  const dateTo = params.to || undefined;

  let coverage, dataset, loadError: string | null = null;
  try {
    [coverage, dataset] = await Promise.all([
      getDataCoverage(),
      getDataset({ page, pageSize: PAGE_SIZE, dateFrom, dateTo }),
    ]);
  } catch (err: any) {
    loadError = err?.message || String(err);
  }

  const totalPages = dataset ? Math.max(1, Math.ceil(dataset.total / PAGE_SIZE)) : 1;
  const qs = (p: number) => {
    const u = new URLSearchParams();
    if (dateFrom) u.set("from", dateFrom);
    if (dateTo) u.set("to", dateTo);
    u.set("page", String(p));
    return `?${u.toString()}`;
  };

  return (
    <>
      <AutoRefresh seconds={30} />

      {loadError && (
        <section>
          <div className="stat-card"><p className="label">Error cargando datos</p><p>{loadError}</p></div>
        </section>
      )}

      <section>
        <h2>Cobertura actual <Info text="Lo que ya está descargado y cacheado -- esto es lo que usan los experimentos, no hace falta volver a bajarlo." /></h2>
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
            <div className="label">Partidos totales</div>
            <div className="value">{coverage?.totalMatches ?? "—"}</div>
          </div>
          <div className="stat-card">
            <div className="label">Terminados</div>
            <div className="value">{coverage?.completedMatches ?? "—"}</div>
          </div>
          <div className="stat-card">
            <div className="label">Filas de cuotas</div>
            <div className="value">{coverage?.totalOddsRows ?? "—"}</div>
          </div>
          <div className="stat-card">
            <div className="label">Partidos con cuota</div>
            <div className="value">{coverage?.matchesWithOdds ?? "—"}</div>
          </div>
        </div>
      </section>

      <section>
        <h2>Ampliar dataset</h2>
        <div className="actions">
          <CollectTrigger />
        </div>
      </section>

      <section>
        <h2>Explorar partidos <Info text="Se actualiza sola cada 30s -- si tienes un collect corriendo, verás crecer la tabla." /></h2>
        <form className="filter-form" action="/datos" method="GET">
          <label>
            Desde <input type="date" name="from" defaultValue={dateFrom} />
          </label>
          <label>
            Hasta <input type="date" name="to" defaultValue={dateTo} />
          </label>
          <button type="submit">Filtrar</button>
          {(dateFrom || dateTo) && <a href="/datos" className="clear-link">Limpiar</a>}
        </form>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th><th>Hora</th><th>Sesión</th><th>Jugador 1</th><th>Jugador 2</th>
                <th>Estado</th><th>Marcador</th><th>Cuota</th>
              </tr>
            </thead>
            <tbody>
              {(dataset?.rows || []).map((r) => (
                <tr key={r.match_uid}>
                  <td>{r.date}</td>
                  <td>{r.time}</td>
                  <td className="truncate" title={r.session_title}>{r.session_title}</td>
                  <td>{r.p1}</td>
                  <td>{r.p2}</td>
                  <td>{r.completed ? "Terminado" : "Pendiente"}</td>
                  <td>{r.completed ? `${r.s1}-${r.s2}` : "—"}</td>
                  <td>{r.has_odds ? "✓" : "—"}</td>
                </tr>
              ))}
              {(!dataset || dataset.rows.length === 0) && !loadError && (
                <tr><td colSpan={8} style={{ color: "var(--muted)" }}>Sin partidos todavía -- lanza un collect arriba.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {dataset && dataset.total > 0 && (
          <div className="pager">
            <span className="hint">{dataset.total} partidos · página {page} de {totalPages}</span>
            <div className="pager-links">
              {page > 1 && <a href={qs(page - 1)}>← Anterior</a>}
              {page < totalPages && <a href={qs(page + 1)}>Siguiente →</a>}
            </div>
          </div>
        )}
      </section>
    </>
  );
}
