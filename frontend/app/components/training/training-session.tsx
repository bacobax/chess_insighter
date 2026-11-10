import { useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { Check, ExternalLink, Pause, Play, RotateCcw } from "lucide-react";
import { Button } from "~/components/ui/button";
import type { TrainingBlock, TrainingCard, TrainingDay, TrainingPlan } from "~/lib/types";
import { CardExercise } from "./card-exercise";
import { ErrorReview, FlashcardDeck } from "./error-review";
import { GameChecklist } from "./game-checklist";
import { OpeningDrill } from "./opening-drill";
import { type HoursKey, WEEKDAYS, isDue, localIsoDate, percent, scaleMinutes, todayKey } from "./training-format";
import { formatClock, useCountdown, usePersistentState } from "./training-hooks";

const SESSION_CARDS = 6;

type Tool = "flashcards" | "review" | "drill" | "calculation" | "checklist";
type Mode = { kind: "block"; index: number } | { kind: "tool"; tool: Tool };

function blockCards(cards: TrainingCard[], day: TrainingDay, block: TrainingBlock): TrainingCard[] {
  const active = cards.filter((card) => !card.retired);
  const process = block.kind === "calculation" ? "miscalculation" : day.weakness;
  const focused = process ? active.filter((card) => card.process === process) : [];
  const pool = focused.length ? focused : active;
  const due = pool.filter((card) => isDue(card));
  return (due.length ? due : pool).slice(0, SESSION_CARDS);
}

function calculationCards(cards: TrainingCard[]): TrainingCard[] {
  const lines = cards.filter((card) => !card.retired && card.refutation_san.length > 1);
  const focused = lines.filter((card) => card.process === "miscalculation");
  return (focused.length ? focused : lines).slice(0, 10);
}

export function TrainingSession({ plan, dayKey, hours }: { plan: TrainingPlan; dayKey: string; hours: HoursKey }) {
  const day = plan.routine.days.find((item) => item.day === dayKey) ?? plan.routine.days[0];
  const [cards, setCards] = useState(plan.cards);
  const [mode, setMode] = useState<Mode>({ kind: "block", index: 0 });
  const [done, setDone] = usePersistentState<number[]>(`tp:done:${plan.id}:${localIsoDate()}:${day.day}`, []);
  const mainRef = useRef<HTMLElement>(null);
  const block = mode.kind === "block" ? day.blocks[mode.index] ?? null : null;
  const dueCount = cards.filter((card) => isDue(card)).length;
  const sessionMinutes = day.blocks.reduce((total, item) => total + scaleMinutes(item.minutes, hours), 0);
  const base = `/report/${encodeURIComponent(plan.username)}/training`;
  const today = todayKey();
  const updateCard = (updated: TrainingCard) => setCards((current) => current.map((card) => (card.card_id === updated.card_id ? updated : card)));
  const blockQueue = useMemo(
    () => (block && ["own_errors", "calculation"].includes(block.kind) ? (block.kind === "calculation" ? calculationCards(cards) : blockCards(cards, day, block)) : []),
    // Freeze the queue when the block opens, so grading a card doesn't reshuffle it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mode, day],
  );

  function open(next: Mode) {
    setMode(next);
    window.requestAnimationFrame(() => mainRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  function toggleDone(index: number) {
    setDone((current) => (current.includes(index) ? current.filter((item) => item !== index) : [...current, index]));
  }

  return (
    <>
      <nav className="tp-weekstrip" aria-label="This week">
        {WEEKDAYS.map((name) => {
          const item = plan.routine.days.find((entry) => entry.day === name);
          return (
            <Link key={name} to={`${base}/session?day=${name}&hours=${hours}`} aria-current={name === day.day ? "page" : undefined}>
              <span className="tp-label" style={{ color: "inherit" }}>{name}{name === today ? " · today" : ""}</span>
              <b>{item?.focus.replace(/^Weakness #\d · /, "")}</b>
              <small>{item ? `${item.blocks.reduce((t, b) => t + scaleMinutes(b.minutes, hours), 0)}′` : ""}</small>
            </Link>
          );
        })}
      </nav>

      <section className="tp-masthead" style={{ paddingBottom: "1.5rem" }}>
        <div>
          <p className="folio">{day.day === today ? "Today" : day.day} · {sessionMinutes} min</p>
          <h1>{day.focus.replace(/^Weakness #\d · /, "")}</h1>
          <p className="tp-lead">{day.weakness ? `Weakness ${day.focus.match(/#\d/)?.[0] ?? ""} of your plan. ` : ""}Work through the blocks in order: start a block's timer, then tick it off when you're done.</p>
        </div>
        <div className="tp-session-progress" aria-label={`${done.length} of ${day.blocks.length} blocks done`}>
          <b>{done.length}<span>/{day.blocks.length}</span></b>
          <span className="tp-label">blocks done</span>
          <div className="tp-ptrack"><div style={{ width: `${(done.length / Math.max(day.blocks.length, 1)) * 100}%` }} /></div>
        </div>
      </section>

      <div className="tp-session">
        <aside className="tp-session-rail" aria-label="Session blocks">
          <p className="tp-label" style={{ margin: 0 }}>Today's session</p>
          {day.blocks.map((item, index) => {
            const selected = mode.kind === "block" && mode.index === index;
            const finished = done.includes(index);
            return (
              <div key={index} className="tp-step" data-selected={selected} data-done={finished}>
                <button type="button" className="tp-step-open" onClick={() => open({ kind: "block", index })} aria-pressed={selected}>
                  <div className="tp-step-head"><span>{String(index + 1).padStart(2, "0")} · {item.label}</span><span>{scaleMinutes(item.minutes, hours)}′</span></div>
                  <b>{item.text}</b>
                </button>
                {selected ? <BlockTimer minutes={scaleMinutes(item.minutes, hours)} /> : null}
                <label className="tp-step-done">
                  <input type="checkbox" checked={finished} onChange={() => toggleDone(index)} />
                  <span>{finished ? <><Check className="inline h-3.5 w-3.5" /> Done</> : "Mark as done"}</span>
                </label>
              </div>
            );
          })}
          <div className="tp-card" style={{ padding: "1rem" }}>
            <p className="tp-label" style={{ margin: 0 }}>Blunder check</p>
            <p style={{ margin: ".5rem 0 0", color: "var(--ink-soft)", fontSize: ".82rem", lineHeight: 1.6 }}>Before every move, look at their <b style={{ color: "var(--ink)" }}>checks</b>, <b style={{ color: "var(--ink)" }}>captures</b> and <b style={{ color: "var(--ink)" }}>threats</b>.</p>
          </div>
        </aside>

        <section ref={mainRef} className="tp-session-main tp-card" style={{ padding: "1.75rem", scrollMarginTop: "100px" }} aria-live="polite">
          <MainPanel
            key={JSON.stringify(mode)}
            mode={mode}
            block={block}
            blockQueue={blockQueue}
            plan={plan}
            cards={cards}
            day={day}
            onReviewed={updateCard}
            onExit={() => setMode({ kind: "block", index: mode.kind === "block" ? mode.index : 0 })}
            onDone={() => mode.kind === "block" && !done.includes(mode.index) && toggleDone(mode.index)}
          />
        </section>
      </div>

      <div className="section-rule"><span>All training tools</span><b>Use any time</b></div>
      <div className="tp-grid-3">
        <ToolCard kind="Your positions" badge={`${dueCount} due`} title="Flashcards" text="Every mistake from your games becomes a card. Each one comes back after 1, 3, 7 and 21 days." active={mode.kind === "tool" && mode.tool === "flashcards"} onOpen={() => open({ kind: "tool", tool: "flashcards" })} cta="Open flashcards" />
        <ToolCard kind="Your positions" badge={`${cards.filter((card) => !card.retired).length} errors`} title="Error review" text="Filter your errors by cause, phase and severity, then practise any selection on the board." active={mode.kind === "tool" && mode.tool === "review"} onOpen={() => open({ kind: "tool", tool: "review" })} cta="Open review" />
        <ToolCard kind="Openings" badge={`${plan.repertoire.recommended.length} lines`} title="Opening drill" text={`Play ${plan.repertoire.recommended.map((item) => item.name.split(" · ")[0]).join(", ")} from memory. Three clean runs in a row masters a line.`} active={mode.kind === "tool" && mode.tool === "drill"} onOpen={() => open({ kind: "tool", tool: "drill" })} cta="Start drilling" />
        <ToolCard kind="Calculation" badge={`${calculationCards(cards).length} lines`} title="Calculation trainer" text="The lines that punished your moves. Play both sides, move by move, before the engine shows you." active={mode.kind === "tool" && mode.tool === "calculation"} onOpen={() => open({ kind: "tool", tool: "calculation" })} cta="Start calculating" />
        <ToolCard kind="Play" badge="Saturday" title="Slow-game checklist" text="The blunder check, a clock budget for your time control, and a post-game log." active={mode.kind === "tool" && mode.tool === "checklist"} onOpen={() => open({ kind: "tool", tool: "checklist" })} cta="Open checklist" />
        <article className="tp-card tp-tool">
          <div className="tp-actions" style={{ justifyContent: "space-between" }}><p className="folio">Puzzles</p><span className="tp-tag">{percent(plan.routine.puzzle_split.mixed)} mixed</span></div>
          <h3>Puzzles</h3>
          <p>Mostly mixed puzzles with no theme given.{plan.routine.puzzle_split.themed_motifs.length ? ` Themed sets: ${plan.routine.puzzle_split.themed_motifs.join(", ")}.` : ""} In-app puzzles are coming soon.</p>
          <a href="https://www.chess.com/puzzles" target="_blank" rel="noreferrer"><Button size="sm" variant="outline">Chess.com puzzles <ExternalLink className="h-4 w-4" /></Button></a>
        </article>
      </div>
    </>
  );
}

function MainPanel({
  mode,
  block,
  blockQueue,
  plan,
  cards,
  day,
  onReviewed,
  onExit,
  onDone,
}: {
  mode: Mode;
  block: TrainingBlock | null;
  blockQueue: TrainingCard[];
  plan: TrainingPlan;
  cards: TrainingCard[];
  day: TrainingDay;
  onReviewed: (card: TrainingCard) => void;
  onExit: () => void;
  onDone: () => void;
}) {
  const username = plan.username;
  if (mode.kind === "tool") {
    const close = <div className="tp-actions" style={{ justifyContent: "flex-end", marginBottom: "-.5rem" }}><Button size="sm" variant="ghost" onClick={onExit}>Back to today's session</Button></div>;
    const body = {
      flashcards: <FlashcardDeck username={username} cards={cards} onReviewed={onReviewed} />,
      review: <ErrorReview username={username} cards={cards} initialProcess={day.weakness} onReviewed={onReviewed} />,
      drill: <OpeningDrill username={username} openings={plan.repertoire.recommended} />,
      calculation: <CardExercise username={username} queue={calculationCards(cards)} calculation title="Calculation trainer" onReviewed={onReviewed} onExit={onExit} onClose={onExit} />,
      checklist: <GameChecklist username={username} focus="play" />,
    }[mode.tool];
    return <div style={{ display: "grid", gap: "1rem" }}>{close}{body}</div>;
  }
  if (!block) return null;
  if (block.kind === "own_errors" || block.kind === "calculation") {
    return blockQueue.length
      ? <CardExercise username={username} queue={blockQueue} calculation={block.kind === "calculation"} title={`${block.label} · ${block.text}`} onReviewed={onReviewed} onExit={onDone} />
      : <div className="tp-empty"><p className="folio">Nothing to review</p><p>No cards are waiting for this block. Good work, or build a new plan with more games.</p></div>;
  }
  if (block.kind === "repertoire") return <OpeningDrill username={username} openings={plan.repertoire.recommended} />;
  if (block.kind === "play") return <GameChecklist username={username} focus="play" />;
  if (block.kind === "review") return <GameChecklist username={username} focus="review" />;
  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <p className="folio">{block.label}</p>
      <h2 className="tp-panel-title">{block.text}</h2>
      <p style={{ margin: 0, color: "var(--ink-soft)", lineHeight: 1.7 }}>
        {block.kind === "puzzles"
          ? "In-app puzzles are coming soon. Until then, solve them on your usual puzzle site: mostly mixed, some themed. Start the timer on the left so the block stays the right length."
          : "This block doesn't have an in-app tool yet. Do it with your usual resources and use the timer on the left."}
      </p>
      {block.kind === "puzzles" ? <a href="https://www.chess.com/puzzles" target="_blank" rel="noreferrer"><Button size="sm" variant="outline">Open Chess.com puzzles <ExternalLink className="h-4 w-4" /></Button></a> : null}
    </div>
  );
}

function BlockTimer({ minutes }: { minutes: number }) {
  const timer = useCountdown(minutes * 60);
  const finished = timer.remaining === 0;
  return (
    <div className="tp-timer" data-finished={finished}>
      <span className="tp-timer-clock" aria-live="off">{finished ? "Time's up" : formatClock(timer.remaining)}</span>
      <div className="tp-timer-buttons">
        <button type="button" onClick={timer.toggle} aria-label={timer.running ? "Pause timer" : "Start timer"} disabled={finished}>{timer.running ? <Pause /> : <Play />}</button>
        <button type="button" onClick={() => timer.add(300)} aria-label="Add 5 minutes">+5</button>
        <button type="button" onClick={timer.reset} aria-label="Reset timer"><RotateCcw /></button>
      </div>
    </div>
  );
}

function ToolCard({ kind, badge, title, text, cta, active, onOpen }: { kind: string; badge: string; title: string; text: string; cta: string; active: boolean; onOpen: () => void }) {
  return (
    <article className={`tp-card tp-tool${active ? " is-accent" : ""}`}>
      <div className="tp-actions" style={{ justifyContent: "space-between" }}><p className="folio">{kind}</p><span className="tp-tag">{badge}</span></div>
      <h3>{title}</h3>
      <p>{text}</p>
      <Button size="sm" variant={active ? "default" : "outline"} onClick={onOpen}>{active ? "Open above" : cta}</Button>
    </article>
  );
}
