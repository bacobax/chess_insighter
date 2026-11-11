import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Loader2 } from "lucide-react";
import { Button } from "~/components/ui/button";
import { TrainingBoard, replayLine, type BoardArrow, type PlayedMove } from "~/components/training/training-board";
import { fetchOpeningStudyChildren } from "~/lib/api";
import { cn } from "~/lib/utils";
import type { OpeningStudyTreeNode } from "~/lib/types";
import type { StudyControlsState } from "./OpeningStudyControls";
import { studyRequestBase } from "./study-request";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

type Level =
  | { status: "loading" }
  | { status: "ready"; children: OpeningStudyTreeNode[] }
  | { status: "error"; message: string };

function prefixKey(prefix: string[]): string {
  return prefix.join("/");
}

// Arrow colours encode whose move it is and the rank: the best candidate is
// the most opaque, lower ranks fade out. Your moves are green, the opponent's
// coral, matching the rest of the app's boards.
const OWN_RGB = "33,231,131";
const OPPONENT_RGB = "255,106,77";

function rankAlpha(index: number, count: number): number {
  if (count <= 1) return 0.95;
  return 0.95 - (0.6 * index) / (count - 1);
}

function arrowColor(own: boolean, index: number, count: number, hovered: number | null): string {
  const rgb = own ? OWN_RGB : OPPONENT_RGB;
  if (hovered !== null) return `rgba(${rgb},${hovered === index ? 1 : 0.14})`;
  return `rgba(${rgb},${rankAlpha(index, count).toFixed(2)})`;
}

function sameMove(uci: string, candidate: string): boolean {
  // The board promotes to a queen by default; match the catalogue either way.
  return uci === candidate || uci.slice(0, 4) === candidate.slice(0, 4);
}

function moveNumberLabel(ply: number): string {
  return ply % 2 === 0 ? `${ply / 2 + 1}.` : `${Math.floor(ply / 2) + 1}…`;
}

type Props = {
  controls: StudyControlsState;
  generationKey: number;
  active: boolean;
  /** Bumping `nonce` moves the board to `path` (e.g. the node selected in the tree view). */
  jump: { path: string[]; nonce: number };
  onNodeSelect?: (node: OpeningStudyTreeNode | null) => void;
};

export function OpeningStudyBoardView({ controls, generationKey, active, jump, onNodeSelect }: Props) {
  const [line, setLine] = useState<string[]>([]);
  const [ply, setPly] = useState(0);
  const [levels, setLevels] = useState<Record<string, Level>>({});
  const [hovered, setHovered] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const requested = useRef(new Set<string>());
  const controlsRef = useRef(controls);
  controlsRef.current = controls;

  // A new generation (Generate / setup / reset) invalidates every cached level.
  // Settings only apply on Generate, mirroring the tree view.
  useEffect(() => {
    requested.current = new Set();
    setLevels({});
    setHovered(null);
    setNotice(null);
  }, [generationKey]);

  // Jump to the position picked in the tree view.
  useEffect(() => {
    if (jump.nonce === 0) return;
    setLine(jump.path);
    setPly(jump.path.length);
    setNotice(null);
  }, [jump]);

  const prefix = useMemo(() => line.slice(0, ply), [line, ply]);
  const parentPrefix = useMemo(() => line.slice(0, Math.max(0, ply - 1)), [line, ply]);
  const replay = useMemo(() => replayLine(START_FEN, prefix), [prefix]);
  const fen = replay.fens[replay.fens.length - 1] ?? START_FEN;
  const sideToMove: "white" | "black" = fen.split(" ")[1] === "b" ? "black" : "white";
  const ownTurn = sideToMove === controls.targetColor;
  const fullReplay = useMemo(() => replayLine(START_FEN, line), [line]);

  const load = useCallback(
    (target: string[]) => {
      const key = prefixKey(target);
      if (generationKey === 0 || requested.current.has(key)) return;
      requested.current.add(key);
      setLevels((prev) => ({ ...prev, [key]: { status: "loading" } }));
      fetchOpeningStudyChildren({ ...studyRequestBase(controlsRef.current), prefixUci: target })
        .then((response) => {
          setLevels((prev) => ({ ...prev, [key]: { status: "ready", children: response.children } }));
        })
        .catch((err: unknown) => {
          requested.current.delete(key);
          setLevels((prev) => ({
            ...prev,
            [key]: { status: "error", message: err instanceof Error ? err.message : "Could not load moves." },
          }));
        });
    },
    [generationKey],
  );

  // Load the current position's candidates, plus its parent level so the
  // node that led here (scores, openings) can be shown in the inspector.
  useEffect(() => {
    if (!active) return;
    load(prefix);
    if (ply > 0) load(parentPrefix);
  }, [active, load, parentPrefix, prefix, ply]);

  const level = levels[prefixKey(prefix)];
  const candidates = level?.status === "ready" ? level.children : [];
  const parentLevel = ply > 0 ? levels[prefixKey(parentPrefix)] : undefined;
  const currentNode = useMemo(() => {
    if (ply === 0 || parentLevel?.status !== "ready") return null;
    const uci = line[ply - 1];
    return parentLevel.children.find((node) => sameMove(uci, node.moveUci)) ?? null;
  }, [line, parentLevel, ply]);
  const offTree = ply > 0 && parentLevel?.status === "ready" && currentNode === null;

  useEffect(() => {
    if (active) onNodeSelect?.(currentNode);
  }, [active, currentNode, onNodeSelect]);

  useEffect(() => setHovered(null), [prefix]);

  const play = useCallback(
    (uci: string) => {
      setNotice(null);
      setLine((prev) => {
        if (prev[ply] && sameMove(uci, prev[ply])) return prev;
        return [...prev.slice(0, ply), uci];
      });
      setPly((current) => current + 1);
    },
    [ply],
  );

  function onBoardMove(move: PlayedMove): boolean {
    const match = candidates.find((node) => sameMove(move.uci, node.moveUci));
    if (!match && level?.status === "ready") {
      setNotice(`${move.san} isn't among the suggested moves here. Exploring it anyway.`);
      setLine((prev) => [...prev.slice(0, ply), move.uci]);
      setPly((current) => current + 1);
      return true;
    }
    play(match?.moveUci ?? move.uci);
    return true;
  }

  const goTo = useCallback((target: number) => {
    setNotice(null);
    setPly(Math.max(0, Math.min(target, line.length)));
  }, [line.length]);

  useEffect(() => {
    if (!active) return;
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && (target.closest("input, textarea, select, [role='treeitem'], [role='dialog']"))) return;
      if (event.key === "ArrowLeft") { event.preventDefault(); goTo(ply - 1); }
      else if (event.key === "ArrowRight") { event.preventDefault(); goTo(ply + 1); }
      else if (event.key === "Home") { event.preventDefault(); goTo(0); }
      else if (event.key === "End") { event.preventDefault(); goTo(line.length); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, goTo, line.length, ply]);

  const arrows: BoardArrow[] = useMemo(() => {
    // Draw the lowest rank first so the best arrow sits on top.
    return candidates
      .map((node, index) => ({
        startSquare: node.moveUci.slice(0, 2),
        endSquare: node.moveUci.slice(2, 4),
        color: arrowColor(ownTurn, index, candidates.length, hovered),
      }))
      .reverse();
  }, [candidates, hovered, ownTurn]);

  const lastMove = ply > 0 ? line[ply - 1] : null;
  const squareStyles = lastMove
    ? {
        [lastMove.slice(0, 2)]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.22)" },
        [lastMove.slice(2, 4)]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.32)" },
      }
    : undefined;

  const orderLabel = controls.opponentMoveOrdering === "engine" ? "strongest first" : "most played first";

  if (generationKey === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm" style={{ color: "var(--ink-soft)" }}>
        Press “Generate suggestions” to load the opening tree on the board.
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-6 overflow-y-auto p-4 lg:flex-row lg:items-start lg:p-6">
      <div className="mx-auto w-full max-w-[min(640px,calc(100vh-10rem))] shrink-0 lg:mx-0 lg:flex-1">
        <TrainingBoard
          className="w-full"
          fen={fen}
          orientation={controls.targetColor}
          movable
          onMove={onBoardMove}
          arrows={arrows}
          squareStyles={squareStyles}
          label={`Opening board, ${sideToMove} to move`}
        />
        <div className="mt-3 flex items-center justify-center gap-1" role="toolbar" aria-label="Move navigation">
          <Button variant="ghost" size="sm" onClick={() => goTo(0)} disabled={ply === 0} aria-label="Start position"><ChevronsLeft className="h-4 w-4" /></Button>
          <Button variant="ghost" size="sm" onClick={() => goTo(ply - 1)} disabled={ply === 0} aria-label="Previous move"><ChevronLeft className="h-4 w-4" /></Button>
          <Button variant="ghost" size="sm" onClick={() => goTo(ply + 1)} disabled={ply >= line.length} aria-label="Next move"><ChevronRight className="h-4 w-4" /></Button>
          <Button variant="ghost" size="sm" onClick={() => goTo(line.length)} disabled={ply >= line.length} aria-label="Last move"><ChevronsRight className="h-4 w-4" /></Button>
        </div>
      </div>

      <section className="flex w-full min-w-0 flex-col gap-4 lg:max-w-sm" aria-live="polite">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[.14em]" style={{ color: ownTurn ? "var(--accent)" : "var(--coral)" }}>
            {ownTurn ? `Your move · ${controls.targetColor}` : `Opponent to move · ${sideToMove}`}
          </p>
          <h2 className="mt-1 text-lg font-bold leading-tight tracking-[-.02em]" style={{ fontFamily: "var(--font-display)" }}>
            {currentNode?.openingNames[0] ?? (ply === 0 ? "Starting position" : offTree ? "Off the suggested tree" : "…")}
          </h2>
          <ol className="mt-2 flex flex-wrap gap-x-1.5 gap-y-1 text-sm" aria-label="Moves played">
            {fullReplay.san.map((san, index) => (
              <li key={`${index}-${san}`}>
                <button
                  type="button"
                  onClick={() => goTo(index + 1)}
                  className={cn("rounded px-1 tabular-nums", index + 1 === ply ? "font-semibold" : "opacity-70 hover:opacity-100")}
                  style={index + 1 === ply ? { background: "var(--glow)", color: "var(--ink)" } : { color: "var(--ink-soft)" }}
                  aria-current={index + 1 === ply ? "step" : undefined}
                >
                  {index % 2 === 0 || index === 0 ? <span style={{ color: "var(--ink-faint)" }}>{moveNumberLabel(index)}</span> : null}
                  {san}
                </button>
              </li>
            ))}
            {fullReplay.san.length === 0 ? <li style={{ color: "var(--ink-faint)" }}>Drag a piece or pick a move below.</li> : null}
          </ol>
          {notice ? <p className="mt-2 text-xs" style={{ color: "var(--acid)" }}>{notice}</p> : null}
        </div>

        <div>
          <div className="mb-2 flex items-baseline justify-between gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-[.12em]" style={{ color: "var(--ink-soft)" }}>
              {ownTurn ? "Your candidate moves" : "Opponent replies"}
            </h3>
            <span className="text-[10px]" style={{ color: "var(--ink-faint)" }}>
              {ownTurn ? "ranked by study score" : orderLabel}
            </span>
          </div>

          {level?.status === "loading" || !level ? (
            <p className="flex items-center gap-2 text-sm" style={{ color: "var(--ink-soft)" }}>
              <Loader2 className="h-4 w-4 animate-spin" /> Loading moves…
            </p>
          ) : level.status === "error" ? (
            <p className="text-sm" style={{ color: "var(--coral)" }}>{level.message}</p>
          ) : candidates.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--ink-soft)" }}>
              No catalogued continuations from this position. Step back or try another move.
            </p>
          ) : (
            <ol className="flex flex-col gap-1.5" onMouseLeave={() => setHovered(null)}>
              {candidates.map((node, index) => (
                <li key={node.moveUci}>
                  <button
                    type="button"
                    onClick={() => play(node.moveUci)}
                    onMouseEnter={() => setHovered(index)}
                    onFocus={() => setHovered(index)}
                    onBlur={() => setHovered(null)}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors focus-visible:outline-2 focus-visible:outline-[var(--accent)]"
                    style={{
                      border: "1px solid var(--line)",
                      background: hovered === index ? "var(--paper-raised)" : "var(--paper)",
                    }}
                  >
                    <span
                      className="h-2.5 w-6 shrink-0 rounded-full"
                      style={{ background: arrowColor(ownTurn, index, candidates.length, null) }}
                      aria-hidden="true"
                    />
                    <span className="w-5 shrink-0 text-xs tabular-nums" style={{ color: "var(--ink-faint)" }}>{index + 1}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold">{node.moveSan}</span>
                      <span className="block truncate text-[11px]" style={{ color: "var(--ink-soft)" }}>
                        {node.openingNames[0] ?? `${node.compatibleLineCount} lines`}
                      </span>
                    </span>
                    <span className="shrink-0 text-right text-[11px] tabular-nums" style={{ color: "var(--ink-soft)" }}>
                      {ownTurn
                        ? <>score <b style={{ color: "var(--ink)" }}>{Math.round(node.studyScore * 100)}</b></>
                        : <>{(node.popularityScore * 100).toFixed(1)}% played</>}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </div>

        <p className="text-[11px] leading-relaxed" style={{ color: "var(--ink-faint)" }}>
          <span style={{ color: "var(--accent)" }}>Green arrows</span> are your moves,{" "}
          <span style={{ color: "var(--coral)" }}>coral arrows</span> the opponent's. Brighter means higher ranked.
          Drag a piece or click a move to step in; use ← and → to move through the line.
        </p>
      </section>
    </div>
  );
}
