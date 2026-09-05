import { useCallback, useState } from "react";
import { useBeforeUnload, useBlocker } from "react-router";
import { PlayerReport } from "./player-report";
import type { PlayerReportInitialParams } from "./player-report";
import type { Hparams, ReportBuildResponse } from "~/lib/types";
import { Input } from "~/components/ui/input";
import { Button } from "~/components/ui/button";
import { cancelReportBuild } from "~/lib/api";

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
  const [activeBuilds, setActiveBuilds] = useState<Map<string, string>>(new Map());
  const normalizedPrimaryUsername = primaryUsername.trim();
  const normalizedOtherUsername = other.trim();
  const primaryIsInitial = normalizedPrimaryUsername.toLowerCase() === initialUsername.trim().toLowerCase();
  const blocker = useBlocker(activeBuilds.size > 0);
  const onBuildActivityChange = useCallback((instanceId: string, buildId: string | null) => {
    setActiveBuilds((current) => {
      const next = new Map(current);
      if (buildId) next.set(instanceId, buildId); else next.delete(instanceId);
      return next;
    });
  }, []);

  useBeforeUnload((event) => {
    if (!activeBuilds.size) return;
    event.preventDefault();
    event.returnValue = "";
  });

  async function leaveAndCancel() {
    await Promise.allSettled(Array.from(activeBuilds.values(), (buildId) => cancelReportBuild(buildId)));
    blocker.proceed?.();
  }

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
      <div className={compare && normalizedOtherUsername ? "grid items-start gap-6 lg:grid-cols-2" : ""}>
        {normalizedPrimaryUsername ? (
          <PlayerReport
            key={normalizedPrimaryUsername.toLowerCase()}
            username={normalizedPrimaryUsername}
            defaultHparams={defaultHparams}
            initialReport={primaryIsInitial ? initialReport : undefined}
            initialParams={primaryIsInitial ? initialParams : undefined}
            enableMistakes
            onBuildActivityChange={onBuildActivityChange}
          />
        ) : (
          <div />
        )}
        {compare && normalizedOtherUsername ? (
          <PlayerReport
            key={normalizedOtherUsername.toLowerCase()}
            username={normalizedOtherUsername}
            defaultHparams={defaultHparams}
            enableMistakes={false}
            onBuildActivityChange={onBuildActivityChange}
          />
        ) : null}
      </div>
      {blocker.state === "blocked" ? (
        <div className="build-leave-backdrop" role="presentation">
          <section className="build-leave-dialog" role="alertdialog" aria-modal="true" aria-labelledby="build-leave-title" aria-describedby="build-leave-copy">
            <p className="folio">Analysis in progress</p>
            <h2 id="build-leave-title">Leave and cancel the build?</h2>
            <p id="build-leave-copy">Report creation only continues while this builder is open. Leaving now will safely stop every active analysis.</p>
            <div><Button variant="outline" autoFocus onClick={() => blocker.reset?.()}>Keep building</Button><Button onClick={() => void leaveAndCancel()}>Leave and cancel</Button></div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
