import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  Target,
  XCircle,
} from "lucide-react";
import { OpeningBoardPreview } from "~/components/report/opening-board-preview";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import {
  ApiRequestError,
  analyzeReportMistakes,
  getActiveReportMistakes,
  queryReportMistakeGames,
} from "~/lib/api";
import type {
  GameSummary,
  MistakeAnalysisItem,
  ReportAnalysisContext,
  ReportBuildRequest,
  ReportMistakesResponse,
} from "~/lib/types";
import { cn } from "~/lib/utils";

type ResultFilter = "all" | "loss" | "draw" | "win";
type RatedFilter = "all" | "rated" | "unrated";
type DetailMode = "simple" | "advanced";
type SortMode = "impact" | "move" | "severity" | "punished";
type GroupMode = "game" | "severity" | "theme" | "outcome";

type ReportMistakesDraft = {
  sidecarId: string;
  selectedIds: string[];
  engineDepth: number;
  maxPunishmentPlies: number;
  timeClass: string;
  ratedFilter: RatedFilter;
  resultFilter: ResultFilter;
  sinceYear: number | "";
  sinceMonth: number | "";
  untilYear: number | "";
  untilMonth: number | "";
};

const TIME_CLASSES = ["rapid", "blitz", "bullet", "daily"];
const GAME_LIST_PAGE_SIZE = 5;
const MISTAKE_GROUPS_PAGE_SIZE = 5;
const RESPONSIVE_INITIAL_DIMENSION = { width: 1, height: 1 };

type RankedMistake = {
  mistake: MistakeAnalysisItem;
  rank: number;
};

type MistakeGameGroup = {
  key: string;
  game: GameSummary | null;
  gameUrl: string | null;
  title?: string;
  subtitle?: string;
  mistakes: RankedMistake[];
};

type GameMistakeStats = {
  mistakes: number;
  blunders: number;
  punished: number;
  worstLoss: number;
  topTheme: string | null;
};

export function MistakesReportSection({
  username,
  reportHash,
  context,
  reportFilters,
  onRebuild,
}: {
  username: string;
  reportHash: string;
  context: ReportAnalysisContext | null;
  reportFilters: Pick<ReportBuildRequest, "time_classes" | "rated_filter" | "since_year" | "since_month" | "until_year" | "until_month"> | null;
  onRebuild: () => void;
}) {
  const [engineDepth, setEngineDepth] = useState(context?.engine_depth ?? 10);
  const [maxPunishmentPlies, setMaxPunishmentPlies] = useState(8);
  const [timeClass, setTimeClass] = useState<string>(reportFilters?.time_classes?.[0] ?? "all");
  const [ratedFilter, setRatedFilter] = useState<RatedFilter>(
    reportFilters?.rated_filter === true ? "rated" : reportFilters?.rated_filter === false ? "unrated" : "all",
  );
  const [resultFilter, setResultFilter] = useState<ResultFilter>("all");
  const [sinceYear, setSinceYear] = useState<number | "">(reportFilters?.since_year ?? "");
  const [sinceMonth, setSinceMonth] = useState<number | "">(reportFilters?.since_month ?? "");
  const [untilYear, setUntilYear] = useState<number | "">(reportFilters?.until_year ?? "");
  const [untilMonth, setUntilMonth] = useState<number | "">(reportFilters?.until_month ?? "");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set(context?.default_game_ids ?? []));
  const [games, setGames] = useState<GameSummary[]>(context?.games ?? []);
  const [gamesLoading, setGamesLoading] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<ReportMistakesResponse | null>(null);
  const [detailMode, setDetailMode] = useState<DetailMode>("simple");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [gameEditorOpen, setGameEditorOpen] = useState(false);
  const [gameListPage, setGameListPage] = useState(1);
  const [catalogPage, setCatalogPage] = useState(1);
  const [catalogHasMore, setCatalogHasMore] = useState(false);
  const [sortMode, setSortMode] = useState<SortMode>("impact");
  const [groupMode, setGroupMode] = useState<GroupMode>("game");
  const [activeTheme, setActiveTheme] = useState<string | null>(null);
  const [mistakeGroupsPage, setMistakeGroupsPage] = useState(1);
  const [draftReady, setDraftReady] = useState(false);
  const sidecarId = context?.sidecar_id ?? context?.default_game_ids.join("|") ?? "missing";

  const apiFilters = useMemo(
    () => ({
      time_classes: timeClass === "all" ? null : [timeClass],
      rated_filter: ratedFilter === "all" ? null : ratedFilter === "rated",
      since_year: sinceYear === "" ? null : sinceYear,
      since_month: sinceMonth === "" ? null : sinceMonth,
      until_year: untilYear === "" ? null : untilYear,
      until_month: untilMonth === "" ? null : untilMonth,
      result_filter: resultFilter === "all" ? null : [resultFilter],
    }),
    [ratedFilter, resultFilter, sinceMonth, sinceYear, timeClass, untilMonth, untilYear],
  );

  useEffect(() => {
    let cancelled = false;
    const initialPickerFilters = {
      time_classes: reportFilters?.time_classes ?? null,
      rated_filter: reportFilters?.rated_filter ?? null,
      since_year: reportFilters?.since_year ?? null,
      since_month: reportFilters?.since_month ?? null,
      until_year: reportFilters?.until_year ?? null,
      until_month: reportFilters?.until_month ?? null,
      result_filter: null,
    };
    setAnalysis(null);
    setDraftReady(false);
    setError(null);
    setGameListPage(1);
    setGames(context?.games ?? []);
    setSelectedIds(new Set(context?.default_game_ids ?? []));
    setEngineDepth(context?.engine_depth ?? 10);
    setMaxPunishmentPlies(8);
    setTimeClass(reportFilters?.time_classes?.[0] ?? "all");
    setRatedFilter(reportFilters?.rated_filter === true ? "rated" : reportFilters?.rated_filter === false ? "unrated" : "all");
    setResultFilter("all");
    setSinceYear(reportFilters?.since_year ?? "");
    setSinceMonth(reportFilters?.since_month ?? "");
    setUntilYear(reportFilters?.until_year ?? "");
    setUntilMonth(reportFilters?.until_month ?? "");
    if (!context?.engine_enriched) return () => { cancelled = true; };

    setAnalysisLoading(true);
    getActiveReportMistakes(reportHash)
      .catch((err) => {
        if (err instanceof ApiRequestError && err.status === 404) {
          return analyzeReportMistakes(reportHash, {
            selected_game_ids: context.default_game_ids,
            engine_depth: context.engine_depth,
            max_punishment_plies: 8,
            picker_filters: initialPickerFilters,
          });
        }
        throw err;
      })
      .then((response) => {
        if (cancelled) return;
        applyAnalysisResponse(response);
        applyDraft(loadReportDraft(reportHash, sidecarId));
        setDraftReady(true);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not analyze mistakes.");
          setDraftReady(true);
        }
      })
      .finally(() => {
        if (!cancelled) setAnalysisLoading(false);
      });
    return () => { cancelled = true; };
  }, [reportHash, sidecarId]);

  useEffect(() => {
    if (!draftReady) return;
    saveReportDraft(reportHash, {
      sidecarId,
      selectedIds: Array.from(selectedIds),
      engineDepth,
      maxPunishmentPlies,
      timeClass,
      ratedFilter,
      resultFilter,
      sinceYear,
      sinceMonth,
      untilYear,
      untilMonth,
    });
  }, [draftReady, engineDepth, maxPunishmentPlies, ratedFilter, reportHash, resultFilter, selectedIds, sidecarId, sinceMonth, sinceYear, timeClass, untilMonth, untilYear]);

  function applyAnalysisResponse(response: ReportMistakesResponse) {
    setAnalysis(response);
    setGames((current) => mergeGames(current, context?.games ?? [], response.selected_games));
    const metadata = response.metadata as Record<string, unknown>;
    setSelectedIds(new Set(stringArray(metadata.selected_game_ids)));
    setEngineDepth(numberOr(metadata.engine_depth, context?.engine_depth ?? 10));
    setMaxPunishmentPlies(numberOr(metadata.max_punishment_plies, 8));
    const filters = metadata.picker_filters;
    if (isRecord(filters)) {
      const classes = stringArray(filters.time_classes);
      setTimeClass(classes[0] ?? "all");
      setRatedFilter(filters.rated_filter === true ? "rated" : filters.rated_filter === false ? "unrated" : "all");
      const results = stringArray(filters.result_filter);
      setResultFilter(isResultFilter(results[0]) ? results[0] : "all");
      setSinceYear(optionalNumber(filters.since_year));
      setSinceMonth(optionalNumber(filters.since_month));
      setUntilYear(optionalNumber(filters.until_year));
      setUntilMonth(optionalNumber(filters.until_month));
    }
  }

  function applyDraft(draft: ReportMistakesDraft | null) {
    if (!draft) return;
    setSelectedIds(new Set(draft.selectedIds));
    setEngineDepth(draft.engineDepth);
    setMaxPunishmentPlies(draft.maxPunishmentPlies);
    setTimeClass(draft.timeClass);
    setRatedFilter(draft.ratedFilter);
    setResultFilter(draft.resultFilter);
    setSinceYear(draft.sinceYear);
    setSinceMonth(draft.sinceMonth);
    setUntilYear(draft.untilYear);
    setUntilMonth(draft.untilMonth);
  }

  const filteredGames = useMemo(
    () => games.filter((game) => resultFilter === "all" || game.result === resultFilter),
    [games, resultFilter],
  );
  const selectedGames = useMemo(
    () => games.filter((game) => game.id && selectedIds.has(game.id)),
    [games, selectedIds],
  );
  const gameListPageCount = Math.max(1, Math.ceil(filteredGames.length / GAME_LIST_PAGE_SIZE));
  const visibleGames = useMemo(() => {
    const start = (gameListPage - 1) * GAME_LIST_PAGE_SIZE;
    return filteredGames.slice(start, start + GAME_LIST_PAGE_SIZE);
  }, [filteredGames, gameListPage]);
  const topMistake = analysis?.mistakes[0] ?? null;
  const gameStats = useMemo(
    () => summarizeGamesFromMistakes(analysis?.mistakes ?? []),
    [analysis?.mistakes],
  );
  const visibleMistakes = useMemo(
    () => rankAndFilterMistakes(analysis?.mistakes ?? [], sortMode, activeTheme),
    [activeTheme, analysis?.mistakes, sortMode],
  );
  const mistakeGroups = useMemo(
    () => groupMistakes(visibleMistakes, mergeGames(games, analysis?.selected_games ?? []), groupMode),
    [analysis?.selected_games, games, groupMode, visibleMistakes],
  );
  const mistakeGroupsPageCount = Math.max(1, Math.ceil(mistakeGroups.length / MISTAKE_GROUPS_PAGE_SIZE));
  const resolvedMistakeGroupsPage = Math.min(mistakeGroupsPage, mistakeGroupsPageCount);
  const mistakeGroupsPageStart = (resolvedMistakeGroupsPage - 1) * MISTAKE_GROUPS_PAGE_SIZE;
  const paginatedMistakeGroups = useMemo(
    () => mistakeGroups.slice(mistakeGroupsPageStart, mistakeGroupsPageStart + MISTAKE_GROUPS_PAGE_SIZE),
    [mistakeGroups, mistakeGroupsPageStart],
  );
  const activeIds = stringArray((analysis?.metadata as Record<string, unknown> | undefined)?.selected_game_ids);
  const stale = Boolean(
    analysis && (
      sortedKey(activeIds) !== sortedKey(Array.from(selectedIds))
      || numberOr(analysis.metadata.engine_depth, 0) !== engineDepth
      || numberOr(analysis.metadata.max_punishment_plies, 0) !== maxPunishmentPlies
    ),
  );

  useEffect(() => {
    setGameListPage((current) => Math.min(current, gameListPageCount));
  }, [gameListPageCount]);

  useEffect(() => {
    setMistakeGroupsPage(1);
  }, [activeTheme, analysis?.analysis_hash, groupMode, sortMode]);

  async function runAnalysis() {
    setAnalysisLoading(true);
    setError(null);
    try {
      const ids = Array.from(selectedIds);
      if (ids.length === 0) throw new Error("Select at least one game.");
      const response = await analyzeReportMistakes(reportHash, {
        selected_game_ids: ids,
        engine_depth: engineDepth,
        max_punishment_plies: maxPunishmentPlies,
        picker_filters: apiFilters,
      });
      applyAnalysisResponse(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not analyze mistakes.");
    } finally {
      setAnalysisLoading(false);
    }
  }

  async function loadCatalog(page = 1) {
    setGamesLoading(true);
    setError(null);
    try {
      const response = await queryReportMistakeGames(reportHash, {
        page,
        page_size: 50,
        ...apiFilters,
      });
      setGames((current) => mergeGames(page === 1 ? context?.games ?? [] : current, response.items));
      setCatalogPage(page);
      setCatalogHasMore(response.has_more && page * response.page_size < 500);
      if (page === 1) setGameListPage(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load games.");
    } finally {
      setGamesLoading(false);
    }
  }

  function toggleSelected(id: string | null) {
    if (!id) return;
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectLosses() {
    setSelectedIds(new Set(games.filter((game) => game.result === "loss").map((game) => game.id).filter(isString)));
  }

  function selectRecent(count: number) {
    setSelectedIds(new Set(filteredGames.slice(0, count).map((game) => game.id).filter(isString)));
  }

  if (!context?.engine_enriched) {
    return (
      <section id="mistakes" aria-labelledby="mistakes-heading" className="scroll-mt-5 space-y-4 border-t border-slate-200 pt-6">
        <div>
          <div className="flex items-center gap-2" style={{ color: "var(--accent)" }}>
            <ShieldAlert className="h-5 w-5" />
            <h2 id="mistakes-heading" className="text-xl" style={{ fontFamily: "var(--font-display)", color: "var(--ink)" }}>Mistakes and learning priorities</h2>
          </div>
          <p className="mt-1 max-w-3xl text-sm" style={{ color: "var(--ink-soft)" }}>Concrete positions where evaluation changed, grouped into practical review priorities.</p>
        </div>
        <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          <p className="font-semibold">Engine data is not available for this report.</p>
          <p className="mt-1 text-amber-800">Rebuild the report once with Stockfish enabled. The profile remains available while the new report is generated.</p>
          <Button className="mt-3" size="sm" onClick={onRebuild}><RefreshCw className="h-4 w-4" /> Rebuild with engine</Button>
        </div>
      </section>
    );
  }

  return (
    <section id="mistakes" aria-labelledby="mistakes-heading" className="scroll-mt-5 space-y-4 border-t border-slate-200 pt-6" style={{ color: "var(--ink)" }}>
        <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <div className="flex items-center gap-2" style={{ color: "var(--accent)" }}>
              <ShieldAlert className="h-5 w-5" />
              <h2 id="mistakes-heading" className="text-xl" style={{ fontFamily: "var(--font-display)", color: "var(--ink)" }}>Mistakes and learning priorities</h2>
            </div>
            <p className="mt-1 max-w-3xl text-sm" style={{ color: "var(--ink-soft)" }}>Review the most consequential decisions from this report, then adjust the game sample independently.</p>
          </div>
          <div className="flex items-center gap-2">
            <SegmentedControl
              value={detailMode}
              onChange={(value) => setDetailMode(value as DetailMode)}
              options={[
                ["simple", "Simple"],
                ["advanced", "Advanced"],
              ]}
              ariaLabel="Analysis detail mode"
            />
            <Button onClick={runAnalysis} disabled={analysisLoading || gamesLoading || selectedIds.size === 0}>
              {analysisLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {analysis ? "Rerun" : "Analyze"}
            </Button>
          </div>
        </div>

        {error ? (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">
            {error}
          </div>
        ) : null}

        {stale ? (
          <div className="mb-4 flex flex-col gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 sm:flex-row sm:items-center sm:justify-between" role="status">
            <span>The game selection or engine settings changed. Results below are from the previous run.</span>
            <Button size="sm" onClick={runAnalysis} disabled={analysisLoading}>Update results</Button>
          </div>
        ) : null}

        <div className="mistakes-report-layout">
          <section className="space-y-4" aria-label="Analyzer controls">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Target className="h-4 w-4" />
                  Analysis setup
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between rounded-md border px-3 py-2" style={{ borderColor: "var(--line)", backgroundColor: "var(--paper-dark)" }}>
                  <div><div className="text-sm font-semibold">{selectedIds.size} games selected</div><div className="text-xs" style={{ color: "var(--ink-soft)" }}>Changes affect only this chapter.</div></div>
                  <Button variant="outline" size="sm" onClick={() => setGameEditorOpen((value) => !value)}>{gameEditorOpen ? "Close" : "Edit"}</Button>
                </div>

                {/* Engine params — collapsible */}
                <button
                  type="button"
                  onClick={() => setSettingsOpen((current) => !current)}
                  className="flex w-full items-center justify-between rounded-md border px-3 py-2 text-sm font-semibold"
                  style={{ borderColor: "var(--line)", backgroundColor: "var(--paper-dark)" }}
                  aria-expanded={settingsOpen}
                >
                  <span className="flex items-center gap-2">
                    <SlidersHorizontal className="h-4 w-4" />
                    Engine settings
                  </span>
                  {settingsOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </button>

                {settingsOpen ? (
                  <div className="grid grid-cols-2 gap-3">
                    <NumberField label="Engine depth" value={engineDepth} min={1} max={30} onChange={setEngineDepth} />
                    <NumberField label="PV plies" value={maxPunishmentPlies} min={1} max={20} onChange={setMaxPunishmentPlies} />
                  </div>
                ) : null}
              </CardContent>
            </Card>

            {gameEditorOpen ? <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="flex items-center gap-2">
                    <Activity className="h-4 w-4" />
                    Games
                  </CardTitle>
                  <span className="text-xs" style={{ color: "var(--ink-soft)" }}>
                    {selectedIds.size} selected
                  </span>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <div className="mb-2 text-xs uppercase" style={{ color: "var(--ink-faint)" }}>Result</div>
                  <div className="grid grid-cols-4 gap-1.5">
                    {(["all", "loss", "draw", "win"] as ResultFilter[]).map((value) => (
                      <ModeButton
                        key={value}
                        active={resultFilter === value}
                        onClick={() => {
                          setResultFilter(value);
                          setGameListPage(1);
                        }}
                        label={title(value)}
                      />
                    ))}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <SelectField label="Time" value={timeClass} onChange={setTimeClass} options={[["all", "All"], ...TIME_CLASSES.map((item) => [item, title(item)] as [string, string])]} />
                  <SelectField label="Rated" value={ratedFilter} onChange={(value) => setRatedFilter(value as RatedFilter)} options={[["all", "All"], ["rated", "Rated"], ["unrated", "Unrated"]]} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <OptionalNumberField label="Since year" value={sinceYear} min={2000} max={2100} onChange={setSinceYear} />
                  <OptionalNumberField label="Since month" value={sinceMonth} min={1} max={12} onChange={setSinceMonth} />
                  <OptionalNumberField label="Until year" value={untilYear} min={2000} max={2100} onChange={setUntilYear} />
                  <OptionalNumberField label="Until month" value={untilMonth} min={1} max={12} onChange={setUntilMonth} />
                </div>
                <Button variant="outline" size="sm" className="w-full" onClick={() => loadCatalog(1)} disabled={gamesLoading}><Search className="h-4 w-4" /> Search games</Button>
                <div className="grid grid-cols-3 gap-1.5">
                  <Button variant="secondary" size="sm" onClick={selectLosses} type="button">Losses</Button>
                  <Button variant="secondary" size="sm" onClick={() => selectRecent(12)} type="button">Recent 12</Button>
                  <Button variant="outline" size="sm" onClick={() => setSelectedIds(new Set())} type="button">Clear</Button>
                </div>
                <div className="space-y-2">
                  {gamesLoading ? (
                    <div className="flex h-24 items-center justify-center">
                      <Loader2 className="h-5 w-5 animate-spin" />
                    </div>
                  ) : filteredGames.length === 0 ? (
                    <div className="rounded-md border p-4 text-sm" style={{ borderColor: "var(--line)", color: "var(--ink-soft)" }}>
                      No games.
                    </div>
                  ) : (
                    visibleGames.map((game) => (
                      <GameRow
                        key={game.id ?? `${game.end_time}-${game.opponent_username}`}
                        game={game}
                        selected={Boolean(game.id && selectedIds.has(game.id))}
                        previewing={false}
                        stats={game.id ? gameStats.get(game.id) ?? null : null}
                        onToggle={() => toggleSelected(game.id)}
                      />
                    ))
                  )}
                </div>
                {filteredGames.length > 0 ? (
                  <nav
                    className="flex items-center justify-between gap-3 border-t pt-3"
                    style={{ borderColor: "var(--line)" }}
                    aria-label="Games pagination"
                  >
                    <span className="text-xs tabular-nums" style={{ color: "var(--ink-soft)" }} aria-live="polite">
                      {(gameListPage - 1) * GAME_LIST_PAGE_SIZE + 1}–{Math.min(gameListPage * GAME_LIST_PAGE_SIZE, filteredGames.length)} of {filteredGames.length}
                    </span>
                    <div className="flex items-center gap-1.5">
                      <Button
                        variant="outline"
                        size="icon"
                        type="button"
                        onClick={() => setGameListPage((current) => Math.max(1, current - 1))}
                        disabled={gameListPage === 1}
                        aria-label="Previous games page"
                      >
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <span className="min-w-12 text-center text-xs font-semibold tabular-nums" style={{ color: "var(--ink-soft)" }}>
                        {gameListPage} / {gameListPageCount}
                      </span>
                      <Button
                        variant="outline"
                        size="icon"
                        type="button"
                        onClick={() => setGameListPage((current) => Math.min(gameListPageCount, current + 1))}
                        disabled={gameListPage === gameListPageCount}
                        aria-label="Next games page"
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </nav>
                ) : null}
                {catalogHasMore ? <Button variant="outline" size="sm" className="w-full" onClick={() => loadCatalog(catalogPage + 1)} disabled={gamesLoading}>Load more</Button> : null}
              </CardContent>
            </Card> : null}
          </section>

          <section className="space-y-4" aria-label="Mistakes analysis results" aria-live="polite">
            <SummaryPanel
              analysis={analysis}
              loading={analysisLoading}
              topMistake={topMistake}
              selectedCount={selectedGames.length}
              username={username}
              reportHash={reportHash}
              analysisHash={analysis?.analysis_hash ?? null}
              activeTheme={activeTheme}
              onThemeSelect={setActiveTheme}
            />

            {analysis?.mistakes.length ? (
              <div className="rounded-md border p-3" style={{ borderColor: "var(--line)", backgroundColor: "var(--paper)" }}>
                <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-center">
                  <div>
                    <h2 className="text-lg font-semibold" style={{ fontFamily: "var(--font-display)" }}>
                      Priority review
                    </h2>
                    <p className="text-sm" style={{ color: "var(--ink-soft)" }}>
                      {visibleMistakes.length} of {analysis.mistakes.length} mistakes shown
                      {activeTheme ? ` for ${themeLabel(activeTheme)}` : ""}. Start with the highest-impact rows.
                    </p>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <SelectField
                      label="Sort"
                      value={sortMode}
                      onChange={(value) => setSortMode(value as SortMode)}
                      options={[
                        ["impact", "Highest impact"],
                        ["move", "Move order"],
                        ["severity", "Severity"],
                        ["punished", "Punished first"],
                      ]}
                    />
                    <SelectField
                      label="Group"
                      value={groupMode}
                      onChange={(value) => setGroupMode(value as GroupMode)}
                      options={[
                        ["game", "By game"],
                        ["severity", "By severity"],
                        ["theme", "By theme"],
                        ["outcome", "By outcome"],
                      ]}
                    />
                  </div>
                </div>
                {activeTheme ? (
                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={() => setActiveTheme(null)}
                      className="rounded-md border px-3 py-1.5 text-xs font-semibold"
                      style={{ borderColor: "var(--line)", backgroundColor: "var(--paper-dark)" }}
                    >
                      Clear theme filter: {themeLabel(activeTheme)}
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}

            {mistakeGroups.length ? (
              <div className="space-y-3">
                {mistakeGroupsPageCount > 1 ? (
                  <div
                    className="flex gap-2 overflow-x-auto rounded-md border p-2"
                    style={{ borderColor: "var(--line)", backgroundColor: "var(--paper-dark)" }}
                    role="tablist"
                    aria-label={groupMode === "game" ? "Mistake game pages" : "Mistake group pages"}
                  >
                    {Array.from({ length: mistakeGroupsPageCount }, (_, index) => {
                      const page = index + 1;
                      const pageStart = index * MISTAKE_GROUPS_PAGE_SIZE + 1;
                      const pageEnd = Math.min((index + 1) * MISTAKE_GROUPS_PAGE_SIZE, mistakeGroups.length);
                      const active = page === resolvedMistakeGroupsPage;
                      return (
                        <button
                          key={page}
                          id={`mistake-games-tab-${page}`}
                          type="button"
                          role="tab"
                          aria-selected={active}
                          aria-controls="mistake-games-panel"
                          onClick={() => setMistakeGroupsPage(page)}
                          className="min-w-24 shrink-0 rounded-full border px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                          style={{
                            borderColor: active ? "var(--acid)" : "var(--line)",
                            backgroundColor: active ? "var(--acid)" : "var(--paper)",
                            color: active ? "#0a0e0b" : "var(--ink)",
                          }}
                        >
                          <span className="block text-xs font-extrabold">Page {page}</span>
                          <span className="block text-[11px] opacity-70">
                            {groupMode === "game" ? "Games" : "Groups"} {pageStart}–{pageEnd}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                ) : null}

                <div
                  id="mistake-games-panel"
                  role="tabpanel"
                  aria-labelledby={mistakeGroupsPageCount > 1 ? `mistake-games-tab-${resolvedMistakeGroupsPage}` : undefined}
                  className="grid gap-2"
                >
                  {paginatedMistakeGroups.map((group, pageGroupIndex) => {
                    const groupIndex = mistakeGroupsPageStart + pageGroupIndex;
                    return (
                      <MistakeGameSection
                        key={group.key}
                        group={group}
                        username={username}
                        reportHash={reportHash}
                        analysisHash={analysis?.analysis_hash ?? ""}
                        groupIndex={groupIndex}
                        totalGroups={mistakeGroups.length}
                        detailMode={detailMode}
                      />
                    );
                  })}
                </div>

                {mistakeGroupsPageCount > 1 ? (
                  <nav
                    className="flex flex-col items-center justify-between gap-3 rounded-md border px-3 py-2 sm:flex-row"
                    style={{ borderColor: "var(--line)", backgroundColor: "var(--paper-dark)" }}
                    aria-label={groupMode === "game" ? "Mistake games pagination" : "Mistake groups pagination"}
                  >
                    <span className="text-xs tabular-nums" style={{ color: "var(--ink-soft)" }} aria-live="polite">
                      {groupMode === "game" ? "Games" : "Groups"} {mistakeGroupsPageStart + 1}–{Math.min(mistakeGroupsPageStart + MISTAKE_GROUPS_PAGE_SIZE, mistakeGroups.length)} of {mistakeGroups.length}
                    </span>
                    <div className="flex items-center gap-1.5">
                      <Button
                        variant="outline"
                        size="icon"
                        type="button"
                        onClick={() => setMistakeGroupsPage((current) => Math.max(1, current - 1))}
                        disabled={resolvedMistakeGroupsPage === 1}
                        aria-label="Previous mistake games page"
                      >
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <span className="min-w-14 text-center text-xs font-semibold tabular-nums" style={{ color: "var(--ink-soft)" }}>
                        {resolvedMistakeGroupsPage} / {mistakeGroupsPageCount}
                      </span>
                      <Button
                        variant="outline"
                        size="icon"
                        type="button"
                        onClick={() => setMistakeGroupsPage((current) => Math.min(mistakeGroupsPageCount, current + 1))}
                        disabled={resolvedMistakeGroupsPage === mistakeGroupsPageCount}
                        aria-label="Next mistake games page"
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </nav>
                ) : null}
              </div>
            ) : analysis && !analysisLoading ? (
              <div className="rounded-md border p-8 text-center" style={{ borderColor: "var(--line)", color: "var(--ink-soft)" }}>
                No candidate mistakes in this sample.
              </div>
            ) : null}
          </section>
        </div>
    </section>
  );
}

function MistakeGameSection({
  group,
  username,
  reportHash,
  analysisHash,
  groupIndex,
  totalGroups,
  detailMode,
}: {
  group: MistakeGameGroup;
  username: string;
  reportHash: string;
  analysisHash: string;
  groupIndex: number;
  totalGroups: number;
  detailMode: DetailMode;
}) {
  const [collapsed, setCollapsed] = useState(groupIndex > 0);
  const game = group.game;
  const topLoss = Math.max(...group.mistakes.map(({ mistake }) => mistake.cp_loss ?? 0));
  const punishedCount = group.mistakes.filter(({ mistake }) => mistake.actual_punished).length;
  const severityCounts = group.mistakes.reduce<Record<string, number>>((counts, { mistake }) => {
    counts[mistake.severity] = (counts[mistake.severity] ?? 0) + 1;
    return counts;
  }, {});

  return (
    <section
      className="rounded-md border"
      style={{
        borderColor: "var(--line)",
        background: "linear-gradient(145deg, var(--paper-raised), var(--paper-dark))",
      }}
      aria-labelledby={`mistake-game-${groupIndex}`}
    >
      <button
        type="button"
        onClick={() => setCollapsed((current) => !current)}
        className="grid w-full gap-3 rounded-t-md border-b p-3 text-left transition-colors hover:bg-black/[0.03] lg:grid-cols-[minmax(0,1fr)_auto]"
        style={{ borderColor: "var(--line)", backgroundColor: "var(--paper-dark)" }}
        aria-expanded={!collapsed}
        aria-controls={`mistake-game-panel-${groupIndex}`}
      >
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {collapsed ? <ChevronRight className="h-4 w-4 shrink-0" /> : <ChevronDown className="h-4 w-4 shrink-0" />}
            <span className={cn("h-2.5 w-2.5 rounded-full", resultColor(game?.result ?? "unknown"))} />
            <h2 id={`mistake-game-${groupIndex}`} className="truncate text-lg font-semibold" style={{ fontFamily: "var(--font-display)" }}>
              {group.title ?? gameLabel(game, group)}
            </h2>
            {group.gameUrl ? (
              <a
                className="text-xs underline-offset-2 hover:underline"
                href={group.gameUrl}
                target="_blank"
                rel="noreferrer"
                onClick={(event) => event.stopPropagation()}
                style={{ color: "var(--accent)" }}
              >
                game
              </a>
            ) : null}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm" style={{ color: "var(--ink-soft)" }}>
            <span>{group.subtitle ?? `Group ${groupIndex + 1}/${totalGroups}`}</span>
            {game ? <span>{formatGameDate(game)}</span> : null}
            {game ? <span>{game.opening_name ?? game.opening_eco ?? "Opening n/a"}</span> : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 lg:justify-end">
          <CompactPill label="Mistakes" value={group.mistakes.length} />
          <CompactPill label="Punished" value={`${punishedCount}/${group.mistakes.length}`} />
          <CompactPill label="Worst" value={formatCp(topLoss)} />
          {Object.entries(severityCounts).map(([severity, count]) => (
            <Badge key={severity} tone={severityTone(severity)}>
              {title(severity)} {count}
            </Badge>
          ))}
        </div>
      </button>

      {!collapsed ? (
        <div id={`mistake-game-panel-${groupIndex}`} className="divide-y" style={{ borderColor: "var(--line)" }}>
          {group.mistakes.map(({ mistake, rank }) => (
            <MistakeRow
              key={mistake.mistake_id}
              mistake={mistake}
              username={username}
              reportHash={reportHash}
              analysisHash={analysisHash}
              detailMode={detailMode}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

const THEME_COLORS = [
  "#ff6a4d", "#21e783", "#60a5fa", "#a78bfa",
  "#2dd4bf", "#fbbf24", "#fb923c", "#22d3ee",
  "#f472b6", "#75e6c2", "#dcff42", "#94a3b8",
];

function blunderThemeCounts(mistakes: MistakeAnalysisItem[]): { theme: string; label: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const mistake of mistakes) {
    if (mistake.severity !== "blunder") continue;
    for (const t of getMistakeThemes(mistake)) {
      counts.set(t, (counts.get(t) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([theme, count]) => ({ theme, label: themeLabel(theme), count }));
}

function SummaryPanel({
  analysis,
  loading,
  topMistake,
  selectedCount,
  username,
  reportHash,
  analysisHash,
  activeTheme,
  onThemeSelect,
}: {
  analysis: ReportMistakesResponse | null;
  loading: boolean;
  topMistake: MistakeAnalysisItem | null;
  selectedCount: number;
  username: string;
  reportHash: string;
  analysisHash: string | null;
  activeTheme: string | null;
  onThemeSelect: (theme: string | null) => void;
}) {
  const summary = analysis?.summary;
  const scopeText = `${selectedCount} selected`;
  const worstLoss = analysis?.mistakes.reduce((max, mistake) => Math.max(max, mistake.cp_loss ?? 0), 0) ?? null;
  const themeData = useMemo(() => blunderThemeCounts(analysis?.mistakes ?? []), [analysis?.mistakes]);

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_250px]">
      <div
        className="rounded-md border p-5"
        style={{
          borderColor: "var(--line)",
          background:
            "linear-gradient(135deg, color-mix(in srgb, var(--coral) 7%, var(--paper-dark)) 0%, var(--paper) 48%, color-mix(in srgb, var(--accent) 7%, var(--paper-dark)) 100%)",
        }}
      >
        {/* Header row */}
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.22em]" style={{ color: "var(--accent)" }}>
              {scopeText}
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-normal" style={{ fontFamily: "var(--font-display)" }}>
              {loading ? "Analyzing..." : summary ? `${summary.mistake_count} mistakes found` : "Ready"}
            </h2>
            <p className="mt-2 max-w-2xl text-sm" style={{ color: "var(--ink-soft)" }}>
              {summary
                ? "Review the biggest evaluation drops first, then train the tactical themes that repeat most often."
                : "Choose a sample, run analysis, then start from the highest-impact mistake."}
            </p>
          </div>
          {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <ShieldAlert className="h-5 w-5" />}
        </div>

        {/* Tactic theme pie + compact stats + legend */}
        {summary ? (
          <div className="mt-5 grid gap-4 lg:grid-cols-[200px_minmax(0,1fr)]">
            {/* Pie chart */}
            <div className="flex items-center justify-center">
              {themeData.length > 0 ? (
                <div style={{ width: 200, height: 200 }}>
                  <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={RESPONSIVE_INITIAL_DIMENSION}>
                    <PieChart>
                      <Pie
                        data={themeData}
                        dataKey="count"
                        nameKey="label"
                        innerRadius={52}
                        outerRadius={88}
                        paddingAngle={2}
                        onClick={(entry) => {
                          const t = (entry as unknown as { theme: string }).theme;
                          onThemeSelect(activeTheme === t ? null : t);
                        }}
                        style={{ cursor: "pointer" }}
                      >
                        {themeData.map((entry, index) => (
                          <Cell
                            key={entry.theme}
                            fill={THEME_COLORS[index % THEME_COLORS.length]}
                            opacity={activeTheme && activeTheme !== entry.theme ? 0.35 : 1}
                            stroke={activeTheme === entry.theme ? "var(--ink)" : "transparent"}
                            strokeWidth={activeTheme === entry.theme ? 2 : 0}
                          />
                        ))}
                      </Pie>
                      <Tooltip
                        formatter={(value) => [`${value} blunder${value !== 1 ? "s" : ""}`]}
                        contentStyle={{
                          backgroundColor: "var(--paper)",
                          border: "1px solid var(--line)",
                          borderRadius: 6,
                          fontSize: 12,
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div
                  className="flex h-[200px] w-[200px] items-center justify-center rounded-full border-2 border-dashed text-center text-xs"
                  style={{ borderColor: "var(--line)", color: "var(--ink-faint)" }}
                >
                  No tactical<br />themes in<br />blunders
                </div>
              )}
            </div>

            {/* Right column: compact stat strip + clickable legend */}
            <div className="flex flex-col gap-3">
              {/* Compact stat strip */}
              <div className="flex flex-wrap gap-2">
                <CompactPill label="Blunders" value={summary.severity_counts.blunder ?? 0} />
                <CompactPill label="Mistakes" value={summary.severity_counts.mistake ?? 0} />
                <CompactPill label="Punished" value={`${summary.actual_punished_count}/${summary.mistake_count}`} />
                <CompactPill label="Worst" value={worstLoss == null ? "—" : formatCp(worstLoss)} />
              </div>

              {/* Clickable theme legend (replaces "Recommended focus" chips) */}
              {themeData.length > 0 ? (
                <div>
                  <div className="mb-2 text-xs uppercase tracking-wider" style={{ color: "var(--ink-faint)" }}>
                    Tactic themes in blunders
                  </div>
                  <div className="flex flex-col gap-1">
                    {themeData.slice(0, 8).map((entry, index) => (
                      <button
                        key={entry.theme}
                        type="button"
                        onClick={() => onThemeSelect(activeTheme === entry.theme ? null : entry.theme)}
                        className="flex items-center gap-2 rounded px-2 py-1 text-left text-xs font-semibold transition-colors"
                        style={{
                          backgroundColor:
                            activeTheme === entry.theme
                              ? `color-mix(in srgb, ${THEME_COLORS[index % THEME_COLORS.length]} 14%, var(--paper))`
                              : "transparent",
                          color: activeTheme === entry.theme ? "var(--ink)" : "var(--ink-soft)",
                        }}
                      >
                        <span
                          className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                          style={{
                            backgroundColor: THEME_COLORS[index % THEME_COLORS.length],
                            opacity: activeTheme && activeTheme !== entry.theme ? 0.35 : 1,
                          }}
                        />
                        <span className="flex-1">{entry.label}</span>
                        <span style={{ color: "var(--ink-faint)" }}>{entry.count}</span>
                      </button>
                    ))}
                    {activeTheme ? (
                      <button
                        type="button"
                        onClick={() => onThemeSelect(null)}
                        className="mt-1 rounded px-2 py-1 text-left text-xs"
                        style={{ color: "var(--accent)" }}
                      >
                        ✕ Clear filter
                      </button>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {/* Action button */}
              <div className="mt-auto">
                <Link
                  to={topMistake && analysisHash ? mistakeDetailUrl(username, reportHash, analysisHash, topMistake.mistake_id) : "#"}
                >
                  <Button variant="default" size="sm" type="button" disabled={!topMistake}>
                    <Target className="h-4 w-4" />
                    Review highest impact
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        ) : (
          /* No analysis yet: show placeholder tiles */
          <div className="mt-5 grid grid-cols-2 gap-2 md:grid-cols-4">
            <StatTile label="Blunders" value="—" />
            <StatTile label="Mistakes" value="—" />
            <StatTile label="Punished" value="—" />
            <StatTile label="Worst loss" value="—" />
          </div>
        )}
      </div>

      <div className="rounded-md border p-3" style={{ borderColor: "var(--line)", backgroundColor: "var(--paper-dark)" }}>
        <OpeningBoardPreview fen={topMistake?.fen_before ?? null} label={topMistake ? `${topMistake.san} before mistake` : "Top mistake"} />
      </div>
    </div>
  );
}

function MistakeRow({
  mistake,
  username,
  reportHash,
  analysisHash,
  detailMode,
}: {
  mistake: MistakeAnalysisItem;
  username: string;
  reportHash: string;
  analysisHash: string;
  detailMode: DetailMode;
}) {
  const allTags = [...mistake.tactics];
  const bestMove = mistake.best_line[0] ?? null;

  return (
    <article className="grid gap-3 p-3 md:grid-cols-[minmax(210px,1fr)_minmax(0,1.4fr)_auto] md:items-center" style={{ backgroundColor: "var(--paper)" }}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={severityTone(mistake.severity)}>{title(mistake.severity)}</Badge>
          <span className="font-semibold">
            {mistake.move_number}
            {mistake.player_color === "black" ? "..." : "."} {mistake.san}
          </span>
          {mistake.actual_punished ? (
            <CheckCircle2 className="h-4 w-4" style={{ color: "var(--accent)" }} aria-label="Punished" />
          ) : (
            <XCircle className="h-4 w-4" style={{ color: "var(--accent)" }} aria-label="Escaped" />
          )}
        </div>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs" style={{ color: "var(--ink-soft)" }}>
          <span>{impactLabel(mistake)}</span>
          <span>{formatEvalTransition(mistake)}</span>
          {detailMode === "advanced" ? <span>{formatCp(mistake.cp_loss)} lost</span> : null}
          {detailMode === "advanced" ? <span>{formatPercent(mistake.wp_loss)} WP</span> : null}
          <span>{mistake.actual_punished ? "Punished" : "Escaped"}</span>
        </div>
      </div>

      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <CompactPill label="Best" value={bestMove ?? "—"} />
          <CompactPill label="Theme" value={allTags[0] ? themeLabel(allTags[0].theme) : "None"} />
          {detailMode === "advanced" ? <CompactPill label="Depth" value={mistake.theoretical_punishment_depth} /> : null}
          {detailMode === "advanced" ? <CompactPill label="Plies" value={mistake.theoretical_punishment_plies} /> : null}
          {detailMode === "advanced" ? <CompactPill label="Stable" value={mistake.stability_reached ? "yes" : "no"} /> : null}
        </div>
        {detailMode === "advanced" ? (
          <div className="mt-2 flex min-w-0 flex-wrap items-center gap-1.5">
            {mistake.best_line.length ? (
              mistake.best_line.slice(0, 6).map((move, moveIndex) => (
                <span
                  key={`${move}-${moveIndex}`}
                  className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px]"
                  style={{ backgroundColor: "var(--paper-dark)", border: "1px solid var(--line)" }}
                  title="Engine punishment line"
                >
                  {move}
                  {moveIndex < Math.min(mistake.best_line.length, 6) - 1 ? <ChevronRight className="h-3 w-3" /> : null}
                </span>
              ))
            ) : (
              <span className="text-xs" style={{ color: "var(--ink-soft)" }}>
                No engine line
              </span>
            )}
            {mistake.best_line.length > 6 ? (
              <span className="text-xs" style={{ color: "var(--ink-soft)" }}>
                +{mistake.best_line.length - 6}
              </span>
            ) : null}
          </div>
        ) : null}
        {allTags.length ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {allTags.slice(0, 4).map((tag, tagIndex) => (
              <Badge key={`${tag.theme}-${tag.move_uci}-${tagIndex}`} tone="green">
                {themeLabel(tag.theme)}
              </Badge>
            ))}
            {allTags.length > 4 ? <Badge tone="ink">+{allTags.length - 4}</Badge> : null}
          </div>
        ) : null}
      </div>

      <Link to={mistakeDetailUrl(username, reportHash, analysisHash, mistake.mistake_id)}>
        <Button variant="outline" size="sm" type="button" className="w-full md:w-auto">
          <Target className="h-4 w-4" />
          Analyze
        </Button>
      </Link>
    </article>
  );
}

function GameRow({
  game,
  selected,
  previewing,
  stats,
  onToggle,
}: {
  game: GameSummary;
  selected: boolean;
  previewing?: boolean;
  stats: GameMistakeStats | null;
  onToggle: () => void;
}) {
  const innerContent = (
    <>
      <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", resultColor(game.result))} />
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold">
          {game.player_color} vs {game.opponent_username ?? "Unknown"}
        </span>
        <span className="block truncate text-xs" style={{ color: "var(--ink-soft)" }}>
          {game.end_time_iso ? new Date(game.end_time_iso).toLocaleDateString() : "Date n/a"} · {game.opening_name ?? game.opening_eco ?? "Opening n/a"}
        </span>
        {stats ? (
          <span className="mt-1 block truncate text-xs font-medium" style={{ color: "var(--accent)" }}>
            {stats.mistakes} mistakes · {stats.blunders} blunders · worst {formatCp(stats.worstLoss)}
            {stats.topTheme ? ` · ${themeLabel(stats.topTheme)}` : ""}
          </span>
        ) : null}
      </span>
    </>
  );

  if (previewing) {
    return (
      <div
        className="grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-md border p-2.5"
        style={{
          borderColor: selected ? "var(--accent)" : "var(--line)",
          backgroundColor: selected
            ? "color-mix(in srgb, var(--accent) 7%, var(--paper))"
            : "var(--paper)",
          opacity: selected ? 1 : 0.4,
        }}
      >
        {innerContent}
        {selected ? (
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--accent)" }} aria-label="Will be analyzed" />
        ) : (
          <span className="text-xs capitalize" style={{ color: "var(--ink-soft)" }}>{game.result}</span>
        )}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onToggle}
      className="grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-md border p-2.5 text-left transition-transform hover:translate-x-0.5"
      style={{
        borderColor: selected ? "var(--accent)" : "var(--line)",
        backgroundColor: selected ? "color-mix(in srgb, var(--accent) 10%, var(--paper))" : "var(--paper)",
      }}
    >
      {innerContent}
      <span className="text-xs capitalize" style={{ color: "var(--ink-soft)" }}>
        {game.result}
      </span>
    </button>
  );
}

function ModeButton({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="h-10 rounded text-sm font-semibold transition-colors"
      style={{
        backgroundColor: active ? "var(--acid)" : "var(--paper-dark)",
        color: active ? "#0a0e0b" : "var(--ink)",
        border: active ? "1px solid var(--acid)" : "1px solid var(--line)",
      }}
    >
      {label}
    </button>
  );
}

function SegmentedControl({
  value,
  options,
  ariaLabel,
  onChange,
}: {
  value: string;
  options: [string, string][];
  ariaLabel: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="grid grid-flow-col rounded-md border p-1" role="group" aria-label={ariaLabel} style={{ borderColor: "var(--line)", backgroundColor: "var(--paper-dark)" }}>
      {options.map(([optionValue, label]) => (
        <button
          key={optionValue}
          type="button"
          onClick={() => onChange(optionValue)}
          className="h-8 rounded px-3 text-xs font-semibold transition-colors"
          style={{
            backgroundColor: value === optionValue ? "var(--acid)" : "transparent",
            color: value === optionValue ? "#0a0e0b" : "var(--ink)",
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function NumberField({ label, value, min, max, onChange }: { label: string; value: number; min: number; max: number; onChange: (value: number) => void }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-wider" style={{ color: "var(--ink-faint)" }}>{label}</span>
      <input
        className="h-10 w-full rounded-md border px-3 text-sm"
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(clamp(Number(event.target.value), min, max))}
        style={{ borderColor: "var(--line)", backgroundColor: "var(--paper)", color: "var(--ink)" }}
      />
    </label>
  );
}

function OptionalNumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number | "";
  min: number;
  max: number;
  onChange: (value: number | "") => void;
}) {
  return (
    <label className="text-xs font-medium">
      <span className="mb-1 block" style={{ color: "var(--ink-soft)" }}>{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(event.target.value === "" ? "" : Number(event.target.value))}
        className="h-9 w-full rounded-md border bg-white px-2 text-sm"
        style={{ borderColor: "var(--line)" }}
      />
    </label>
  );
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-wider" style={{ color: "var(--ink-faint)" }}>{label}</span>
      <select
        className="h-10 w-full rounded-md border px-3 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        style={{ borderColor: "var(--line)", backgroundColor: "var(--paper)", color: "var(--ink)" }}
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>{optionLabel}</option>
        ))}
      </select>
    </label>
  );
}

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border px-3 py-3" style={{ borderColor: "var(--line)", background: "linear-gradient(145deg, var(--paper-raised), var(--paper-dark))", boxShadow: "inset 0 1px 0 rgba(255,255,255,.025)" }}>
      <div className="text-xs uppercase tracking-wider" style={{ color: "var(--ink-faint)" }}>{label}</div>
      <div className="mt-1 text-xl font-semibold leading-none" style={{ fontFamily: "var(--font-display)" }}>{value}</div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md px-3 py-2" style={{ backgroundColor: "var(--paper-dark)", border: "1px solid var(--line)" }}>
      <div className="text-xs uppercase tracking-wider" style={{ color: "var(--ink-faint)" }}>{label}</div>
      <div className="mt-1 font-semibold">{value}</div>
    </div>
  );
}

function CompactPill({ label, value }: { label: string; value: string | number }) {
  return (
    <span
      className="inline-flex h-7 items-center gap-1 rounded border px-2 text-xs"
      style={{ borderColor: "var(--line)", backgroundColor: "var(--paper)", color: "var(--ink)" }}
    >
      <span style={{ color: "var(--ink-faint)" }}>{label}</span>
      <span className="font-semibold">{value}</span>
    </span>
  );
}

function Badge({ children, tone }: { children: ReactNode; tone: "red" | "amber" | "green" | "ink" }) {
  const styles = {
    red: { backgroundColor: "color-mix(in srgb, var(--coral) 12%, var(--paper-dark))", color: "#ff9c89", borderColor: "color-mix(in srgb, var(--coral) 48%, var(--line))" },
    amber: { backgroundColor: "color-mix(in srgb, #f59e0b 11%, var(--paper-dark))", color: "#fcd34d", borderColor: "color-mix(in srgb, #f59e0b 48%, var(--line))" },
    green: { backgroundColor: "color-mix(in srgb, var(--accent) 10%, var(--paper-dark))", color: "var(--accent)", borderColor: "color-mix(in srgb, var(--accent) 44%, var(--line))" },
    ink: { backgroundColor: "var(--paper-dark)", color: "var(--ink)", borderColor: "var(--line)" },
  }[tone];
  return (
    <span className="inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold" style={styles}>
      {children}
    </span>
  );
}

function resultColor(result: GameSummary["result"]) {
  if (result === "win") return "bg-emerald-500";
  if (result === "loss") return "bg-red-500";
  if (result === "draw") return "bg-amber-500";
  return "bg-slate-400";
}

function severityTone(severity: string): "red" | "amber" | "green" | "ink" {
  if (severity === "blunder") return "red";
  if (severity === "mistake") return "amber";
  if (severity === "inaccuracy") return "ink";
  return "green";
}

function title(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function themeLabel(value: string) {
  return title(value).replace("K", "k");
}

function formatCp(value: number | null) {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${Math.round(value)} cp`;
}

function formatPercent(value: number | null | undefined, digits = 0) {
  if (value == null) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

function formatNumber(value: number | null | undefined, digits = 0) {
  if (value == null) return "—";
  return value.toFixed(digits);
}

function clamp(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function isString(value: string | null): value is string {
  return typeof value === "string" && value.length > 0;
}

function rankAndFilterMistakes(mistakes: MistakeAnalysisItem[], sortMode: SortMode, activeTheme: string | null): RankedMistake[] {
  const ranked = mistakes
    .map((mistake, rank) => ({ mistake, rank }))
    .filter(({ mistake }) => !activeTheme || mistakeHasTheme(mistake, activeTheme));

  return ranked.sort((left, right) => {
    if (sortMode === "move") {
      return left.mistake.ply - right.mistake.ply || left.rank - right.rank;
    }
    if (sortMode === "severity") {
      return severityRank(right.mistake.severity) - severityRank(left.mistake.severity) || impactValue(right.mistake) - impactValue(left.mistake);
    }
    if (sortMode === "punished") {
      return Number(right.mistake.actual_punished) - Number(left.mistake.actual_punished) || impactValue(right.mistake) - impactValue(left.mistake);
    }
    return impactValue(right.mistake) - impactValue(left.mistake) || left.rank - right.rank;
  });
}

function groupMistakes(rankedMistakes: RankedMistake[], games: GameSummary[], groupMode: GroupMode): MistakeGameGroup[] {
  if (groupMode === "severity") {
    return groupRankedMistakes(rankedMistakes, ({ mistake }) => mistake.severity, (key) => ({
      title: title(key),
      subtitle: "Mistakes grouped by severity",
    }));
  }
  if (groupMode === "theme") {
    return groupRankedMistakes(rankedMistakes, ({ mistake }) => primaryTheme(mistake) ?? "no_theme", (key) => ({
      title: key === "no_theme" ? "No tactical theme" : themeLabel(key),
      subtitle: "Mistakes grouped by recurring tactic",
    }));
  }
  if (groupMode === "outcome") {
    return groupRankedMistakes(rankedMistakes, ({ mistake }) => (mistake.actual_punished ? "punished" : "escaped"), (key) => ({
      title: key === "punished" ? "Punished by opponent" : "Opponent let it go",
      subtitle: "Mistakes grouped by actual game outcome",
    }));
  }
  return groupMistakesByGame(rankedMistakes, games);
}

function groupRankedMistakes(
  rankedMistakes: RankedMistake[],
  getKey: (ranked: RankedMistake) => string,
  describe: (key: string) => Pick<MistakeGameGroup, "title" | "subtitle">,
): MistakeGameGroup[] {
  const groups = new Map<string, MistakeGameGroup>();
  rankedMistakes.forEach((ranked) => {
    const key = getKey(ranked);
    const existing = groups.get(key);
    if (existing) {
      existing.mistakes.push(ranked);
      return;
    }
    groups.set(key, {
      key,
      game: null,
      gameUrl: null,
      mistakes: [ranked],
      ...describe(key),
    });
  });
  return Array.from(groups.values());
}

function groupMistakesByGame(rankedMistakes: RankedMistake[], games: GameSummary[]): MistakeGameGroup[] {
  const gamesById = new Map(games.filter((game) => game.id).map((game) => [game.id as string, game]));
  const gamesByUrl = new Map(games.filter((game) => game.url).map((game) => [game.url as string, game]));
  const groups = new Map<string, MistakeGameGroup>();

  rankedMistakes.forEach(({ mistake, rank }) => {
    const key = gameGroupKey(mistake, rank);
    const game = (mistake.game_uuid ? gamesById.get(mistake.game_uuid) : null) ?? (mistake.game_url ? gamesByUrl.get(mistake.game_url) : null) ?? null;
    const existing = groups.get(key);
    if (existing) {
      existing.mistakes.push({ mistake, rank });
      if (!existing.game && game) existing.game = game;
      if (!existing.gameUrl && mistake.game_url) existing.gameUrl = mistake.game_url;
      return;
    }
    groups.set(key, {
      key,
      game,
      gameUrl: mistake.game_url ?? game?.url ?? null,
      title: gameLabel(game, { key, game, gameUrl: mistake.game_url ?? game?.url ?? null, mistakes: [] }),
      subtitle: game ? `${formatGameDate(game)} · ${game.opening_name ?? game.opening_eco ?? "Opening n/a"}` : "Game from analysis",
      mistakes: [{ mistake, rank }],
    });
  });

  return Array.from(groups.values());
}

function summarizeGamesFromMistakes(mistakes: MistakeAnalysisItem[]) {
  const stats = new Map<string, GameMistakeStats>();
  mistakes.forEach((mistake) => {
    if (!mistake.game_uuid) return;
    const current = stats.get(mistake.game_uuid) ?? {
      mistakes: 0,
      blunders: 0,
      punished: 0,
      worstLoss: 0,
      topTheme: null,
    };
    const themes = getMistakeThemes(mistake);
    current.mistakes += 1;
    current.blunders += mistake.severity === "blunder" ? 1 : 0;
    current.punished += mistake.actual_punished ? 1 : 0;
    current.worstLoss = Math.max(current.worstLoss, mistake.cp_loss ?? 0);
    current.topTheme = themes[0] ?? current.topTheme;
    stats.set(mistake.game_uuid, current);
  });
  return stats;
}

function topThemeEntries(themeCounts: Record<string, number>) {
  return Object.entries(themeCounts).sort((left, right) => right[1] - left[1]);
}

function getMistakeThemes(mistake: MistakeAnalysisItem) {
  return Array.from(new Set(mistake.tactics.map((tag) => tag.theme)));
}

function primaryTheme(mistake: MistakeAnalysisItem) {
  return getMistakeThemes(mistake)[0] ?? null;
}

function mistakeHasTheme(mistake: MistakeAnalysisItem, theme: string) {
  return getMistakeThemes(mistake).includes(theme);
}

function impactValue(mistake: MistakeAnalysisItem) {
  return mistake.cp_loss ?? (mistake.wp_loss == null ? 0 : mistake.wp_loss * 1000);
}

function severityRank(severity: string) {
  if (severity === "blunder") return 3;
  if (severity === "mistake") return 2;
  if (severity === "inaccuracy") return 1;
  return 0;
}

function impactLabel(mistake: MistakeAnalysisItem) {
  const before = evalBucket(mistake.user_eval_before_cp);
  const after = evalBucket(mistake.user_eval_after_cp);
  if (before !== after) return `Position changed from ${before} to ${after}`;
  if ((mistake.cp_loss ?? 0) >= 250) return `Major drop while still ${after}`;
  if ((mistake.cp_loss ?? 0) >= 120) return `Important chance lost`;
  return `Small but measurable slip`;
}

function evalBucket(cp: number | null) {
  if (cp == null) return "unclear";
  if (cp >= 250) return "winning";
  if (cp >= 80) return "better";
  if (cp > -80) return "balanced";
  if (cp > -250) return "worse";
  return "losing";
}

function formatEvalTransition(mistake: MistakeAnalysisItem) {
  return `${formatCp(mistake.user_eval_before_cp)} -> ${formatCp(mistake.user_eval_after_cp)}`;
}

function gameGroupKey(mistake: MistakeAnalysisItem, rank: number) {
  return mistake.game_uuid ?? mistake.game_url ?? `unknown-game-${rank}`;
}

function gameLabel(game: GameSummary | null, group: MistakeGameGroup) {
  if (game) {
    const colorLabel = title(game.player_color);
    return `${colorLabel} vs ${game.opponent_username ?? "Unknown"} · ${title(game.result)}`;
  }
  const firstMistake = group.mistakes[0]?.mistake;
  if (firstMistake?.game_uuid) return `Game ${firstMistake.game_uuid}`;
  if (firstMistake?.game_url) return "Game from analysis";
  return "Unknown game";
}

function formatGameDate(game: GameSummary | null) {
  if (!game?.end_time_iso) return "Date n/a";
  return new Date(game.end_time_iso).toLocaleDateString();
}

function mistakeDetailUrl(username: string, reportHash: string, analysisHash: string, mistakeId: string) {
  const query = new URLSearchParams({ analysisHash });
  return `/report/${encodeURIComponent(username)}/reports/${encodeURIComponent(reportHash)}/mistake/${encodeURIComponent(mistakeId)}?${query.toString()}`;
}

function numberOr(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function optionalNumber(value: unknown): number | "" {
  return typeof value === "number" && Number.isFinite(value) ? value : "";
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter(isString) : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isResultFilter(value: unknown): value is ResultFilter {
  return value === "all" || value === "loss" || value === "draw" || value === "win";
}

function mergeGames(...collections: GameSummary[][]): GameSummary[] {
  const games = new Map<string, GameSummary>();
  for (const collection of collections) {
    for (const game of collection) {
      const key = game.id ?? game.url;
      if (key) games.set(key, game);
    }
  }
  return Array.from(games.values()).sort((left, right) => (right.end_time ?? 0) - (left.end_time ?? 0));
}

function sortedKey(values: string[]) {
  return [...values].sort().join("\n");
}

function reportDraftKey(reportHash: string) {
  return `chess-insighter:report-mistakes-draft:${reportHash}`;
}

function loadReportDraft(reportHash: string, sidecarId: string): ReportMistakesDraft | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(reportDraftKey(reportHash));
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<ReportMistakesDraft>;
    if (value.sidecarId !== sidecarId || !Array.isArray(value.selectedIds) || !isRatedFilter(value.ratedFilter) || !isResultFilter(value.resultFilter)) return null;
    return {
      sidecarId,
      selectedIds: value.selectedIds.filter(isString),
      engineDepth: numberOr(value.engineDepth, 10),
      maxPunishmentPlies: numberOr(value.maxPunishmentPlies, 8),
      timeClass: typeof value.timeClass === "string" ? value.timeClass : "all",
      ratedFilter: value.ratedFilter,
      resultFilter: value.resultFilter,
      sinceYear: optionalNumber(value.sinceYear),
      sinceMonth: optionalNumber(value.sinceMonth),
      untilYear: optionalNumber(value.untilYear),
      untilMonth: optionalNumber(value.untilMonth),
    };
  } catch {
    return null;
  }
}

function saveReportDraft(reportHash: string, draft: ReportMistakesDraft) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(reportDraftKey(reportHash), JSON.stringify(draft));
  } catch {
    // The backend still restores the last completed analysis if storage is unavailable.
  }
}

function isRatedFilter(value: unknown): value is RatedFilter {
  return value === "all" || value === "rated" || value === "unrated";
}
