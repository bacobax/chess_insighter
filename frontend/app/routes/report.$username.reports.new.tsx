import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router";
import { ArrowLeft, Loader2 } from "lucide-react";
import { AppShell } from "~/components/layout/app-shell";
import { CompareReportView } from "~/components/report/compare-report-view";
import type { PlayerReportInitialParams } from "~/components/report/player-report";
import { Button } from "~/components/ui/button";
import { getDefaultHparams } from "~/lib/api";
import type { Hparams } from "~/lib/types";

export default function NewReportPage() {
  const { username = "" } = useParams();
  const location = useLocation();
  const initialParams = (location.state as { rebuildParams?: PlayerReportInitialParams } | null)?.rebuildParams;
  const [hparams, setHparams] = useState<Hparams | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { getDefaultHparams().then(setHparams).catch((err) => setError(err instanceof Error ? err.message : "Could not load report settings.")); }, []);
  return <AppShell><main id="main-content" className="editorial-shell"><header className="report-builder-header"><Link to={`/report/${encodeURIComponent(username)}`}><Button variant="ghost"><ArrowLeft /> Player dossier</Button></Link><p className="folio">New analysis / {username}</p><h1>Build a report worth keeping.</h1><p>Choose the evidence window, inspect the completed analysis, then save it to the player dossier with an optional title.</p></header>{error ? <p className="form-error">{error}</p> : null}{!hparams && !error ? <div className="dashboard-loading"><Loader2 className="animate-spin" /> Loading analysis controls…</div> : null}{hparams ? <CompareReportView username={username} defaultHparams={hparams} initialParams={initialParams} /> : null}</main></AppShell>;
}
