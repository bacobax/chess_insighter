import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { Chessboard } from "react-chessboard";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronsLeft,
  ChevronsRight,
  CircleDot,
  GitCompareArrows,
  Keyboard,
  RotateCcw,
  ShieldAlert,
  StepBack,
  StepForward,
  XCircle,
} from "lucide-react";
import { Button } from "~/components/ui/button";
import type { MistakeAnalysisItem, PunishmentLineMove, TacticTag } from "~/lib/types";

type Track = "engine" | "actual";
type BoardArrow = {
  startSquare: string;
  endSquare: string;
  color: string;
};

type StoredBlunder = {
  username: string;
  mistake: MistakeAnalysisItem;
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
  stable: boolean;
  tactics: TacticTag[];
  source: "blunder" | Track;
};

const BLUNDER_STORAGE_PREFIX = "chess-insighter:blunder";

export default function BlunderAnalysisPage() {
  const params = useParams();
  const username = params.username ?? "";
  const blunderKey = params.blunderKey ?? "";
  const [stored, setStored] = useState<StoredBlunder | null>(null);
  const [track, setTrack] = useState<Track>("engine");
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    const raw = sessionStorage.getItem(`${BLUNDER_STORAGE_PREFIX}:${username}:${blunderKey}`);
    if (!raw) return;
    try {
      setStored(JSON.parse(raw) as StoredBlunder);
    } catch {
      setStored(null);
    }
  }, [blunderKey, username]);

  const mistake = stored?.mistake ?? null;
  const engineSteps = useMemo(() => (mistake ? buildSteps(mistake, "engine") : []), [mistake]);
  const actualSteps = useMemo(() => (mistake ? buildSteps(mistake, "actual") : []), [mistake]);
  const activeSteps = track === "engine" ? engineSteps : actualSteps;
  const step = activeSteps[Math.min(stepIndex, Math.max(activeSteps.length - 1, 0))] ?? null;

  useEffect(() => {
    setStepIndex((current) => Math.min(current, Math.max(activeSteps.length - 1, 0)));
  }, [activeSteps.length]);

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
        setTrack((current) => (current === "engine" ? "actual" : "engine"));
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeSteps.length]);

  if (!mistake || !step) {
    return (
      <main className="min-h-screen px-4 py-8" style={{ color: "var(--ink)" }}>
        <div className="mx-auto max-w-3xl rounded-md border p-6" style={{ borderColor: "var(--line)", backgroundColor: "var(--paper)" }}>
          <Link to={`/mistakes/${encodeURIComponent(username)}`}>
            <Button variant="outline">
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
          </Link>
          <h1 className="mt-5 text-3xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
            Blunder line unavailable
          </h1>
          <p className="mt-2 text-sm" style={{ color: "var(--ink-soft)" }}>
            Open a blunder from the analyzer results so the board can load the stored line data.
          </p>
        </div>
      </main>
    );
  }

  const canBack = stepIndex > 0;
  const canForward = stepIndex < activeSteps.length - 1;
  const arrow = moveArrow(step.moveUci, track);

  return (
    <main className="min-h-screen px-4 py-6" style={{ color: "var(--ink)" }}>
      <div className="mx-auto max-w-7xl">
        <header className="mb-4 flex flex-col justify-between gap-3 lg:flex-row lg:items-end">
          <div className="flex items-center gap-3">
            <Link to={`/mistakes/${encodeURIComponent(username)}`}>
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
          </div>
          <div className="flex flex-wrap gap-2">
            <LineSwitch active={track === "engine"} onClick={() => { setTrack("engine"); setStepIndex(0); }} tone="engine">
              Engine punishment
            </LineSwitch>
            <LineSwitch active={track === "actual"} onClick={() => { setTrack("actual"); setStepIndex(0); }} tone="actual">
              Actual game
            </LineSwitch>
          </div>
        </header>

        <div className="grid gap-4 xl:grid-cols-[minmax(360px,580px)_minmax(0,1fr)]">
          <section className="space-y-4">
            <div
              className="rounded-md border p-3"
              style={{
                borderColor: "var(--line)",
                background:
                  "linear-gradient(135deg, color-mix(in srgb, var(--ink) 5%, var(--paper)) 0%, var(--paper-dark) 100%)",
              }}
            >
              <div className="overflow-hidden rounded-md" style={{ border: "1px solid var(--line)" }}>
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
                Left/right steps through the current line. Up/down switches between engine punishment and the actual game.
              </div>
            </div>
          </section>

          <section className="space-y-4">
            <LineStatus mistake={mistake} step={step} track={track} stepIndex={stepIndex} total={activeSteps.length} />
            <LineTimeline title="Engine punishment" track="engine" steps={engineSteps} active={track === "engine"} activeIndex={stepIndex} onSelect={(index) => { setTrack("engine"); setStepIndex(index); }} />
            <LineTimeline title="Actual game" track="actual" steps={actualSteps} active={track === "actual"} activeIndex={stepIndex} onSelect={(index) => { setTrack("actual"); setStepIndex(index); }} />
            <ComparisonPanel mistake={mistake} />
          </section>
        </div>
      </div>
    </main>
  );
}

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
    stable: move.stable_after_move,
    tactics: move.tactics,
    source: track,
  };
}

function LineStatus({ mistake, step, track, stepIndex, total }: { mistake: MistakeAnalysisItem; step: BoardStep; track: Track; stepIndex: number; total: number }) {
  return (
    <div
      className="rounded-md border p-5"
      style={{
        borderColor: "var(--line)",
        background:
          track === "engine"
            ? "linear-gradient(135deg, color-mix(in srgb, #2d5016 13%, var(--paper)) 0%, var(--paper) 74%)"
            : "linear-gradient(135deg, color-mix(in srgb, var(--accent) 12%, var(--paper)) 0%, var(--paper) 74%)",
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.22em]" style={{ color: track === "engine" ? "#2d5016" : "var(--accent)" }}>
            {track === "engine" ? "Punishing line" : "Actual line"} · {stepIndex + 1}/{total}
          </p>
          <h2 className="mt-1 text-2xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
            {step.label}: {step.san}
          </h2>
        </div>
        <Badge tone={severityTone(mistake.severity)}>{title(mistake.severity)}</Badge>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        <Metric label="Lost" value={formatCp(mistake.cp_loss)} />
        <Metric label="WP loss" value={formatPercent(mistake.wp_loss)} />
        <Metric label="Current eval" value={formatCp(step.evalCp)} />
        <Metric label="Retained" value={formatPercent(step.retainedWpLoss)} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {step.stable ? <Badge tone="green">Stable</Badge> : <Badge tone="ink">Volatile</Badge>}
        {step.tactics.map((tag, index) => (
          <Badge key={`${tag.theme}-${index}`} tone="green">{themeLabel(tag.theme)}</Badge>
        ))}
      </div>
    </div>
  );
}

function LineTimeline({ title, track, steps, active, activeIndex, onSelect }: { title: string; track: Track; steps: BoardStep[]; active: boolean; activeIndex: number; onSelect: (index: number) => void }) {
  return (
    <div className="rounded-md border p-4" style={{ borderColor: active ? lineColor(track) : "var(--line)", backgroundColor: "var(--paper)" }}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base font-semibold" style={{ fontFamily: "var(--font-display)" }}>
          {track === "engine" ? <ShieldAlert className="h-4 w-4" /> : <GitCompareArrows className="h-4 w-4" />}
          {title}
        </h2>
        <span className="text-xs" style={{ color: "var(--ink-soft)" }}>{steps.length} positions</span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {steps.map((step, index) => (
          <button
            key={step.key}
            type="button"
            onClick={() => onSelect(index)}
            className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 rounded-md border p-2 text-left transition-transform hover:translate-x-0.5"
            style={{
              borderColor: active && activeIndex === index ? lineColor(track) : "var(--line)",
              backgroundColor: active && activeIndex === index ? activeBg(track) : "var(--paper-dark)",
            }}
          >
            <CircleDot className="h-3.5 w-3.5" style={{ color: step.source === "blunder" ? "var(--ink)" : lineColor(track) }} />
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold">{step.label}</span>
              <span className="block truncate text-xs" style={{ color: "var(--ink-soft)" }}>{step.moveUci ?? "position"} · {formatCp(step.evalCp)}</span>
            </span>
            {step.stable ? <CheckCircle2 className="h-4 w-4" style={{ color: "#2d5016" }} /> : null}
          </button>
        ))}
      </div>
    </div>
  );
}

function ComparisonPanel({ mistake }: { mistake: MistakeAnalysisItem }) {
  return (
    <div className="rounded-md border p-4" style={{ borderColor: "var(--line)", backgroundColor: "var(--paper)" }}>
      <h2 className="text-base font-semibold" style={{ fontFamily: "var(--font-display)" }}>Punishment result</h2>
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

function LineSwitch({ active, tone, onClick, children }: { active: boolean; tone: Track; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="h-10 rounded px-4 text-sm font-semibold transition-colors"
      style={{
        backgroundColor: active ? lineColor(tone) : "var(--paper-dark)",
        color: active ? "var(--paper)" : "var(--ink)",
        border: "1px solid var(--line)",
      }}
    >
      {children}
    </button>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border px-3 py-2" style={{ borderColor: "var(--line)", backgroundColor: "rgba(244,236,216,0.72)" }}>
      <div className="text-xs uppercase tracking-wider" style={{ color: "var(--ink-faint)" }}>{label}</div>
      <div className="mt-1 font-semibold">{value}</div>
    </div>
  );
}

function Badge({ children, tone }: { children: ReactNode; tone: "red" | "amber" | "green" | "ink" }) {
  const styles = {
    red: { backgroundColor: "color-mix(in srgb, var(--accent) 13%, var(--paper))", color: "var(--accent)", borderColor: "color-mix(in srgb, var(--accent) 36%, var(--paper))" },
    amber: { backgroundColor: "color-mix(in srgb, #8b6914 15%, var(--paper))", color: "#8b6914", borderColor: "#c4aa60" },
    green: { backgroundColor: "color-mix(in srgb, #2d5016 13%, var(--paper))", color: "#2d5016", borderColor: "#8ab578" },
    ink: { backgroundColor: "var(--paper-dark)", color: "var(--ink)", borderColor: "var(--line)" },
  }[tone];
  return <span className="inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold" style={styles}>{children}</span>;
}

function moveArrow(uci: string | null, track: Track): BoardArrow | null {
  if (!uci || uci.length < 4) return null;
  return {
    startSquare: uci.slice(0, 2),
    endSquare: uci.slice(2, 4),
    color: track === "engine" ? "rgba(45, 80, 22, 0.78)" : "rgba(124, 58, 45, 0.78)",
  };
}

function lineColor(track: Track) {
  return track === "engine" ? "#2d5016" : "var(--accent)";
}

function activeBg(track: Track) {
  return track === "engine"
    ? "color-mix(in srgb, #2d5016 11%, var(--paper))"
    : "color-mix(in srgb, var(--accent) 11%, var(--paper))";
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

function formatCp(value: number | null) {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${Math.round(value)} cp`;
}

function formatPercent(value: number | null | undefined, digits = 0) {
  if (value == null) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}
