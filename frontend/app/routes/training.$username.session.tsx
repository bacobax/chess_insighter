import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ArrowLeft, Loader2 } from "lucide-react";
import { AppShell } from "~/components/layout/app-shell";
import { Button } from "~/components/ui/button";
import { HOURS_OPTIONS, type HoursKey, todayKey } from "~/components/training/training-format";
import { TrainingSession } from "~/components/training/training-session";
import { getTrainingPlan } from "~/lib/api";
import type { TrainingPlan } from "~/lib/types";

export default function TrainingSessionPage() {
  const { username = "" } = useParams();
  const [searchParams] = useSearchParams();
  const [plan, setPlan] = useState<TrainingPlan | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const dayKey = searchParams.get("day") ?? todayKey();
  const hoursParam = searchParams.get("hours");
  const hours: HoursKey = HOURS_OPTIONS.some((option) => option.key === hoursParam) ? (hoursParam as HoursKey) : "standard";

  useEffect(() => {
    getTrainingPlan(username).then(setPlan).catch((err) => setError(err instanceof Error ? err.message : "Could not load the training plan."));
  }, [username]);

  const planPath = `/report/${encodeURIComponent(username)}/training`;
  return (
    <AppShell>
      <main id="main-content" className="editorial-shell">
        <Link to={planPath} className="tp-back"><ArrowLeft /> {username} · training plan</Link>
        {error ? <p className="form-error">{error}</p> : null}
        {plan === undefined && !error ? <div className="dashboard-loading"><Loader2 className="animate-spin" /> Loading session…</div> : null}
        {plan === null ? (
          <div className="tp-empty" style={{ marginTop: "2rem" }}>
            <p className="folio">No training plan yet</p>
            <p>Build a plan first. Your sessions come from it.</p>
            <Link to={planPath}><Button>Build training plan</Button></Link>
          </div>
        ) : null}
        {plan ? <TrainingSession key={dayKey} plan={plan} dayKey={dayKey} hours={hours} /> : null}
      </main>
    </AppShell>
  );
}
