import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ArrowRight, BookOpen, Clock3, FileText, Loader2, Plus } from "lucide-react";
import { AppShell } from "~/components/layout/app-shell";
import { Button } from "~/components/ui/button";
import { getDashboard } from "~/lib/api";
import type { DashboardResponse } from "~/lib/types";

function formatDate(value: string | null): string {
  if (!value) return "No activity yet";
  return new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { getDashboard().then(setDashboard).catch((err) => setError(err instanceof Error ? err.message : "Could not open the dashboard.")); }, []);
  return (
    <AppShell>
      <main id="main-content" className="editorial-shell">
        <header className="dashboard-masthead">
          <div><p className="folio">Personal archive / Dashboard</p><h1>The players<br />on your <em>board.</em></h1></div>
          <p>Every dossier begins with the player, then unfolds into the reports you have chosen to keep.</p>
        </header>
        {error ? <div className="form-error" role="alert">{error}</div> : null}
        {!dashboard && !error ? <div className="dashboard-loading"><Loader2 className="animate-spin" /> Preparing your archive…</div> : null}
        {dashboard ? (
          <>
            <section className="archive-metrics" aria-label="Archive summary">
              <article><FileText /><span>{dashboard.report_count}</span><p>Saved reports</p></article>
              <article><BookOpen /><span>{dashboard.player_count}</span><p>Player dossiers</p></article>
              <article><Clock3 /><span className="date-metric">{formatDate(dashboard.latest_activity_at)}</span><p>Latest activity</p></article>
            </section>
            <div className="section-rule"><span>Player dossiers</span><b>{String(dashboard.player_count).padStart(2, "0")}</b></div>
            {dashboard.players.length === 0 ? (
              <section className="archive-empty"><span aria-hidden="true">♙</span><p className="folio">Your first dossier</p><h2>Start with a Chess.com handle.</h2><p>Use the player search above, build an analysis, and save the report when it deserves a place here.</p></section>
            ) : (
              <section className="dossier-grid">
                {dashboard.players.map((player, playerIndex) => (
                  <article className="dossier-card" key={player.username} style={{ animationDelay: `${playerIndex * 70}ms` }}>
                    <div className="dossier-number">{String(playerIndex + 1).padStart(2, "0")}</div>
                    <div className="dossier-heading"><p className="folio">Chess.com player</p><h2>{player.username}</h2><p>{player.report_count} saved {player.report_count === 1 ? "report" : "reports"}</p></div>
                    <ol className="report-rail">
                      {player.reports.slice(0, 3).map((report, index) => <li key={report.id}><span>{String(index + 1).padStart(2, "0")}</span><div><b>{report.title ?? report.generated_label}</b><small>{formatDate(report.saved_at)}</small></div></li>)}
                    </ol>
                    <Link className="dossier-link" to={`/report/${encodeURIComponent(player.username)}`}>Open dossier <ArrowRight /></Link>
                  </article>
                ))}
              </section>
            )}
          </>
        ) : null}
      </main>
    </AppShell>
  );
}
