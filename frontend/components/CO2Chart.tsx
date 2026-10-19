"use client";

import { useMemo, useState } from "react";
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { Point } from "@/lib/types";
import { THRESHOLDS, fmt, fmtTime } from "@/lib/status";

const RANGES = [
  { label: "1 jam", minutes: 60 },
  { label: "3 jam", minutes: 180 },
  { label: "6 jam", minutes: 360 },
];

type Row = { t: number; actual?: number; forecast?: number };

export default function CO2Chart({ history, forecast }: { history: Point[]; forecast: Point[] }) {
  const [range, setRange] = useState(180);

  const data = useMemo<Row[]>(() => {
    const h = history.slice(-range);
    const last = h[h.length - 1];
    const rows: Row[] = h.map((p) => ({ t: p.t, actual: p.co2 }));
    rows[rows.length - 1] = { t: last.t, actual: last.co2, forecast: last.co2 };
    forecast.forEach((p) => rows.push({ t: p.t, forecast: p.co2 }));
    return rows;
  }, [history, forecast, range]);

  const nowT = history[history.length - 1].t;
  const yMax = Math.max(1600, ...data.map((d) => Math.max(d.actual ?? 0, d.forecast ?? 0))) + 100;

  return (
    <section className="rounded-3xl bg-paper p-6 shadow-[0_1px_0_var(--color-line)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-base font-semibold">Riwayat dan prediksi CO₂</h2>
        <div className="inline-flex rounded-full bg-fog p-1" role="group" aria-label="Rentang waktu">
          {RANGES.map((r) => (
            <button key={r.minutes} type="button" onClick={() => setRange(r.minutes)}
              aria-pressed={range === r.minutes}
              className={`rounded-full px-3 py-1 text-sm focus-visible:outline-2 focus-visible:outline-ink ${
                range === r.minutes ? "bg-ink text-paper" : "text-muted hover:text-ink"
              }`}>
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
            <defs>
              <linearGradient id="co2fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#12282b" stopOpacity={0.18} />
                <stop offset="100%" stopColor="#12282b" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 4" vertical={false} />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={fmtTime}
              tick={{ fontSize: 12, fill: "#587377" }} tickLine={false} axisLine={false} minTickGap={48} />
            <YAxis domain={[400, yMax]} tick={{ fontSize: 12, fill: "#587377" }} tickLine={false} axisLine={false}
              tickFormatter={(v) => fmt(Number(v))} width={52} />
            <ReferenceLine y={THRESHOLDS.watch} stroke="#c98a12" strokeDasharray="4 4" />
            <ReferenceLine y={THRESHOLDS.high} stroke="#d4492e" strokeWidth={1.5}
              label={{ value: "1.000 ppm", position: "insideTopLeft", fontSize: 11, fill: "#d4492e" }} />
            <ReferenceLine x={nowT} stroke="#587377" strokeDasharray="2 3"
              label={{ value: "Sekarang", position: "insideTopRight", fontSize: 11, fill: "#587377" }} />
            <Tooltip
              labelFormatter={(l) => fmtTime(Number(l))}
              formatter={(v, name) => [`${fmt(Number(v))} ppm`, name === "actual" ? "Terukur" : "Prediksi GRU"]}
              contentStyle={{ borderRadius: 12, border: "1px solid var(--color-line)", fontSize: 13 }}
            />
            <Area dataKey="actual" type="monotone" stroke="#12282b" strokeWidth={2} fill="url(#co2fill)"
              dot={false} isAnimationActive={false} />
            <Line dataKey="forecast" type="monotone" stroke="#d4492e" strokeWidth={2.5} strokeDasharray="6 4"
              dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted">
        <span className="inline-flex items-center gap-2"><span className="h-0.5 w-5 bg-ink" /> Terukur (sensor)</span>
        <span className="inline-flex items-center gap-2">
          <span className="w-5 border-t-2 border-dashed border-high" /> Prediksi 15 menit ke depan
        </span>
      </div>
    </section>
  );
}
