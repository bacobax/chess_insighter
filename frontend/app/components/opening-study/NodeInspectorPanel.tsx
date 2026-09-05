import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "~/lib/utils";
import type { MetricComponent, NodeBreakdown, OpeningStudyTreeNode, StyleMatchComponent } from "~/lib/types";
import { ZoomableBoard } from "~/components/board/BoardZoomModal";
import { MiniChessBoard } from "./MiniChessBoard";

function clamp01(v: number) {
  return Math.max(0, Math.min(1, v));
}

// The 9 style features that compose the player / opening vectors.
const STYLE_FEATURES: Array<{ key: string; label: string; color: string }> = [
  { key: "tactical_density", label: "Tactical", color: "#dc2626" },
  { key: "quiet_position_density", label: "Quiet", color: "#2563eb" },
  { key: "king_safety_risk", label: "King risk", color: "#f59e0b" },
  { key: "early_castling_tendency", label: "Early castle", color: "#059669" },
  { key: "opposite_side_castling_tendency", label: "Opp. castle", color: "#7c3aed" },
  { key: "middlegame_complexity", label: "Complexity", color: "#0891b2" },
  { key: "pawn_structure_sharpness", label: "Pawn sharp.", color: "#be185d" },
  { key: "material_imbalance", label: "Material imb.", color: "#ea580c" },
  { key: "endgame_likelihood_proxy", label: "Endgame", color: "#16a34a" },
];

// Aggregate metric breakdown sections.
type BreakdownStatKey = "engineSoundness" | "aggressiveness" | "memoryComplexity" | "systemness";

const METRIC_SECTIONS: Array<{
  key: keyof NodeBreakdown;
  statKey: BreakdownStatKey;
  label: string;
  color: string;
  description: string;
  isCost?: boolean;
}> = [
  {
    key: "engineSoundness",
    statKey: "engineSoundness",
    label: "Engine soundness",
    color: "#0f766e",
    description: "Stockfish centipawn utility from the target color's perspective. Equal is 50%; lossy positions drop toward 0%.",
  },
  {
    key: "aggressiveness",
    statKey: "aggressiveness",
    label: "Aggressiveness",
    color: "#dc2626",
    description: "35 × tactical density + 25 × complexity + 20 × opp. castling + 20 × material imbalance",
  },
  {
    key: "memoryComplexity",
    statKey: "memoryComplexity",
    label: "Memory complexity",
    color: "#7c3aed",
    description: "55 × line count + 25 × structure diversity + 20 × position entropy — higher means harder to memorize",
    isCost: true,
  },
  {
    key: "systemness",
    statKey: "systemness",
    label: "Systemness",
    color: "#059669",
    description: "65 × (1 − entropy) + 35 × (1 − diversity) — higher means more repeatable, principled positions",
  },
];

function DualBar({
  playerValue,
  openingValue,
  playerColor,
  openingColor,
}: {
  playerValue: number;
  openingValue: number;
  playerColor: string;
  openingColor: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="relative h-1 w-full overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full" style={{ width: `${clamp01(playerValue) * 100}%`, backgroundColor: playerColor }} />
      </div>
      <div className="relative h-1 w-full overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full" style={{ width: `${clamp01(openingValue) * 100}%`, backgroundColor: openingColor }} />
      </div>
    </div>
  );
}

function StyleProfileSection({
  openingFeatures,
  playerVector,
}: {
  openingFeatures: Record<string, number>;
  playerVector: Record<string, number> | null;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2 text-[10px] text-slate-400">
        <span className="font-medium uppercase tracking-wide">Style profile</span>
        <div className="flex items-center gap-1">
          <span className="inline-block h-1.5 w-3 rounded-full bg-slate-400" />
          <span>you</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="inline-block h-1.5 w-3 rounded-full bg-slate-600" />
          <span>opening</span>
        </div>
      </div>
      {STYLE_FEATURES.map(({ key, label, color }) => {
        const openingVal = openingFeatures[key] ?? 0;
        const playerVal = playerVector?.[key] ?? null;
        const openingPct = (clamp01(openingVal) * 100).toFixed(0);
        const playerPct = playerVal !== null ? (clamp01(playerVal) * 100).toFixed(0) : null;
        return (
          <div key={key} className="mb-1.5">
            <div className="mb-0.5 flex items-center justify-between text-[9px] text-slate-400">
              <span className="font-medium">{label}</span>
              <span className="tabular-nums">
                {playerPct !== null ? `${playerPct}% · ` : ""}
                <span style={{ color }}>{openingPct}%</span>
              </span>
            </div>
            {playerVal !== null ? (
              <DualBar
                playerValue={playerVal}
                openingValue={openingVal}
                playerColor="#94a3b8"
                openingColor={color}
              />
            ) : (
              <div className="relative h-1 w-full overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full" style={{ width: `${openingPct}%`, backgroundColor: color }} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function formatRawValue(comp: MetricComponent): string {
  if (comp.rawValue == null) return `${(clamp01(comp.value) * 100).toFixed(1)}%`;
  if (comp.rawUnit === "lines") return `${Math.round(comp.rawValue)} lines`;
  if (comp.rawUnit === "cp") return `${comp.rawValue > 0 ? "+" : ""}${Math.round(comp.rawValue)} cp`;
  if (comp.rawUnit === "entropy" || comp.rawUnit === "diversity") return `${comp.rawValue.toFixed(3)} (pre-inv)`;
  return comp.rawValue.toFixed(4);
}

function MetricBreakdownSection({
  section,
  components,
  statValue,
  showRaw,
}: {
  section: (typeof METRIC_SECTIONS)[0];
  components: MetricComponent[];
  statValue: number;
  showRaw: boolean;
}) {
  const [open, setOpen] = useState(false);
  const pct = (clamp01(statValue) * 100).toFixed(0);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between py-0.5 text-[10px] text-slate-600 hover:text-slate-900"
      >
        <div className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: section.color }} />
          <span className="font-medium">{section.label}</span>
          {section.isCost && <span className="text-[9px] text-slate-400">(cost)</span>}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="tabular-nums text-slate-400">{pct}%</span>
          <ChevronDown className={cn("h-3 w-3 text-slate-400 transition-transform duration-150", open && "rotate-180")} />
        </div>
      </button>

      {open && (
        <div className="ml-3 mt-1 mb-1">
          <p className="mb-1.5 text-[9px] leading-relaxed text-slate-400">{section.description}</p>
          {components.map((comp) => {
            const contribution = clamp01(comp.value) * comp.weight;
            return (
              <div key={comp.key} className="mb-1">
                <div className="mb-0.5 flex items-center justify-between text-[9px]">
                  <span className="font-medium text-slate-500">{comp.label}</span>
                  <span className="tabular-nums">
                    <span style={{ color: section.color }}>
                      {showRaw ? formatRawValue(comp) : `${(clamp01(comp.value) * 100).toFixed(1)}%`}
                    </span>
                    <span className="mx-0.5 text-slate-300">×{comp.weight.toFixed(2)}</span>
                    <span className="text-slate-500">= {(contribution * 100).toFixed(1)}%</span>
                  </span>
                </div>
                <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="absolute h-full rounded-full opacity-30"
                    style={{ width: `${clamp01(comp.value) * 100}%`, backgroundColor: section.color }}
                  />
                  <div
                    className="absolute h-full rounded-full"
                    style={{ width: `${contribution * 100}%`, backgroundColor: section.color }}
                  />
                </div>
              </div>
            );
          })}
          <p className="mt-1 text-[9px] text-slate-400">
            Bright = contribution (value × weight). Faint = raw value.
          </p>
        </div>
      )}
    </div>
  );
}

function StyleMatchBreakdownSection({
  components,
  statValue,
}: {
  components: StyleMatchComponent[];
  statValue: number;
}) {
  const [open, setOpen] = useState(false);
  const pct = (clamp01(statValue) * 100).toFixed(0);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between py-0.5 text-[10px] text-slate-600 hover:text-slate-900"
      >
        <div className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" />
          <span className="font-medium">Style match</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="tabular-nums text-slate-400">{pct}%</span>
          <ChevronDown className={cn("h-3 w-3 text-slate-400 transition-transform duration-150", open && "rotate-180")} />
        </div>
      </button>

      {open && (
        <div className="ml-3 mt-1 mb-1">
          <p className="mb-1.5 text-[9px] leading-relaxed text-slate-400">
            Weighted cosine similarity across 9 style dimensions. Each bar shows your value (grey) vs opening's value (blue), weighted by feature importance.
          </p>
          {components.map((comp) => {
            const diff = Math.abs(comp.playerValue - comp.openingValue);
            const alignmentColor = diff < 0.15 ? "#059669" : diff < 0.35 ? "#d97706" : "#dc2626";
            return (
              <div key={comp.key} className="mb-1.5">
                <div className="mb-0.5 flex items-center justify-between text-[9px] text-slate-400">
                  <span className="font-medium">{comp.label}</span>
                  <span className="tabular-nums flex items-center gap-1.5">
                    <span className="text-slate-400">{(comp.playerValue * 100).toFixed(1)}%</span>
                    <span className="text-slate-300">/</span>
                    <span className="text-blue-500">{(comp.openingValue * 100).toFixed(1)}%</span>
                    <span style={{ color: alignmentColor }}>Δ{(diff * 100).toFixed(1)}%</span>
                    <span className="text-slate-300">w={comp.weight.toFixed(1)}</span>
                  </span>
                </div>
                <DualBar
                  playerValue={comp.playerValue}
                  openingValue={comp.openingValue}
                  playerColor="#94a3b8"
                  openingColor="#2563eb"
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function PracticalGambleSection({ node }: { node: OpeningStudyTreeNode }) {
  const [open, setOpen] = useState(false);
  const value = node.practicalGamble;
  const label = value == null ? "—" : `${(clamp01(value) * 100).toFixed(0)}%`;
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center justify-between py-0.5 text-[10px] text-slate-600 hover:text-slate-900"
      >
        <div className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
          <span className="font-medium">Practical gamble</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="tabular-nums text-slate-400">{label}</span>
          <ChevronDown className={cn("h-3 w-3 text-slate-400 transition-transform duration-150", open && "rotate-180")} />
        </div>
      </button>
      {open && (
        <div className="ml-3 mb-1 mt-1 text-[9px] leading-relaxed text-slate-400">
          <p>
            Advantage retained against popularity-weighted Lichess replies compared with Stockfish&apos;s best defense.
          </p>
          {value == null ? (
            <p className="mt-1 text-amber-600">Unavailable: fewer than 30 covered games or no snapshot data.</p>
          ) : (
            <div className="mt-1.5 grid grid-cols-3 gap-2 rounded bg-slate-50 p-1.5">
              <div><span className="block text-slate-500">Raw gap</span><span className="font-medium text-slate-700">+{(node.practicalGambleRaw ?? 0).toFixed(4)}</span></div>
              <div><span className="block text-slate-500">Games</span><span className="font-medium text-slate-700">{node.practicalGambleSampleSize.toLocaleString()}</span></div>
              <div><span className="block text-slate-500">Coverage</span><span className="font-medium text-slate-700">{(node.practicalGambleCoverage * 100).toFixed(1)}%</span></div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

type Props = {
  node: OpeningStudyTreeNode;
  playerVector: Record<string, number> | null;
};

export function NodeInspectorPanel({ node, playerVector }: Props) {
  const bd = node.breakdown;
  const [showRaw, setShowRaw] = useState(false);

  return (
    <div className="flex flex-col gap-3 rounded-md p-3" style={{ border: "1px solid var(--line)", backgroundColor: "var(--paper-dark)" }}>
      <div>
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold" style={{ color: "var(--ink)", fontFamily: "var(--font-display)" }}>Opening inspector</span>
          <span className="text-[10px]" style={{ color: "var(--ink-faint)" }}>{node.compatibleLineCount} lines</span>
        </div>
        <p className="mt-0.5 line-clamp-2 text-[10px]" style={{ color: "var(--ink-soft)" }}>
          {node.openingNames.length > 0 ? node.openingNames.join(" · ") : node.moveSan}
        </p>
        {!node.isTargetMove && (
          <p className="mt-1 text-[10px] tabular-nums" style={{ color: "var(--ink-faint)" }}>
            Lichess popularity {(node.popularityScore * 100).toFixed(1)}%
            {node.popularityGames > 0 ? ` · ${node.popularityGames.toLocaleString()} games` : " · no snapshot games"}
          </p>
        )}
      </div>
      <div className="flex justify-center">
        <ZoomableBoard fen={node.boardPreviewFen} label={node.openingNames[0] ?? node.moveSan}>
          <MiniChessBoard fen={node.boardPreviewFen} size={140} />
        </ZoomableBoard>
      </div>

      {bd?.openingFeatures && Object.keys(bd.openingFeatures).length > 0 && (
        <StyleProfileSection openingFeatures={bd.openingFeatures} playerVector={playerVector} />
      )}

      {bd && (
        <div>
          <div className="mb-1 flex items-center justify-between">
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400">Metric breakdown</p>
            <button
              type="button"
              onClick={() => setShowRaw((v) => !v)}
              className={cn(
                "rounded px-1.5 py-0.5 text-[9px] font-medium transition-colors",
                showRaw
                  ? "bg-slate-700 text-white"
                  : "bg-slate-100 text-slate-500 hover:bg-slate-200",
              )}
            >
              {showRaw ? "raw" : "%"}
            </button>
          </div>
          <div className="flex flex-col divide-y divide-slate-100">
            {bd.playerStyleMatch && bd.playerStyleMatch.length > 0 && (
              <StyleMatchBreakdownSection components={bd.playerStyleMatch} statValue={node.stats.playerStyleMatch} />
            )}
            <PracticalGambleSection node={node} />
            {METRIC_SECTIONS.map((section) => {
              const components = bd[section.key] as MetricComponent[] | undefined;
              if (!components || components.length === 0) return null;
              return (
                <MetricBreakdownSection
                  key={section.key}
                  section={section}
                  components={components}
                  statValue={node.stats[section.statKey]}
                  showRaw={showRaw}
                />
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
