import { useState } from "react";
import type { FormEvent } from "react";
import { ExternalLink, Trash2 } from "lucide-react";
import { Button } from "~/components/ui/button";
import { localIsoDate, formatShortDate } from "./training-format";
import { usePersistentState } from "./training-hooks";

const CHECKS = [
  { key: "checks", label: "Their checks", detail: "Every check they could give after your move." },
  { key: "captures", label: "Their captures", detail: "Every capture, including ones that look bad for them." },
  { key: "threats", label: "Their threats", detail: "What their last move wants to do next." },
];

const PRESETS = [
  { label: "10+0", base: 10, increment: 0 },
  { label: "15+10", base: 15, increment: 10 },
  { label: "30+0", base: 30, increment: 0 },
  { label: "30+20", base: 30, increment: 20 },
];

// Share of the base clock to still have at each move: half of it at move 20.
const CHECKPOINTS = [
  { move: 10, share: 0.75 },
  { move: 20, share: 0.5 },
  { move: 30, share: 0.3 },
];

const CAUSES = ["missed threat", "missed opportunity", "miscalculation", "misjudged position", "hope chess", "conversion", "time trouble", "nothing major"];

type LogEntry = { id: string; date: string; opponent: string; result: string; criticalMove: string; cause: string; why: string; lesson: string };

function formatMinutes(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.round(seconds % 60)).padStart(2, "0")}`;
}

/** Slow-game routine: the blunder check, a clock budget, and a post-game log. */
export function GameChecklist({ username, focus }: { username: string; focus: "play" | "review" }) {
  const key = username.toLowerCase();
  const [ticks, setTicks] = usePersistentState<Record<string, number>>(`tp:checks:${key}:${localIsoDate()}`, {});
  const [preset, setPreset] = usePersistentState(`tp:clock:${key}`, 1);
  const [log, setLog] = usePersistentState<LogEntry[]>(`tp:gamelog:${key}`, []);
  const clock = PRESETS[preset] ?? PRESETS[1];

  const checklist = (
    <section className="tp-card" aria-labelledby="tp-checks-h" style={{ display: "grid", gap: "1rem" }}>
      <div>
        <p className="folio">Before every move</p>
        <h3 id="tp-checks-h" className="tp-panel-subtitle">The blunder check</h3>
      </div>
      <div className="tp-check-grid">
        {CHECKS.map((check, index) => (
          <button key={check.key} type="button" className="tp-check-card" onClick={() => setTicks((current) => ({ ...current, [check.key]: (current[check.key] ?? 0) + 1 }))}>
            <span className="tp-check-index">{index + 1}</span>
            <b>{check.label}</b>
            <small>{check.detail}</small>
            <span className="tp-label">Used {ticks[check.key] ?? 0}× today</span>
          </button>
        ))}
      </div>
      <p className="tp-note" style={{ margin: 0 }}>Tap a card each time you run that check during today's game. It builds the habit, and the counts show which check you skip.</p>
    </section>
  );

  const budget = (
    <section className="tp-card" aria-labelledby="tp-clock-h" style={{ display: "grid", gap: "1rem" }}>
      <div className="tp-actions" style={{ justifyContent: "space-between" }}>
        <div>
          <p className="folio">Clock budget</p>
          <h3 id="tp-clock-h" className="tp-panel-subtitle">Half your clock at move 20</h3>
        </div>
        <div className="tp-seg" role="group" aria-label="Time control">
          {PRESETS.map((item, index) => (
            <button key={item.label} type="button" aria-pressed={index === preset} onClick={() => setPreset(index)}>{item.label}</button>
          ))}
        </div>
      </div>
      <div className="tp-bars">
        {CHECKPOINTS.map((point) => {
          const seconds = clock.base * 60 * point.share + clock.increment * point.move;
          const total = clock.base * 60 + clock.increment * point.move;
          return (
            <div key={point.move} className="tp-bar is-hot">
              <span>By move {point.move}</span>
              <div className="tp-track"><div className="tp-fill" style={{ width: `${(seconds / total) * 100}%` }} /></div>
              <span className="tp-bar-value">{formatMinutes(seconds)}</span>
            </div>
          );
        })}
      </div>
      <p className="tp-note" style={{ margin: 0 }}>Clock you should still have left, increments included. Fall behind and you're heading for time trouble.</p>
    </section>
  );

  const review = <ReviewLog log={log} onAdd={(entry) => setLog((current) => [entry, ...current].slice(0, 50))} onRemove={(id) => setLog((current) => current.filter((item) => item.id !== id))} />;

  return (
    <div style={{ display: "grid", gap: "1.25rem" }}>
      <div className="tp-actions" style={{ justifyContent: "space-between", alignItems: "end" }}>
        <div>
          <p className="folio">{focus === "play" ? "Slow game · 15+10 or longer" : "Self-review"}</p>
          <h2 className="tp-panel-title">{focus === "play" ? "Play one slow game with the checklist open." : "Review the game yourself before the engine."}</h2>
        </div>
        {focus === "play" ? (
          <a href="https://www.chess.com/play/online" target="_blank" rel="noreferrer"><Button variant="outline">Play on Chess.com <ExternalLink className="h-4 w-4" /></Button></a>
        ) : null}
      </div>
      {focus === "play" ? <>{checklist}{budget}{review}</> : <>{review}{checklist}</>}
    </div>
  );
}

function ReviewLog({ log, onAdd, onRemove }: { log: LogEntry[]; onAdd: (entry: LogEntry) => void; onRemove: (id: string) => void }) {
  const [draft, setDraft] = useState({ opponent: "", result: "loss", criticalMove: "", cause: CAUSES[0], why: "", lesson: "" });
  const update = (field: keyof typeof draft) => (event: { target: { value: string } }) => setDraft((current) => ({ ...current, [field]: event.target.value }));

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.why.trim() && !draft.criticalMove.trim()) return;
    onAdd({ id: `${Date.now()}`, date: localIsoDate(), ...draft });
    setDraft((current) => ({ ...current, opponent: "", criticalMove: "", why: "", lesson: "" }));
  }

  return (
    <section className="tp-card" aria-labelledby="tp-log-h" style={{ display: "grid", gap: "1rem" }}>
      <div>
        <p className="folio">After the game · under 10 minutes</p>
        <h3 id="tp-log-h" className="tp-panel-subtitle">Find the critical moment</h3>
      </div>
      <form className="tp-log-form" onSubmit={submit}>
        <label className="tp-input"><span className="tp-label">Opponent</span><input value={draft.opponent} onChange={update("opponent")} placeholder="Optional" /></label>
        <label className="tp-input"><span className="tp-label">Result</span>
          <select value={draft.result} onChange={update("result")}><option value="win">Win</option><option value="draw">Draw</option><option value="loss">Loss</option></select>
        </label>
        <label className="tp-input"><span className="tp-label">Critical move</span><input value={draft.criticalMove} onChange={update("criticalMove")} placeholder="e.g. 23…Qc2" /></label>
        <label className="tp-input"><span className="tp-label">What went wrong</span>
          <select value={draft.cause} onChange={update("cause")}>{CAUSES.map((cause) => <option key={cause}>{cause}</option>)}</select>
        </label>
        <label className="tp-input tp-log-wide"><span className="tp-label">Why</span><textarea value={draft.why} onChange={update("why")} placeholder="One or two sentences, before you turn on the engine" /></label>
        <label className="tp-input tp-log-wide"><span className="tp-label">Lesson for next time</span><input value={draft.lesson} onChange={update("lesson")} placeholder="Optional" /></label>
        <div className="tp-log-wide"><Button type="submit" size="sm">Add to error log</Button></div>
      </form>
      {log.length ? (
        <ul className="tp-log-list">
          {log.slice(0, 8).map((entry) => (
            <li key={entry.id}>
              <span className="tp-label">{formatShortDate(entry.date)}</span>
              <div>
                <b>{entry.criticalMove || "Game"}{entry.opponent ? ` vs ${entry.opponent}` : ""} · {entry.result}</b>
                <small>{entry.cause}{entry.why ? ` — ${entry.why}` : ""}{entry.lesson ? ` Lesson: ${entry.lesson}` : ""}</small>
              </div>
              <button type="button" onClick={() => onRemove(entry.id)} aria-label="Delete entry"><Trash2 className="h-4 w-4" /></button>
            </li>
          ))}
        </ul>
      ) : <p className="tp-note" style={{ margin: 0 }}>Your game log is empty. It is saved in this browser only.</p>}
    </section>
  );
}
