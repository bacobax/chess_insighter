import { useState } from "react";
import { PlayerReport } from "./player-report";
import type { PlayerReportInitialParams } from "./player-report";
import type { Hparams, ReportBuildResponse } from "~/lib/types";
import { Input } from "~/components/ui/input";

export function CompareReportView({
  username: initialUsername,
  defaultHparams,
  initialReport,
  initialParams,
}: {
  username: string;
  defaultHparams: Hparams;
  initialReport?: ReportBuildResponse;
  initialParams?: PlayerReportInitialParams;
}) {
  const [primaryUsername, setPrimaryUsername] = useState(initialUsername);
  const [compare, setCompare] = useState(false);
  const [other, setOther] = useState("");
  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 rounded-md border bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-700">Player 1:</span>
          <Input className="max-w-[200px]" value={primaryUsername} onChange={(event) => setPrimaryUsername(event.target.value)} placeholder="Chess.com username" />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={compare} onChange={(event) => setCompare(event.target.checked)} />
          Compare with another user
        </label>
        {compare ? (
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-700">Player 2:</span>
            <Input className="max-w-[200px]" value={other} onChange={(event) => setOther(event.target.value)} placeholder="Second Chess.com username" />
          </div>
        ) : null}
      </div>
      <div className={compare && other.trim() ? "grid gap-6 lg:grid-cols-2" : ""}>
        {primaryUsername.trim() ? (
          <PlayerReport
            username={primaryUsername.trim()}
            defaultHparams={defaultHparams}
            initialReport={initialReport}
            initialParams={initialParams}
          />
        ) : (
          <div />
        )}
        {compare && other.trim() ? <PlayerReport username={other.trim()} defaultHparams={defaultHparams} /> : null}
      </div>
    </div>
  );
}
