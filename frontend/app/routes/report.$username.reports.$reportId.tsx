import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { ArrowLeft, Loader2 } from "lucide-react";
import { AppShell } from "~/components/layout/app-shell";
import { CompareReportView } from "~/components/report/compare-report-view";
import { Button } from "~/components/ui/button";
import { getDefaultHparams, getReport } from "~/lib/api";
import type { Hparams, ReportBuildResponse } from "~/lib/types";

export default function SavedReportPage() {
  const { username = "", reportId = "" } = useParams();
  const [hparams, setHparams] = useState<Hparams | null>(null);
  const [report, setReport] = useState<ReportBuildResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    Promise.all([getDefaultHparams(), getReport(reportId)])
      .then(([defaults, saved]) => { setHparams(defaults); setReport(saved); })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not open this report."));
  }, [reportId]);
  return <AppShell><main id="main-content" className="editorial-shell"><header className="saved-report-header"><Link to={`/report/${encodeURIComponent(username)}`}><Button variant="ghost"><ArrowLeft /> Player dossier</Button></Link><p className="folio">Saved report / {username}</p><h1>{report?.title ?? "Player analysis"}</h1>{report?.title && report.request_params ? <p>{report.request_params.max_games} games · {report.request_params.use_engine ? "engine analysis" : "no engine"}</p> : null}</header>{error ? <p className="form-error">{error}</p> : null}{(!report || !hparams) && !error ? <div className="dashboard-loading"><Loader2 className="animate-spin" /> Opening report…</div> : null}{report && hparams ? <CompareReportView username={username} defaultHparams={hparams} initialReport={report} initialParams={report.request_params ?? undefined} /> : null}</main></AppShell>;
}
