import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ArrowRight } from "lucide-react";
import { Button } from "~/components/ui/button";
import { getTrainingPlan } from "~/lib/api";
import type { TrainingPlan } from "~/lib/types";
import { formatDate, isDue } from "./training-format";

/** Player-dossier card that opens the training plan without needing a report. */
export function TrainingPlanEntry({ username }: { username: string }) {
  const [plan, setPlan] = useState<TrainingPlan | null | undefined>(undefined);
  useEffect(() => { getTrainingPlan(username).then(setPlan).catch(() => setPlan(null)); }, [username]);
  const base = `/report/${encodeURIComponent(username)}/training`;

  return (
    <div className="tp-feature">
      <div>
        <p className="folio">Built from your recent games</p>
        <h2>Turn your last games into a plan for the week.</h2>
        <p>The engine checks every move in your last games, the same way the mistakes analyzer does. You get back three things you can work from straight away.</p>
        <div className="tp-actions" style={{ marginTop: "1.75rem" }}>
          {plan ? (
            <>
              <Link to={base}><Button style={{ background: "var(--accent)", color: "#0a0e0b" }}>Open training plan <ArrowRight /></Button></Link>
              <Link to={`${base}/session`}><Button variant="ghost">Today's session</Button></Link>
            </>
          ) : (
            <Link to={base}><Button style={{ background: "var(--accent)", color: "#0a0e0b" }} disabled={plan === undefined}>Build training plan <ArrowRight /></Button></Link>
          )}
        </div>
        {plan ? (
          <div className="tp-status-line">
            <span>Last plan {formatDate(plan.metadata.created_on)} · {plan.metadata.games_analyzed} games</span>
            <span>{plan.cards.filter((card) => isDue(card)).length} flashcards due</span>
            <span>Next check {formatDate(plan.metadata.reevaluate_on)}</span>
          </div>
        ) : null}
      </div>
      <ol className="tp-trio">
        <li><span>01</span><div><b>Diagnosis of your errors</b><small>Why you make them, where in the game, and the motifs to drill</small></div></li>
        <li><span>02</span><div><b>Opening repertoire</b><small>A few short openings to learn and stick with</small></div></li>
        <li><span>03</span><div><b>Weekly training routine</b><small>A session a day, built around your top two weaknesses</small></div></li>
      </ol>
    </div>
  );
}
