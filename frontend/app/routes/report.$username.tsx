import { useEffect, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router";
import { ArrowLeft, Loader2, ScanSearch } from "lucide-react";
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
    <main id="main-content" className="page-shell min-h-screen px-5 py-8 sm:px-8 lg:px-12 lg:py-12" style={{ color: "var(--ink)" }}>
      <div className="mx-auto max-w-7xl space-y-5">
        <header className="mb-8 flex flex-col justify-between gap-6 border-b border-[var(--line)] pb-8 sm:flex-row sm:items-end">
          <div>
            <Link to={`/games/${encodeURIComponent(username)}`}>
              <Button variant="ghost" size="sm" className="mb-7 -ml-3"><ArrowLeft className="h-4 w-4" /> Match archive</Button>
            </Link>
            <p className="eyebrow mb-3 flex items-center gap-2"><ScanSearch className="h-3.5 w-3.5" /> Intelligence report / {username}</p>
            <h1 className="font-[var(--font-display)] text-[clamp(2.8rem,7vw,5.5rem)] font-medium leading-[.88] tracking-[-.065em]">PLAYER<br /><span className="text-[var(--accent)]">PROFILE.</span></h1>
          </div>
          <p className="max-w-sm text-sm leading-6 text-[var(--ink-soft)]">Build, compare, and save a decision-level model of how this player approaches the game.</p>
        </header>
        {error ? <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
        {!ready && !error ? <div className="flex h-48 items-center justify-center rounded-[20px] border border-[var(--line)] bg-[var(--paper)]"><Loader2 className="h-6 w-6 animate-spin text-[var(--accent)]" /></div> : null}
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
