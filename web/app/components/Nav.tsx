"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Resumen" },
  { href: "/datos", label: "Datos" },
  { href: "/experimentos", label: "Experimentos" },
  { href: "/picks", label: "Picks en vivo" },
  { href: "/cadenas", label: "Cadenas de barridas" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="nav">
      {LINKS.map((l) => (
        <Link key={l.href} href={l.href} className={`nav-link ${pathname === l.href ? "active" : ""}`}>
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
