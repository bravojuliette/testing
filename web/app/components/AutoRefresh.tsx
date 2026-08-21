"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Refresca la pagina (vuelve a pedir los datos del Server Component,
 * sin recargar todo el navegador) cada `seconds` segundos. Da la sensacion
 * de "en vivo" sin websockets: Turso no los ofrece, pero para un panel que
 * se mira de vez en cuando, un poll cada 20-30s es mas que suficiente. */
export function AutoRefresh({ seconds = 20 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const id = setInterval(() => router.refresh(), seconds * 1000);
    return () => clearInterval(id);
  }, [router, seconds]);
  return null;
}
