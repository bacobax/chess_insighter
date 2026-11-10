import { useMemo, useState } from "react";
import { CheckCircle2, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Lightbulb, Loader2, RotateCcw, XCircle } from "lucide-react";
import { Chess } from "chess.js";
import { Button } from "~/components/ui/button";
import { reviewTrainingCard } from "~/lib/api";
import type { TrainingCard, TrainingCardReviewRequest } from "~/lib/types";
import { ARROW_BEST, ARROW_HINT, ARROW_PLAYED, TrainingBoard, replayLine, type BoardArrow } from "./training-board";
import { formatShortDate, moveLabel, percent } from "./training-format";
import { useLineTrainer, useShortcuts } from "./training-hooks";

const PROCESS_OPTIONS = ["missed_threat", "missed_opportunity", "miscalculation", "evaluation", "hope_chess", "technique", "time_trouble"];
const GRADES: { grade: TrainingCardReviewRequest["grade"]; label: string; key: string; detail: string }[] = [
  { grade: "again", label: "Missed it", key: "1", detail: "back tomorrow" },
  { grade: "hard", label: "Found it slowly", key: "2", detail: "same interval" },
  { grade: "good", label: "Found it", key: "3", detail: "longer interval" },
];

type Exercise = {
  kind: "threat" | "move" | "calculation";
  prompt: string;
  instruction: string;
  startFen: string;
  moves: string[];
  userSide: "white" | "black" | "both";
};

function afterPlayed(card: TrainingCard): string {
  try {
    const chess = new Chess(card.fen_before);
    chess.move({ from: card.played_uci.slice(0, 2), to: card.played_uci.slice(2, 4), promotion: card.played_uci[4] ?? "q" });
    return chess.fen();
  } catch {
    return card.fen_before;
  }
}

function exerciseFor(card: TrainingCard, calculation: boolean): Exercise {
  const played = moveLabel(card, card.played_san);
  const opponent = card.player_color === "white" ? "black" : "white";
  const fenAfter = afterPlayed(card);
  if (calculation && card.refutation_san.length > 1) {
    return {
      kind: "calculation",
      prompt: `You played ${played}. Calculate how it gets punished.`,
      instruction: `Play the whole line on the board, both sides, ${card.refutation_san.length} moves deep.`,
      startFen: fenAfter,
      moves: card.refutation_san,
      userSide: "both",
    };
  }
  if ((card.process === "missed_threat" || card.process === "hope_chess" || !card.best_san) && card.refutation_san.length) {
    return {
      kind: "threat",
      prompt: `You played ${played}. What was your opponent's best reply?`,
      instruction: `You play ${opponent}'s moves; your replies are played for you.`,
      startFen: fenAfter,
      moves: card.refutation_san,
      userSide: opponent,
    };
  }
  return {
    kind: "move",
    prompt: `You played ${played} here. Find a better move.`,
    instruction: "Play your move on the board: drag a piece, or click it and then its target square.",
    startFen: card.fen_before,
    moves: card.best_san ? [card.best_san] : [],
    userSide: card.player_color,
  };
}

type Result = { card: TrainingCard; grade: TrainingCardReviewRequest["grade"] };

export function CardExercise({
  username,
  queue,
  calculation = false,
  title,
  onReviewed,
  onExit,
  onClose,
}: {
  username: string;
  queue: TrainingCard[];
  calculation?: boolean;
  title?: string;
  onReviewed: (card: TrainingCard) => void;
  /** Called from the end-of-block summary. */
  onExit?: () => void;
  /** Leave before the end; omit to hide the Close button. */
  onClose?: () => void;
}) {
  const [items, setItems] = useState(queue);
  const [index, setIndex] = useState(0);
  const [results, setResults] = useState<Result[]>([]);
  const card = items[index];

  if (!card) {
    return (
      <SessionSummary
        results={results}
        onRetry={(missed) => { setItems(missed); setIndex(0); setResults([]); }}
        onExit={onExit}
      />
    );
  }

  return (
    <div style={{ display: "grid", gap: "1.25rem" }}>
      <div className="tp-exercise-top">
        <div>
          <p className="folio">{title ?? "Your own errors"}</p>
          <span className="tp-label">Position {index + 1} of {items.length}</span>
        </div>
        <div className="tp-ptrack" style={{ flex: "1 1 160px", maxWidth: 320 }} role="progressbar" aria-valuemin={0} aria-valuemax={items.length} aria-valuenow={index}>
          <div style={{ width: `${(index / items.length) * 100}%` }} />
        </div>
        {onClose ? <Button size="sm" variant="ghost" onClick={onClose}>Close</Button> : null}
      </div>
      <CardPuzzle
        key={card.card_id + index}
        username={username}
        card={card}
        calculation={calculation}
        onGraded={(updated, grade) => {
          onReviewed(updated);
          setResults((current) => [...current, { card: updated, grade }]);
          setIndex((current) => current + 1);
        }}
        onSkip={() => setIndex((current) => current + 1)}
      />
    </div>
  );
}

function CardPuzzle({
  username,
  card,
  calculation,
  onGraded,
  onSkip,
}: {
  username: string;
  card: TrainingCard;
  calculation: boolean;
  onGraded: (card: TrainingCard, grade: TrainingCardReviewRequest["grade"]) => void;
  onSkip: () => void;
}) {
  const exercise = useMemo(() => exerciseFor(card, calculation), [card, calculation]);
  const trainer = useLineTrainer(exercise.startFen, exercise.moves, exercise.userSide);
  const [revealed, setRevealed] = useState(false);
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const solved = trainer.done && !revealed;
  const showAnswer = trainer.done || revealed;
  const suggested: TrainingCardReviewRequest["grade"] = revealed ? "again" : trainer.mistakes === 0 && trainer.hints === 0 ? "good" : "hard";

  async function grade(value: TrainingCardReviewRequest["grade"]) {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      // Only send what changed, so an empty note keeps an earlier one and an untouched cause keeps an earlier label.
      const updated = await reviewTrainingCard(username, card.card_id, {
        grade: value,
        ...(label ? { label } : {}),
        ...(note.trim() ? { note } : {}),
      });
      onGraded(updated, value);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save your answer.");
      setSaving(false);
    }
  }

  function reveal() {
    setRevealed(true);
    trainer.finish();
  }

  useShortcuts({
    h: trainer.hint,
    Space: () => { if (!showAnswer) reveal(); },
    Enter: () => { if (showAnswer) void grade(suggested); },
    "1": () => { if (showAnswer) void grade("again"); },
    "2": () => { if (showAnswer) void grade("hard"); },
    "3": () => { if (showAnswer) void grade("good"); },
  });

  const arrows: BoardArrow[] = [];
  if (trainer.hintSquare && trainer.userTurn) {
    const target = replayLine(trainer.fen, [exercise.moves[trainer.index]]).uci[0];
    if (target) arrows.push({ startSquare: target.slice(0, 2), endSquare: target.slice(2, 4), color: ARROW_HINT });
  }
  const lastMoveStyles = trainer.lastMove
    ? { [trainer.lastMove.from]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.22)" }, [trainer.lastMove.to]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.32)" } }
    : undefined;
  const hintStyles = trainer.hintSquare ? { [trainer.hintSquare]: { boxShadow: "inset 0 0 0 4px #dcff42" } } : {};

  return (
    <div className="tp-exercise">
      <div>
        {showAnswer ? (
          <AnswerStepper card={card} />
        ) : (
          <TrainingBoard
            fen={trainer.fen}
            orientation={card.player_color}
            movable={trainer.userTurn}
            onMove={trainer.onMove}
            arrows={arrows}
            squareStyles={{ ...lastMoveStyles, ...hintStyles }}
            wrongSquare={trainer.wrongSquare}
            label={`Training position, you play ${exercise.userSide === "both" ? "both sides" : exercise.userSide}`}
          />
        )}
        <div className="tp-actions" style={{ justifyContent: "space-between", marginTop: ".75rem", color: "var(--ink-soft)", fontFamily: "var(--font-mono)", fontSize: ".66rem" }}>
          <span>{card.opponent ? `vs ${card.opponent} · ` : ""}you were {card.player_color}</span>
          <span>{card.severity} · lost {percent(card.wp_loss)}</span>
        </div>
      </div>

      <div style={{ display: "grid", gap: "1.1rem", alignContent: "start" }}>
        <div>
          <p className="folio">{exercise.kind === "threat" ? "Find the threat" : exercise.kind === "calculation" ? "Calculate the line" : "Find the move"}{card.motifs.length ? ` · ${card.motifs.join(", ").toLowerCase()}` : ""}</p>
          <h2>{exercise.prompt}</h2>
          {!showAnswer ? <p className="tp-note" style={{ marginTop: ".5rem" }}>{exercise.instruction}</p> : null}
        </div>

        {!showAnswer ? (
          <>
            <div className="tp-trainer-status" aria-live="polite">
              <span>{trainer.userTurn ? "Your move" : "…"}</span>
              <span>{trainer.index} / {trainer.total} moves</span>
              <span className={trainer.mistakes ? "tp-neg" : ""}>{trainer.mistakes} wrong</span>
              <span>{trainer.hints} hints</span>
            </div>
            {trainer.playedSan.length ? <div className="tp-line">{trainer.playedSan.join(" ")}</div> : null}
            <div className="tp-actions">
              <Button variant="outline" onClick={trainer.hint} disabled={!trainer.userTurn}><Lightbulb className="h-4 w-4" /> Hint <kbd>H</kbd></Button>
              <Button variant="ghost" onClick={reveal}>Show the answer <kbd>Space</kbd></Button>
              <Button variant="ghost" onClick={onSkip}>Skip</Button>
            </div>
          </>
        ) : (
          <>
            <div className={`tp-verdict ${solved && trainer.mistakes === 0 && trainer.hints === 0 ? "is-good" : solved ? "is-ok" : "is-bad"}`}>
              {solved ? <CheckCircle2 className="h-5 w-5" /> : <XCircle className="h-5 w-5" />}
              <span>
                {solved
                  ? trainer.mistakes === 0 && trainer.hints === 0 ? "Solved on the first try." : `Solved with ${trainer.mistakes} wrong ${trainer.mistakes === 1 ? "try" : "tries"} and ${trainer.hints} ${trainer.hints === 1 ? "hint" : "hints"}.`
                  : "Here is the answer. Step through it on the board."}
              </span>
            </div>
            <div className="tp-move-cmp">
              <div><span className="tp-label">You played</span><b className="tp-neg">{moveLabel(card, card.played_san)}</b></div>
              <div><span className="tp-label">Better</span><b className="tp-pos">{moveLabel(card, card.best_san)}</b></div>
            </div>
            <div className="tp-input">
              <label htmlFor="tp-label">Cause</label>
              <select id="tp-label" value={label || card.label || card.process} onChange={(event) => setLabel(event.target.value)}>
                {PROCESS_OPTIONS.map((option) => <option key={option} value={option}>{option.replace(/_/g, " ")}{option === card.process ? " (suggested)" : ""}</option>)}
              </select>
            </div>
            <div className="tp-input">
              <label htmlFor="tp-note">Why it went wrong (optional)</label>
              <textarea id="tp-note" placeholder={card.note ?? "One sentence for your error log"} value={note} onChange={(event) => setNote(event.target.value)} />
            </div>
            <div>
              <p className="tp-label" style={{ margin: "0 0 .5rem" }}>How did it go? <span style={{ textTransform: "none", letterSpacing: 0 }}>Enter picks the suggested grade</span></p>
              <div className="tp-grades">
                {GRADES.map((item) => (
                  <button key={item.grade} type="button" className="tp-grade" data-suggested={item.grade === suggested} disabled={saving} onClick={() => void grade(item.grade)}>
                    <b>{item.label}</b>
                    <small>{item.detail}</small>
                    <kbd>{item.key}</kbd>
                  </button>
                ))}
              </div>
              {saving ? <p className="tp-note"><Loader2 className="inline h-3 w-3 animate-spin" /> Saving…</p> : null}
            </div>
            {error ? <p className="form-error">{error}</p> : null}
          </>
        )}
      </div>
    </div>
  );
}

/** The game position, your move, then the engine's punishment line, one step at a time. */
function AnswerStepper({ card }: { card: TrainingCard }) {
  const line = useMemo(() => replayLine(card.fen_before, [card.played_uci, ...card.refutation_san]), [card]);
  const [step, setStep] = useState(0);
  const last = line.fens.length - 1;
  const go = (value: number) => setStep(Math.max(0, Math.min(last, value)));
  useShortcuts({ ArrowLeft: () => go(step - 1), ArrowRight: () => go(step + 1), Home: () => go(0), End: () => go(last) });

  const arrows: BoardArrow[] = [];
  if (step === 0) {
    arrows.push({ startSquare: card.played_uci.slice(0, 2), endSquare: card.played_uci.slice(2, 4), color: ARROW_PLAYED });
    if (card.best_uci) arrows.push({ startSquare: card.best_uci.slice(0, 2), endSquare: card.best_uci.slice(2, 4), color: ARROW_BEST });
  } else if (step < last) {
    const next = line.uci[step];
    arrows.push({ startSquare: next.slice(0, 2), endSquare: next.slice(2, 4), color: ARROW_HINT });
  }
  const moved = step > 0 ? line.uci[step - 1] : null;
  const squareStyles = moved ? { [moved.slice(0, 2)]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.22)" }, [moved.slice(2, 4)]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.32)" } } : undefined;

  return (
    <div style={{ display: "grid", gap: ".75rem" }}>
      <TrainingBoard fen={line.fens[step]} orientation={card.player_color} arrows={arrows} squareStyles={squareStyles} label="Answer line" />
      <div className="tp-stepper">
        <button type="button" onClick={() => go(0)} aria-label="Start"><ChevronsLeft /></button>
        <button type="button" onClick={() => go(step - 1)} aria-label="Previous move"><ChevronLeft /></button>
        <ol aria-label="Answer line">
          <li><button type="button" aria-current={step === 0} onClick={() => go(0)}>Start</button></li>
          {line.san.map((san, i) => (
            <li key={i}>
              <button type="button" aria-current={step === i + 1} className={i === 0 ? "tp-neg" : ""} onClick={() => go(i + 1)}>{san}</button>
            </li>
          ))}
        </ol>
        <button type="button" onClick={() => go(step + 1)} aria-label="Next move"><ChevronRight /></button>
        <button type="button" onClick={() => go(last)} aria-label="End"><ChevronsRight /></button>
      </div>
      <p className="tp-note" style={{ margin: 0 }}>Red: your move. Green: the better move. Yellow: the next move in the line. Use ← and →.</p>
    </div>
  );
}

function SessionSummary({ results, onRetry, onExit }: { results: Result[]; onRetry: (missed: TrainingCard[]) => void; onExit?: () => void }) {
  const counts = { again: 0, hard: 0, good: 0 };
  for (const result of results) counts[result.grade] += 1;
  const missed = results.filter((result) => result.grade === "again").map((result) => result.card);
  if (!results.length) {
    return <div className="tp-empty"><p className="folio">Nothing reviewed</p><p>You skipped every position. They stay due.</p>{onExit ? <Button size="sm" variant="outline" onClick={onExit}>Close</Button> : null}</div>;
  }
  return (
    <div style={{ display: "grid", gap: "1.25rem" }}>
      <div>
        <p className="folio">Block done</p>
        <h2 style={{ margin: ".5rem 0 0", fontFamily: "var(--font-display)", fontSize: "2.2rem", fontWeight: 400, letterSpacing: "-.03em" }}>
          {counts.good} of {results.length} found cleanly.
        </h2>
      </div>
      <div className="tp-summary-stats">
        <div><b className="tp-pos">{counts.good}</b><span>Found it</span></div>
        <div><b>{counts.hard}</b><span>Found it slowly</span></div>
        <div><b className="tp-neg">{counts.again}</b><span>Missed it</span></div>
      </div>
      <ul className="tp-summary-list">
        {results.map(({ card, grade }) => (
          <li key={card.card_id}>
            <span className={grade === "again" ? "tp-neg" : grade === "good" ? "tp-pos" : ""}>{moveLabel(card, card.played_san)}</span>
            <span>{card.process.replace(/_/g, " ")}</span>
            <span>{card.retired ? "Retired" : `Next: ${formatShortDate(card.due_on)}`}</span>
          </li>
        ))}
      </ul>
      <div className="tp-actions">
        {missed.length ? <Button onClick={() => onRetry(missed)}><RotateCcw className="h-4 w-4" /> Try the {missed.length} missed again</Button> : null}
        {onExit ? <Button variant="outline" onClick={onExit}>Done</Button> : null}
      </div>
    </div>
  );
}
