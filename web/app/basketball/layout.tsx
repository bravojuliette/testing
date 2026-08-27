import Link from "next/link";
import { BballNav } from "../components/BballNav";

/** Layout compartido por las secciones del panel de basketball (no por /login ni /table-tennis). */
export default function BasketballLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="page">
      <div className="page-header">
        <h1>
          <Link href="/" className="home-link" title="Volver al inicio">←</Link> 🏀 Basketball
        </h1>
        <form className="logout-form" action="/api/logout" method="POST">
          <button type="submit">Salir</button>
        </form>
      </div>
      <BballNav />
      <div className="page-body">{children}</div>
    </main>
  );
}
