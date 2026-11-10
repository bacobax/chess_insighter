import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { CheckCircle2, ExternalLink, Lightbulb, Loader2, RotateCcw, Shuffle } from "lucide-react";
import { Button } from "~/components/ui/button";
import { getOpeningDrillLine } from "~/lib/api";
import type { OpeningDrillLine, TrainingOpeningRecommendation } from "~/lib/types";
import { ARROW_HINT, TrainingBoard, parseSanLine, replayLine, type BoardArrow } from "./training-board";
import { useLineTrainer, usePersistentState, useShortcuts } from "./training-hooks";

const MASTERED_AFTER = 3;
const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

type Progress = Record<string, { runs: number; clean: number; streak: number }>;

/** Play your side of each repertoire opening from memory against popular opponent replies. */
export function OpeningDrill({ username, openings }: { username: string; openings: TrainingOpeningRecommendation[] }) {
  const [active, setActive] = useState(0);
  const [progress, setProgress] = usePersistentState<Progress>(`tp:drill:${username.toLowerCase()}`, {});
  const opening = openings[active];
  if (!opening) return <p className="tp-empty">No openings in this plan yet.</p>;

  return (
    <div style={{ display: "grid", gap: "1.25rem" }}>
      <div>
        <p className="folio">Opening drill</p>
        <h2 className="tp-panel-title">Play your side from memory.</h2>
      </div>
      <div className="tp-tabs" role="tablist" aria-label="Openings">
        {openings.map((item, index) => {
          const stats = progress[item.slot];
          const mastered = (stats?.streak ?? 0) >= MASTERED_AFTER;
          return (
            <button key={item.slot} type="button" role="tab" aria-selected={index === active} onClick={() => setActive(index)}>
              <small>{item.slot_label}</small>
              <b>{item.name.split(" · ")[0]}</b>
              <span className="tp-mastery" aria-label={`${Math.min(stats?.streak ?? 0, MASTERED_AFTER)} of ${MASTERED_AFTER} clean runs in a row`}>
                {Array.from({ length: MASTERED_AFTER }, (_, i) => <i key={i} data-on={i < (stats?.streak ?? 0)} />)}
                {mastered ? <CheckCircle2 className="h-3.5 w-3.5 tp-pos" /> : null}
              </span>
            </button>
          );
        })}
      </div>
      <DrillBoard
        key={opening.slot}
        opening={opening}
        username={username}
        stats={progress[opening.slot]}
        onFinished={(clean) => setProgress((current) => {
          const stats = current[opening.slot] ?? { runs: 0, clean: 0, streak: 0 };
          return { ...current, [opening.slot]: { runs: stats.runs + 1, clean: stats.clean + (clean ? 1 : 0), streak: clean ? stats.streak + 1 : 0 } };
        })}
        onNext={openings.length > 1 ? () => setActive((active + 1) % openings.length) : undefined}
      />
    </div>
  );
}

function DrillBoard({
  opening,
  username,
  stats,
  onFinished,
  onNext,
}: {
  opening: TrainingOpeningRecommendation;
  username: string;
  stats?: { runs: number; clean: number; streak: number };
  onFinished: (clean: boolean) => void;
  onNext?: () => void;
}) {
  const side = opening.slot === "white" ? "white" : "black";
  const mainLine = useMemo(() => parseSanLine(opening.line), [opening.line]);
  const [variations, setVariations] = usePersistentState(`tp:drill-variations:${username.toLowerCase()}`, true);
  const [drill, setDrill] = useState<OpeningDrillLine | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [requestId, setRequestId] = useState(0);
  const moves = drill?.moves ?? mainLine;
  const trainer = useLineTrainer(START_FEN, moves, side);
  const [recorded, setRecorded] = useState(false);
  const clean = trainer.mistakes === 0 && trainer.hints === 0;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getOpeningDrillLine(opening.line, side, variations)
      .then((line) => { if (!cancelled) setDrill(line.moves.length ? line : null); })
      .catch((err) => {
        if (cancelled) return;
        setDrill(null);
        setError(`${err instanceof Error ? err.message : "Could not load a variation."} Drilling the main line instead.`);
      })
      .finally(() => { if (!cancelled) { setLoading(false); setRecorded(false); } });
    return () => { cancelled = true; };
  }, [opening.line, side, variations, requestId]);

  useEffect(() => {
    if (trainer.done && !recorded && !loading) {
      setRecorded(true);
      onFinished(clean);
    }
    // Record each finished run once; `onFinished` is a fresh closure every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trainer.done, recorded, loading]);

  function restart() {
    setRecorded(false);
    trainer.reset();
  }

  const newLine = () => setRequestId((current) => current + 1);
  useShortcuts({ h: trainer.hint, r: restart, v: newLine, n: () => onNext?.() });

  const arrows: BoardArrow[] = [];
  if (trainer.hintSquare && trainer.userTurn) {
    const next = replayLine(trainer.fen, [moves[trainer.index]]).uci[0];
    if (next) arrows.push({ startSquare: next.slice(0, 2), endSquare: next.slice(2, 4), color: ARROW_HINT });
  }
  const squareStyles = trainer.lastMove
    ? { [trainer.lastMove.from]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.22)" }, [trainer.lastMove.to]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.32)" } }
    : undefined;
  const deviatesAt = drill?.deviates_at ?? null;
  const deviation = deviatesAt !== null ? drill?.opponent_choices.find((choice) => choice.ply === deviatesAt) : undefined;
  const offBook = deviation && trainer.index > (deviatesAt ?? 0);
  const userMoves = Math.ceil(moves.length / 2);

  return (
    <div className="tp-exercise">
      <div>
        <TrainingBoard
          fen={trainer.fen}
          orientation={side}
          movable={trainer.userTurn && !loading}
          onMove={trainer.onMove}
          arrows={arrows}
          squareStyles={squareStyles}
          wrongSquare={trainer.wrongSquare}
          label={`${opening.name}, you play ${side}`}
        />
        <div className="tp-ptrack" style={{ marginTop: ".75rem" }} role="progressbar" aria-valuemin={0} aria-valuemax={moves.length} aria-valuenow={trainer.index}>
          <div style={{ width: `${(trainer.index / Math.max(moves.length, 1)) * 100}%` }} />
        </div>
      </div>
      <div style={{ display: "grid", gap: "1rem", alignContent: "start" }}>
        <div>
          <p className="folio">{opening.slot_label} · you play {side}</p>
          <h2>{opening.name}</h2>
          <p className="tp-note" style={{ marginTop: ".5rem" }}>{opening.learn_depth}. About {userMoves} moves of yours in this line.</p>
        </div>

        <div className="tp-seg" role="group" aria-label="Opponent moves">
          <button type="button" aria-pressed={variations} onClick={() => setVariations(true)}>Popular variations</button>
          <button type="button" aria-pressed={!variations} onClick={() => setVariations(false)}>Main line only</button>
        </div>

        {loading ? <p className="tp-note" style={{ margin: 0 }}><Loader2 className="inline h-3.5 w-3.5 animate-spin" /> Picking a variation…</p> : null}
        {error ? <p className="form-error" style={{ margin: 0 }}>{error}</p> : null}

        <ol className="tp-drill-line" aria-label="Moves so far">
          {moves.map((san, index) => {
            const played = index < trainer.index;
            const mine = (index % 2 === 0) === (side === "white");
            const deviated = deviatesAt !== null && index === deviatesAt;
            return (
              <li key={index} data-state={played ? "played" : index === trainer.index ? "next" : "hidden"} data-mine={mine} data-deviation={deviated && played}>
                {index % 2 === 0 ? <span className="tp-move-no">{index / 2 + 1}.</span> : null}
                {played || trainer.done ? san : index === trainer.index && mine ? "?" : "·"}
              </li>
            );
          })}
        </ol>

        {offBook && deviation ? (
          <div className="tp-verdict is-ok">
            <Shuffle className="h-5 w-5" />
            <span>
              Your opponent left the main line with {deviation.san}{deviation.share != null ? ` (${Math.round(deviation.share * 100)}% of Lichess games here)` : ""}. From here, play the most common answer.
            </span>
          </div>
        ) : null}

        {trainer.done && !loading ? (
          <div className={`tp-verdict ${clean ? "is-good" : "is-ok"}`}>
            <CheckCircle2 className="h-5 w-5" />
            <span>
              {drill?.variation ? <b style={{ display: "block" }}>{drill.eco ? `${drill.eco} · ` : ""}{drill.variation}</b> : null}
              {clean ? "Clean run, no mistakes." : `Done, with ${trainer.mistakes} wrong ${trainer.mistakes === 1 ? "move" : "moves"} and ${trainer.hints} ${trainer.hints === 1 ? "hint" : "hints"}.`} {(stats?.streak ?? 0) >= MASTERED_AFTER ? "You know this opening." : `${Math.max(0, MASTERED_AFTER - (stats?.streak ?? 0))} more clean ${MASTERED_AFTER - (stats?.streak ?? 0) === 1 ? "run" : "runs"} in a row to master it.`}
            </span>
          </div>
        ) : !loading ? (
          <div className="tp-trainer-status" aria-live="polite">
            <span>{trainer.userTurn ? "Your move" : "Opponent…"}</span>
            <span className={trainer.mistakes ? "tp-neg" : ""}>{trainer.mistakes} wrong</span>
            <span>{trainer.hints} hints</span>
          </div>
        ) : null}

        <div className="tp-actions">
          {!trainer.done ? <Button variant="outline" onClick={trainer.hint} disabled={!trainer.userTurn || loading}><Lightbulb className="h-4 w-4" /> Hint <kbd>H</kbd></Button> : null}
          {variations ? <Button variant={trainer.done ? "default" : "ghost"} onClick={newLine} disabled={loading}><Shuffle className="h-4 w-4" /> New variation <kbd>V</kbd></Button> : null}
          <Button variant={trainer.done && !variations ? "default" : "ghost"} onClick={restart} disabled={loading}><RotateCcw className="h-4 w-4" /> {trainer.done ? "Same line again" : "Restart"} <kbd>R</kbd></Button>
          {trainer.done && onNext ? <Button variant="outline" onClick={onNext}>Next opening <kbd>N</kbd></Button> : null}
        </div>

        <dl className="tp-kv">
          {opening.plans ? <><dt>Plans</dt><dd>{opening.plans}</dd></> : null}
          {opening.trap ? <><dt>Trap</dt><dd>{opening.trap}</dd></> : null}
          <dt>Runs</dt><dd>{stats ? `${stats.clean} clean of ${stats.runs}` : "Not drilled yet"}</dd>
        </dl>
        <Link to={`/opening-study?username=${encodeURIComponent(username)}&color=${side}`} className="tp-note" style={{ display: "inline-flex", alignItems: "center", gap: ".35rem" }}>
          Explore side lines in Opening Study <ExternalLink className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );
}
