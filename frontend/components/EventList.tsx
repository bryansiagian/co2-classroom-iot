import type { DashboardEvent } from "@/lib/types";
import { LEVEL_META, fmtTime } from "@/lib/status";

export default function EventList({ events }: { events: DashboardEvent[] }) {
  return (
    <section className="rounded-3xl bg-paper p-6 shadow-[0_1px_0_var(--color-line)]">
      <h2 className="text-base font-semibold">Kejadian terbaru</h2>
      {events.length === 0 ? (
        <p className="mt-4 text-sm text-muted">Belum ada kejadian. CO₂ masih aman sejak dashboard dibuka.</p>
      ) : (
        <ul className="mt-4 space-y-4">
          {events.map((e, i) => (
            <li key={`${e.t}-${i}`} className="flex gap-3">
              <span className="mt-1.5 size-2.5 shrink-0 rounded-full" style={{ background: LEVEL_META[e.level].color }} />
              <div>
                <p className="text-sm font-medium">{e.text}</p>
                <p className="text-sm text-muted">Pukul {fmtTime(e.t)} WIB</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
