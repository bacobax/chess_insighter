import { useEffect, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router";
import { ArrowLeft, Loader2 } from "lucide-react";
import { Button } from "~/components/ui/button";
import { CompareReportView } from "~/components/report/compare-report-view";
import type { PlayerReportInitialParams } from "~/components/report/player-report";
import { getDefaultHparams, getReportByHash } from "~/lib/api";
import type { Hparams, ReportBuildResponse } from "~/lib/types";

export default function ReportPage() {
  const { username = "" } = useParams();
  const [searchParams] = useSearchParams();
  const location = useLocation();

  const restoreHash = searchParams.get("restore");
  const rebuildParams = (location.state as { rebuildParams?: PlayerReportInitialParams } | null)?.rebuildParams;

  const [hparams, setHparams] = useState<Hparams | null>(null);
  const [initialReport, setInitialReport] = useState<ReportBuildResponse | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const tasks: Promise<unknown>[] = [
      getDefaultHparams().then(setHparams).catch((err) => {
        setError(err instanceof Error ? err.message : "Could not load default hparams.");
      }),
    ];
    if (restoreHash) {
      tasks.push(
        getReportByHash(restoreHash)
          .then(setInitialReport)
          .catch((err) => {
            setError(err instanceof Error ? err.message : "Could not load saved report.");
          }),
      );
    }
    Promise.all(tasks);
  }, [restoreHash]);

  useEffect(() => {
    if (!initialReport || location.hash !== "#mistakes") return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById("mistakes")?.scrollIntoView({ block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [initialReport, location.hash]);

  const ready = hparams !== null && (!restoreHash || initialReport !== undefined);

  return (
    <main className="min-h-screen px-4 py-8" style={{ color: "var(--ink)" }}>
      <div className="mx-auto max-w-7xl space-y-5">
        <Link to={`/games/${encodeURIComponent(username)}`}>
          <Button variant="ghost" size="sm"><ArrowLeft className="h-4 w-4" /> Games</Button>
        </Link>
        {error ? <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
        {!ready && !error ? <div className="flex h-48 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-slate-500" /></div> : null}
        {ready && hparams ? (
          <CompareReportView
            username={username}
            defaultHparams={hparams}
            initialReport={initialReport}
            initialParams={rebuildParams}
          />
        ) : null}
      </div>
    </main>
  );
}
