import type { LucideIcon } from "lucide-react";

export default function StatTile({
  icon: Icon, label, value, hint,
}: { icon: LucideIcon; label: string; value: string; hint: string }) {
  return (
    <div className="rounded-2xl bg-paper p-4 shadow-[0_1px_0_var(--color-line)]">
      <div className="flex items-center gap-2 text-sm text-muted">
        <Icon className="size-4" aria-hidden /> {label}
      </div>
      <div className="mt-2 text-2xl font-bold">{value}</div>
      <div className="mt-1 text-sm text-muted">{hint}</div>
    </div>
  );
}
