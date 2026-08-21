"use client";

import { useState, FormEvent } from "react";
import { Label } from "./Info";

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
      <p>Revisa las sesiones de ahora mismo con la estrategia activa y manda email si hay algo accionable. Esto ya corre solo cada 10 min — úsalo solo para forzar una comprobación ya.</p>
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
      grid_json: String(fd.get("grid_json") || ""),
    });
  }

  return (
    <div className="action-card">
      <h3>Lanzar experimento (sweep)</h3>
      <p>
        Prueba muchas combinaciones de parámetros sobre el histórico ya descargado (rápido, no toca la red).
        Cada combinación se evalúa en dos periodos: train (para mirar) y test (a ciegas — la validación real).
      </p>
      <form onSubmit={onSubmit} className="field-form">
        <label>
          <Label text="Inicio de calentamiento" tip="Desde cuándo se alimenta el Elo antes de generar ningún pick. Cuanto antes, más contexto tienen los jugadores." />
          <input name="warmup_start" type="date" required />
        </label>
        <label>
          <Label text="Inicio de train" tip="A partir de aquí se generan picks 'de entrenamiento' — puedes mirarlos, pero no elijas parámetros solo por cómo salen aquí." />
          <input name="train_start" type="date" required />
        </label>
        <label>
          <Label text="Inicio de test" tip="A partir de aquí es validación a ciegas: este periodo nunca se usa para elegir parámetros. Es la métrica que importa." />
          <input name="test_start" type="date" required />
        </label>
        <label>
          <Label text="Fin de test" tip="Último día del periodo de test." />
          <input name="test_end" type="date" required />
        </label>
        <label>
          <Label text="Mínimo de picks en test" tip="Descarta configuraciones con muy pocos picks en test — evita que 2 aciertos de suerte parezcan un sistema ganador." />
          <input name="min_test_samples" placeholder="20" defaultValue="20" />
        </label>
        <label>
          <Label text="Grilla de parámetros (opcional)" tip={'JSON: {"campo": [valores]}. Si lo dejas vacío, se usa una grilla por defecto sobre min_model/min_edge/min_ev.'} />
          <input name="grid_json" placeholder='{"min_model":[0.52,0.58]}' />
        </label>
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
      <h3>Ampliar dataset (collect)</h3>
      <p>
        Descarga partidos + cuotas históricas de TT-Series y BetsAPI para un rango de fechas y los guarda aquí abajo.
        Es lento (limitado por la cuota de la API, ~15 min/día) pero se puede cortar y reanudar sin perder progreso —
        los días que ya tengas se saltan solos.
      </p>
      <form onSubmit={onSubmit} className="field-form">
        <label>
          <Label text="Desde" tip="Primer día del rango a descargar." />
          <input name="start" type="date" required />
        </label>
        <label>
          <Label text="Hasta" tip="Último día del rango a descargar." />
          <input name="end" type="date" required />
        </label>
        <button type="submit" disabled={status === "loading"}>
          {status === "loading" ? "Lanzando..." : "Lanzar collect"}
        </button>
      </form>
      {message && <p className={`action-status ${status === "ok" ? "ok" : status === "err" ? "err" : ""}`}>{message}</p>}
    </div>
  );
}
