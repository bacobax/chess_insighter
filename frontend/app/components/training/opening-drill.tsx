import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { CheckCircle2, Circle, CircleDot, ExternalLink, Lightbulb, Loader2, Play, RotateCcw, Shuffle } from "lucide-react";
import { Button } from "~/components/ui/button";
import { getOpeningDrillCatalog } from "~/lib/api";
import type { OpeningDrillLine, TrainingOpeningRecommendation } from "~/lib/types";
import { ARROW_HINT, TrainingBoard, parseSanLine, replayLine, type BoardArrow } from "./training-board";
import { useLineTrainer, usePersistentState, useShortcuts } from "./training-hooks";

const MASTERED_AFTER = 3;
const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

type Progress = Record<string, { runs: number; clean: number; streak: number }>;
type LineProgress = Record<string, Record<string, { runs: number; clean: number }>>;
type LineFilter = "all" | "missing" | "explored";

function weightedPick(lines: OpeningDrillLine[]): OpeningDrillLine {
  const total = lines.reduce((sum, line) => sum + Math.max(line.probability, 0.001), 0);
  let roll = Math.random() * total;
  for (const line of lines) {
    roll -= Math.max(line.probability, 0.001);
    if (roll <= 0) return line;
  }
  return lines[lines.length - 1];
}

function sanWithNumbers(moves: string[], from = 0): string {
  return moves
    .slice(from)
    .map((san, offset) => {
      const index = from + offset;
      const number = Math.floor(index / 2) + 1;
      if (index % 2 === 0) return `${number}.${san}`;
      return offset === 0 ? `${number}…${san}` : san;
    })
    .join(" ");
}

/** Play your side of each repertoire opening from memory against popular opponent replies. */
export function OpeningDrill({ username, openings }: { username: string; openings: TrainingOpeningRecommendation[] }) {
  const user = username.toLowerCase();
  const [active, setActive] = useState(0);
  const [progress, setProgress] = usePersistentState<Progress>(`tp:drill:${user}`, {});
  const [lineProgress, setLineProgress] = usePersistentState<LineProgress>(`tp:drill-lines:${user}`, {});
  const [catalogs, setCatalogs] = useState<Record<string, OpeningDrillLine[]>>({});
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
          const catalog = catalogs[item.slot];
          const explored = catalog ? catalog.filter((line) => lineProgress[item.slot]?.[line.id]).length : null;
          return (
            <button key={item.slot} type="button" role="tab" aria-selected={index === active} onClick={() => setActive(index)}>
              <small>{item.slot_label}</small>
              <b>{item.name.split(" · ")[0]}</b>
              <span className="tp-mastery" aria-label={`${Math.min(stats?.streak ?? 0, MASTERED_AFTER)} of ${MASTERED_AFTER} clean runs in a row`}>
                {Array.from({ length: MASTERED_AFTER }, (_, i) => <i key={i} data-on={i < (stats?.streak ?? 0)} />)}
                {mastered ? <CheckCircle2 className="h-3.5 w-3.5 tp-pos" /> : null}
                {catalog ? <small style={{ marginLeft: ".35rem" }}>{explored}/{catalog.length} lines</small> : null}
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
        explored={lineProgress[opening.slot] ?? {}}
        onCatalog={(lines) => setCatalogs((current) => ({ ...current, [opening.slot]: lines }))}
        onFinished={(lineId, clean) => {
          setProgress((current) => {
            const stats = current[opening.slot] ?? { runs: 0, clean: 0, streak: 0 };
            return { ...current, [opening.slot]: { runs: stats.runs + 1, clean: stats.clean + (clean ? 1 : 0), streak: clean ? stats.streak + 1 : 0 } };
          });
          if (lineId) {
            setLineProgress((current) => {
              const slot = current[opening.slot] ?? {};
              const stats = slot[lineId] ?? { runs: 0, clean: 0 };
              return { ...current, [opening.slot]: { ...slot, [lineId]: { runs: stats.runs + 1, clean: stats.clean + (clean ? 1 : 0) } } };
            });
          }
        }}
        onNext={openings.length > 1 ? () => setActive((active + 1) % openings.length) : undefined}
      />
    </div>
  );
}

function DrillBoard({
  opening,
  username,
  stats,
  explored,
  onCatalog,
  onFinished,
  onNext,
}: {
  opening: TrainingOpeningRecommendation;
  username: string;
  stats?: { runs: number; clean: number; streak: number };
  explored: Record<string, { runs: number; clean: number }>;
  onCatalog: (lines: OpeningDrillLine[]) => void;
  onFinished: (lineId: string | null, clean: boolean) => void;
  onNext?: () => void;
}) {
  const side = opening.slot === "white" ? "white" : "black";
  const mainLine = useMemo(() => parseSanLine(opening.line), [opening.line]);
  const [variations, setVariations] = usePersistentState(`tp:drill-variations:${username.toLowerCase()}`, true);
  const [catalog, setCatalog] = useState<OpeningDrillLine[] | null>(null);
  const [current, setCurrent] = useState<OpeningDrillLine | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const moves = current?.moves ?? mainLine;
  const trainer = useLineTrainer(START_FEN, moves, side);
  const [recorded, setRecorded] = useState(false);
  const boardRef = useRef<HTMLDivElement>(null);
  const clean = trainer.mistakes === 0 && trainer.hints === 0;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getOpeningDrillCatalog(opening.line, side)
      .then((response) => {
        if (cancelled) return;
        setCatalog(response.lines);
        onCatalog(response.lines);
      })
      .catch((err) => {
        if (!cancelled) setError(`${err instanceof Error ? err.message : "Could not load the variations."} Drilling the main line instead.`);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // Load once per opening; `onCatalog` is a fresh closure every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opening.line, side]);

  /** Main line, a chosen line, or the next line to explore: unexplored ones first, weighted by how often you'll meet them. */
  function start(line?: OpeningDrillLine, useVariations = variations) {
    if (!catalog?.length) return;
    let next = line;
    if (!next) {
      if (!useVariations) next = catalog[0];
      else {
        const missing = catalog.filter((item) => !explored[item.id] && item.id !== current?.id);
        const pool = missing.length ? missing : catalog.filter((item) => item.id !== current?.id);
        next = weightedPick(pool.length ? pool : catalog);
      }
    }
    setRecorded(false);
    if (next.id === current?.id) trainer.reset();
    setCurrent(next);
  }

  useEffect(() => {
    if (catalog && !current) start();
    // Pick the first line once the catalog arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalog]);

  useEffect(() => {
    if (trainer.done && !recorded && !loading) {
      setRecorded(true);
      onFinished(current?.id ?? null, clean);
    }
    // Record each finished run once; `onFinished` is a fresh closure every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trainer.done, recorded, loading]);

  function restart() {
    setRecorded(false);
    trainer.reset();
  }

  function switchMode(next: boolean) {
    setVariations(next);
    start(undefined, next);
  }

  useShortcuts({ h: trainer.hint, r: restart, v: () => start(), n: () => onNext?.() });

  const arrows: BoardArrow[] = [];
  if (trainer.hintSquare && trainer.userTurn) {
    const next = replayLine(trainer.fen, [moves[trainer.index]]).uci[0];
    if (next) arrows.push({ startSquare: next.slice(0, 2), endSquare: next.slice(2, 4), color: ARROW_HINT });
  }
  const squareStyles = trainer.lastMove
    ? { [trainer.lastMove.from]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.22)" }, [trainer.lastMove.to]: { boxShadow: "inset 0 0 0 999px rgba(220,255,66,.32)" } }
    : undefined;
  const deviatesAt = current?.deviates_at ?? null;
  const deviation = deviatesAt !== null ? current?.opponent_choices.find((choice) => choice.ply === deviatesAt) : undefined;
  const offBook = deviation && trainer.index > (deviatesAt ?? 0);
  const userMoves = Math.ceil(moves.length / 2);

  return (
    <div style={{ display: "grid", gap: "1.75rem" }}>
      <div className="tp-exercise" ref={boardRef} style={{ scrollMarginTop: "100px" }}>
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
            <p className="tp-note" style={{ marginTop: ".5rem" }}>
              {current && !current.main_line ? `A variation you'll meet in about ${Math.max(1, Math.round(current.probability * 100))}% of games. ` : `Main line. ${opening.learn_depth}. `}About {userMoves} moves of yours.
            </p>
          </div>

          <div className="tp-seg" role="group" aria-label="Opponent moves">
            <button type="button" aria-pressed={variations} onClick={() => switchMode(true)}>Popular variations</button>
            <button type="button" aria-pressed={!variations} onClick={() => switchMode(false)}>Main line only</button>
          </div>

          {loading ? <p className="tp-note" style={{ margin: 0 }}><Loader2 className="inline h-3.5 w-3.5 animate-spin" /> Loading the variations…</p> : null}
          {error ? <p className="form-error" style={{ margin: 0 }}>{error}</p> : null}

          <ol className="tp-drill-line" aria-label="Moves so far">
            {moves.map((san, index) => {
              const played = index < trainer.index;
              const mine = (index % 2 === 0) === (side === "white");
              return (
                <li key={index} data-state={played ? "played" : index === trainer.index ? "next" : "hidden"} data-mine={mine} data-deviation={deviatesAt === index && played}>
                  {index % 2 === 0 ? <span className="tp-move-no">{index / 2 + 1}.</span> : null}
                  {played || trainer.done ? san : index === trainer.index && mine ? "?" : "·"}
                </li>
              );
            })}
          </ol>

          {offBook && deviation ? (
            <div className="tp-verdict is-ok">
              <Shuffle className="h-5 w-5" />
              <span>Your opponent left the main line with {deviation.san}{deviation.share != null ? ` (${Math.round(deviation.share * 100)}% of Lichess games here)` : ""}. From here, play the most common answer.</span>
            </div>
          ) : null}

          {trainer.done && !loading ? (
            <div className={`tp-verdict ${clean ? "is-good" : "is-ok"}`}>
              <CheckCircle2 className="h-5 w-5" />
              <span>
                {current?.variation ? <b style={{ display: "block" }}>{current.eco ? `${current.eco} · ` : ""}{current.variation}</b> : null}
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
            {variations ? <Button variant={trainer.done ? "default" : "ghost"} onClick={() => start()} disabled={loading || !catalog}><Shuffle className="h-4 w-4" /> Next variation <kbd>V</kbd></Button> : null}
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

      {catalog ? (
        <VariationCoverage
          catalog={catalog}
          explored={explored}
          currentId={current?.id ?? null}
          onDrill={(line) => {
            if (!line.main_line && !variations) setVariations(true);
            start(line);
            boardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
        />
      ) : null}
    </div>
  );
}

/** Which lines of this opening you've drilled, which are missing, and how much of your games they cover. */
function VariationCoverage({
  catalog,
  explored,
  currentId,
  onDrill,
}: {
  catalog: OpeningDrillLine[];
  explored: Record<string, { runs: number; clean: number }>;
  currentId: string | null;
  onDrill: (line: OpeningDrillLine) => void;
}) {
  const [filter, setFilter] = useState<LineFilter>("all");
  const done = catalog.filter((line) => explored[line.id]);
  const covered = done.reduce((sum, line) => sum + line.probability, 0);
  const missingLines = catalog.filter((line) => !explored[line.id]);
  const biggestGap = [...missingLines].sort((a, b) => b.probability - a.probability)[0];
  const rows = filter === "all" ? catalog : filter === "missing" ? missingLines : done;

  return (
    <section className="tp-coverage" aria-labelledby="tp-coverage-h">
      <div className="tp-coverage-head">
        <div>
          <p className="folio">Variations</p>
          <h3 id="tp-coverage-h" className="tp-panel-subtitle">
            {missingLines.length === 0 ? `All ${catalog.length} lines explored.` : `${done.length} of ${catalog.length} lines explored · ${missingLines.length} missing`}
          </h3>
          <p className="tp-note" style={{ margin: ".35rem 0 0" }}>
            The lines you've drilled cover <b style={{ color: "var(--ink)" }}>{Math.round(covered * 100)}%</b> of the games you're likely to meet.
            {biggestGap ? ` Biggest gap: ${biggestGap.variation ?? "a side line"} (${Math.max(1, Math.round(biggestGap.probability * 100))}%).` : ""}
          </p>
        </div>
        <div className="tp-seg" role="group" aria-label="Show lines">
          {(["all", "missing", "explored"] as LineFilter[]).map((value) => (
            <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)}>
              {value === "all" ? `All ${catalog.length}` : value === "missing" ? `Missing ${missingLines.length}` : `Explored ${done.length}`}
            </button>
          ))}
        </div>
      </div>
      <div className="tp-coverage-bar" role="img" aria-label={`${Math.round(covered * 100)}% of likely games covered`}>
        {catalog.map((line) => (
          <span
            key={line.id}
            data-state={explored[line.id]?.clean ? "clean" : explored[line.id] ? "drilled" : "missing"}
            data-current={line.id === currentId}
            style={{ flexGrow: Math.max(line.probability, 0.004) }}
            title={`${line.variation ?? "Line"} · ${Math.max(1, Math.round(line.probability * 100))}%`}
          />
        ))}
      </div>
      <div className="tp-legend">
        <span><i style={{ background: "#21e783" }} />Drilled cleanly</span>
        <span><i style={{ background: "#dcff42" }} />Drilled, with mistakes</span>
        <span><i style={{ background: "#314139" }} />Not explored yet</span>
      </div>
      {rows.length ? (
        <ul className="tp-variation-list">
          {rows.map((line) => {
            const stats = explored[line.id];
            const state = stats?.clean ? "clean" : stats ? "drilled" : "missing";
            const from = line.deviates_at ?? Math.max(0, line.moves.length - 4);
            return (
              <li key={line.id} data-state={state} data-current={line.id === currentId}>
                <span className="tp-variation-icon" aria-hidden="true">
                  {state === "clean" ? <CheckCircle2 /> : state === "drilled" ? <CircleDot /> : <Circle />}
                </span>
                <span className="tp-variation-main">
                  <b>{line.main_line ? "Main line · " : ""}{line.variation ?? "Unnamed line"}{line.eco ? <small> {line.eco}</small> : null}</b>
                  <small>{from > 0 ? "… " : ""}{sanWithNumbers(line.moves, from)}</small>
                </span>
                <span className="tp-variation-meta">
                  <b>{Math.max(1, Math.round(line.probability * 100))}%</b>
                  <small>{stats ? `${stats.clean}/${stats.runs} clean` : "Not yet"}</small>
                </span>
                <Button size="sm" variant={state === "missing" ? "outline" : "ghost"} onClick={() => onDrill(line)} disabled={line.id === currentId} aria-label={`Drill ${line.variation ?? "this line"}`}>
                  {line.id === currentId ? "On the board" : <><Play className="h-3.5 w-3.5" /> Drill</>}
                </Button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="tp-empty">{filter === "missing" ? "Nothing missing: every line has been drilled." : "No lines drilled yet."}</p>
      )}
    </section>
  );
}
