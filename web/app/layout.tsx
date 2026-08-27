import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Picks",
  description: "TT Elite (tenis de mesa) y teoría de totales de basketball",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
