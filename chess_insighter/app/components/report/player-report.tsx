import { useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Progress } from "~/components/ui/progress";
import { FavouriteOpeningsChart, MetricBarChart, SkillRadarChart } from "~/components/charts/report-charts";
import { buildReport } from "~/lib/api";
import type { Hparams, ReportBuildResponse } from "~/lib/types";
import { formatNumber, formatPercent } from "~/lib/utils";
import { OpeningBoardPreview } from "./opening-board-preview";
import { ReportConfigForm } from "./report-config-form";

export function PlayerReport({ username, defaultHparams }: { username: string; defaultHparams: Hparams }) {
  const [hparams, setHparams] = useState<Hparams>(defaultHparams);
  const [maxGames, setMaxGames] = useState(20);
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
      const response = await buildReport({ username, hparams, max_games: maxGames, engine_depth: engineDepth, use_engine: useEngine, refresh_cache: refreshCache });
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
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-sm">
              <span className="mb-1 block text-slate-600">Max games</span>
              <input className="h-10 w-full rounded-md border px-3" type="number" min={1} max={500} value={maxGames} onChange={(event) => setMaxGames(Number(event.target.value))} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-600">Engine depth</span>
              <input className="h-10 w-full rounded-md border px-3" type="number" min={1} max={30} value={engineDepth} onChange={(event) => setEngineDepth(Number(event.target.value))} />
            </label>
            <div className="flex items-end gap-4 pb-2 text-sm">
              <label className="flex items-center gap-2"><input type="checkbox" checked={useEngine} onChange={(e) => setUseEngine(e.target.checked)} /> Use engine</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={refreshCache} onChange={(e) => setRefreshCache(e.target.checked)} /> Refresh</label>
            </div>
          </div>
          <ReportConfigForm value={hparams} onChange={setHparams} />
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
      <OpeningFeaturePanels report={report} />
      <OpeningCharacteristics report={report} />
      <TopOpeningMatches report={report} />
      <MetricBarChart title="Opening Components" data={charts.opening_components} />
      <MetricBarChart title="Time Management Indicators" data={charts.time_management_indicators} />
      <MetricBarChart title="Advantage Capitalization Components" data={charts.advantage_capitalization_components} />
      <MetricBarChart title="Resourcefulness Components" data={charts.resourcefulness_components} />
      <MetricBarChart title="Game Analysis Components" data={charts.game_analysis_components} />
      <MetricBarChart title="Average Time Spent by Complexity" data={charts.average_time_by_complexity} percent={false} />
    </div>
  );
}

function OpeningFeaturePanels({ report }: { report: ReportBuildResponse }) {
  return (
    <Card>
      <CardHeader><CardTitle>Top 3 Opening Features</CardTitle></CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        {report.report.charts.top_opening_features.map((opening) => (
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
      </CardContent>
    </Card>
  );
}

function OpeningCharacteristics({ report }: { report: ReportBuildResponse }) {
  return (
    <Card>
      <CardHeader><CardTitle>Opening Characteristics</CardTitle></CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        {report.report.charts.opening_characteristics.map((item) => (
          <div key={item.key} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
            <span className="font-medium">{item.label}</span> <span className="text-slate-500">{formatPercent(item.value)}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function TopOpeningMatches({ report }: { report: ReportBuildResponse }) {
  return (
    <Card>
      <CardHeader><CardTitle>Top K Opening Matches</CardTitle></CardHeader>
      <CardContent className="grid gap-4">
        {report.report.charts.top_opening_matches.map((match) => (
          <div key={match.opening_name} className="grid gap-4 rounded-md border p-3 sm:grid-cols-[96px_1fr]">
            <OpeningBoardPreview fen={match.fen} />
            <div>
              <div className="font-semibold">{match.opening_name}</div>
              <div className="mt-1 text-sm text-slate-500">similarity {formatNumber(match.similarity_score, 3)} · ECO {match.eco_values ?? "n/a"} · lines {match.line_count ?? "n/a"}</div>
              <div className="mt-2 text-xs text-slate-500">{match.representative_pgn ?? "No representative line"}</div>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
