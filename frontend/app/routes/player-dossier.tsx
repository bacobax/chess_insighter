import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ArrowLeft, ArrowRight, Edit3, FilePlus2, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { PlayerStatsPanel } from "~/components/games/player-stats-panel";
import { AppShell } from "~/components/layout/app-shell";
import { Button } from "~/components/ui/button";
import { deleteReport, getPlayerReports, renameReport } from "~/lib/api";
import type { ReportSummary } from "~/lib/types";

function date(value: string) { return new Date(value).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); }

export default function PlayerDossierPage() {
  const { username = "" } = useParams();
  const navigate = useNavigate();
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => getPlayerReports(username).then((response) => setReports(response.reports)).catch((err) => setError(err instanceof Error ? err.message : "Could not load reports."));
  useEffect(() => { void load(); }, [username]);
  async function remove(report: ReportSummary) {
    if (!window.confirm(`Delete “${report.title ?? report.generated_label}”?`)) return;
    await deleteReport(report.id); setReports((current) => current?.filter((item) => item.id !== report.id) ?? null);
  }
  async function rename(report: ReportSummary) {
    const value = window.prompt("Report title (leave blank to use the generated label)", report.title ?? "");
    if (value === null) return;
    const updated = await renameReport(report.id, value); setReports((current) => current?.map((item) => item.id === report.id ? updated : item) ?? null);
  }
  return <AppShell><main id="main-content" className="editorial-shell"><header className="player-masthead"><Link to="/dashboard"><ArrowLeft /> Dashboard</Link><div><p className="folio">Chess.com dossier / Live snapshot</p><h1>{username}</h1><p>The latest public games shape this general profile. Saved reports below preserve the deeper studies you chose to keep.</p></div><div className="masthead-actions"><Link to={`/games/${encodeURIComponent(username)}`}><Button variant="outline">Match archive</Button></Link><Link to={`/report/${encodeURIComponent(username)}/reports/new`}><Button><FilePlus2 /> New report</Button></Link></div></header><section aria-labelledby="general-profile"><div className="section-rule"><span id="general-profile">General information</span><b>Live</b></div><PlayerStatsPanel username={username} /></section><section aria-labelledby="saved-reports"><div className="section-rule"><span id="saved-reports">Saved reports</span><b>{String(reports?.length ?? 0).padStart(2, "0")}</b></div>{error ? <p className="form-error">{error}</p> : null}{reports === null && !error ? <div className="dashboard-loading"><Loader2 className="animate-spin" /> Loading reports…</div> : null}{reports?.length === 0 ? <div className="reports-empty"><p className="folio">No reports saved yet</p><h2>General information is only the opening move.</h2><p>Build a configurable analysis, inspect the result, then save it to this dossier.</p><Link to={`/report/${encodeURIComponent(username)}/reports/new`}><Button>Build first report <ArrowRight /></Button></Link></div> : null}<div className="saved-report-list">{reports?.map((report, index) => <article key={report.id} className="saved-report-row"><span className="report-index">{String(index + 1).padStart(2, "0")}</span><div className="report-copy"><p className="folio">{date(report.saved_at)}</p><h3>{report.title ?? report.generated_label}</h3>{report.title ? <p>{report.generated_label}</p> : null}<small>{report.games_analyzed} games · depth {report.request_params.engine_depth} · {report.request_params.use_engine ? "engine analysis" : "no engine"}</small></div><div className="report-actions"><Link to={`/report/${encodeURIComponent(username)}/reports/${report.id}`}><Button size="sm">Open <ArrowRight /></Button></Link><Button size="sm" variant="outline" onClick={() => navigate(`/report/${encodeURIComponent(username)}/reports/new`, { state: { rebuildParams: report.request_params } })}><RefreshCw /> Rebuild</Button><Button size="sm" variant="ghost" onClick={() => void rename(report)} aria-label="Rename report"><Edit3 /></Button><Button size="sm" variant="ghost" onClick={() => void remove(report)} aria-label="Delete report"><Trash2 /></Button></div></article>)}</div></section></main></AppShell>;
}
