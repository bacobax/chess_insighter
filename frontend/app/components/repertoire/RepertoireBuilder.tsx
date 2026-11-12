import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Loader2, Trash2 } from "lucide-react";
import { Button } from "~/components/ui/button";
import { TrainingBoard, replayLine, sideToMove, type BoardArrow, type PlayedMove } from "~/components/training/training-board";
import { studyRequestBase } from "~/components/opening-study/study-request";
import type { StudyControlsState } from "~/components/opening-study/OpeningStudyControls";
import { fetchOpeningStudyChildren } from "~/lib/api";
import { cn } from "~/lib/utils";
import type { OpeningStudyTreeNode, RepertoireColor, RepertoireMove } from "~/lib/types";
import { START_FEN, formatCp, formatPercent, useRepertoirePosition, type RepertoireApi } from "./repertoire-hooks";

const OWN_RGB = "33,231,131";
const OPPONENT_RGB = "255,106,77";

function sameMove(a: string, b: string): boolean {
  return a === b || a.slice(0, 4) === b.slice(0, 4);
}

/** Lab study scores for this position's moves, when the position is a catalogued one. */
function useLabScores(color: RepertoireColor, labPrefixUci: string[] | null, controls: StudyControlsState | undefined, enabled: boolean) {
  const [scores, setScores] = useState<Record<string, Record<string, OpeningStudyTreeNode>>>({});
  const key = labPrefixUci ? labPrefixUci.join(" ") : null;
  useEffect(() => {
    if (!enabled || !controls || key === null || scores[key]) return;
    let cancelled = false;
    fetchOpeningStudyChildren({ ...studyRequestBase(controls), targetColor: color, prefixUci: labPrefixUci ?? [] })
      .then((response) => {
        if (cancelled) return;
        // Matched by move, not path: for a transposition the Lab answers with its own move order.
        const byMove = Object.fromEntries(response.children.map((node) => [node.moveUci.slice(0, 4), node]));
        setScores((current) => ({ ...current, [key]: byMove }));
      })
      .catch(() => {
        // Lab scores are extra information; the repertoire works without them.
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled, controls, color]);
  return key !== null ? scores[key] ?? null : null;
}

type Props = {
  color: RepertoireColor;
  api: RepertoireApi;
  /** Moves before the part being built (e.g. 1.e4 for "Black vs 1.e4"); the board never goes before them. */
  startPrefixUci: string[];
  /** Opening Lab controls: when given, catalogued positions show Lab study scores. */
  studyControls?: StudyControlsState;
  /** Bumping `nonce` moves the board to `path`. */
  jump: { path: string[]; nonce: number };
  active: boolean;
};

/** Walk the board and pick your move at each of your turns, among the moves the engine accepts. */
export function RepertoireBuilder({ color, api, startPrefixUci, studyControls, jump, active }: Props) {
  const [line, setLine] = useState<string[]>(startPrefixUci);
  const [ply, setPly] = useState(startPrefixUci.length);
  const [hovered, setHovered] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const minPly = startPrefixUci.length;

  useEffect(() => {
    if (jump.nonce === 0) return;
    setLine(jump.path);
    setPly(jump.path.length);
  }, [jump]);

  const prefix = useMemo(() => line.slice(0, ply), [line, ply]);
  const replay = useMemo(() => replayLine(START_FEN, prefix), [prefix]);
  const fullReplay = useMemo(() => replayLine(START_FEN, line), [line]);
  const fen = replay.fens[replay.fens.length - 1] ?? START_FEN;
  const ownTurn = sideToMove(fen) === color;
  const settings = api.repertoire?.settings;
  const settingsKey = settings ? `${settings.cpTolerance}|${settings.minEvalCp}` : "default";
  const position = useRepertoirePosition(color, prefix, settingsKey, active);
  const data = position.data;
  const choice = data && api.repertoire ? api.repertoire.choices[data.epd] ?? null : null;
  const labScores = useLabScores(color, data?.ownTurn ? data.labPrefixUci : null, studyControls, active);

  useEffect(() => { setSaveError(null); setHovered(null); }, [prefix]);

  const play = useCallback((uci: string) => {
    setLine((current) => (current[ply] && sameMove(current[ply], uci) ? current : [...current.slice(0, ply), uci]));
    setPly((current) => current + 1);
  }, [ply]);

  const goTo = useCallback((target: number) => {
    setPly(Math.max(minPly, Math.min(target, line.length)));
  }, [line.length, minPly]);

  useEffect(() => {
    if (!active) return;
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && target.closest("input, textarea, select, [role='dialog']")) return;
      if (event.key === "ArrowLeft") { event.preventDefault(); goTo(ply - 1); }
      else if (event.key === "ArrowRight") { event.preventDefault(); goTo(ply + 1); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, goTo, ply]);

  async function choose(move: RepertoireMove) {
    setSaving(move.uci);
    setSaveError(null);
    try {
      await api.setChoice(prefix, move.uci);
      play(move.uci);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not save this move.");
    } finally {
      setSaving(null);
    }
  }

  async function removeChoice() {
    setSaveError(null);
    try {
      await api.removeChoice(prefix);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not remove this move.");
    }
  }

  const moves = data?.moves ?? [];
  const arrows: BoardArrow[] = useMemo(() => {
    const list: BoardArrow[] = [];
    for (const move of moves) {
      const mine = choice && sameMove(choice.uci, move.uci);
      if (ownTurn && !mine && move.playable !== true) continue;
      const alpha = hovered ? (hovered === move.uci ? 1 : 0.12) : ownTurn ? (mine ? 0.95 : 0.3) : Math.min(0.95, 0.25 + move.share);
      list.push({ startSquare: move.uci.slice(0, 2), endSquare: move.uci.slice(2, 4), color: `rgba(${ownTurn ? OWN_RGB : OPPONENT_RGB},${alpha})` });
    }
    return list.reverse();
  }, [moves, choice, ownTurn, hovered]);

  const lastMove = ply > 0 ? line[ply - 1] : null;
  const squareStyles = lastMove
    ? { [lastMove.slice(0, 2)]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.22)" }, [lastMove.slice(2, 4)]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.32)" } }
    : undefined;

  function onBoardMove(move: PlayedMove): boolean {
    play(moves.find((item) => sameMove(item.uci, move.uci))?.uci ?? move.uci);
    return true;
  }

  const choiceMove = choice ? moves.find((move) => sameMove(move.uci, choice.uci)) : undefined;
  const choiceRejected = choice && choiceMove?.playable === false;

  return (
    <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
      <div className="mx-auto w-full max-w-[min(560px,calc(100vh-12rem))] shrink-0 lg:mx-0 lg:flex-1">
        <TrainingBoard
          className="w-full"
          animate={active}
          fen={fen}
          orientation={color}
          movable
          onMove={onBoardMove}
          arrows={arrows}
          squareStyles={squareStyles}
          label={`Repertoire board, ${sideToMove(fen)} to move`}
        />
        <div className="mt-3 flex items-center justify-center gap-1" role="toolbar" aria-label="Move navigation">
          <Button variant="ghost" size="sm" onClick={() => goTo(minPly)} disabled={ply <= minPly} aria-label="First position"><ChevronsLeft className="h-4 w-4" /></Button>
          <Button variant="ghost" size="sm" onClick={() => goTo(ply - 1)} disabled={ply <= minPly} aria-label="Previous move"><ChevronLeft className="h-4 w-4" /></Button>
          <Button variant="ghost" size="sm" onClick={() => goTo(ply + 1)} disabled={ply >= line.length} aria-label="Next move"><ChevronRight className="h-4 w-4" /></Button>
          <Button variant="ghost" size="sm" onClick={() => goTo(line.length)} disabled={ply >= line.length} aria-label="Last move"><ChevronsRight className="h-4 w-4" /></Button>
        </div>
      </div>

      <section className="flex w-full min-w-0 flex-col gap-4 lg:max-w-md" aria-live="polite">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[.14em]" style={{ color: ownTurn ? "var(--accent)" : "var(--coral)" }}>
            {ownTurn ? `Your move · ${color}` : `Opponent to move · ${sideToMove(fen)}`}
          </p>
          <h2 className="mt-1 text-lg font-bold leading-tight tracking-[-.02em]" style={{ fontFamily: "var(--font-display)" }}>
            {data?.opening?.name ?? (ply === 0 ? "Starting position" : position.loading || !data ? "…" : "Unnamed position")}
          </h2>
          <ol className="mt-2 flex flex-wrap gap-x-1.5 gap-y-1 text-sm" aria-label="Moves played">
            {fullReplay.san.map((san, index) => (
              <li key={`${index}-${san}`}>
                <button
                  type="button"
                  onClick={() => goTo(index + 1)}
                  disabled={index + 1 < minPly}
                  className={cn("rounded px-1 tabular-nums", index + 1 === ply ? "font-semibold" : "opacity-70 hover:opacity-100")}
                  style={index + 1 === ply ? { background: "var(--glow)", color: "var(--ink)" } : { color: "var(--ink-soft)" }}
                  aria-current={index + 1 === ply ? "step" : undefined}
                >
                  {index % 2 === 0 ? <span style={{ color: "var(--ink-faint)" }}>{Math.floor(index / 2) + 1}.</span> : null}
                  {san}
                </button>
              </li>
            ))}
            {fullReplay.san.length === 0 ? <li style={{ color: "var(--ink-faint)" }}>Pick a move below or drag a piece.</li> : null}
          </ol>
        </div>

        {ownTurn && choice ? (
          <div className="flex items-center gap-3 rounded-lg px-3 py-2" style={{ border: `1px solid ${choiceRejected ? "var(--coral)" : "var(--accent)"}`, background: "var(--paper)" }}>
            {choiceRejected ? <AlertTriangle className="h-4 w-4 shrink-0" style={{ color: "var(--coral)" }} /> : <Check className="h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} />}
            <div className="min-w-0 flex-1 text-sm">
              <b>Your move here: {choice.san}</b>
              <span className="block text-[11px]" style={{ color: "var(--ink-soft)" }}>
                {choiceRejected
                  ? `A suggested default that loses ${choiceMove?.cpLoss ?? "?"} cp to the best move. Pick another below.`
                  : choice.source === "seed" ? "Suggested default." : "Chosen by you."}
              </span>
            </div>
            <Button size="sm" variant="ghost" onClick={removeChoice} aria-label={`Remove ${choice.san} from your repertoire`}><Trash2 className="h-4 w-4" /></Button>
          </div>
        ) : null}

        {saveError ? <p className="text-sm" style={{ color: "var(--coral)" }}>{saveError}</p> : null}
        {data?.messages.map((message) => <p key={message} className="text-xs" style={{ color: "var(--ink-soft)" }}>{message}</p>)}
        {data?.popularity.outOfBook ? (
          <p className="text-xs" style={{ color: "var(--acid)" }}>Out of book: fewer than 30 games reach this position, so your lines stop here.</p>
        ) : null}

        <div>
          <div className="mb-2 flex items-baseline justify-between gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-[.12em]" style={{ color: "var(--ink-soft)" }}>
              {ownTurn ? "Moves you can choose" : "How opponents reply"}
            </h3>
            {ownTurn && data?.settings ? (
              <span className="text-[10px]" style={{ color: "var(--ink-faint)" }}>
                allowed: ≤ {data.settings.cpTolerance} cp worse than best, eval ≥ {formatCp(data.settings.minEvalCp)}
              </span>
            ) : null}
          </div>

          {position.error ? (
            <div className="flex items-center gap-2 text-sm" style={{ color: "var(--coral)" }}>
              {position.error} <Button size="sm" variant="ghost" onClick={position.retry}>Retry</Button>
            </div>
          ) : position.loading && !moves.length ? (
            <p className="flex items-center gap-2 text-sm" style={{ color: "var(--ink-soft)" }}>
              <Loader2 className="h-4 w-4 animate-spin" />
              {ownTurn ? "Checking the moves with Stockfish. The first visit to a position can take 10 seconds or more." : "Loading how often each reply is played…"}
            </p>
          ) : moves.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--ink-soft)" }}>No data for this position.</p>
          ) : (
            <ol className="flex flex-col gap-1.5" onMouseLeave={() => setHovered(null)}>
              {moves.map((move) => {
                const mine = Boolean(choice && sameMove(choice.uci, move.uci));
                const lab = labScores?.[move.uci.slice(0, 4)];
                return (
                  <li key={move.uci}>
                    <div
                      className="flex w-full items-center gap-3 rounded-lg px-3 py-2"
                      style={{
                        border: `1px solid ${mine ? "var(--accent)" : "var(--line)"}`,
                        background: hovered === move.uci ? "var(--paper-raised)" : "var(--paper)",
                        opacity: ownTurn && move.playable === false ? 0.6 : 1,
                      }}
                      onMouseEnter={() => setHovered(move.uci)}
                    >
                      <button type="button" className="min-w-0 flex-1 text-left" onClick={() => play(move.uci)} aria-label={`Play ${move.san} on the board`}>
                        <span className="block text-sm font-semibold">{move.san}{mine ? <span className="ml-2 text-[10px] uppercase tracking-[.12em]" style={{ color: "var(--accent)" }}>your move</span> : null}</span>
                        <span className="block truncate text-[11px]" style={{ color: "var(--ink-soft)" }}>
                          {formatPercent(move.share)} of games
                          {ownTurn ? ` · eval ${formatCp(move.cp, move.mate)}` : ""}
                          {ownTurn && move.cpLoss ? ` · ${move.cpLoss} cp worse than best` : ""}
                          {ownTurn && move.cpLoss === 0 ? " · engine's best move" : ""}
                          {lab ? ` · Lab score ${Math.round(lab.studyScore * 100)}` : ""}
                        </span>
                        {move.openingName ? <span className="block truncate text-[11px]" style={{ color: "var(--ink-faint)" }}>{move.openingName}</span> : null}
                        {lab?.explanation?.summary ? <span className="mt-1 block text-[11px] leading-snug" style={{ color: "var(--ink-faint)" }}>{lab.explanation.summary}</span> : null}
                      </button>
                      {ownTurn ? (
                        move.playable === true && !mine ? (
                          <Button size="sm" variant="outline" disabled={saving !== null} onClick={() => choose(move)}>
                            {saving === move.uci ? <Loader2 className="h-4 w-4 animate-spin" /> : "Choose"}
                          </Button>
                        ) : move.playable === false ? (
                          <span className="text-[10px] uppercase tracking-[.1em]" style={{ color: "var(--coral)" }}>loses too much</span>
                        ) : move.playable === null ? (
                          <span className="text-[10px]" style={{ color: "var(--ink-faint)" }}>checking…</span>
                        ) : null
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
          {position.loading && moves.length ? (
            <p className="mt-2 flex items-center gap-2 text-[11px]" style={{ color: "var(--ink-faint)" }}><Loader2 className="h-3 w-3 animate-spin" /> Still loading the rest…</p>
          ) : null}
        </div>

        <p className="text-[11px] leading-relaxed" style={{ color: "var(--ink-faint)" }}>
          On your turns, choose one move: only moves close to the engine's best can be saved. On the opponent's turns, step into each common
          reply and choose your answer. ← and → move through the line.
        </p>
      </section>
    </div>
  );
}
