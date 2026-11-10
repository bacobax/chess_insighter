import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ArrowLeft, Loader2 } from "lucide-react";
import { AppShell } from "~/components/layout/app-shell";
import { TrainingPlanView } from "~/components/training/training-plan-view";
import { TrainingSetup } from "~/components/training/training-setup";
import { getTrainingPlan } from "~/lib/api";
import type { TrainingPlan } from "~/lib/types";

export default function TrainingPlanPage() {
  const { username = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [plan, setPlan] = useState<TrainingPlan | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const setup = searchParams.get("view") === "setup";

  useEffect(() => {
    setPlan(undefined);
    getTrainingPlan(username).then(setPlan).catch((err) => setError(err instanceof Error ? err.message : "Could not load the training plan."));
  }, [username]);

  const dossier = `/report/${encodeURIComponent(username)}`;
  return (
    <AppShell>
      <main id="main-content" className="editorial-shell">
        <Link to={dossier} className="tp-back"><ArrowLeft /> {username} · dossier</Link>
        {error ? <p className="form-error">{error}</p> : null}
        {plan === undefined && !error ? <div className="dashboard-loading"><Loader2 className="animate-spin" /> Loading training plan…</div> : null}
        {plan === null || (plan && setup) ? (
          <>
            <section className="tp-masthead" style={{ paddingBottom: "2rem" }}>
              <div>
                <p className="folio">Training plan / {plan ? "Rebuild" : "New build"}</p>
                <h1>Which games<br />should we read?</h1>
                <p className="tp-lead">Pick the games to use. The engine then checks every move you played, the same way the mistakes analyzer does, and turns the result into a plan. A build takes a few minutes.</p>
              </div>
            </section>
            <TrainingSetup
              username={username}
              initial={plan?.request_params}
              onComplete={(built) => { setPlan(built); setSearchParams({}); }}
              onCancel={plan ? () => setSearchParams({}) : undefined}
            />
          </>
        ) : null}
        {plan && !setup ? <TrainingPlanView plan={plan} onRebuild={() => setSearchParams({ view: "setup" })} /> : null}
      </main>
    </AppShell>
  );
}
