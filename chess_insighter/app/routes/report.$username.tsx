import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { ArrowLeft, Loader2 } from "lucide-react";
import { Button } from "~/components/ui/button";
import { CompareReportView } from "~/components/report/compare-report-view";
import { getDefaultHparams } from "~/lib/api";
import type { Hparams } from "~/lib/types";

export default function ReportPage() {
  const { username = "" } = useParams();
  const [hparams, setHparams] = useState<Hparams | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDefaultHparams().then(setHparams).catch((err) => setError(err instanceof Error ? err.message : "Could not load default hparams."));
  }, []);

  return (
    <main className="min-h-screen px-4 py-8" style={{ color: "var(--ink)" }}>
      <div className="mx-auto max-w-7xl space-y-5">
        <Link to={`/games/${encodeURIComponent(username)}`}>
          <Button variant="ghost" size="sm"><ArrowLeft className="h-4 w-4" /> Games</Button>
        </Link>
        {error ? <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
        {!hparams && !error ? <div className="flex h-48 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-slate-500" /></div> : null}
        {hparams ? <CompareReportView username={username} defaultHparams={hparams} /> : null}
      </div>
    </main>
  );
}
