import { LEVEL_META, fmt, levelFor } from "@/lib/status";

const CX = 160, CY = 170, R = 130, MIN = 400, MAX = 2000;

const clamp = (v: number) => Math.min(MAX, Math.max(MIN, v));
const ang = (v: number) => Math.PI + ((clamp(v) - MIN) / (MAX - MIN)) * Math.PI;
const pt = (v: number, r = R) => ({ x: CX + r * Math.cos(ang(v)), y: CY + r * Math.sin(ang(v)) });
const arc = (a: number, b: number) => {
  const p = pt(a), q = pt(b);
  return `M${p.x.toFixed(2)} ${p.y.toFixed(2)} A${R} ${R} 0 0 1 ${q.x.toFixed(2)} ${q.y.toFixed(2)}`;
};

const BANDS = [
  { from: 400, to: 800, color: "var(--color-good)" },
  { from: 800, to: 1000, color: "var(--color-watch)" },
  { from: 1000, to: 1500, color: "var(--color-high)" },
  { from: 1500, to: 2000, color: "var(--color-critical)" },
];

export default function Gauge({ current, predicted }: { current: number; predicted: number }) {
  const level = levelFor(current);
  const meta = LEVEL_META[level];
  const predLevel = LEVEL_META[levelFor(predicted)];
  const cur = pt(current);
  const prd = pt(predicted);

  return (
    <section className="rounded-3xl bg-paper p-6 shadow-[0_1px_0_var(--color-line)]">
      <h2 className="text-base font-semibold">Konsentrasi CO₂ sekarang</h2>

      <svg viewBox="0 0 320 200" className="mx-auto mt-2 w-full max-w-md" role="img"
        aria-label={`CO₂ saat ini ${fmt(current)} ppm, prediksi 15 menit lagi ${fmt(predicted)} ppm`}>
        {BANDS.map((b, i) => (
          <path key={b.from} d={arc(b.from + (i ? 6 : 0), b.to - (i < 3 ? 6 : 0))}
            fill="none" stroke={b.color} strokeWidth={14} strokeLinecap="round" opacity={0.9} />
        ))}
        {[800, 1000, 1500].map((v) => {
          const p = pt(v, R + 20);
          return (
            <text key={v} x={p.x} y={p.y} fontSize="11" fill="var(--color-muted)"
              textAnchor="middle" dominantBaseline="middle">{fmt(v)}</text>
          );
        })}
        <circle cx={prd.x} cy={prd.y} r={7} fill="var(--color-paper)" stroke={predLevel.color} strokeWidth={3} />
        <circle cx={cur.x} cy={cur.y} r={8} fill="var(--color-ink)" stroke="var(--color-paper)" strokeWidth={3} />
        <text x={CX} y={148} textAnchor="middle" fontSize="58" fontWeight="700" fill="var(--color-ink)">
          {fmt(current)}
        </text>
        <text x={CX} y={172} textAnchor="middle" fontSize="14" fill="var(--color-muted)">ppm</text>
      </svg>

      <div className="mt-1 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm">
        <span className="inline-flex items-center gap-2 font-medium" style={{ color: meta.color }}>
          <span className="size-2.5 rounded-full" style={{ background: meta.color }} />
          {meta.label}
        </span>
        <span className="inline-flex items-center gap-2 text-muted">
          <span className="size-3 rounded-full border-[3px]" style={{ borderColor: predLevel.color }} />
          Prediksi 15 menit lagi: <strong className="text-ink">{fmt(predicted)} ppm</strong>
        </span>
      </div>
    </section>
  );
}
