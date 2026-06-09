import type { OpeningStudyTreeNode } from "~/lib/types";

type Bar = {
  label: string;
  value: number;
  color: string;
  // When true, a high value is a *cost* (harder to learn), not a virtue.
  isCost?: boolean;
};

function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

export function StatBarChart({ stats }: { stats: OpeningStudyTreeNode["stats"] }) {
  const bars: Bar[] = [
    { label: "Style", value: stats.playerStyleMatch, color: "#2563eb" },
    { label: "Aggro", value: stats.aggressiveness, color: "#dc2626" },
    { label: "Gamble", value: stats.gambleness, color: "#d97706" },
    { label: "Memory", value: stats.memoryComplexity, color: "#7c3aed", isCost: true },
    { label: "System", value: stats.systemness, color: "#059669" },
  ];
  return (
    <div className="flex flex-col gap-1">
      {bars.map((bar) => {
        const pct = clamp01(bar.value) * 100;
        return (
          <div key={bar.label} className="flex items-center gap-1.5">
            <span className="w-12 shrink-0 text-[9px] font-medium uppercase tracking-wide text-slate-500">
              {bar.label}
            </span>
            <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full"
                style={{ width: `${pct}%`, backgroundColor: bar.color }}
                title={`${bar.label}${bar.isCost ? " (complexity — higher is harder)" : ""}: ${pct.toFixed(0)}%`}
              />
            </div>
            <span className="w-6 shrink-0 text-right text-[9px] tabular-nums text-slate-400">{pct.toFixed(0)}</span>
          </div>
        );
      })}
    </div>
  );
}
