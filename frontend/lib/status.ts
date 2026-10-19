import type { Level } from "./types";

// Ambang utama 1000 ppm; 800 dan 1500 untuk analisis sensitivitas (sesuai proposal TA)
export const THRESHOLDS = { watch: 800, high: 1000, critical: 1500 };

export function levelFor(ppm: number): Level {
  if (ppm >= THRESHOLDS.critical) return "critical";
  if (ppm >= THRESHOLDS.high) return "high";
  if (ppm >= THRESHOLDS.watch) return "watch";
  return "good";
}

export const LEVEL_META: Record<Level, { label: string; color: string }> = {
  good: { label: "Baik", color: "var(--color-good)" },
  watch: { label: "Perlu dipantau", color: "var(--color-watch)" },
  high: { label: "Tinggi", color: "var(--color-high)" },
  critical: { label: "Sangat tinggi", color: "var(--color-critical)" },
};

const nf = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export const fmt = (n: number) => nf.format(Math.round(n));
export const fmt1 = (n: number) => nf1.format(n);

export const fmtTime = (t: number) =>
  new Date(t).toLocaleTimeString("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Jakarta",
  }).replace(".", ":");
