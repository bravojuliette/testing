"use client";

import { useState, FormEvent } from "react";

function useTrigger(type: string) {
  const [status, setStatus] = useState<"idle" | "loading" | "ok" | "err">("idle");
  const [message, setMessage] = useState("");

  async function trigger(inputs: Record<string, string>) {
    setStatus("loading");
    setMessage("");
    try {
      const res = await fetch("/api/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, inputs }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || `Error ${res.status}`);
      setStatus("ok");
      setMessage("Lanzado. Revisa la pestaña Actions de GitHub para ver el progreso.");
    } catch (err: any) {
      setStatus("err");
      setMessage(err?.message || String(err));
    }
  }

  return { status, message, trigger };
}

export function ScanTrigger() {
  const { status, message, trigger } = useTrigger("scan");

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    trigger({});
  }

  return (
    <div className="action-card">
      <h3>Scan en vivo</h3>
      <p>Revisa las sesiones de ahora mismo y manda email si hay algo accionable.</p>
      <form onSubmit={onSubmit}>
        <button type="submit" disabled={status === "loading"}>
          {status === "loading" ? "Lanzando..." : "Lanzar scan ahora"}
        </button>
      </form>
      {message && <p className={`action-status ${status === "ok" ? "ok" : status === "err" ? "err" : ""}`}>{message}</p>}
    </div>
  );
}

export function SweepTrigger() {
  const { status, message, trigger } = useTrigger("sweep");

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    trigger({
      warmup_start: String(fd.get("warmup_start") || ""),
      train_start: String(fd.get("train_start") || ""),
      test_start: String(fd.get("test_start") || ""),
      test_end: String(fd.get("test_end") || ""),
      min_test_samples: String(fd.get("min_test_samples") || "20"),
    });
  }

  return (
    <div className="action-card">
      <h3>Sweep de parámetros</h3>
      <p>Barre configuraciones sobre el histórico ya cacheado (train/test, sin sobreajustar).</p>
      <form onSubmit={onSubmit}>
        <input name="warmup_start" placeholder="warmup_start (YYYY-MM-DD)" required />
        <input name="train_start" placeholder="train_start (YYYY-MM-DD)" required />
        <input name="test_start" placeholder="test_start (YYYY-MM-DD)" required />
        <input name="test_end" placeholder="test_end (YYYY-MM-DD)" required />
        <input name="min_test_samples" placeholder="min. muestras test (20)" />
        <button type="submit" disabled={status === "loading"}>
          {status === "loading" ? "Lanzando..." : "Lanzar sweep"}
        </button>
      </form>
      {message && <p className={`action-status ${status === "ok" ? "ok" : status === "err" ? "err" : ""}`}>{message}</p>}
    </div>
  );
}

export function CollectTrigger() {
  const { status, message, trigger } = useTrigger("collect");

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    trigger({
      start: String(fd.get("start") || ""),
      end: String(fd.get("end") || ""),
    });
  }

  return (
    <div className="action-card">
      <h3>Collect histórico</h3>
      <p>Descarga y cachea TT-Series + BetsAPI para un rango de fechas. Puede tardar.</p>
      <form onSubmit={onSubmit}>
        <input name="start" placeholder="start (YYYY-MM-DD)" required />
        <input name="end" placeholder="end (YYYY-MM-DD)" required />
        <button type="submit" disabled={status === "loading"}>
          {status === "loading" ? "Lanzando..." : "Lanzar collect"}
        </button>
      </form>
      {message && <p className={`action-status ${status === "ok" ? "ok" : status === "err" ? "err" : ""}`}>{message}</p>}
    </div>
  );
}
