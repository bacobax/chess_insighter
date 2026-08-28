import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { Chessboard } from "react-chessboard";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronsLeft,
  ChevronsRight,
  Keyboard,
  Loader2,
  StepBack,
  StepForward,
  XCircle,
} from "lucide-react";
import { Button } from "~/components/ui/button";
import { analyzePosition, getReportMistakeDetail } from "~/lib/api";
import type { MistakeAnalysisItem, PositionAnalysis, PunishmentLineMove, TacticTag } from "~/lib/types";

type Track = "engine" | "actual" | "optimal";
type BoardArrow = {
  startSquare: string;
  endSquare: string;
  color: string;
};

type BoardStep = {
  key: string;
  label: string;
  moveUci: string | null;
  san: string;
  fen: string;
  sideToMove: "white" | "black" | null;
  retainedWpLoss: number | null;
  evalCp: number | null;
  userWinProb: number | null;
  stable: boolean;
  tactics: TacticTag[];
  source: "blunder" | Track;
};

// ─── Tactic colour palette ────────────────────────────────────────────────────
const TACTIC_PRIORITY = [
  "check",
  "double_check",
  "discovered_check",
  "absolute_pin",
  "skewer",
  "fork",
  "king_attraction",
  "checkmate_in_k",
] as const;

type TacticTheme = (typeof TACTIC_PRIORITY)[number];

const THEME_COLORS: Record<TacticTheme, { bg: string; border: string; text: string; label: string }> = {
  check:            { bg: "#dbeafe", border: "#3b82f6", text: "#1e40af", label: "Check" },
  double_check:     { bg: "#e0f2fe", border: "#0891b2", text: "#0e7490", label: "Double check" },
  discovered_check: { bg: "#ede9fe", border: "#7c3aed", text: "#5b21b6", label: "Discovered check" },
  checkmate_in_k:   { bg: "#fee2e2", border: "#dc2626", text: "#991b1b", label: "Checkmate" },
  fork:             { bg: "#fef3c7", border: "#d97706", text: "#92400e", label: "Fork" },
  absolute_pin:     { bg: "#ffedd5", border: "#ea580c", text: "#9a3412", label: "Pin" },
  skewer:           { bg: "#ccfbf1", border: "#0d9488", text: "#115e59", label: "Skewer" },
  king_attraction:  { bg: "#fce7f3", border: "#db2777", text: "#9d174d", label: "King attraction" },
};

function primaryTactic(tactics: TacticTag[]): TacticTheme | null {
  if (!tactics.length) return null;
  const themes = tactics.map((t) => t.theme as TacticTheme);
  for (let i = TACTIC_PRIORITY.length - 1; i >= 0; i--) {
    if (themes.includes(TACTIC_PRIORITY[i])) return TACTIC_PRIORITY[i];
  }
  return themes[0] as TacticTheme;
}

export default function BlunderAnalysisPage() {
  const params = useParams();
  const [searchParams] = useSearchParams();
  const username = params.username ?? "";
  const mistakeId = params.mistakeId ?? "";
  const cacheHash = searchParams.get("cacheHash") ?? "";
  const analysisHash = searchParams.get("analysisHash") ?? "";
  const [mistake, setMistake] = useState<MistakeAnalysisItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(true);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [analysisEngineDepth, setAnalysisEngineDepth] = useState(10);
  const [track, setTrack] = useState<Track>("engine");
  const [stepIndex, setStepIndex] = useState(0);

  // Position analysis cache: fen → PositionAnalysis
  const [positionCache, setPositionCache] = useState<Map<string, PositionAnalysis>>(new Map());
  const loadingFens = useRef<Set<string>>(new Set());

  // Optimal branch expansion: which actual-step FEN is expanded
  const [expandedFen, setExpandedFen] = useState<string | null>(null);
  const reportUrl = `/report/${encodeURIComponent(username)}?restore=${encodeURIComponent(cacheHash)}#mistakes`;

  useEffect(() => {
    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);
    if (!cacheHash || !analysisHash || !mistakeId) {
      setDetailLoading(false);
      setDetailError("The report, analysis, and mistake identifiers are required.");
      return () => { cancelled = true; };
    }
    getReportMistakeDetail(cacheHash, analysisHash, mistakeId)
      .then((response) => {
        if (cancelled) return;
        setMistake(response.mistake);
        const depth = response.metadata.engine_depth;
        setAnalysisEngineDepth(typeof depth === "number" ? depth : 10);
      })
      .catch((err) => {
        if (!cancelled) setDetailError(err instanceof Error ? err.message : "Could not load this mistake.");
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => { cancelled = true; };
  }, [analysisHash, cacheHash, mistakeId]);

  const engineSteps = useMemo(() => (mistake ? buildSteps(mistake, "engine") : []), [mistake]);
  const actualSteps = useMemo(() => (mistake ? buildSteps(mistake, "actual") : []), [mistake]);

  const optimalSteps = useMemo(() => {
    if (!expandedFen || !mistake) return [];
    const cached = positionCache.get(expandedFen);
    if (!cached?.optimal_line) return [];
    return cached.optimal_line.map((move) => lineMoveToStep(move, "optimal"));
  }, [expandedFen, positionCache, mistake]);

  const activeSteps =
    track === "engine" ? engineSteps : track === "actual" ? actualSteps : optimalSteps;
  const step = activeSteps[Math.min(stepIndex, Math.max(activeSteps.length - 1, 0))] ?? null;

  useEffect(() => {
    setStepIndex((current) => Math.min(current, Math.max(activeSteps.length - 1, 0)));
  }, [activeSteps.length]);

  // Lazy position analysis: fetch and cache for a given FEN
  const requestPositionAnalysis = useCallback(
    (fen: string) => {
      if (!mistake) return;
      if (positionCache.has(fen) || loadingFens.current.has(fen)) return;
      loadingFens.current.add(fen);
      analyzePosition({
        fen,
        player_color: mistake.player_color,
        rating: mistake.user_rating ?? 1500,
        engine_depth: analysisEngineDepth,
        max_plies: 6,
      })
        .then((result) => {
          setPositionCache((prev) => new Map(prev).set(fen, result));
        })
        .catch(() => {
          // silently drop failed analyses
        })
        .finally(() => {
          loadingFens.current.delete(fen);
        });
    },
    [analysisEngineDepth, mistake, positionCache],
  );

  // When the selected step changes, prefetch its position analysis
  useEffect(() => {
    if (step?.fen) requestPositionAnalysis(step.fen);
  }, [step?.fen, requestPositionAnalysis]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!activeSteps.length) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        setStepIndex((current) => Math.min(activeSteps.length - 1, current + 1));
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        setStepIndex((current) => Math.max(0, current - 1));
      } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
        event.preventDefault();
        setTrack((current) => {
          if (current === "engine") return "actual";
          if (current === "actual") return optimalSteps.length > 0 ? "optimal" : "engine";
          return "engine";
        });
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeSteps.length, optimalSteps.length]);

  if (!mistake || !step) {
    return (
      <main className="min-h-screen px-4 py-8" style={{ color: "var(--ink)" }}>
        <div className="mx-auto max-w-3xl rounded-md border p-6" style={{ borderColor: "var(--line)", backgroundColor: "var(--paper)" }}>
          <Link to={reportUrl}>
            <Button variant="outline">
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
          </Link>
          <h1 className="mt-5 text-3xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>{detailLoading ? "Loading mistake" : "Mistake unavailable"}</h1>
          <p className="mt-2 text-sm" style={{ color: "var(--ink-soft)" }}>
            {detailLoading ? "Loading the saved analysis from this player report." : detailError ?? "This mistake is not part of the selected analysis."}
          </p>
          {detailLoading ? <Loader2 className="mt-4 h-5 w-5 animate-spin" /> : null}
        </div>
      </main>
    );
  }

  const canBack = stepIndex > 0;
  const canForward = stepIndex < activeSteps.length - 1;
  const arrow = moveArrow(step.moveUci, track);

  // Compute white win probability for the eval bar
  const userWinProb = step.userWinProb;
  const whiteWinProb =
    userWinProb != null
      ? mistake.player_color === "white"
        ? userWinProb
        : 1 - userWinProb
      : 0.5;

  const handleNodeSelect = (newTrack: Track, newIndex: number) => {
    setTrack(newTrack);
    setStepIndex(newIndex);
  };

  const handleExpand = (fen: string) => {
    if (expandedFen === fen) {
      // toggle off
      setExpandedFen(null);
      if (track === "optimal") setTrack("actual");
    } else {
      setExpandedFen(fen);
      requestPositionAnalysis(fen);
    }
  };

  const isLoadingFen = (fen: string) => loadingFens.current.has(fen) && !positionCache.has(fen);
  const currentPositionAnalysis = step?.fen ? positionCache.get(step.fen) ?? null : null;

  return (
    <main className="min-h-screen px-4 py-6" style={{ color: "var(--ink)" }}>
      <div className="mx-auto max-w-7xl">
        <header className="mb-4 flex items-center gap-3">
          <Link to={reportUrl}>
            <Button variant="outline" size="icon" aria-label="Back to mistakes">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <p className="text-xs uppercase tracking-[0.22em]" style={{ color: "var(--accent)" }}>
              {username} · move {mistake.move_number}{mistake.player_color === "black" ? "..." : "."}
            </p>
            <h1 className="text-3xl font-semibold tracking-normal" style={{ fontFamily: "var(--font-display)" }}>
              {mistake.san} under the lens
            </h1>
          </div>
        </header>

        <div className="grid gap-4 xl:grid-cols-[minmax(360px,580px)_minmax(0,1fr)]">
          {/* ── Left column: board + eval bar + controls ── */}
          <section className="space-y-4">
            <div
              className="rounded-md border p-3"
              style={{
                borderColor: "var(--line)",
                background:
                  "linear-gradient(135deg, color-mix(in srgb, var(--ink) 5%, var(--paper)) 0%, var(--paper-dark) 100%)",
              }}
            >
              {/* Board + eval bar side by side */}
              <div className="flex gap-2">
                <EvalBar
                  whiteWinProb={whiteWinProb}
                  userWinProb={userWinProb}
                  playerColor={mistake.player_color}
                />
                <div className="flex-1 overflow-hidden rounded-md" style={{ border: "1px solid var(--line)" }}>
                  <Chessboard
                    options={{
                      position: step.fen,
                      boardOrientation: mistake.player_color,
                      allowDragging: false,
                      allowDrawingArrows: true,
                      arrows: arrow ? [arrow] : [],
                      clearArrowsOnPositionChange: false,
                      showNotation: true,
                      animationDurationInMs: 180,
                      boardStyle: { width: "100%", aspectRatio: "1 / 1" },
                    }}
                  />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2 rounded-md border p-3" style={{ borderColor: "var(--line)", backgroundColor: "var(--paper)" }}>
              <Button variant="outline" size="icon" disabled={!canBack} onClick={() => setStepIndex(0)} aria-label="First position">
                <ChevronsLeft className="h-4 w-4" />
              </Button>
              <div className="flex justify-center gap-2">
                <Button variant="outline" disabled={!canBack} onClick={() => setStepIndex((current) => Math.max(0, current - 1))}>
                  <StepBack className="h-4 w-4" />
                  Back
                </Button>
                <Button disabled={!canForward} onClick={() => setStepIndex((current) => Math.min(activeSteps.length - 1, current + 1))}>
                  Forward
                  <StepForward className="h-4 w-4" />
                </Button>
              </div>
              <Button variant="outline" size="icon" disabled={!canForward} onClick={() => setStepIndex(activeSteps.length - 1)} aria-label="Last position">
                <ChevronsRight className="h-4 w-4" />
              </Button>
            </div>

            <div className="rounded-md border p-3 text-sm" style={{ borderColor: "var(--line)", backgroundColor: "var(--paper-dark)" }}>
              <div className="flex items-center gap-2 font-semibold">
                <Keyboard className="h-4 w-4" />
                Arrow keys
              </div>
              <div className="mt-1" style={{ color: "var(--ink-soft)" }}>
                Left/right steps through the line. Up/down switches between branches.
              </div>
            </div>
          </section>

          {/* ── Right column: status + fork diagram + top lines + comparison ── */}
          <section className="space-y-4">
            <LineStatus mistake={mistake} step={step} track={track} stepIndex={stepIndex} total={activeSteps.length} userWinProb={userWinProb} />
            <ForkDiagram
              mistake={mistake}
              engineSteps={engineSteps}
              actualSteps={actualSteps}
              optimalSteps={optimalSteps}
              expandedFen={expandedFen}
              track={track}
              stepIndex={stepIndex}
              onSelect={handleNodeSelect}
              onExpand={handleExpand}
              isLoadingFen={isLoadingFen}
            />
            <TopLinesPanel
              analysis={currentPositionAnalysis}
              playerColor={mistake.player_color}
              isLoading={step?.fen ? isLoadingFen(step.fen) : false}
            />
            <ComparisonPanel mistake={mistake} />
          </section>
        </div>
      </div>
    </main>
  );
}

// ─── Eval Bar ─────────────────────────────────────────────────────────────────

function EvalBar({
  whiteWinProb,
  userWinProb,
  playerColor,
}: {
  whiteWinProb: number;
  userWinProb: number | null;
  playerColor: "white" | "black";
}) {
  const whitePct = Math.round(whiteWinProb * 100);
  const blackPct = 100 - whitePct;
  const userPct = userWinProb != null ? Math.round(userWinProb * 100) : null;

  // When board is oriented for black (player is black), the bar is also flipped:
  // black is at the bottom, white at the top
  const isFlipped = playerColor === "black";

  const topColor = isFlipped ? "#fff" : "#1a1a1a";
  const bottomColor = isFlipped ? "#1a1a1a" : "#fff";
  const topPct = isFlipped ? whitePct : blackPct;
  const bottomPct = isFlipped ? blackPct : whitePct;

  return (
    <div
      className="flex shrink-0 flex-col overflow-hidden rounded-md"
      style={{
        width: "22px",
        border: "1px solid var(--line)",
        position: "relative",
      }}
      title={userPct != null ? `Win probability: ${userPct}%` : "Eval bar"}
    >
      {/* Top portion */}
      <div
        style={{
          flex: `0 0 ${topPct}%`,
          backgroundColor: topColor,
          transition: "flex-basis 0.4s ease",
          minHeight: "2px",
        }}
      />
      {/* Thin divider */}
      <div style={{ height: "1px", backgroundColor: "var(--line)", flexShrink: 0 }} />
      {/* Bottom portion */}
      <div
        style={{
          flex: `0 0 ${bottomPct}%`,
          backgroundColor: bottomColor,
          transition: "flex-basis 0.4s ease",
          minHeight: "2px",
        }}
      />
      {/* Annotation */}
      {userPct != null && (
        <div
          className="absolute bottom-1 left-0 right-0 text-center text-[9px] font-bold leading-none"
          style={{
            color: playerColor === "white" ? "#1a1a1a" : "#fff",
            mixBlendMode: "difference",
            letterSpacing: "0",
          }}
        >
          {userPct}
        </div>
      )}
    </div>
  );
}

// ─── Fork Diagram ─────────────────────────────────────────────────────────────

function ForkDiagram({
  mistake,
  engineSteps,
  actualSteps,
  optimalSteps,
  expandedFen,
  track,
  stepIndex,
  onSelect,
  onExpand,
  isLoadingFen,
}: {
  mistake: MistakeAnalysisItem;
  engineSteps: BoardStep[];
  actualSteps: BoardStep[];
  optimalSteps: BoardStep[];
  expandedFen: string | null;
  track: Track;
  stepIndex: number;
  onSelect: (track: Track, index: number) => void;
  onExpand: (fen: string) => void;
  isLoadingFen: (fen: string) => boolean;
}) {
  const trunk = engineSteps.slice(0, 2);
  const engineBranch = engineSteps.slice(2);
  const actualBranch = actualSteps.slice(2);

  const allThemesPresent = useMemo(() => {
    const themes = new Set<TacticTheme>();
    for (const s of [...engineBranch, ...actualBranch, ...optimalSteps]) {
      const t = primaryTactic(s.tactics);
      if (t) themes.add(t);
    }
    return Array.from(themes);
  }, [engineBranch, actualBranch, optimalSteps]);

  const isActive = (t: Track, i: number) => track === t && stepIndex === i;

  return (
    <div
      className="rounded-md border p-4"
      style={{ borderColor: "var(--line)", backgroundColor: "var(--paper)" }}
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold" style={{ fontFamily: "var(--font-display)" }}>
          Divergence map
        </h2>
        <div className="flex items-center gap-3 text-xs" style={{ color: "var(--ink-soft)" }}>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-6 rounded-full" style={{ backgroundColor: "#16a34a" }} />
            stable
          </span>
          <span className="flex items-center gap-1">
            <span
              className="inline-block h-0 w-6 rounded-full"
              style={{ borderTop: "2px dashed #d97706" }}
            />
            volatile
          </span>
        </div>
      </div>

      <div className="overflow-x-auto pb-2">
        <div className="inline-flex min-w-full flex-col gap-0">
          {/* ── Trunk row ── */}
          <div className="flex items-center">
            {trunk.map((s, i) => {
              const isBlunder = s.source === "blunder" && i === 1;
              const active = isActive("engine", i);
              return (
                <div key={s.key} className="flex items-center">
                  {i > 0 && <Connector stable={false} isBlunder />}
                  <DiagramNode
                    step={s}
                    active={active || (isActive("actual", i) && i < 2)}
                    isBlunder={isBlunder}
                    isTrunk
                    onClick={() => onSelect("engine", i)}
                    secondaryActive={isActive("actual", i) && i < 2}
                  />
                </div>
              );
            })}
            {(engineBranch.length > 0 || actualBranch.length > 0) && <ForkSplit />}
          </div>

          {/* ── Branches ── */}
          {(engineBranch.length > 0 || actualBranch.length > 0) && (
            <div className="relative ml-[calc(2*var(--node-w,88px)+24px+12px)] flex flex-col gap-3 pt-1" style={{ "--node-w": "88px" } as React.CSSProperties}>
              {/* Engine branch */}
              <BranchRow
                steps={engineBranch}
                trackType="engine"
                baseIndex={2}
                activeIndex={track === "engine" ? stepIndex : -1}
                onSelect={(i) => onSelect("engine", i)}
                label="Engine punishment"
                labelColor="#2d5016"
              />
              {/* Actual branch */}
              <BranchRow
                steps={actualBranch}
                trackType="actual"
                baseIndex={2}
                activeIndex={track === "actual" ? stepIndex : -1}
                onSelect={(i) => onSelect("actual", i)}
                label="Actual game"
                labelColor="var(--accent)"
                onExpand={onExpand}
                expandedFen={expandedFen}
                isLoadingFen={isLoadingFen}
              />
              {/* Optimal branch (when expanded) */}
              {expandedFen && optimalSteps.length > 0 && (
                <BranchRow
                  steps={optimalSteps}
                  trackType="optimal"
                  baseIndex={0}
                  activeIndex={track === "optimal" ? stepIndex : -1}
                  onSelect={(i) => onSelect("optimal", i)}
                  label="Optimal from here"
                  labelColor="#7c3aed"
                />
              )}
              {expandedFen && optimalSteps.length === 0 && isLoadingFen(expandedFen) && (
                <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--ink-soft)" }}>
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Computing optimal line…
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Legend ── */}
      {allThemesPresent.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2 border-t pt-3" style={{ borderColor: "var(--line)" }}>
          {allThemesPresent.map((theme) => {
            const c = THEME_COLORS[theme];
            return (
              <span
                key={theme}
                className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium"
                style={{ backgroundColor: c.bg, borderColor: c.border, color: c.text }}
              >
                <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: c.border }} />
                {c.label}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

function BranchRow({
  steps,
  trackType,
  baseIndex,
  activeIndex,
  onSelect,
  label,
  labelColor,
  onExpand,
  expandedFen,
  isLoadingFen,
}: {
  steps: BoardStep[];
  trackType: Track;
  baseIndex: number;
  activeIndex: number;
  onSelect: (absoluteIndex: number) => void;
  label: string;
  labelColor: string;
  onExpand?: (fen: string) => void;
  expandedFen?: string | null;
  isLoadingFen?: (fen: string) => boolean;
}) {
  return (
    <div className="flex items-center gap-0">
      <span
        className="mr-2 w-[72px] shrink-0 text-right text-[10px] font-semibold uppercase tracking-wider"
        style={{ color: labelColor }}
      >
        {label}
      </span>
      {steps.map((s, i) => (
        <div key={s.key} className="flex items-center">
          {i > 0 && <Connector stable={s.stable} />}
          {i === 0 && <Connector stable={s.stable} isFirstBranch trackType={trackType} />}
          <DiagramNode
            step={s}
            active={activeIndex === baseIndex + i}
            isBlunder={false}
            isTrunk={false}
            onClick={() => onSelect(baseIndex + i)}
            onExpand={trackType === "actual" && onExpand ? () => onExpand(s.fen) : undefined}
            isExpanded={trackType === "actual" && expandedFen === s.fen}
            isLoadingExpand={trackType === "actual" && isLoadingFen ? isLoadingFen(s.fen) : false}
          />
        </div>
      ))}
    </div>
  );
}

function DiagramNode({
  step,
  active,
  isBlunder,
  isTrunk,
  onClick,
  secondaryActive,
  onExpand,
  isExpanded,
  isLoadingExpand,
}: {
  step: BoardStep;
  active: boolean;
  isBlunder: boolean;
  isTrunk: boolean;
  onClick: () => void;
  secondaryActive?: boolean;
  onExpand?: () => void;
  isExpanded?: boolean;
  isLoadingExpand?: boolean;
}) {
  const tactic = primaryTactic(step.tactics);
  const tacticColor = tactic ? THEME_COLORS[tactic] : null;
  const extraCount = step.tactics.length > 1 ? step.tactics.length - 1 : 0;

  const bg = isBlunder
    ? "color-mix(in srgb, var(--accent) 15%, var(--paper))"
    : tacticColor
    ? tacticColor.bg
    : active
    ? "var(--paper-dark)"
    : "var(--paper)";

  const border = isBlunder
    ? "var(--accent)"
    : tacticColor
    ? tacticColor.border
    : active || secondaryActive
    ? "var(--ink)"
    : "var(--line)";

  const textColor = isBlunder
    ? "var(--accent)"
    : tacticColor
    ? tacticColor.text
    : "var(--ink)";

  return (
    <div className="relative">
      <button
        type="button"
        onClick={onClick}
        className="relative flex h-[52px] w-[84px] flex-col items-center justify-center rounded-md border transition-transform hover:-translate-y-0.5"
        style={{
          backgroundColor: bg,
          borderColor: border,
          borderWidth: active || secondaryActive ? "2px" : "1px",
          boxShadow: active ? "0 2px 8px rgba(0,0,0,0.12)" : undefined,
        }}
        title={step.label}
      >
        <span
          className="block max-w-[72px] truncate text-center text-xs font-bold leading-none"
          style={{ color: textColor }}
        >
          {step.san === "start" ? "·" : step.san}
        </span>
        <span
          className="mt-0.5 block text-center text-[10px] leading-none"
          style={{ color: isBlunder ? "var(--accent)" : tacticColor ? tacticColor.text : "var(--ink-faint)" }}
        >
          {isBlunder ? "blunder" : step.label}
        </span>
        {tactic && (
          <span
            className="absolute -top-1.5 -right-1.5 flex h-3.5 w-3.5 items-center justify-center rounded-full text-[8px] font-bold"
            style={{ backgroundColor: tacticColor!.border, color: "#fff" }}
          >
            {extraCount > 0 ? `+${extraCount}` : "!"}
          </span>
        )}
      </button>
      {/* Expand button for actual-game nodes */}
      {onExpand && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onExpand(); }}
          className="absolute -bottom-1.5 -left-1.5 flex h-4 w-4 items-center justify-center rounded-full border text-[9px] font-bold transition-colors"
          style={{
            backgroundColor: isExpanded ? "#7c3aed" : "var(--paper)",
            borderColor: isExpanded ? "#7c3aed" : "var(--line)",
            color: isExpanded ? "#fff" : "var(--ink-soft)",
          }}
          title={isExpanded ? "Hide optimal line" : "Show optimal engine line from here"}
          aria-label={isExpanded ? "Collapse optimal line" : "Expand optimal line"}
        >
          {isLoadingExpand ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : isExpanded ? "−" : "+"}
        </button>
      )}
    </div>
  );
}

function Connector({
  stable,
  isBlunder,
  isFirstBranch,
  trackType,
}: {
  stable: boolean;
  isBlunder?: boolean;
  isFirstBranch?: boolean;
  trackType?: Track;
}) {
  const color = isBlunder ? "var(--line)" : stable ? "#16a34a" : "#d97706";
  return (
    <div
      className="mx-0.5 h-0 w-5 shrink-0"
      style={{
        borderTop: isBlunder
          ? `2px solid ${color}`
          : stable
          ? `2px solid ${color}`
          : `2px dashed ${color}`,
      }}
    />
  );
}

function ForkSplit() {
  return (
    <div
      className="mx-0.5 h-[60px] w-4 shrink-0"
      style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='60'%3E%3Cpath d='M0 30 L8 30 L8 10 M8 30 L8 50' stroke='%23999' stroke-width='1.5' fill='none'/%3E%3C/svg%3E")`,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "center",
      }}
    />
  );
}

// ─── Top-3 lines panel ────────────────────────────────────────────────────────

function TopLinesPanel({
  analysis,
  playerColor,
  isLoading,
}: {
  analysis: PositionAnalysis | null;
  playerColor: "white" | "black";
  isLoading: boolean;
}) {
  if (!analysis && !isLoading) return null;

  return (
    <div
      className="rounded-md border p-4"
      style={{ borderColor: "var(--line)", backgroundColor: "var(--paper)" }}
    >
      <h2 className="mb-2 text-sm font-semibold" style={{ fontFamily: "var(--font-display)" }}>
        Top engine lines from here
      </h2>
      {isLoading && !analysis && (
        <div className="flex items-center gap-2 text-xs" style={{ color: "var(--ink-soft)" }}>
          <Loader2 className="h-3 w-3 animate-spin" />
          Analysing position…
        </div>
      )}
      {analysis?.top_lines.map((line) => {
        const winPct = line.user_win_prob != null ? Math.round(line.user_win_prob * 100) : null;
        const mateStr = line.mate_in != null ? `#${Math.abs(line.mate_in)}` : null;
        const displayPct = mateStr ?? (winPct != null ? `${winPct}%` : null);
        const sanText = line.line_san.length > 0 ? line.line_san.join(" ") : line.first_san;
        const truncated = line.line_san.length >= 6;

        // Pill colour: green for favourable (>55%), red for unfavourable (<45%), neutral otherwise
        const pillBg =
          winPct == null
            ? "var(--paper-dark)"
            : playerColor === "white"
            ? winPct >= 55
              ? "color-mix(in srgb, #16a34a 15%, var(--paper))"
              : winPct <= 45
              ? "color-mix(in srgb, var(--accent) 12%, var(--paper))"
              : "var(--paper-dark)"
            : winPct <= 45
            ? "color-mix(in srgb, #16a34a 15%, var(--paper))"
            : winPct >= 55
            ? "color-mix(in srgb, var(--accent) 12%, var(--paper))"
            : "var(--paper-dark)";
        const pillText =
          winPct == null
            ? "var(--ink)"
            : playerColor === "white"
            ? winPct >= 55
              ? "#2d5016"
              : winPct <= 45
              ? "var(--accent)"
              : "var(--ink)"
            : winPct <= 45
            ? "#2d5016"
            : winPct >= 55
            ? "var(--accent)"
            : "var(--ink)";

        return (
          <div
            key={line.rank}
            className="flex items-baseline gap-2 border-b py-1.5 text-xs last:border-b-0"
            style={{ borderColor: "var(--line)" }}
          >
            <span
              className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold tabular-nums"
              style={{ backgroundColor: pillBg, color: pillText, minWidth: "34px", textAlign: "center" }}
            >
              {displayPct ?? "—"}
            </span>
            <span className="font-mono text-[11px] leading-snug" style={{ color: "var(--ink-soft)" }}>
              {sanText}
              {truncated && <span style={{ color: "var(--ink-faint)" }}>…</span>}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ─── Existing helpers ─────────────────────────────────────────────────────────

function buildSteps(mistake: MistakeAnalysisItem, track: Track): BoardStep[] {
  const continuation = track === "engine" ? mistake.best_line_moves : mistake.actual_line_moves;
  const steps: BoardStep[] = [
    {
      key: "before",
      label: "Before blunder",
      moveUci: null,
      san: "start",
      fen: mistake.fen_before,
      sideToMove: null,
      retainedWpLoss: null,
      evalCp: mistake.user_eval_before_cp,
      userWinProb: mistake.win_prob_before,
      stable: false,
      tactics: [],
      source: "blunder",
    },
    {
      key: "blunder",
      label: "Blunder",
      moveUci: mistake.uci,
      san: mistake.san,
      fen: mistake.fen_after,
      sideToMove: mistake.player_color,
      retainedWpLoss: mistake.wp_loss,
      evalCp: mistake.user_eval_after_cp,
      userWinProb: mistake.win_prob_after,
      stable: false,
      tactics: [],
      source: "blunder",
    },
  ];
  continuation.forEach((move) => {
    steps.push(lineMoveToStep(move, track));
  });
  return steps;
}

function lineMoveToStep(move: PunishmentLineMove, track: Track): BoardStep {
  return {
    key: `${track}-${move.ply_offset}-${move.move_uci}`,
    label: `+${move.ply_offset}`,
    moveUci: move.move_uci,
    san: move.san,
    fen: move.fen_after,
    sideToMove: move.side_to_move,
    retainedWpLoss: move.retained_wp_loss,
    evalCp: move.user_eval_cp,
    userWinProb: move.user_win_prob,
    stable: move.stable_after_move,
    tactics: move.tactics,
    source: track,
  };
}

function LineStatus({
  mistake,
  step,
  track,
  stepIndex,
  total,
  userWinProb,
}: {
  mistake: MistakeAnalysisItem;
  step: BoardStep;
  track: Track;
  stepIndex: number;
  total: number;
  userWinProb: number | null;
}) {
  const trackLabel = track === "engine" ? "Punishing line" : track === "actual" ? "Actual line" : "Optimal line";
  const trackColor = track === "engine" ? "#2d5016" : track === "actual" ? "var(--accent)" : "#7c3aed";

  return (
    <div
      className="rounded-md border p-5"
      style={{
        borderColor: "var(--line)",
        background:
          track === "engine"
            ? "linear-gradient(135deg, color-mix(in srgb, #2d5016 13%, var(--paper)) 0%, var(--paper) 74%)"
            : track === "actual"
            ? "linear-gradient(135deg, color-mix(in srgb, var(--accent) 12%, var(--paper)) 0%, var(--paper) 74%)"
            : "linear-gradient(135deg, color-mix(in srgb, #7c3aed 10%, var(--paper)) 0%, var(--paper) 74%)",
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.22em]" style={{ color: trackColor }}>
            {trackLabel} · {stepIndex + 1}/{total}
          </p>
          <h2 className="mt-1 text-2xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
            {step.label}: {step.san}
          </h2>
        </div>
        <Badge tone={severityTone(mistake.severity)}>{title(mistake.severity)}</Badge>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        <Metric
          label="Win chance"
          value={userWinProb != null ? `${Math.round(userWinProb * 100)}%` : "—"}
        />
        <Metric label="WP lost" value={formatPercent(mistake.wp_loss)} />
        <Metric label="Retained" value={formatPercent(step.retainedWpLoss)} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {step.stable ? <Badge tone="green">Stable</Badge> : <Badge tone="ink">Volatile</Badge>}
        {step.tactics.map((tag, index) => (
          <Badge key={`${tag.theme}-${index}`} tone="green">
            {themeLabel(tag.theme)}
          </Badge>
        ))}
      </div>
    </div>
  );
}

function ComparisonPanel({ mistake }: { mistake: MistakeAnalysisItem }) {
  return (
    <div className="rounded-md border p-4" style={{ borderColor: "var(--line)", backgroundColor: "var(--paper)" }}>
      <h2 className="text-base font-semibold" style={{ fontFamily: "var(--font-display)" }}>
        Punishment result
      </h2>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <Metric label="Engine depth" value={mistake.theoretical_punishment_depth} />
        <Metric label="Actual hits" value={mistake.actual_punishing_moves_played} />
        <Metric label="Outcome" value={mistake.actual_punished ? "punished" : "missed"} />
      </div>
      <div className="mt-3 flex items-start gap-2 text-sm" style={{ color: "var(--ink-soft)" }}>
        {mistake.actual_punished ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "#2d5016" }} />
        ) : (
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} />
        )}
        <span>
          {mistake.actual_punished
            ? "The opponent preserved enough of the engine punishment."
            : `The punishment was missed${mistake.missed_actual_move_uci ? ` with ${mistake.missed_actual_move_uci}` : ""}${mistake.missed_best_move_uci ? ` instead of ${mistake.missed_best_move_uci}` : ""}.`}
        </span>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div
      className="rounded-md border px-3 py-2"
      style={{ borderColor: "var(--line)", backgroundColor: "rgba(244,236,216,0.72)" }}
    >
      <div className="text-xs uppercase tracking-wider" style={{ color: "var(--ink-faint)" }}>
        {label}
      </div>
      <div className="mt-1 font-semibold">{value}</div>
    </div>
  );
}

function Badge({
  children,
  tone,
}: {
  children: ReactNode;
  tone: "red" | "amber" | "green" | "ink";
}) {
  const styles = {
    red: {
      backgroundColor: "color-mix(in srgb, var(--accent) 13%, var(--paper))",
      color: "var(--accent)",
      borderColor: "color-mix(in srgb, var(--accent) 36%, var(--paper))",
    },
    amber: {
      backgroundColor: "color-mix(in srgb, #8b6914 15%, var(--paper))",
      color: "#8b6914",
      borderColor: "#c4aa60",
    },
    green: {
      backgroundColor: "color-mix(in srgb, #2d5016 13%, var(--paper))",
      color: "#2d5016",
      borderColor: "#8ab578",
    },
    ink: {
      backgroundColor: "var(--paper-dark)",
      color: "var(--ink)",
      borderColor: "var(--line)",
    },
  }[tone];
  return (
    <span className="inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold" style={styles}>
      {children}
    </span>
  );
}

function moveArrow(uci: string | null, track: Track): BoardArrow | null {
  if (!uci || uci.length < 4) return null;
  return {
    startSquare: uci.slice(0, 2),
    endSquare: uci.slice(2, 4),
    color:
      track === "engine"
        ? "rgba(45, 80, 22, 0.78)"
        : track === "optimal"
        ? "rgba(124, 58, 237, 0.78)"
        : "rgba(124, 58, 45, 0.78)",
  };
}

function severityTone(severity: string): "red" | "amber" | "green" | "ink" {
  if (severity === "blunder") return "red";
  if (severity === "mistake") return "amber";
  if (severity === "inaccuracy") return "ink";
  return "green";
}

function title(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function themeLabel(value: string) {
  return title(value).replace("K", "k");
}

function formatPercent(value: number | null | undefined, digits = 0) {
  if (value == null) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}
