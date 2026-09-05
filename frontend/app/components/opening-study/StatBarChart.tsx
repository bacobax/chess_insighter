import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";
import type { OpeningStudyTreeNode } from "~/lib/types";

type Bar = {
  label: string;
  shortLabel: string;
  value: number | null;
  color: string;
};

function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function barsFor(stats: OpeningStudyTreeNode["stats"]): Bar[] {
  return [
    { label: "Style", shortLabel: "ST", value: stats.playerStyleMatch, color: "#3b82f6" },
    { label: "Engine", shortLabel: "EN", value: stats.engineSoundness, color: "#14b8a6" },
    { label: "Aggro", shortLabel: "AG", value: stats.aggressiveness, color: "#ef4444" },
    { label: "Practical", shortLabel: "PG", value: stats.practicalGamble, color: "#f59e0b" },
    { label: "Memory", shortLabel: "ME", value: stats.memoryComplexity, color: "#8b5cf6" },
    { label: "System", shortLabel: "SY", value: stats.systemness, color: "#10b981" },
  ];
}

function FullBars({ bars }: { bars: Bar[] }) {
  return (
    <div className="flex flex-col gap-1.5">
      {bars.map((bar) => {
        const pct = bar.value == null ? null : clamp01(bar.value) * 100;
        return (
          <div key={bar.label} className="flex items-center gap-1.5">
            <span
              className="w-9 shrink-0 text-[7px] font-semibold uppercase tracking-[.04em]"
              style={{ color: "rgba(255,255,255,.68)" }}
            >
              {bar.label}
            </span>
            <div
              className="relative h-1 flex-1 overflow-hidden rounded-full"
              style={{ backgroundColor: "rgba(255,255,255,.11)" }}
            >
              <div
                className="h-full rounded-full"
                style={{ width: `${pct ?? 0}%`, backgroundColor: bar.color }}
              />
            </div>
            <span
              className="w-5 shrink-0 text-right text-[7px] tabular-nums"
              style={{ color: "rgba(255,255,255,.55)" }}
            >
              {pct == null ? "—" : pct.toFixed(0)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Keeps the six metrics legible without permanently competing with the board.
 * Hover/focus gives a quick peek; clicking pins the detailed panel open.
 */
export function StatBarChart({ stats }: { stats: OpeningStudyTreeNode["stats"] }) {
  const bars = barsFor(stats);
  const panelId = useId();
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [pinned, setPinned] = useState(false);
  const revealed = hovered || focused || pinned;

  useEffect(() => {
    if (!pinned) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPinned(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [pinned]);

  return (
    <div
      className="mt-auto w-full"
      onClick={(event) => event.stopPropagation()}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {revealed ? (
        <div
          id={panelId}
          role="region"
          aria-label="Position profile statistics"
          className="mb-2 w-full rounded-lg border p-2.5 backdrop-blur-xl"
          style={{
            background: "linear-gradient(155deg, rgba(13,22,17,.98), rgba(8,13,10,.98))",
            borderColor: "rgba(33,231,131,.42)",
          }}
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <span
              className="text-[7px] font-bold uppercase tracking-[.12em]"
              style={{ color: "var(--accent)" }}
            >
              Position profile
            </span>
            {pinned ? (
              <button
                type="button"
                className="grid h-5 w-5 place-items-center rounded-full transition-colors hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--acid)]"
                style={{ color: "rgba(255,255,255,.7)" }}
                onClick={() => setPinned(false)}
                aria-label="Collapse position profile statistics"
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            ) : (
              <span className="text-[6px] uppercase tracking-wider" style={{ color: "rgba(255,255,255,.38)" }}>
                details
              </span>
            )}
          </div>
          <FullBars bars={bars} />
        </div>
      ) : null}

      <button
        type="button"
        className="block w-full rounded-lg border px-2 py-1.5 text-left shadow-lg backdrop-blur-md transition-[transform,background-color,border-color] duration-150 hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--acid)]"
        style={{
          backgroundColor: "rgba(9,15,11,.88)",
          borderColor: revealed ? "rgba(33,231,131,.62)" : "rgba(255,255,255,.17)",
        }}
        onClick={() => setPinned(true)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        aria-expanded={revealed}
        aria-controls={panelId}
        aria-pressed={pinned}
        aria-label="Show position profile statistics"
      >
        <span className="sr-only">Show all position profile statistics</span>
        <span aria-hidden="true" className="flex flex-col gap-[2px]">
          {bars.map((bar) => {
            const pct = bar.value == null ? null : clamp01(bar.value) * 100;
            return (
              <span key={bar.label} className="flex items-center gap-1">
                <span
                  className="w-3 text-[5px] font-bold leading-none tracking-tight"
                  style={{ color: "rgba(255,255,255,.56)" }}
                >
                  {bar.shortLabel}
                </span>
                <span
                  className="h-[2px] flex-1 overflow-hidden rounded-full"
                  style={{ backgroundColor: "rgba(255,255,255,.13)" }}
                >
                  <span
                    className="block h-full rounded-full"
                    style={{ width: `${pct ?? 0}%`, backgroundColor: bar.color }}
                  />
                </span>
              </span>
            );
          })}
        </span>
      </button>
    </div>
  );
}
