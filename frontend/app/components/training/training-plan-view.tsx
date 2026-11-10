import { useState } from "react";
import { Link } from "react-router";
import { ArrowRight, RefreshCw } from "lucide-react";
import { Button } from "~/components/ui/button";
import type { TrainingPlan } from "~/lib/types";
import {
  BLOCK_COLORS,
  HOURS_OPTIONS,
  type HoursKey,
  VERDICTS,
  dayMinutes,
  formatDate,
  formatShortDate,
  isDue,
  percent,
  scaleMinutes,
  signedPawns,
  todayKey,
} from "./training-format";

export function TrainingPlanView({ plan, onRebuild }: { plan: TrainingPlan; onRebuild: () => void }) {
  const [hours, setHours] = useState<HoursKey>("standard");
  const { metadata, diagnosis, repertoire, routine } = plan;
  const sessionPath = `/report/${encodeURIComponent(plan.username)}/training/session`;
  const today = todayKey();
  const weekMinutes = routine.days.reduce((total, day) => total + dayMinutes(day, hours), 0);
  const maxRate = Math.max(...diagnosis.process_tags.map((tag) => tag.rate_per_100), 0.01);
  const topTags = new Set(diagnosis.top_weaknesses.map((tag) => tag.tag));
  const timeClasses = Object.entries(metadata.time_classes).map(([name, count]) => `${name[0].toUpperCase()}${name.slice(1)} ${count}`).join(" · ");
  const dueCount = plan.cards.filter((card) => isDue(card)).length;
  const ownBlocks = diagnosis.motifs.filter((motif) => motif.own_block);
  const frequentPlayed = repertoire.played.filter((row) => row.verdict !== "ignore");

  return (
    <>
      <section className="tp-masthead">
        <div>
          <p className="folio">Training plan / Built {formatDate(metadata.created_on)} from the last {metadata.games_analyzed} games</p>
          <h1>Train what<br />you <em>lose</em> to.</h1>
          <p className="tp-lead">The engine checked every move from your last {metadata.games_analyzed} games. Here is why your errors happen, the few openings to settle on, and a week of training built from both.</p>
        </div>
        <div className="tp-actions">
          <Button variant="outline" onClick={onRebuild}><RefreshCw className="h-4 w-4" /> Rebuild plan</Button>
          <Link to={sessionPath}><Button style={{ background: "var(--accent)", color: "#0a0e0b" }}>Start today's session <ArrowRight className="h-4 w-4" /></Button></Link>
        </div>
      </section>

      <div className="tp-metrics">
        <div className="tp-metric"><span className="tp-label">Games analysed</span><b>{metadata.games_analyzed}</b><small>{timeClasses}</small></div>
        <div className="tp-metric"><span className="tp-label">Errors</span><b>{diagnosis.rate_per_100.toFixed(1)}<span> / 100 moves</span></b><small>{diagnosis.error_count} mistakes and blunders · {diagnosis.blunder_count} blunders</small></div>
        <div className="tp-metric"><span className="tp-label">Rating</span><b>{metadata.rating ?? "—"}</b><small>Score {percent(metadata.score)} over these games</small></div>
        <div className="tp-metric"><span className="tp-label">Re-evaluate</span><b>{formatShortDate(metadata.reevaluate_on)}</b><small>In 6 weeks, on new games only</small></div>
      </div>

      <nav className="tp-nav" aria-label="Plan sections">
        <a href="#diagnosis"><span>01</span> Diagnosis</a>
        <a href="#repertoire"><span>02</span> Repertoire</a>
        <a href="#routine"><span>03</span> Weekly routine</a>
      </nav>

      <section id="diagnosis" className="tp-section" aria-labelledby="tp-diagnosis-heading">
        <div className="section-rule"><span>01 · Diagnosis</span><b>{diagnosis.error_count} errors</b></div>
        {diagnosis.error_count === 0 ? (
          <p className="tp-empty">No mistakes or blunders were found in these games. Try more games or a higher engine depth.</p>
        ) : (
          <>
            <div className="tp-section-head">
              <h2 id="tp-diagnosis-heading">Most of your errors come from {diagnosis.top_weaknesses[0]?.title.toLowerCase() ?? "a few habits"}.</h2>
              <p>Every mistake and blunder is labelled with why it happened. These causes account for {percent(diagnosis.top_weaknesses.reduce((total, tag) => total + tag.share, 0))} of your errors, and they shape the whole plan.</p>
            </div>
            <div className="tp-grid-3">
              {diagnosis.top_weaknesses.map((weakness, index) => (
                <article key={weakness.tag} className="tp-card is-accent tp-weak">
                  <div className="tp-weak-top">
                    <span className="tp-rank">{String(index + 1).padStart(2, "0")}</span>
                    <span className="tp-tag">{percent(weakness.share)} of errors</span>
                  </div>
                  <h4>{weakness.title}</h4>
                  <p>{weakness.definition}</p>
                  <div className="tp-prescription">
                    <p className="folio">How you'll train it</p>
                    <strong>{weakness.training}</strong>
                    <small>{weakness.rate_per_100.toFixed(1)} per 100 moves · {weakness.count} errors</small>
                  </div>
                </article>
              ))}
            </div>

            <div className="tp-grid-2" style={{ marginTop: "1.25rem" }}>
              <div className="tp-card">
                <div className="tp-sub-head"><h3>All causes</h3><p>Errors per 100 moves</p></div>
                <div className="tp-bars">
                  {diagnosis.process_tags.map((tag) => (
                    <div key={tag.tag} className={`tp-bar${topTags.has(tag.tag) ? " is-hot" : ""}`}>
                      <span>{tag.title}</span>
                      <div className="tp-track" role="img" aria-label={`${tag.title}: ${tag.rate_per_100.toFixed(1)} per 100 moves`}>
                        <div className="tp-fill" style={{ width: `${(tag.rate_per_100 / maxRate) * 100}%` }} />
                      </div>
                      <span className="tp-bar-value">{tag.rate_per_100.toFixed(1)}</span>
                    </div>
                  ))}
                </div>
                <p className="tp-note">Each error gets one cause from simple rules, so treat it as a first guess. You confirm or change it during your sessions.</p>
              </div>
              <div className="tp-card">
                <div className="tp-sub-head"><h3>What else stands out</h3></div>
                {diagnosis.insights.length ? (
                  <ul className="tp-insights">
                    {diagnosis.insights.map((insight, index) => (
                      <li key={insight.headline}><span>{String(index + 1).padStart(2, "0")}</span><div><b>{insight.headline}</b> {insight.detail}</div></li>
                    ))}
                  </ul>
                ) : <p className="tp-note">Nothing else stands out yet. More games will sharpen the picture.</p>}
                <div className="tp-actions" style={{ marginTop: "1rem" }}>
                  <span className="tp-label">Motifs to drill</span>
                  {ownBlocks.length
                    ? ownBlocks.map((motif) => <span key={motif.motif} className="tp-chip is-good">{motif.motif} · {motif.count}</span>)
                    : <span className="tp-chip is-muted">None yet: a motif needs 4+ errors in 3+ games</span>}
                </div>
              </div>
            </div>
          </>
        )}
      </section>

      <section id="repertoire" className="tp-section" aria-labelledby="tp-repertoire-heading">
        <div className="section-rule"><span>02 · Opening repertoire</span><b>{repertoire.recommended.length} openings</b></div>
        <div className="tp-section-head">
          <h2 id="tp-repertoire-heading">
            {repertoire.mode === "simple" ? "A few short openings. Learn them, then stop thinking about openings." : "Your own lines, learned deeper."}
          </h2>
          <p>
            {repertoire.mode === "simple"
              ? "At this level, points are lost in the middlegame, not in the theory. So the plan picks solid openings where the theory ends early and you get a normal middlegame quickly, and sticks with them."
              : "Your errors start early enough that opening work pays off. The plan keeps the lines you already play and takes them 8–12 moves deep."}
          </p>
        </div>

        <div className="tp-card tp-mode">
          <div>
            <p className="folio">Repertoire mode</p>
            <h3>{repertoire.mode === "simple" ? "Simple, short lines" : "Deeper main lines"}</h3>
          </div>
          {repertoire.reasons.map((reason) => (
            <div key={reason} className="tp-reason"><span className="tp-chip is-good" aria-hidden="true">✓</span><span>{reason}</span></div>
          ))}
        </div>

        <div className="tp-grid-3">
          {repertoire.recommended.map((opening) => (
            <article key={opening.slot} className="tp-card tp-rep">
              <p className="folio">{opening.slot_label}</p>
              <h4>{opening.name}</h4>
              <div className="tp-line">{opening.line}</div>
              <div className="tp-actions"><span className="tp-tag">{opening.learn_depth}</span>{opening.your_games ? <span className="tp-tag">You: {opening.your_games} games · {percent(opening.your_score)}</span> : <span className="tp-tag">New for you</span>}</div>
              <dl className="tp-kv">
                <dt>Why this</dt><dd>{opening.why}</dd>
                {opening.plans ? <><dt>Plans</dt><dd>{opening.plans}</dd></> : null}
                {opening.trap ? <><dt>Trap</dt><dd>{opening.trap}</dd></> : null}
                {opening.replaces.length ? <><dt>Replaces</dt><dd>{opening.replaces.join(", ")}</dd></> : null}
              </dl>
            </article>
          ))}
        </div>
        {frequentPlayed.length ? (
          <details className="tp-note">
            <summary style={{ cursor: "pointer", color: "var(--ink)" }}>What you play now ({frequentPlayed.length} lines with 3+ games)</summary>
            <ul style={{ margin: ".75rem 0 0", paddingLeft: "1.1rem", display: "grid", gap: ".4rem" }}>
              {frequentPlayed.map((row) => (
                <li key={`${row.slot}-${row.choice}`}>
                  <b style={{ color: "var(--ink)" }}>{row.slot_label} · {row.choice}</b> ({row.name}) — {row.games} games, {percent(row.score)}, eval at move 15 {signedPawns(row.avg_eval_at_15)}{row.first_error_move ? `, first error around move ${row.first_error_move}` : ""}{" "}
                  <span className={`tp-chip ${VERDICTS[row.verdict].tone}`}>{VERDICTS[row.verdict].label}</span>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
        <p className="tp-note">Against anything else, use opening principles: develop, castle, and take your share of the centre. Add a line only after it comes up in your own games several times.</p>
      </section>

      <section id="routine" className="tp-section" aria-labelledby="tp-routine-heading">
        <div className="section-rule"><span>03 · Weekly routine</span><b>≈ {(weekMinutes / 60).toFixed(1)} h / week</b></div>
        <div className="tp-section-head">
          <h2 id="tp-routine-heading">One session a day, built around your top two weaknesses.</h2>
          <p>Tuesday and Thursday go to your two biggest weaknesses. Wednesday drills your openings. Each session opens in the training page with everything you need for it.</p>
        </div>
        <div className="tp-actions" style={{ justifyContent: "space-between", marginBottom: "1.25rem" }}>
          <div className="tp-seg" role="group" aria-label="Hours per week">
            {HOURS_OPTIONS.map((option) => (
              <button key={option.key} type="button" aria-pressed={hours === option.key} onClick={() => setHours(option.key)}>{option.label}</button>
            ))}
          </div>
          <div className="tp-legend">
            {BLOCK_COLORS.map((item) => <span key={item.label}><i style={{ background: item.color }} />{item.label}</span>)}
          </div>
        </div>
        <div className="tp-week">
          {routine.days.map((day) => (
            <article key={day.day} className={`tp-day${day.session === "weakness" ? " is-weakness" : ""}${day.session === "play" ? " is-play" : ""}${day.day === today ? " is-today" : ""}`}>
              <div className="tp-day-top"><b>{day.day}</b><span>{dayMinutes(day, hours)} min</span></div>
              <h5>{day.focus}</h5>
              {day.blocks.map((block, index) => (
                <div key={index} className="tp-block" data-kind={block.kind}>
                  <div className="tp-block-head"><span>{block.label}</span><i>{scaleMinutes(block.minutes, hours)}′</i></div>
                  <p>{block.text}</p>
                </div>
              ))}
              <Link to={`${sessionPath}?day=${day.day}&hours=${hours}`} style={{ marginTop: "auto" }}>
                <Button size="sm" variant="outline" className="w-full">{day.day === today ? "Start · today" : "Open session"}</Button>
              </Link>
            </article>
          ))}
        </div>
        <div className="tp-week-total">
          <span>Total <b>{weekMinutes} min</b></span>
          <span>{dueCount} flashcards due · puzzles {percent(routine.puzzle_split.mixed)} mixed, {percent(routine.puzzle_split.themed)} themed</span>
        </div>
      </section>

      <section className="tp-closing" aria-labelledby="tp-next-heading">
        <div>
          <p className="folio">Next check · {formatDate(metadata.reevaluate_on)}</p>
          <h3 id="tp-next-heading">In six weeks, rebuild this on your new games.</h3>
          <p>Use the same engine depth. If a weakness improves, it gets less time and the next one moves up. If nothing changes after two checks, the diagnosis or the training method needs another look.</p>
        </div>
        <div className="tp-actions">
          <Button size="sm" variant="outline" onClick={onRebuild}><RefreshCw className="h-4 w-4" /> Rebuild plan</Button>
        </div>
      </section>
    </>
  );
}
