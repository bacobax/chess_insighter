import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Circle, CircleDot, Hammer, Lightbulb, Play, RotateCcw, Shuffle } from "lucide-react";
import { Button } from "~/components/ui/button";
import { ARROW_HINT, TrainingBoard, replayLine, type BoardArrow } from "~/components/training/training-board";
import { useLineTrainer, usePersistentState, useShortcuts } from "~/components/training/training-hooks";
import type { RepertoireColor, RepertoireLine } from "~/lib/types";
import { START_FEN, formatPercent, numberedSan } from "./repertoire-hooks";

type Progress = Record<string, { runs: number; clean: number }>;
type Filter = "all" | "missing" | "drilled";

const DRILLABLE = new Set(["complete", "out_of_book", "needs_choice"]);

function weightedPick(lines: RepertoireLine[]): RepertoireLine {
  const total = lines.reduce((sum, line) => sum + Math.max(line.reach, 0.001), 0);
  let roll = Math.random() * total;
  for (const line of lines) {
    roll -= Math.max(line.reach, 0.001);
    if (roll <= 0) return line;
  }
  return lines[lines.length - 1];
}

type Props = {
  color: RepertoireColor;
  lines: RepertoireLine[];
  startPly: number;
  /** Per-account key for progress kept in this browser. */
  progressKey: string;
  /** Open the builder at a position (a line that still needs your move). */
  onBuild: (prefixUci: string[]) => void;
  active: boolean;
};

/** Play your side of each repertoire line from memory; the opponent plays its common replies. */
export function RepertoireDrill({ color, lines, startPly, progressKey, onBuild, active }: Props) {
  const drillable = useMemo(() => lines.filter((line) => DRILLABLE.has(line.status) && line.ownMoves > 0), [lines]);
  const [progress, setProgress] = usePersistentState<Progress>(progressKey, {});
  const [currentId, setCurrentId] = useState<string | null>(null);
  const current = drillable.find((line) => line.id === currentId) ?? null;
  const moves = useMemo(() => current?.san ?? [], [current]);
  const trainer = useLineTrainer(START_FEN, moves, color);
  const [recorded, setRecorded] = useState(false);
  const boardRef = useRef<HTMLDivElement>(null);
  const clean = trainer.mistakes === 0 && trainer.hints === 0;

  /** The given line, or the next one: never-drilled lines first, weighted by how often you meet them. */
  function start(line?: RepertoireLine) {
    if (!drillable.length) return;
    let next = line;
    if (!next) {
      const others = drillable.filter((item) => item.id !== currentId);
      const fresh = others.filter((item) => !progress[item.id]);
      next = weightedPick(fresh.length ? fresh : others.length ? others : drillable);
    }
    setRecorded(false);
    if (next.id === currentId) trainer.reset();
    setCurrentId(next.id);
  }

  // Pick a line when the list arrives, or when the current one disappears (e.g. after an edit).
  useEffect(() => {
    if (!current && drillable.length) start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drillable, current]);

  useEffect(() => {
    if (!current || !trainer.done || recorded) return;
    setRecorded(true);
    setProgress((all) => {
      const stats = all[current.id] ?? { runs: 0, clean: 0 };
      return { ...all, [current.id]: { runs: stats.runs + 1, clean: stats.clean + (clean ? 1 : 0) } };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trainer.done, recorded, current]);

  useShortcuts({ h: trainer.hint, r: () => { setRecorded(false); trainer.reset(); }, v: () => start() }, active);

  if (!drillable.length) {
    return (
      <div className="tp-empty">
        <p className="folio">Nothing to drill yet</p>
        <p>Choose your first moves in Build mode; every line with at least one of your moves becomes a drill.</p>
      </div>
    );
  }

  const arrows: BoardArrow[] = [];
  if (trainer.hintSquare && trainer.userTurn) {
    const next = replayLine(trainer.fen, [moves[trainer.index]]).uci[0];
    if (next) arrows.push({ startSquare: next.slice(0, 2), endSquare: next.slice(2, 4), color: ARROW_HINT });
  }
  const squareStyles = trainer.lastMove
    ? { [trainer.lastMove.from]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.22)" }, [trainer.lastMove.to]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.32)" } }
    : undefined;
  const stats = current ? progress[current.id] : undefined;

  return (
    <div style={{ display: "grid", gap: "1.75rem" }}>
      <div className="tp-exercise" ref={boardRef} style={{ scrollMarginTop: "100px" }}>
        <div>
          <TrainingBoard
            className="w-full"
            animate={active}
            fen={trainer.fen}
            orientation={color}
            movable={trainer.userTurn}
            onMove={trainer.onMove}
            arrows={arrows}
            squareStyles={squareStyles}
            wrongSquare={trainer.wrongSquare}
            label={`Repertoire drill, you play ${color}`}
          />
          <div className="tp-ptrack" style={{ marginTop: ".75rem" }} role="progressbar" aria-valuemin={0} aria-valuemax={moves.length} aria-valuenow={trainer.index}>
            <div style={{ width: `${(trainer.index / Math.max(moves.length, 1)) * 100}%` }} />
          </div>
        </div>
        <div style={{ display: "grid", gap: "1rem", alignContent: "start" }}>
          <div>
            <p className="folio">You play {color} · met in {current ? formatPercent(current.reach) : "–"} of games</p>
            {/* The name would give away the opponent's replies, so it shows once the line is played. */}
            <h2 className="tp-panel-subtitle">{trainer.done ? current?.openingName ?? "Unnamed line" : "Which line will it be?"}</h2>
          </div>

          <ol className="tp-drill-line" aria-label="Moves so far">
            {moves.map((san, index) => {
              const played = index < trainer.index;
              const mine = (index % 2 === 0) === (color === "white");
              const before = index < startPly;
              return (
                <li key={index} data-state={played || before ? "played" : index === trainer.index ? "next" : "hidden"} data-mine={mine && !before}>
                  {index % 2 === 0 ? <span className="tp-move-no">{index / 2 + 1}.</span> : null}
                  {played || trainer.done ? san : index === trainer.index && mine ? "?" : "·"}
                </li>
              );
            })}
          </ol>

          {trainer.done ? (
            <div className={`tp-verdict ${clean ? "is-good" : "is-ok"}`}>
              <CheckCircle2 className="h-5 w-5" />
              <span>
                {clean ? "Clean run, no mistakes." : `Done, with ${trainer.mistakes} wrong ${trainer.mistakes === 1 ? "move" : "moves"} and ${trainer.hints} ${trainer.hints === 1 ? "hint" : "hints"}.`}
                {current?.status === "needs_choice" ? " Your repertoire has no move here yet." : ""}
              </span>
            </div>
          ) : (
            <div className="tp-trainer-status" aria-live="polite">
              <span>{trainer.userTurn ? "Your move" : "Opponent…"}</span>
              <span className={trainer.mistakes ? "tp-neg" : ""}>{trainer.mistakes} wrong</span>
              <span>{trainer.hints} hints</span>
            </div>
          )}

          <div className="tp-actions">
            {!trainer.done ? <Button variant="outline" onClick={trainer.hint} disabled={!trainer.userTurn}><Lightbulb className="h-4 w-4" /> Hint <kbd>H</kbd></Button> : null}
            <Button variant={trainer.done ? "default" : "ghost"} onClick={() => start()}><Shuffle className="h-4 w-4" /> Next line <kbd>V</kbd></Button>
            <Button variant="ghost" onClick={() => { setRecorded(false); trainer.reset(); }}><RotateCcw className="h-4 w-4" /> {trainer.done ? "Same line again" : "Restart"} <kbd>R</kbd></Button>
            {trainer.done && current?.status === "needs_choice" ? (
              <Button variant="outline" onClick={() => onBuild(current.prefixUci)}><Hammer className="h-4 w-4" /> Choose your next move</Button>
            ) : null}
          </div>
          <p className="tp-note" style={{ margin: 0 }}>{stats ? `${stats.clean} clean of ${stats.runs} runs on this line.` : "First time on this line."}</p>
        </div>
      </div>

      <DrillCoverage
        lines={drillable}
        progress={progress}
        currentId={currentId}
        startPly={startPly}
        onDrill={(line) => {
          start(line);
          boardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}
      />
    </div>
  );
}

/** Which lines you have drilled, which not yet, and how much of your games they cover. */
function DrillCoverage({
  lines,
  progress,
  currentId,
  startPly,
  onDrill,
}: {
  lines: RepertoireLine[];
  progress: Progress;
  currentId: string | null;
  startPly: number;
  onDrill: (line: RepertoireLine) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const drilled = lines.filter((line) => progress[line.id]);
  const missing = lines.filter((line) => !progress[line.id]);
  const total = lines.reduce((sum, line) => sum + line.reach, 0);
  const covered = drilled.reduce((sum, line) => sum + line.reach, 0);
  const rows = filter === "all" ? lines : filter === "missing" ? missing : drilled;

  return (
    <section className="tp-coverage" aria-labelledby="rep-drill-coverage">
      <div className="tp-coverage-head">
        <div>
          <p className="folio">Lines</p>
          <h3 id="rep-drill-coverage" className="tp-panel-subtitle">
            {missing.length === 0 ? `All ${lines.length} lines drilled.` : `${drilled.length} of ${lines.length} lines drilled`}
          </h3>
          <p className="tp-note" style={{ margin: ".35rem 0 0" }}>
            The lines you've drilled come up in <b style={{ color: "var(--ink)" }}>{formatPercent(covered)}</b> of your games
            {total < 0.995 ? ` (your repertoire's lines cover ${formatPercent(total)} in all)` : ""}.
          </p>
        </div>
        <div className="tp-seg" role="group" aria-label="Show lines">
          {(["all", "missing", "drilled"] as Filter[]).map((value) => (
            <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)}>
              {value === "all" ? `All ${lines.length}` : value === "missing" ? `Not yet ${missing.length}` : `Drilled ${drilled.length}`}
            </button>
          ))}
        </div>
      </div>
      <div className="tp-coverage-bar" role="img" aria-label={`${formatPercent(covered)} of games covered by drilled lines`}>
        {lines.map((line) => (
          <span
            key={line.id}
            data-state={progress[line.id]?.clean ? "clean" : progress[line.id] ? "drilled" : "missing"}
            data-current={line.id === currentId}
            style={{ flexGrow: Math.max(line.reach, 0.004) }}
            title={`${numberedSan(line.san)} · ${formatPercent(line.reach)}`}
          />
        ))}
      </div>
      {rows.length ? (
        <ul className="tp-variation-list">
          {rows.map((line) => {
            const stats = progress[line.id];
            const state = stats?.clean ? "clean" : stats ? "drilled" : "missing";
            const from = Math.max(startPly, line.san.length - 6);
            return (
              <li key={line.id} data-state={state} data-current={line.id === currentId}>
                <span className="tp-variation-icon" aria-hidden="true">
                  {state === "clean" ? <CheckCircle2 /> : state === "drilled" ? <CircleDot /> : <Circle />}
                </span>
                <span className="tp-variation-main">
                  <b>{line.openingName ?? "Unnamed line"}{line.status === "needs_choice" ? <small> · needs your next move</small> : null}</b>
                  <small>{from > 0 ? "… " : ""}{numberedSan(line.san, from)}</small>
                </span>
                <span className="tp-variation-meta">
                  <b>{formatPercent(line.reach)}</b>
                  <small>{stats ? `${stats.clean}/${stats.runs} clean` : "Not yet"}</small>
                </span>
                <Button size="sm" variant={state === "missing" ? "outline" : "ghost"} onClick={() => onDrill(line)} disabled={line.id === currentId}>
                  {line.id === currentId ? "On the board" : <><Play className="h-3.5 w-3.5" /> Drill</>}
                </Button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="tp-empty">{filter === "missing" ? "Every line has been drilled." : "No lines drilled yet."}</p>
      )}
    </section>
  );
}
