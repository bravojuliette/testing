"use client";

import { useState } from "react";
import type { BballEquityPoint } from "../../lib/bballDb";

/** Curva de bankroll de la teoría de totales: apostar 1u UNDER en cada pick
 * que cumplió el umbral, en orden cronológico. Mismo patrón visual que
 * EquityCurveChart (tenis de mesa), adaptado a los campos de basketball
 * (fecha sin hora, resultado WIN/LOSS/PUSH en vez de boolean). */
export function BballEquityChart({ points }: { points: BballEquityPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);

  if (points.length === 0) {
    return <p className="hint">Sin picks todavía con este criterio.</p>;
  }

  const width = 720;
  const height = 220;
  const padL = 44;
  const padR = 16;
  const padT = 16;
  const padB = 28;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;

  const toTs = (p: BballEquityPoint) => new Date(`${p.date}T00:00:00Z`).getTime();
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
  const originX = padL;
  const pathD = `M ${originX} ${yScale(0)} ` + coords.map((c) => `L ${c.x} ${c.y}`).join(" ");

  const yTicks = [yLo + (yHi - yLo) * 0.02, 0, yHi - (yHi - yLo) * 0.02].filter(
    (v, i, arr) => i === 0 || Math.abs(v - arr[i - 1]) > (yHi - yLo) * 0.15,
  );

  const fmtDate = (ts: number) => new Date(ts).toLocaleDateString("es-ES", { month: "short", year: "numeric" });
  const xTickCount = 4;
  const xTicks = Array.from({ length: xTickCount + 1 }, (_, i) => t0 + (tSpan * i) / xTickCount);

  const colorFor = (result: string) =>
    result === "WIN" ? "var(--win)" : result === "LOSS" ? "var(--loss)" : "var(--pending)";

  const active = hover !== null ? coords[hover] : null;

  return (
    <div style={{ position: "relative" }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{ width: "100%", height: "auto", display: "block" }}
        role="img"
        aria-label="Evolución del bank apostando a la teoría de totales, en orden cronológico"
      >
        {yTicks.map((v, i) => (
          <g key={i}>
            <line
              x1={padL} x2={width - padR} y1={yScale(v)} y2={yScale(v)}
              stroke="var(--border)" strokeWidth={v === 0 ? 1.5 : 1}
              strokeDasharray={v === 0 ? "4 3" : undefined}
            />
            <text x={padL - 8} y={yScale(v)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill="var(--muted)">
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

        <path d={pathD} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

        {coords.map((c, i) => (
          <circle
            key={i} cx={c.x} cy={c.y} r={hover === i ? 5 : 3.5}
            fill={colorFor(c.p.result)} stroke="var(--card)" strokeWidth={1}
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
          <div style={{ color: "var(--muted)" }}>{active.p.date}</div>
          <div>{active.p.homeTeam} vs {active.p.awayTeam} -- U{active.p.line} @{active.p.underOdds.toFixed(2)}</div>
          <div>Total real: {active.p.finalTotal ?? "?"} (esperado {active.p.expTotal})</div>
          <div style={{ color: colorFor(active.p.result), fontWeight: 600 }}>
            {active.p.result} ({active.p.pnl >= 0 ? "+" : ""}{active.p.pnl.toFixed(2)}u)
          </div>
          <div>Acumulado: {active.p.cumPnl >= 0 ? "+" : ""}{active.p.cumPnl.toFixed(2)}u</div>
        </div>
      )}

      <div style={{ display: "flex", gap: 16, marginTop: 6, fontSize: 11, color: "var(--muted)" }}>
        <span><span style={{ color: "var(--win)" }}>●</span> ganada</span>
        <span><span style={{ color: "var(--loss)" }}>●</span> perdida</span>
        <span><span style={{ color: "var(--pending)" }}>●</span> push</span>
      </div>
    </div>
  );
}
