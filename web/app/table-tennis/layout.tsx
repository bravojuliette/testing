import Link from "next/link";
import { Nav } from "../components/Nav";

/** Layout compartido por las 5 secciones del panel de TT Elite (no por /login ni /basketball). */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="page">
      <div className="page-header">
        <h1>
          <Link href="/" className="home-link" title="Volver al inicio">←</Link> TT Elite
        </h1>
        <form className="logout-form" action="/api/logout" method="POST">
          <button type="submit">Salir</button>
        </form>
      </div>
      <Nav />
      <div className="page-body">{children}</div>
    </main>
  );
}
