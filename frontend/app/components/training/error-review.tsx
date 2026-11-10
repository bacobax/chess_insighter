import { useMemo, useState } from "react";
import { Play, Shuffle } from "lucide-react";
import { MiniChessBoard } from "~/components/opening-study/MiniChessBoard";
import { Button } from "~/components/ui/button";
import type { TrainingCard } from "~/lib/types";
import { CardExercise } from "./card-exercise";
import { formatShortDate, isDue, moveLabel, percent } from "./training-format";

const LADDER = [
  { key: "new", label: "New", test: (card: TrainingCard) => card.reviews === 0 },
  { key: "1", label: "1 day", test: (card: TrainingCard) => card.reviews > 0 && card.interval_days <= 1 && !card.retired },
  { key: "3", label: "3 days", test: (card: TrainingCard) => card.interval_days === 3 && !card.retired },
  { key: "7", label: "7 days", test: (card: TrainingCard) => card.interval_days === 7 && !card.retired },
  { key: "21", label: "21 days", test: (card: TrainingCard) => card.interval_days >= 21 && !card.retired },
  { key: "retired", label: "Retired", test: (card: TrainingCard) => card.retired },
];

const PHASES: Record<string, string> = {
  opening: "Opening",
  middlegame_tactics: "Middlegame · tactics",
  middlegame_positional: "Middlegame · positional",
  endgame: "Endgame",
};

type Sort = "loss" | "due" | "recent";

function shuffled<T>(items: T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

/** Flashcards: the spaced-repetition ladder, then the due cards. */
export function FlashcardDeck({ username, cards, onReviewed }: { username: string; cards: TrainingCard[]; onReviewed: (card: TrainingCard) => void }) {
  const [queue, setQueue] = useState<TrainingCard[] | null>(null);
  const due = cards.filter((card) => isDue(card));
  const active = cards.filter((card) => !card.retired);
  if (queue) return <CardExercise username={username} queue={queue} title="Flashcards" onReviewed={onReviewed} onExit={() => setQueue(null)} onClose={() => setQueue(null)} />;

  return (
    <div style={{ display: "grid", gap: "1.25rem" }}>
      <div>
        <p className="folio">Flashcards · your own positions</p>
        <h2 className="tp-panel-title">{due.length ? `${due.length} ${due.length === 1 ? "card is" : "cards are"} due today.` : "Nothing due today."}</h2>
        <p className="tp-note" style={{ marginTop: ".5rem" }}>Each mistake from your games comes back after 1, 3, 7 and 21 days. A card retires after three correct answers in a row, 7 or more days apart.</p>
      </div>
      <div className="tp-ladder" role="list" aria-label="Cards by review interval">
        {LADDER.map((step) => {
          const count = cards.filter(step.test).length;
          return (
            <div key={step.key} role="listitem" data-empty={count === 0}>
              <b>{count}</b>
              <span>{step.label}</span>
              <i style={{ height: `${cards.length ? Math.max(6, (count / cards.length) * 100) : 0}%` }} aria-hidden="true" />
            </div>
          );
        })}
      </div>
      <div className="tp-actions">
        <Button disabled={!due.length} onClick={() => setQueue(due.slice(0, 20))} style={{ background: "var(--accent)", color: "#0a0e0b" }}>
          <Play className="h-4 w-4" /> Review {Math.min(due.length, 20)} due
        </Button>
        <Button variant="outline" disabled={!active.length} onClick={() => setQueue(shuffled(active).slice(0, 10))}>
          <Shuffle className="h-4 w-4" /> Cram 10 random
        </Button>
      </div>
    </div>
  );
}

/** Browse every error with filters, then practise any selection. */
export function ErrorReview({
  username,
  cards,
  initialProcess,
  onReviewed,
}: {
  username: string;
  cards: TrainingCard[];
  initialProcess?: string | null;
  onReviewed: (card: TrainingCard) => void;
}) {
  const [process, setProcess] = useState<string | null>(initialProcess ?? null);
  const [phase, setPhase] = useState<string | null>(null);
  const [severity, setSeverity] = useState<string | null>(null);
  const [showRetired, setShowRetired] = useState(false);
  const [sort, setSort] = useState<Sort>("loss");
  const [queue, setQueue] = useState<TrainingCard[] | null>(null);

  const processCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const card of cards) counts.set(card.process, (counts.get(card.process) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [cards]);

  const filtered = useMemo(() => {
    const rows = cards.filter((card) =>
      (showRetired || !card.retired)
      && (!process || (card.label ?? card.process) === process)
      && (!phase || card.domain === phase)
      && (!severity || card.severity === severity),
    );
    const by: Record<Sort, (a: TrainingCard, b: TrainingCard) => number> = {
      loss: (a, b) => (b.wp_loss ?? 0) - (a.wp_loss ?? 0),
      due: (a, b) => a.due_on.localeCompare(b.due_on),
      recent: (a, b) => (b.game_end_time ?? 0) - (a.game_end_time ?? 0),
    };
    return rows.sort(by[sort]);
  }, [cards, process, phase, severity, showRetired, sort]);

  if (queue) return <CardExercise username={username} queue={queue} title="Error review" onReviewed={onReviewed} onExit={() => setQueue(null)} onClose={() => setQueue(null)} />;

  return (
    <div style={{ display: "grid", gap: "1.25rem" }}>
      <div className="tp-actions" style={{ justifyContent: "space-between", alignItems: "end" }}>
        <div>
          <p className="folio">Error review</p>
          <h2 className="tp-panel-title">{filtered.length} of {cards.length} errors</h2>
        </div>
        <Button disabled={!filtered.length} onClick={() => setQueue(filtered.slice(0, 15))} style={{ background: "var(--accent)", color: "#0a0e0b" }}>
          <Play className="h-4 w-4" /> Practise {Math.min(filtered.length, 15)}
        </Button>
      </div>

      <div className="tp-filters">
        <div className="tp-pills" role="group" aria-label="Filter by cause">
          <button type="button" className="tp-pill" aria-pressed={process === null} onClick={() => setProcess(null)}>All causes</button>
          {processCounts.map(([name, count]) => (
            <button key={name} type="button" className="tp-pill" aria-pressed={process === name} onClick={() => setProcess(process === name ? null : name)}>
              {name.replace(/_/g, " ")} · {count}
            </button>
          ))}
        </div>
        <div className="tp-filter-row">
          <label className="tp-select">
            <span>Phase</span>
            <select value={phase ?? ""} onChange={(event) => setPhase(event.target.value || null)}>
              <option value="">All</option>
              {Object.entries(PHASES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          </label>
          <label className="tp-select">
            <span>Severity</span>
            <select value={severity ?? ""} onChange={(event) => setSeverity(event.target.value || null)}>
              <option value="">All</option>
              <option value="blunder">Blunders</option>
              <option value="mistake">Mistakes</option>
            </select>
          </label>
          <label className="tp-select">
            <span>Sort</span>
            <select value={sort} onChange={(event) => setSort(event.target.value as Sort)}>
              <option value="loss">Biggest loss first</option>
              <option value="due">Due soonest</option>
              <option value="recent">Most recent game</option>
            </select>
          </label>
          <label className="check" style={{ display: "flex", gap: ".5rem", alignItems: "center", color: "var(--ink-soft)", fontSize: ".82rem", minHeight: 44 }}>
            <input type="checkbox" checked={showRetired} onChange={(event) => setShowRetired(event.target.checked)} style={{ width: 18, height: 18, accentColor: "#21e783" }} />
            Show retired
          </label>
        </div>
      </div>

      {filtered.length ? (
        <ul className="tp-error-list">
          {filtered.slice(0, 60).map((card, index) => (
            <li key={card.card_id}>
              <button type="button" onClick={() => setQueue([card, ...filtered.filter((other) => other.card_id !== card.card_id).slice(0, 14)])} aria-label={`Practise ${moveLabel(card, card.played_san)}`}>
                <MiniChessBoard fen={card.fen_before} size={72} flipped={card.player_color === "black"} highlights={{ [card.played_uci.slice(0, 2)]: "from", [card.played_uci.slice(2, 4)]: "to" }} />
                <span className="tp-error-main">
                  <b>{moveLabel(card, card.played_san)} <span className="tp-label" style={{ letterSpacing: ".06em" }}>{card.severity}</span></b>
                  <small>{(card.label ?? card.process).replace(/_/g, " ")} · {PHASES[card.domain] ?? card.domain}{card.motifs.length ? ` · ${card.motifs.join(", ")}` : ""}</small>
                  <small>{card.opponent ? `vs ${card.opponent}` : ""}{card.note ? ` · “${card.note}”` : ""}</small>
                </span>
                <span className="tp-error-meta">
                  <b className="tp-neg">−{percent(card.wp_loss)}</b>
                  <small>{card.retired ? "Retired" : isDue(card) ? "Due now" : `Due ${formatShortDate(card.due_on)}`}</small>
                  <small className="tp-error-go">#{index + 1} · Practise →</small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="tp-empty">No errors match these filters.</p>
      )}
      {filtered.length > 60 ? <p className="tp-note">Showing the first 60. Narrow the filters to see the rest.</p> : null}
    </div>
  );
}
