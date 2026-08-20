import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TT Elite",
  description: "Picks de TT Elite Series",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
