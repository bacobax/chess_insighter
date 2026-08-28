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
      <div className="flex flex-col gap-4 rounded-[20px] border border-[var(--line)] bg-[linear-gradient(145deg,var(--paper-raised),var(--paper-dark))] p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <span className="eyebrow whitespace-nowrap">Player 01</span>
          <Input className="max-w-[200px]" value={primaryUsername} onChange={(event) => setPrimaryUsername(event.target.value)} placeholder="Chess.com username" />
        </div>
        <label className="flex min-h-11 items-center gap-2 rounded-full border border-[var(--line)] px-4 text-sm font-semibold">
          <input type="checkbox" checked={compare} onChange={(event) => setCompare(event.target.checked)} />
          Compare with another user
        </label>
        {compare ? (
          <div className="flex items-center gap-2">
            <span className="eyebrow whitespace-nowrap">Player 02</span>
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
            enableMistakes
          />
        ) : (
          <div />
        )}
        {compare && other.trim() ? <PlayerReport username={other.trim()} defaultHparams={defaultHparams} enableMistakes={false} /> : null}
      </div>
    </div>
  );
}
