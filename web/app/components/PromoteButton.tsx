"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function PromoteButton({ experimentId, isActive }: { experimentId: number; isActive: boolean }) {
  const [status, setStatus] = useState<"idle" | "loading" | "err">("idle");
  const [error, setError] = useState("");
  const router = useRouter();

  async function onClick() {
    setStatus("loading");
    setError("");
    try {
      const res = await fetch("/api/promote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ experimentId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || `Error ${res.status}`);
      router.refresh();
      setStatus("idle");
    } catch (err: any) {
      setStatus("err");
      setError(err?.message || String(err));
    }
  }

  if (isActive) {
    return <span className="badge SI">Activa</span>;
  }

  return (
    <div>
      <button className="promote-btn" onClick={onClick} disabled={status === "loading"}>
        {status === "loading" ? "Promoviendo..." : "Promover"}
      </button>
      {status === "err" && <p className="action-status err" style={{ marginTop: 4 }}>{error}</p>}
    </div>
  );
}
