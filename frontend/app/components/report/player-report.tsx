import { useEffect, useId, useState } from "react";
import { Link, useNavigate } from "react-router";
import { BarChart3, Bookmark, BookmarkCheck, BookOpen, Loader2, Network, RefreshCw } from "lucide-react";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Progress } from "~/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
import { FavouriteOpeningsChart, MetricBarChart, SkillRadarChart } from "~/components/charts/report-charts";
import { cancelReportBuild, getReport, getReportBuildStatus, reportBuildSocketUrl, saveReport, startReportBuild } from "~/lib/api";
import type { Hparams, MetricPoint, OpeningReportGroup, ReportBuildJobAccepted, ReportBuildJobStatus, ReportBuildRequest, ReportBuildResponse, ReportCharts } from "~/lib/types";
import { formatPercent } from "~/lib/utils";
import { ReportConfigForm } from "./report-config-form";
import { MistakesReportSection } from "./mistakes-report-section";

export type PlayerReportInitialParams = Pick<
  ReportBuildRequest,
  "max_games" | "engine_depth" | "use_engine" | "time_classes" | "rated_filter" | "since_year" | "since_month" | "hparams"
>;

export function PlayerReport({
  username,
  defaultHparams,
  initialReport,
  initialParams,
  enableMistakes = true,
  onBuildActivityChange,
}: {
  username: string;
  defaultHparams: Hparams;
  initialReport?: ReportBuildResponse;
  initialParams?: PlayerReportInitialParams;
  enableMistakes?: boolean;
  onBuildActivityChange?: (instanceId: string, buildId: string | null) => void;
}) {
  const buildInstanceId = useId();
  const initialBuildRequest: ReportBuildRequest | null =
    initialReport && initialParams
      ? {
          username,
          hparams: initialParams.hparams,
          max_games: initialParams.max_games,
          engine_depth: initialParams.engine_depth,
          use_engine: initialParams.use_engine,
          refresh_cache: false,
          time_classes: initialParams.time_classes ?? null,
          rated_filter: initialParams.rated_filter ?? null,
          since_year: initialParams.since_year ?? null,
          since_month: initialParams.since_month ?? null,
        }
      : null;
  const [hparams, setHparams] = useState<Hparams>(initialParams?.hparams ?? defaultHparams);
  const [maxGames, setMaxGames] = useState(initialParams?.max_games ?? 20);
  const [timeClass, setTimeClass] = useState<string>(
    initialParams?.time_classes && initialParams.time_classes.length === 1
      ? initialParams.time_classes[0]
      : "all",
  );
  const [ratedFilter, setRatedFilter] = useState<string>(
    initialParams?.rated_filter === true ? "rated" : initialParams?.rated_filter === false ? "unrated" : "all",
  );
  const [sinceYear, setSinceYear] = useState<number | "">(initialParams?.since_year ?? "");
  const [sinceMonth, setSinceMonth] = useState<number | "">(initialParams?.since_month ?? "");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [engineDepth, setEngineDepth] = useState(initialParams?.engine_depth ?? 10);
  const [useEngine, setUseEngine] = useState(initialParams?.use_engine ?? true);
  const [refreshCache, setRefreshCache] = useState(false);
  const [report, setReport] = useState<ReportBuildResponse | null>(initialReport ?? null);
  const [lastBuildRequest, setLastBuildRequest] = useState<ReportBuildRequest | null>(initialBuildRequest);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [buildJob, setBuildJob] = useState<ReportBuildJobAccepted | null>(null);
  const [buildProgress, setBuildProgress] = useState<ReportBuildJobStatus | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!loading) return;
    const timer = window.setInterval(() => setElapsedSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [loading]);

  async function submit(overrides: Partial<Pick<ReportBuildRequest, "use_engine" | "refresh_cache">> = {}) {
    setLoading(true);
    setElapsedSeconds(0);
    setBuildProgress(null);
    setError(null);
    const request: ReportBuildRequest = {
      username,
      hparams,
      max_games: maxGames,
      engine_depth: engineDepth,
      use_engine: overrides.use_engine ?? useEngine,
      refresh_cache: overrides.refresh_cache ?? refreshCache,
      time_classes: timeClass === "all" ? null : [timeClass],
      rated_filter: ratedFilter === "all" ? null : ratedFilter === "rated",
      since_year: sinceYear === "" ? null : sinceYear,
      since_month: sinceMonth === "" ? null : sinceMonth,
    };
    try {
      const accepted = await startReportBuild(request);
      setBuildJob(accepted);
      onBuildActivityChange?.(buildInstanceId, accepted.build_id);
      const terminal = await waitForReportBuild(accepted, setBuildProgress);
      if (terminal.status !== "completed" || !terminal.report_id) {
        throw new Error(terminal.error ?? (terminal.status === "cancelled" ? "Report build cancelled." : "Could not build report."));
      }
      const response = await getReport(terminal.report_id);
      setReport(response);
      setLastBuildRequest(request);
      setHparams(response.normalized_hparams);
      setUseEngine(request.use_engine);
      setRefreshCache(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build report.");
    } finally {
      setLoading(false);
      setBuildJob(null);
      onBuildActivityChange?.(buildInstanceId, null);
    }
  }

  async function cancelActiveBuild() {
    if (!buildJob) return;
    setBuildProgress((current) => current ? { ...current, stage: "cancelling", message: "Cancelling analysis safely" } : current);
    await cancelReportBuild(buildJob.build_id);
  }

  return (
    <div className="player-report min-w-0 space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{username}</CardTitle>
          <CardDescription>Configure the analysis run and build a cached player report.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="player-report-filters">
            <label className="text-sm">
              <span className="mb-1 block text-slate-600">Max games</span>
              <input className="h-10 w-full rounded-md border px-3" type="number" min={1} max={500} value={maxGames} onChange={(event) => setMaxGames(Number(event.target.value))} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-600">Time category</span>
              <select className="h-10 w-full rounded-md border px-3 bg-white" value={timeClass} onChange={(e) => setTimeClass(e.target.value)}>
                <option value="all">All</option>
                <option value="bullet">Bullet</option>
                <option value="blitz">Blitz</option>
                <option value="rapid">Rapid</option>
                <option value="daily">Daily</option>
              </select>
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-600">Rated</span>
              <select className="h-10 w-full rounded-md border px-3 bg-white" value={ratedFilter} onChange={(e) => setRatedFilter(e.target.value)}>
                <option value="all">All</option>
                <option value="rated">Rated</option>
                <option value="unrated">Unrated</option>
              </select>
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-600">Since year</span>
              <input className="h-10 w-full rounded-md border px-3" type="number" min={2000} value={sinceYear} onChange={(event) => setSinceYear(event.target.value === "" ? "" : Number(event.target.value))} placeholder="e.g. 2023" />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-600">Since month</span>
              <input className="h-10 w-full rounded-md border px-3" type="number" min={1} max={12} value={sinceMonth} onChange={(event) => setSinceMonth(event.target.value === "" ? "" : Number(event.target.value))} placeholder="1-12" />
            </label>
            <label className="flex min-h-16 cursor-pointer items-center gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
              <input type="checkbox" checked={refreshCache} onChange={(e) => setRefreshCache(e.target.checked)} />
              <span>
                <span className="block font-medium text-slate-900">Refresh cache</span>
                <span className="block text-xs leading-4 text-slate-500">Fetch and analyze fresh data</span>
              </span>
            </label>
          </div>
          
          <div>
            <button type="button" onClick={() => setShowAdvanced(!showAdvanced)} className="text-sm text-blue-600 hover:underline">
              {showAdvanced ? "Hide advanced filters" : "Show advanced filters"}
            </button>
          </div>

          {showAdvanced && (
            <div className="space-y-4 rounded-md border border-slate-200 bg-slate-50 p-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-sm">
                  <span className="mb-1 block text-slate-600">Engine depth</span>
                  <input className="h-10 w-full rounded-md border px-3 bg-white" type="number" min={1} max={30} value={engineDepth} onChange={(event) => setEngineDepth(Number(event.target.value))} />
                </label>
                <div className="flex items-end gap-4 pb-2 text-sm">
                  <label className="flex items-center gap-2"><input type="checkbox" checked={useEngine} onChange={(e) => setUseEngine(e.target.checked)} /> Use engine</label>
                </div>
              </div>
              <ReportConfigForm value={hparams} onChange={setHparams} />
            </div>
          )}

          <Button onClick={() => void submit()} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Build Report
          </Button>
          {loading && buildProgress ? (
            <div className="build-progress-panel" aria-live="polite" aria-atomic="true">
              <div className="build-progress-copy">
                <div><span className="folio">Live analysis</span><strong>{buildProgress.message}</strong></div>
                <span className="build-progress-value">{Math.round(buildProgress.progress * 100)}%</span>
              </div>
              <Progress value={buildProgress.progress} />
              <div className="build-progress-meta">
                <span>{buildProgress.stage.replace(/_/g, " ")}</span>
                <span>{formatElapsed(elapsedSeconds)}</span>
                {buildProgress.processed != null && buildProgress.total != null ? <span>{buildProgress.processed} / {buildProgress.total}</span> : null}
                <Button variant="outline" onClick={() => void cancelActiveBuild()}>Cancel build</Button>
              </div>
            </div>
          ) : null}
          {error ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
        </CardContent>
      </Card>
      {report ? (
        <ReportDashboard
          report={report}
          username={username}
          buildRequest={lastBuildRequest}
          enableMistakes={enableMistakes}
          onRebuildMistakes={() => void submit({ use_engine: true, refresh_cache: true })}
        />
      ) : null}
    </div>
  );
}

function waitForReportBuild(
  accepted: ReportBuildJobAccepted,
  onProgress: (status: ReportBuildJobStatus) => void,
): Promise<ReportBuildJobStatus> {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    let finished = false;
    const handle = (snapshot: ReportBuildJobStatus) => {
      onProgress(snapshot);
      if (["completed", "failed", "cancelled"].includes(snapshot.status)) {
        finished = true;
        resolve(snapshot);
        return true;
      }
      return false;
    };
    const connect = () => {
      if (finished) return;
      const socket = new WebSocket(reportBuildSocketUrl(accepted.build_id, accepted.socket_token));
      socket.onopen = () => { attempts = 0; };
      socket.onmessage = (event) => handle(JSON.parse(String(event.data)) as ReportBuildJobStatus);
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        if (finished) return;
        window.setTimeout(async () => {
          try {
            const current = await getReportBuildStatus(accepted.build_id);
            if (!handle(current) && attempts++ < 6) connect();
            else if (!finished && attempts >= 6) reject(new Error("Lost connection to the report build."));
          } catch (error) {
            if (attempts++ < 6) connect(); else reject(error);
          }
        }, Math.min(750 * 2 ** attempts, 8000));
      };
    };
    connect();
  });
}

function formatElapsed(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

function ReportDashboard({
  report,
  username,
  buildRequest,
  enableMistakes,
  onRebuildMistakes,
}: {
  report: ReportBuildResponse;
  username: string;
  buildRequest: ReportBuildRequest | null;
  enableMistakes: boolean;
  onRebuildMistakes: () => void;
}) {
  const charts = report.report.charts;
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">(report.saved ? "saved" : "idle");
  const navigate = useNavigate();
  const dashboardId = useId();
  const skillProfileHeadingId = `${dashboardId}-skill-profile`;
  const openingRepertoireHeadingId = `${dashboardId}-opening-repertoire`;

  async function handleSave() {
    if (!buildRequest || !report.report_id) return;
    const title = window.prompt("Optional report title", report.title ?? "");
    if (title === null) return;
    setSaveState("saving");
    try {
      await saveReport(report.report_id, title);
      setSaveState("saved");
      navigate(`/report/${encodeURIComponent(username)}/reports/${encodeURIComponent(report.report_id)}`);
    } catch {
      setSaveState("error");
      setTimeout(() => setSaveState("idle"), 2000);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 rounded-md border bg-white p-4 text-sm text-slate-600 sm:flex-row sm:items-center sm:justify-between">
        <span>
          Analysis <span className="font-medium text-slate-950">{report.cache_hit ? "restored from cache" : "computed now"}</span>
          {report.report_id ? <>{" · "}report <span className="font-mono text-xs">{report.report_id.slice(0, 8)}</span></> : null}
        </span>
        {buildRequest ? (
          <button
            type="button"
            onClick={handleSave}
            disabled={saveState === "saving" || saveState === "saved"}
            className="inline-flex h-8 items-center justify-center gap-1.5 self-start rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60 sm:self-auto"
          >
            {saveState === "saving" ? (
              <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Saving…</>
            ) : saveState === "saved" ? (
              <><BookmarkCheck className="h-3.5 w-3.5 text-green-600" /> Saved</>
            ) : saveState === "error" ? (
              <>Error</>
            ) : (
              <><Bookmark className="h-3.5 w-3.5" /> Save</>
            )}
          </button>
        ) : null}
      </div>
      <SkillProfileSection charts={charts} headingId={skillProfileHeadingId} />
      {enableMistakes ? (
        <MistakesReportSection
          username={username}
          reportHash={report.report_id ?? report.cache_hash}
          context={report.report.analysis_context ?? null}
          reportFilters={buildRequest}
          onRebuild={onRebuildMistakes}
        />
      ) : null}
      <OpeningRepertoireSection report={report} username={username} headingId={openingRepertoireHeadingId} />
    </div>
  );
}

type SkillEvidence = {
  key: string;
  label: string;
  description: string;
  data: MetricPoint[];
  secondary?: MetricPoint[];
};

function SkillProfileSection({ charts, headingId }: { charts: ReportCharts; headingId: string }) {
  const [activeEvidence, setActiveEvidence] = useState("openings");
  const scoreByKey = new Map(charts.skill_profile.map((item) => [item.key, item.value]));
  const evidence: SkillEvidence[] = [
    {
      key: "openings",
      label: "Openings",
      description: "Book accuracy, stability after leaving theory, and results from opening positions.",
      data: charts.opening_components,
    },
    {
      key: "time_management",
      label: "Time management",
      description: "Clock-pressure risks and how thinking time changes with position complexity.",
      data: charts.time_management_indicators,
      secondary: charts.average_time_by_complexity,
    },
    {
      key: "advantage_capitalization",
      label: "Advantage conversion",
      description: "How reliably favorable positions are preserved and converted into results.",
      data: charts.advantage_capitalization_components,
    },
    {
      key: "resourcefulness",
      label: "Resourcefulness",
      description: "The ability to recover, avoid collapse, and save difficult positions.",
      data: charts.resourcefulness_components,
    },
    {
      key: "game_analysis",
      label: "Game analysis",
      description: "Whether recurring weaknesses improve across the analyzed games.",
      data: charts.game_analysis_components,
    },
  ];

  return (
    <section aria-labelledby={headingId} className="space-y-4 border-t border-slate-200 pt-6">
      <ReportSectionHeading
        icon={<BarChart3 className="h-5 w-5" />}
        title="Player profile"
        description="Composite skill scores first, followed by the measurements that support them."
        headingId={headingId}
      />
      <div className="player-report-profile-grid">
        <SkillRadarChart data={charts.skill_profile} />
        <SkillScoreList data={charts.skill_profile} />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Score evidence</CardTitle>
          <CardDescription>The underlying measurements available for each composite score.</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs value={activeEvidence} onValueChange={setActiveEvidence}>
            <TabsList className="flex h-auto w-full max-w-full justify-start gap-1 overflow-x-auto">
              {evidence.map((item) => (
                <TabsTrigger key={item.key} value={item.key} className="min-w-[9rem] flex-1 whitespace-normal px-3 py-2 text-left">
                  <span className="block">
                    <span className="block text-xs font-medium">{item.label}</span>
                    <span className="mt-0.5 block text-xs opacity-70">{formatPercent(scoreByKey.get(item.key))}</span>
                  </span>
                </TabsTrigger>
              ))}
            </TabsList>
            {evidence.map((item) => (
              <TabsContent key={item.key} value={item.key} className="border-t border-slate-200 pt-5">
                {activeEvidence === item.key ? (
                  <>
                    <div className="mb-5 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
                      <div>
                        <h4 className="text-base font-semibold" style={{ fontFamily: "var(--font-display)", color: "var(--ink)" }}>{item.label}</h4>
                        <p className="mt-1 max-w-2xl text-sm" style={{ color: "var(--ink-soft)" }}>{item.description}</p>
                      </div>
                      <div className="text-sm" style={{ color: "var(--ink-soft)" }}>
                        Profile score <span className="font-semibold" style={{ color: "var(--ink)" }}>{formatPercent(scoreByKey.get(item.key))}</span>
                      </div>
                    </div>
                    <div className={item.secondary ? "player-report-evidence-grid" : ""}>
                      <MetricBarChart
                        title={item.key === "time_management" ? "Risk indicators" : "Score components"}
                        data={item.data}
                        embedded
                      />
                      {item.secondary ? (
                        <MetricBarChart
                          title="Thinking time by complexity"
                          description="Average seconds spent per move in each position category."
                          data={item.secondary}
                          percent={false}
                          embedded
                          directional={false}
                        />
                      ) : null}
                    </div>
                  </>
                ) : null}
              </TabsContent>
            ))}
          </Tabs>
        </CardContent>
      </Card>
    </section>
  );
}

function SkillScoreList({ data }: { data: MetricPoint[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Scores at a glance</CardTitle>
        <CardDescription>All profile dimensions on the same 0–100 scale.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="player-report-score-grid">
          {data.map((item) => (
            <div key={item.key}>
              <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
                <span className="min-w-0 font-medium">{item.label}</span>
                <span className="shrink-0 tabular-nums text-slate-600">{formatPercent(item.value)}</span>
              </div>
              <Progress value={item.value} />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function OpeningRepertoireSection({
  report,
  username,
  headingId,
}: {
  report: ReportBuildResponse;
  username: string;
  headingId: string;
}) {
  const charts = report.report.charts;
  const groups = charts.opening_report_groups;
  const characteristics = {
    white: groups?.white?.opening_characteristics ?? charts.opening_characteristics,
    black: groups?.black?.opening_characteristics ?? charts.opening_characteristics,
    both: groups?.both?.opening_characteristics ?? charts.opening_characteristics,
  };
  const studyUrl = `/opening-study?username=${encodeURIComponent(username)}&reportId=${encodeURIComponent(report.report_id ?? "")}`;

  return (
    <section aria-labelledby={headingId} className="space-y-4 border-t border-slate-200 pt-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <ReportSectionHeading
          icon={<BookOpen className="h-5 w-5" />}
          title="Opening repertoire"
          description="What appears most often and the kinds of positions reached from those openings."
          headingId={headingId}
        />
        <Link to={studyUrl} className="self-start sm:self-auto">
          <Button variant="outline" size="sm">
            <Network className="h-4 w-4" /> Study repertoire
          </Button>
        </Link>
      </div>
      <div className="player-report-opening-grid">
        <FavouriteOpeningsChart data={charts.favourite_openings} />
        <Card>
          <CardHeader>
            <CardTitle>Position tendencies</CardTitle>
            <CardDescription>Typical characteristics of the positions produced by the repertoire.</CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="both">
              <TabsList className="grid w-full grid-cols-3 sm:w-auto">
                <TabsTrigger value="white">As White</TabsTrigger>
                <TabsTrigger value="black">As Black</TabsTrigger>
                <TabsTrigger value="both">Overall</TabsTrigger>
              </TabsList>
              <TabsContent value="white"><OpeningCharacteristics data={characteristics.white} /></TabsContent>
              <TabsContent value="black"><OpeningCharacteristics data={characteristics.black} /></TabsContent>
              <TabsContent value="both"><OpeningCharacteristics data={characteristics.both} /></TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

const OPENING_CHARACTERISTIC_GROUPS = [
  { title: "Position character", keys: ["tactical_density", "quiet_position_density", "middlegame_complexity"] },
  { title: "King safety", keys: ["king_safety_risk", "early_castling_tendency", "opposite_side_castling_tendency"] },
  { title: "Structure and outcome", keys: ["pawn_structure_sharpness", "material_imbalance", "endgame_likelihood_proxy", "final_structure_entropy"] },
];

function OpeningCharacteristics({ data }: { data: OpeningReportGroup["opening_characteristics"] }) {
  const groupedKeys = new Set(OPENING_CHARACTERISTIC_GROUPS.flatMap((group) => group.keys));
  const groups = [
    ...OPENING_CHARACTERISTIC_GROUPS.map((group) => ({
      ...group,
      items: group.keys.map((key) => data.find((item) => item.key === key)).filter((item): item is MetricPoint => Boolean(item)),
    })),
    {
      title: "Other",
      keys: [],
      items: data.filter((item) => !groupedKeys.has(item.key)),
    },
  ].filter((group) => group.items.length > 0);

  return (
    <div className="player-report-characteristics">
      {groups.map((group) => (
        <div key={group.title} className="player-report-characteristic-group">
          <h4 className="mb-3 text-sm font-semibold" style={{ color: "var(--ink)" }}>{group.title}</h4>
          <div className="space-y-3">
            {group.items.map((item) => (
              <div key={item.key}>
                <div className="mb-1.5 flex items-baseline justify-between gap-3 text-xs">
                  <span className="font-medium">{item.label}</span>
                  <span className="shrink-0 tabular-nums text-slate-600">{formatPercent(item.value)}</span>
                </div>
                <Progress value={item.value} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ReportSectionHeading({
  icon,
  title,
  description,
  headingId,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  headingId: string;
}) {
  return (
    <div>
      <div className="flex items-center gap-2" style={{ color: "var(--accent)" }}>
        {icon}
        <h2 id={headingId} className="text-xl" style={{ fontFamily: "var(--font-display)", color: "var(--ink)" }}>{title}</h2>
      </div>
      <p className="mt-1 max-w-3xl text-sm" style={{ color: "var(--ink-soft)" }}>{description}</p>
    </div>
  );
}
