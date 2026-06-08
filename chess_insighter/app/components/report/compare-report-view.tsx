import { useState } from "react";
import { PlayerReport } from "./player-report";
import type { Hparams } from "~/lib/types";
import { Input } from "~/components/ui/input";

export function CompareReportView({ username, defaultHparams }: { username: string; defaultHparams: Hparams }) {
  const [compare, setCompare] = useState(false);
  const [other, setOther] = useState("");
  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 rounded-md border bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={compare} onChange={(event) => setCompare(event.target.checked)} />
          Compare with another user
        </label>
        {compare ? <Input className="max-w-xs" value={other} onChange={(event) => setOther(event.target.value)} placeholder="Second Chess.com username" /> : null}
      </div>
      <div className={compare && other.trim() ? "grid gap-6 xl:grid-cols-2" : ""}>
        <PlayerReport username={username} defaultHparams={defaultHparams} />
        {compare && other.trim() ? <PlayerReport username={other.trim()} defaultHparams={defaultHparams} /> : null}
      </div>
    </div>
  );
}
