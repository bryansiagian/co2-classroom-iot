import { Wind } from "lucide-react";
import type { Recommendation } from "@/lib/types";

const VIEW = {
  none: { title: "Belum perlu ventilasi", led: "Hijau", color: "var(--color-good)", bg: "#dcefe7" },
  watch: { title: "Pantau dulu, siap membuka jendela", led: "Kuning", color: "var(--color-watch)", bg: "#f6e8c8" },
  flush: { title: "Buka jendela dan pintu", led: "Merah", color: "var(--color-high)", bg: "#f6d9d1" },
} as const;

export default function RecommendationCard({ rec }: { rec: Recommendation }) {
  const v = VIEW[rec.action];
  return (
    <section className="flex flex-col rounded-3xl p-6" style={{ background: v.bg }}>
      <div className="flex items-center gap-2 text-sm font-medium text-ink/70">
        <Wind className="size-4" aria-hidden /> Rekomendasi ventilasi
      </div>
      <h2 className="mt-4 text-3xl font-bold leading-tight text-ink">{v.title}</h2>
      {rec.action === "flush" && (
        <p className="mt-2 text-lg font-semibold" style={{ color: v.color }}>
          Selama {rec.minutes} menit
        </p>
      )}
      <p className="mt-3 max-w-prose text-[15px] leading-relaxed text-ink/80">{rec.reason}</p>
      <div className="mt-auto flex items-center gap-2 pt-6 text-sm text-ink/70">
        <span className="size-3 rounded-full" style={{ background: v.color }} />
        LED di ruangan menyala {v.led.toLowerCase()}
      </div>
    </section>
  );
}
