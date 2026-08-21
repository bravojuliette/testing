import { Nav } from "../components/Nav";

/** Layout compartido por las 4 secciones del panel (no por /login). */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="page">
      <div className="page-header">
        <h1>TT Elite</h1>
        <form className="logout-form" action="/api/logout" method="POST">
          <button type="submit">Salir</button>
        </form>
      </div>
      <Nav />
      <div className="page-body">{children}</div>
    </main>
  );
}
