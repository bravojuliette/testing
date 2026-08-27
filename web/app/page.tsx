import Link from "next/link";

export const metadata = { title: "Picks" };

export default function LandingPage() {
  return (
    <div className="landing-page">
      <h1>¿Qué sistema querés ver?</h1>
      <div className="landing-grid">
        <Link href="/table-tennis" className="landing-tile">
          <span className="emoji">🏓</span>
          <h2>Tenis de Mesa</h2>
          <p>Picks de TT Elite Series -- Elo, experimentos, datos y cadenas de barridas.</p>
        </Link>
        <Link href="/basketball" className="landing-tile">
          <span className="emoji">🏀</span>
          <h2>Basketball</h2>
          <p>Teoría de totales por debajo de la media de scoring -- ROI, hit rate y picks en vivo.</p>
        </Link>
      </div>
    </div>
  );
}
