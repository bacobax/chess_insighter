import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Loader2, RefreshCw } from "lucide-react";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Progress } from "~/components/ui/progress";
import { FavouriteOpeningsChart, MetricBarChart, SkillRadarChart } from "~/components/charts/report-charts";
import { buildReport, rematchOpenings } from "~/lib/api";
import type { Hparams, OpeningMatch, OpeningMatchMode, OpeningReportGroup, ReportBuildResponse } from "~/lib/types";
import { formatNumber, formatPercent } from "~/lib/utils";
import { OpeningBoardPreview } from "./opening-board-preview";
import { ReportConfigForm } from "./report-config-form";

export function PlayerReport({ username, defaultHparams }: { username: string; defaultHparams: Hparams }) {
  const [hparams, setHparams] = useState<Hparams>(defaultHparams);
  const [maxGames, setMaxGames] = useState(20);
  const [timeClass, setTimeClass] = useState<string>("all");
  const [ratedFilter, setRatedFilter] = useState<string>("all");
  const [sinceYear, setSinceYear] = useState<number | "">("");
  const [sinceMonth, setSinceMonth] = useState<number | "">("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [engineDepth, setEngineDepth] = useState(10);
  const [useEngine, setUseEngine] = useState(true);
  const [refreshCache, setRefreshCache] = useState(false);
  const [report, setReport] = useState<ReportBuildResponse | null>(null);
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
      {report ? <ReportDashboard report={report} /> : null}
    </div>
  );
}

function ReportDashboard({ report }: { report: ReportBuildResponse }) {
  const charts = report.report.charts;
  return (
    <div className="space-y-5">
      <div className="rounded-md border bg-white p-4 text-sm text-slate-600">
        Cache <span className="font-medium text-slate-950">{report.cache_hit ? "hit" : "miss"}</span> · hash <span className="font-mono text-xs">{report.cache_hash.slice(0, 12)}</span>
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
  const [rematching, setRematching] = useState(false);
  const [rematchError, setRematchError] = useState<string | null>(null);

  useEffect(() => {
    setMatches(initialMatches);
    setMatchMode(initialMatches[0]?.match_mode ?? "cosine");
    setRematchError(null);
  }, [report.cache_hash, targetColor]);

  async function changeMatchMode(nextMode: OpeningMatchMode) {
    setMatchMode(nextMode);
    setRematching(true);
    setRematchError(null);
    try {
      const response = await rematchOpenings({
        cache_hash: report.cache_hash,
        match_mode: nextMode,
        target_color: targetColor,
        limit: matches.length || 15,
      });
      setMatches(response.top_opening_matches);
      setMatchMode(response.match_mode);
    } catch (err) {
      setRematchError(err instanceof Error ? err.message : "Could not update opening matches.");
    } finally {
      setRematching(false);
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="text-base font-semibold">Top K Opening Matches</h3>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <span>Match type</span>
          <select
            className="h-9 rounded-md border px-2 text-sm"
            value={matchMode}
            disabled={rematching}
            onChange={(event) => changeMatchMode(event.target.value as OpeningMatchMode)}
          >
            <option value="cosine">Cosine similarity</option>
            <option value="dot_product">Dot product</option>
          </select>
        </label>
      </div>
      <div className="grid gap-3">
        {rematchError ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{rematchError}</div> : null}
        {matches.map((match, index) => (
          <div key={`${targetColor}-${match.opening_name}-${index}`} className="grid max-w-2xl gap-3 rounded-md border p-3 sm:grid-cols-[80px_minmax(0,1fr)]">
            <OpeningBoardPreview fen={match.fen} />
            <div className="min-w-0">
              <div className="truncate font-semibold" title={match.opening_name}>{match.opening_name}</div>
              <div className="mt-1 truncate text-sm text-slate-500" title={`ECO ${match.eco_values ?? "n/a"}`}>{matchMode === "dot_product" ? "dot" : "cos"} {formatNumber(match.similarity_score, 3)} · {match.used_vector_color} · ECO {match.eco_values ?? "n/a"} · lines {match.line_count ?? "n/a"}</div>
              <div className="mt-2 line-clamp-2 text-xs text-slate-500">{match.representative_pgn ?? "No representative line"}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
