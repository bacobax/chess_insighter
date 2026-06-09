import { cn } from "~/lib/utils";

export function Progress({ value, className }: { value: number | null | undefined; className?: string }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value * 100));
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full", className)} style={{ backgroundColor: "var(--line-faint)" }}>
      <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: "var(--accent)" }} />
    </div>
  );
}
