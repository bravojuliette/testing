"use client";

import { useState } from "react";
import type { EquityCurvePoint } from "../../lib/db";

/** Curva de bankroll (equity curve) de la estrategia de cadenas: apostar 1u
 * a A en cada señal jugada, en orden cronológico. Un solo punto de partida
 * (0,0) se antepone para que la línea arranque en el origen. Line chart de
 * una sola serie -- sin leyenda de color por serie (solo hace falta el
 * estado ganada/perdida de cada marcador, resuelto con texto en el
 * tooltip, no solo color). */
export function EquityCurveChart({ points }: { points: EquityCurvePoint[] }) {
  const [hover, setHover] = useState<number | null>(null);

  if (points.length === 0) {
    return <p className="hint">Sin apuestas jugadas todavía con este criterio.</p>;
  }

  const width = 720;
  const height = 220;
  const padL = 44;
  const padR = 16;
  const padT = 16;
  const padB = 28;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;

  const toTs = (p: EquityCurvePoint) => new Date(`${p.date}T${p.time}:00Z`).getTime();
  const t0 = toTs(points[0]);
  const tN = toTs(points[points.length - 1]);
  const tSpan = Math.max(1, tN - t0);

  const cumVals = [0, ...points.map((p) => p.cumPnl)];
  const yMin = Math.min(0, ...cumVals);
  const yMax = Math.max(0, ...cumVals);
  const yPad = Math.max(0.5, (yMax - yMin) * 0.12);
  const yLo = yMin - yPad;
  const yHi = yMax + yPad;
  const yScale = (v: number) => padT + innerH - ((v - yLo) / (yHi - yLo)) * innerH;
  const xScale = (ts: number) => padL + ((ts - t0) / tSpan) * innerW;

  const coords = points.map((p) => ({ x: xScale(toTs(p)), y: yScale(p.cumPnl), p }));
  const originX = padL; // el origen (0,0) se dibuja en el instante del primer pick
  const pathD =
    `M ${originX} ${yScale(0)} ` + coords.map((c) => `L ${c.x} ${c.y}`).join(" ");

  const zeroY = yScale(0);
  const yTicks = [yLo + (yHi - yLo) * 0.02, 0, yHi - (yHi - yLo) * 0.02].filter(
    (v, i, arr) => i === 0 || Math.abs(v - arr[i - 1]) > (yHi - yLo) * 0.15,
  );

  const fmtDate = (ts: number) =>
    new Date(ts).toLocaleDateString("es-ES", { month: "short", year: "numeric" });
  const xTickCount = 4;
  const xTicks = Array.from({ length: xTickCount + 1 }, (_, i) => t0 + (tSpan * i) / xTickCount);

  const active = hover !== null ? coords[hover] : null;

  return (
    <div style={{ position: "relative" }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{ width: "100%", height: "auto", display: "block" }}
        role="img"
        aria-label="Evolución del bank apostando a la estrategia de cadenas, en orden cronológico"
      >
        {/* Gridlines (recesivas) */}
        {yTicks.map((v, i) => (
          <g key={i}>
            <line
              x1={padL} x2={width - padR} y1={yScale(v)} y2={yScale(v)}
              stroke="var(--border)" strokeWidth={v === 0 ? 1.5 : 1}
              strokeDasharray={v === 0 ? "4 3" : undefined}
            />
            <text x={padL - 8} y={yScale(v)} textAnchor="end" dominantBaseline="middle"
                  fontSize={10} fill="var(--muted)">
              {v >= 0 ? "+" : ""}{v.toFixed(1)}u
            </text>
          </g>
        ))}

        {xTicks.map((ts, i) => (
          <text
            key={i} x={xScale(ts)} y={height - 8}
            textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"}
            fontSize={10} fill="var(--muted)"
          >
            {fmtDate(ts)}
          </text>
        ))}

        {/* Linea de la curva */}
        <path d={pathD} fill="none" stroke="var(--accent)" strokeWidth={2}
              strokeLinejoin="round" strokeLinecap="round" />

        {/* Marcadores, coloreados por resultado (ganada/perdida) */}
        {coords.map((c, i) => (
          <circle
            key={i} cx={c.x} cy={c.y} r={hover === i ? 5 : 3.5}
            fill={c.p.won ? "var(--win)" : "var(--loss)"}
            stroke="var(--card)" strokeWidth={1}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover((h) => (h === i ? null : h))}
            style={{ cursor: "pointer" }}
          />
        ))}
      </svg>

      {active && (
        <div
          style={{
            position: "absolute",
            left: `${(active.x / width) * 100}%`,
            top: `${Math.max(0, (active.y / height) * 100 - 18)}%`,
            transform: "translate(-50%, -100%)",
            background: "var(--card)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            padding: "6px 10px",
            fontSize: 12,
            whiteSpace: "nowrap",
            pointerEvents: "none",
            boxShadow: "0 2px 8px rgba(0,0,0,0.25)",
            zIndex: 10,
          }}
        >
          <div style={{ color: "var(--muted)" }}>{active.p.date} {active.p.time}</div>
          <div>{active.p.playerA} vs {active.p.playerY} @{active.p.odds.toFixed(2)}</div>
          <div style={{ color: active.p.won ? "var(--win)" : "var(--loss)", fontWeight: 600 }}>
            {active.p.won ? "GANADA" : "PERDIDA"} ({active.p.pnl >= 0 ? "+" : ""}{active.p.pnl.toFixed(2)}u)
          </div>
          <div>Acumulado: {active.p.cumPnl >= 0 ? "+" : ""}{active.p.cumPnl.toFixed(2)}u</div>
        </div>
      )}

      <div style={{ display: "flex", gap: 16, marginTop: 6, fontSize: 11, color: "var(--muted)" }}>
        <span><span style={{ color: "var(--win)" }}>●</span> ganada</span>
        <span><span style={{ color: "var(--loss)" }}>●</span> perdida</span>
      </div>
    </div>
  );
}
