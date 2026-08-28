import { cn } from "~/lib/utils";

export function Progress({ value, className }: { value: number | null | undefined; className?: string }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value * 100));
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full", className)} style={{ backgroundColor: "var(--line-faint)" }}>
      <div className="h-full rounded-full transition-[width] duration-700" style={{ width: `${pct}%`, background: "linear-gradient(90deg, var(--accent), var(--acid))", boxShadow: "0 0 14px var(--glow)" }} />
    </div>
  );
}
