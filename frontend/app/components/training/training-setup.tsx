import { useState } from "react";
import type { FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "~/components/ui/button";
import { cancelTrainingPlanBuild, getTrainingPlan, getTrainingPlanBuildStatus, startTrainingPlanBuild, trainingPlanBuildSocketUrl } from "~/lib/api";
import { waitForBuild } from "~/lib/build-jobs";
import type { ReportBuildJobAccepted, ReportBuildJobStatus, TrainingPlan, TrainingPlanBuildRequest, TrainingTimeClass } from "~/lib/types";

const TIME_CLASSES: { key: TrainingTimeClass; label: string }[] = [
  { key: "bullet", label: "Bullet" },
  { key: "blitz", label: "Blitz" },
  { key: "rapid", label: "Rapid" },
  { key: "daily", label: "Daily" },
];

const DEPTHS = [
  { depth: 10, label: "Depth 10 · fast" },
  { depth: 12, label: "Depth 12 · recommended" },
  { depth: 16, label: "Depth 16 · slow" },
];

const STAGES = [
  { key: "fetching_games", label: "Fetch your games from Chess.com" },
  { key: "filtering", label: "Skip variants and games under 10 moves" },
  { key: "engine", label: "Engine analysis and mistake detection" },
  { key: "plan", label: "Diagnose errors and build the plan" },
];

function gamesHint(games: number): string {
  if (games < 50) return "Under 50 games the diagnosis gets noisy. 50–100 is recommended.";
  if (games > 100) return "Over 100 games starts to include older habits. 50–100 is recommended.";
  return "Recommended range: 50–100 games.";
}

function stageState(stage: string, index: number): "done" | "now" | "todo" {
  const current = STAGES.findIndex((item) => item.key === (stage === "mistakes" ? "engine" : stage));
  if (stage === "complete" || index < current) return "done";
  return index === current ? "now" : "todo";
}

export function TrainingSetup({
  username,
  initial,
  onComplete,
  onCancel,
}: {
  username: string;
  initial?: TrainingPlanBuildRequest | null;
  onComplete: (plan: TrainingPlan) => void;
  onCancel?: () => void;
}) {
  const [maxGames, setMaxGames] = useState(initial?.max_games ?? 80);
  const [timeClasses, setTimeClasses] = useState<TrainingTimeClass[]>(initial?.time_classes ?? ["blitz", "rapid"]);
  const [depth, setDepth] = useState(initial?.engine_depth ?? 12);
  const [job, setJob] = useState<ReportBuildJobAccepted | null>(null);
  const [progress, setProgress] = useState<ReportBuildJobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  function toggleClass(key: TrainingTimeClass) {
    setTimeClasses((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]);
  }

  async function build(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setProgress(null);
    try {
      const accepted = await startTrainingPlanBuild({
        username,
        max_games: maxGames,
        time_classes: timeClasses.length ? timeClasses : null,
        engine_depth: depth,
      });
      setJob(accepted);
      const terminal = await waitForBuild(accepted, setProgress, trainingPlanBuildSocketUrl, getTrainingPlanBuildStatus);
      if (terminal.status !== "completed") {
        throw new Error(terminal.error ?? (terminal.status === "cancelled" ? "Training plan build cancelled." : "Could not build the training plan."));
      }
      const plan = await getTrainingPlan(username);
      if (!plan) throw new Error("The training plan finished but could not be loaded.");
      onComplete(plan);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build the training plan.");
    } finally {
      setJob(null);
    }
  }

  const running = job !== null;
  const pct = Math.round((progress?.progress ?? 0) * 100);

  return (
    <div className="tp-setup">
      <form className="tp-card" style={{ padding: ".5rem 1.75rem" }} onSubmit={build} aria-label="Training plan settings">
        <div className="tp-field">
          <label htmlFor="tp-games">Number of recent games</label>
          <div className="tp-range">
            <input id="tp-games" type="range" min={30} max={150} step={10} value={maxGames} disabled={running} onChange={(event) => setMaxGames(Number(event.target.value))} />
            <output htmlFor="tp-games">{maxGames}</output>
          </div>
          <small>{gamesHint(maxGames)}</small>
        </div>
        <div className="tp-field">
          <span className="tp-field-label" id="tp-classes">Time classes</span>
          <div className="tp-pills" role="group" aria-labelledby="tp-classes">
            {TIME_CLASSES.map((item) => (
              <button key={item.key} type="button" className="tp-pill" aria-pressed={timeClasses.includes(item.key)} disabled={running} onClick={() => toggleClass(item.key)}>{item.label}</button>
            ))}
          </div>
          <small>Pick your main time class plus one slower one. With none selected, all of them are used.</small>
        </div>
        <div className="tp-field">
          <span className="tp-field-label" id="tp-depth">Engine depth</span>
          <div className="tp-pills" role="group" aria-labelledby="tp-depth">
            {DEPTHS.map((item) => (
              <button key={item.depth} type="button" className="tp-pill" aria-pressed={depth === item.depth} disabled={running} onClick={() => setDepth(item.depth)}>{item.label}</button>
            ))}
          </div>
          <small>Every move is checked at this depth, then each mistake gets a refutation line. Use the same depth when you re-evaluate. Games already analysed in an earlier training build are reused.</small>
        </div>
        <div className="tp-field">
          <span className="tp-field-label">Always applied</span>
          <small>Standard chess only. Games under 10 moves (aborts, early resignations) are skipped.</small>
        </div>
        <div className="tp-field tp-actions">
          <Button type="submit" disabled={running} style={{ background: "var(--accent)", color: "#0a0e0b" }}>
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Build training plan
          </Button>
          {onCancel && !running ? <Button type="button" variant="ghost" onClick={onCancel}>Back to current plan</Button> : null}
        </div>
      </form>

      <aside style={{ display: "grid", gap: "1.25rem" }}>
        <div className="tp-progress" aria-live="polite">
          <div className="tp-progress-top">
            <div>
              <p className="folio">{running ? "Building" : error ? "Stopped" : "Ready"}</p>
              <p style={{ margin: ".4rem 0 0", color: "var(--ink-soft)", fontSize: ".85rem" }}>
                {progress?.message ?? (running ? "Starting…" : "Nothing is running yet.")}
              </p>
            </div>
            <b>{pct}%</b>
          </div>
          <div className="tp-ptrack"><div style={{ width: `${pct}%` }} /></div>
          <ol className="tp-steps">
            {STAGES.map((stage, index) => {
              const state = progress ? stageState(progress.stage, index) : "todo";
              return (
                <li key={stage.key} data-state={state}>
                  <span className="tp-step-dot" aria-hidden="true">{state === "done" ? "✓" : state === "now" ? "•" : ""}</span>
                  <span>{stage.label}</span>
                </li>
              );
            })}
          </ol>
          {error ? <p className="form-error">{error}</p> : null}
          {running ? (
            <div className="tp-actions">
              <Button type="button" size="sm" variant="outline" onClick={() => job && void cancelTrainingPlanBuild(job.build_id)}>Stop</Button>
              <small style={{ color: "var(--ink-soft)" }}>Keep this page open: leaving it stops the build after 30 seconds.</small>
            </div>
          ) : null}
        </div>
        <div className="tp-card">
          <p className="folio">What comes out</p>
          <ol className="tp-trio" style={{ marginTop: ".75rem" }}>
            <li><span>01</span><div><b>Diagnosis</b><small>Your top 3 error causes and how to train each one</small></div></li>
            <li><span>02</span><div><b>Repertoire</b><small>A few short openings to learn, matched to your level</small></div></li>
            <li><span>03</span><div><b>Weekly routine</b><small>A session a day, with flashcards from your own errors</small></div></li>
          </ol>
        </div>
      </aside>
    </div>
  );
}
