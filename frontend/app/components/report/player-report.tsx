import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ChevronDown, ChevronRight, Loader2, Network, RefreshCw } from "lucide-react";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Progress } from "~/components/ui/progress";
import { FavouriteOpeningsChart, MetricBarChart, SkillRadarChart } from "~/components/charts/report-charts";
import { buildReport, rematchOpenings } from "~/lib/api";
import type { Hparams, OpeningMatch, OpeningMatchMode, OpeningReportGroup, ReportBuildRequest, ReportBuildResponse } from "~/lib/types";
import { formatNumber, formatPercent } from "~/lib/utils";
import { OpeningBoardPreview } from "./opening-board-preview";
import { ReportConfigForm } from "./report-config-form";

export type PlayerReportInitialParams = Pick<
  ReportBuildRequest,
  "max_games" | "engine_depth" | "use_engine" | "time_classes" | "rated_filter" | "since_year" | "since_month" | "hparams"
>;

export function PlayerReport({
  username,
  defaultHparams,
  initialReport,
  initialParams,
}: {
  username: string;
  defaultHparams: Hparams;
  initialReport?: ReportBuildResponse;
  initialParams?: PlayerReportInitialParams;
}) {
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setLoading(true);
    setError(null);
    try {
      const response = await buildReport({
        username,
        hparams,
        max_games: maxGames,
        engine_depth: engineDepth,
        use_engine: useEngine,
        refresh_cache: refreshCache,
        time_classes: timeClass === "all" ? null : [timeClass],
        rated_filter: ratedFilter === "all" ? null : ratedFilter === "rated",
        since_year: sinceYear === "" ? null : sinceYear,
        since_month: sinceMonth === "" ? null : sinceMonth,
      });
      setReport(response);
      setHparams(response.normalized_hparams);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build report.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{username}</CardTitle>
          <CardDescription>Configure the analysis run and build a cached player report.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
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
                  <label className="flex items-center gap-2"><input type="checkbox" checked={refreshCache} onChange={(e) => setRefreshCache(e.target.checked)} /> Refresh cache</label>
                </div>
              </div>
              <ReportConfigForm value={hparams} onChange={setHparams} />
            </div>
          )}

          <Button onClick={submit} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Build Report
          </Button>
          {error ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
        </CardContent>
      </Card>
      {report ? <ReportDashboard report={report} username={username} /> : null}
    </div>
  );
}

function ReportDashboard({ report, username }: { report: ReportBuildResponse; username: string }) {
  const charts = report.report.charts;
  const studyUrl = `/opening-study?username=${encodeURIComponent(username)}&cacheHash=${encodeURIComponent(report.cache_hash)}`;
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between rounded-md border bg-white p-4 text-sm text-slate-600">
        <span>
          Cache <span className="font-medium text-slate-950">{report.cache_hit ? "hit" : "miss"}</span>
          {" · "}hash <span className="font-mono text-xs">{report.cache_hash.slice(0, 12)}</span>
        </span>
        <Link to={studyUrl}>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <Network className="h-3.5 w-3.5" /> Opening Study Tree
          </button>
        </Link>
      </div>
      <SkillRadarChart data={charts.skill_profile} />
      <FavouriteOpeningsChart data={charts.favourite_openings} />
      <OpeningReportSections report={report} />
      <MetricBarChart title="Opening Components" data={charts.opening_components} />
      <MetricBarChart title="Time Management Indicators" data={charts.time_management_indicators} />
      <MetricBarChart title="Advantage Capitalization Components" data={charts.advantage_capitalization_components} />
      <MetricBarChart title="Resourcefulness Components" data={charts.resourcefulness_components} />
      <MetricBarChart title="Game Analysis Components" data={charts.game_analysis_components} />
      <MetricBarChart title="Average Time Spent by Complexity" data={charts.average_time_by_complexity} percent={false} />
    </div>
  );
}

function OpeningReportSections({ report }: { report: ReportBuildResponse }) {
  const groups = report.report.charts.opening_report_groups ?? {
    white: {
      opening_characteristics: report.report.charts.opening_characteristics,
      top_opening_features: report.report.charts.top_opening_features.filter((item) => item.color === "white"),
      top_opening_matches: report.report.charts.top_opening_matches.filter((item) => item.target_color === "white"),
    },
    black: {
      opening_characteristics: report.report.charts.opening_characteristics,
      top_opening_features: report.report.charts.top_opening_features.filter((item) => item.color === "black"),
      top_opening_matches: report.report.charts.top_opening_matches.filter((item) => item.target_color === "black"),
    },
    both: {
      opening_characteristics: report.report.charts.opening_characteristics,
      top_opening_features: report.report.charts.top_opening_features,
      top_opening_matches: report.report.charts.top_opening_matches,
    },
  };
  const [open, setOpen] = useState<Record<"white" | "black" | "both", boolean>>({
    white: true,
    black: true,
    both: true,
  });
  const sections: Array<{ key: "white" | "black" | "both"; title: string }> = [
    { key: "white", title: "White" },
    { key: "black", title: "Black" },
    { key: "both", title: "Both (Avg)" },
  ];

  return (
    <div className="space-y-4">
      {sections.map((section) => (
        <Card key={section.key}>
          <CardHeader className="space-y-0">
            <button
              type="button"
              className="flex w-full items-center justify-between text-left"
              onClick={() => setOpen((current) => ({ ...current, [section.key]: !current[section.key] }))}
            >
              <CardTitle>{section.title}</CardTitle>
              {open[section.key] ? <ChevronDown className="h-5 w-5 text-slate-500" /> : <ChevronRight className="h-5 w-5 text-slate-500" />}
            </button>
          </CardHeader>
          {open[section.key] ? (
            <CardContent className="space-y-5">
              <OpeningCharacteristics data={groups[section.key].opening_characteristics} />
              <OpeningFeaturePanels data={groups[section.key].top_opening_features} />
              <TopOpeningMatches report={report} group={groups[section.key]} targetColor={section.key} />
            </CardContent>
          ) : null}
        </Card>
      ))}
    </div>
  );
}

function OpeningFeaturePanels({ data }: { data: OpeningReportGroup["top_opening_features"] }) {
  return (
    <section className="space-y-3">
      <h3 className="text-base font-semibold">Top 3 Opening Features</h3>
      <div className="grid gap-4 md:grid-cols-2">
        {data.map((opening) => (
          <div key={`${opening.color}-${opening.opening_name}`} className="rounded-md border p-4">
            <div className="mb-3 text-sm font-semibold">{opening.color}: {opening.opening_name}</div>
            <div className="space-y-3">
              {opening.features.map((feature) => (
                <div key={feature.key}>
                  <div className="mb-1 flex justify-between text-xs"><span>{feature.label}</span><span>{formatPercent(feature.value)}</span></div>
                  <Progress value={feature.value} />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function OpeningCharacteristics({ data }: { data: OpeningReportGroup["opening_characteristics"] }) {
  return (
    <section className="space-y-3">
      <h3 className="text-base font-semibold">Opening Characteristics</h3>
      <div className="flex flex-wrap gap-2">
        {data.map((item) => (
          <div key={item.key} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
            <span className="font-medium">{item.label}</span> <span className="text-slate-500">{formatPercent(item.value)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function TopOpeningMatches({ report, group, targetColor }: { report: ReportBuildResponse; group: OpeningReportGroup; targetColor: "white" | "black" | "both" }) {
  const initialMatches = group.top_opening_matches;
  const [matches, setMatches] = useState<OpeningMatch[]>(initialMatches);
  const [matchMode, setMatchMode] = useState<OpeningMatchMode>(initialMatches[0]?.match_mode ?? "cosine");
  const [topK, setTopK] = useState<number>(initialMatches.length || 3);
  const [rematching, setRematching] = useState(false);
  const [rematchError, setRematchError] = useState<string | null>(null);

  useEffect(() => {
    setMatches(initialMatches);
    setMatchMode(initialMatches[0]?.match_mode ?? "cosine");
    setTopK(initialMatches.length || 3);
    setRematchError(null);
  }, [report.cache_hash, targetColor]);

  async function refresh(mode: OpeningMatchMode, k: number) {
    setRematching(true);
    setRematchError(null);
    try {
      const response = await rematchOpenings({
        cache_hash: report.cache_hash,
        match_mode: mode,
        target_color: targetColor,
        limit: k,
      });
      setMatches(response.top_opening_matches);
      setMatchMode(response.match_mode);
    } catch (err) {
      setRematchError(err instanceof Error ? err.message : "Could not update opening matches.");
    } finally {
      setRematching(false);
    }
  }

  async function changeMatchMode(nextMode: OpeningMatchMode) {
    setMatchMode(nextMode);
    await refresh(nextMode, topK);
  }

  async function changeTopK(k: number) {
    const clamped = Math.min(50, Math.max(1, k));
    setTopK(clamped);
    await refresh(matchMode, clamped);
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="text-base font-semibold" style={{ fontFamily: "var(--font-display)", color: "var(--ink)" }}>Top Opening Matches</h3>
        <div className="flex flex-wrap items-center gap-3 text-sm" style={{ color: "var(--ink-soft)" }}>
          <label className="flex items-center gap-1.5">
            <span>K</span>
            <input
              type="number"
              min={1}
              max={50}
              value={topK}
              disabled={rematching}
              className="h-8 w-16 rounded px-2 text-sm outline-none focus:ring-2"
              style={{ backgroundColor: "var(--paper)", border: "1px solid var(--line)", color: "var(--ink)" }}
              onChange={(e) => {
                const val = Number(e.target.value);
                if (val >= 1 && val <= 50) changeTopK(val);
              }}
            />
          </label>
          <label className="flex items-center gap-1.5">
            <span>Mode</span>
            <select
              className="h-8 rounded px-2 text-sm outline-none"
              style={{ backgroundColor: "var(--paper)", border: "1px solid var(--line)", color: "var(--ink)" }}
              value={matchMode}
              disabled={rematching}
              onChange={(event) => changeMatchMode(event.target.value as OpeningMatchMode)}
            >
              <option value="cosine">Cosine</option>
              <option value="dot_product">Dot product</option>
            </select>
          </label>
        </div>
      </div>
      <div className="grid gap-3">
        {rematchError ? <div className="rounded-md p-3 text-sm" style={{ border: "1px solid #e8c4b8", backgroundColor: "#f9ede9", color: "#7c3a2d" }}>{rematchError}</div> : null}
        {matches.map((match, index) => (
          <div key={`${targetColor}-${match.opening_name}-${index}`} className="grid max-w-2xl gap-3 rounded-md p-3 sm:grid-cols-[80px_minmax(0,1fr)]" style={{ border: "1px solid var(--line)" }}>
            <OpeningBoardPreview fen={match.fen} label={match.opening_name} />
            <div className="min-w-0">
              <div className="truncate font-semibold" style={{ color: "var(--ink)" }} title={match.opening_name}>{match.opening_name}</div>
              <div className="mt-1 truncate text-sm" style={{ color: "var(--ink-soft)" }} title={`ECO ${match.eco_values ?? "n/a"}`}>{matchMode === "dot_product" ? "dot" : "cos"} {formatNumber(match.similarity_score, 3)} · {match.used_vector_color} · ECO {match.eco_values ?? "n/a"} · lines {match.line_count ?? "n/a"}</div>
              <div className="mt-2 line-clamp-2 text-xs" style={{ color: "var(--ink-faint)" }}>{match.representative_pgn ?? "No representative line"}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
