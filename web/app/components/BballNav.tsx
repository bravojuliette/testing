"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/basketball", label: "Resumen" },
  { href: "/basketball/picks", label: "Picks en vivo" },
];

export function BballNav() {
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
