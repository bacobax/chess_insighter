import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import {
  Activity,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Loader2,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  Target,
  XCircle,
} from "lucide-react";
import { OpeningBoardPreview } from "~/components/report/opening-board-preview";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { analyzeMistakes, queryGames } from "~/lib/api";
import type { GameSummary, MistakeAnalysisItem, MistakesAnalysisResponse } from "~/lib/types";
import { cn } from "~/lib/utils";

type Mode = "latest" | "selected";
type ResultFilter = "all" | "loss" | "draw" | "win";
type RatedFilter = "all" | "rated" | "unrated";
type DetailMode = "simple" | "advanced";
type SortMode = "impact" | "move" | "severity" | "punished";
type GroupMode = "game" | "severity" | "theme" | "outcome";

const TIME_CLASSES = ["rapid", "blitz", "bullet", "daily"];
const BLUNDER_STORAGE_PREFIX = "chess-insighter:blunder";
const ANALYSIS_STORAGE_PREFIX = "chess-insighter:mistakes-analysis";

type PersistedMistakesState = {
  version: 1;
  mode: Mode;
  maxGames: number;
  engineDepth: number;
  maxPunishmentPlies: number;
  timeClass: string;
  ratedFilter: RatedFilter;
  resultFilter: ResultFilter;
  selectedIds: string[];
  games: GameSummary[];
  analysis: MistakesAnalysisResponse | null;
};

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

export default function MistakesPage() {
  const params = useParams();
  const username = params.username ?? "";
  const [mode, setMode] = useState<Mode>("latest");
  const [maxGames, setMaxGames] = useState(20);
  const [engineDepth, setEngineDepth] = useState(10);
  const [maxPunishmentPlies, setMaxPunishmentPlies] = useState(8);
  const [timeClass, setTimeClass] = useState<string>("all");
  const [ratedFilter, setRatedFilter] = useState<RatedFilter>("all");
  const [resultFilter, setResultFilter] = useState<ResultFilter>("all");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [games, setGames] = useState<GameSummary[]>([]);
  const [gamesLoading, setGamesLoading] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<MistakesAnalysisResponse | null>(null);
  const [restored, setRestored] = useState(false);
  const [detailMode, setDetailMode] = useState<DetailMode>("simple");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sortMode, setSortMode] = useState<SortMode>("impact");
  const [groupMode, setGroupMode] = useState<GroupMode>("game");
  const [activeTheme, setActiveTheme] = useState<string | null>(null);

  const apiFilters = useMemo(
    () => ({
      time_classes: timeClass === "all" ? null : [timeClass],
      rated_filter: ratedFilter === "all" ? null : ratedFilter === "rated",
    }),
    [ratedFilter, timeClass],
  );

  useEffect(() => {
    const saved = loadPersistedState(username);
    if (saved) {
      setMode(saved.mode);
      setMaxGames(saved.maxGames);
      setEngineDepth(saved.engineDepth);
      setMaxPunishmentPlies(saved.maxPunishmentPlies);
      setTimeClass(saved.timeClass);
      setRatedFilter(saved.ratedFilter);
      setResultFilter(saved.resultFilter);
      setSelectedIds(new Set(saved.selectedIds));
      setGames(saved.games);
      setAnalysis(saved.analysis);
    } else {
      setMode("latest");
      setMaxGames(20);
      setEngineDepth(10);
      setMaxPunishmentPlies(8);
      setTimeClass("all");
      setRatedFilter("all");
      setResultFilter("all");
      setSelectedIds(new Set());
      setGames([]);
      setAnalysis(null);
    }
    setError(null);
    setRestored(true);
  }, [username]);

  useEffect(() => {
    if (!restored) return;
    setGamesLoading(true);
    queryGames({ username, page: 1, page_size: 100, ...apiFilters })
      .then((response) => setGames(response.items))
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load games."))
      .finally(() => setGamesLoading(false));
  }, [apiFilters, restored, username]);

  useEffect(() => {
    if (!restored) return;
    persistState(username, {
      version: 1,
      mode,
      maxGames,
      engineDepth,
      maxPunishmentPlies,
      timeClass,
      ratedFilter,
      resultFilter,
      selectedIds: Array.from(selectedIds),
      games,
      analysis,
    });
  }, [
    analysis,
    engineDepth,
    games,
    maxGames,
    maxPunishmentPlies,
    mode,
    ratedFilter,
    restored,
    resultFilter,
    selectedIds,
    timeClass,
    username,
  ]);

  const filteredGames = useMemo(
    () => games.filter((game) => resultFilter === "all" || game.result === resultFilter),
    [games, resultFilter],
  );
  const selectedGames = useMemo(
    () => filteredGames.filter((game) => game.id && selectedIds.has(game.id)),
    [filteredGames, selectedIds],
  );
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
    () => groupMistakes(visibleMistakes, games, groupMode),
    [games, groupMode, visibleMistakes],
  );

  async function runAnalysis() {
    setAnalysisLoading(true);
    setError(null);
    try {
      const filteredLatestIds =
        mode === "latest" && resultFilter !== "all"
          ? filteredGames.slice(0, maxGames).map((game) => game.id).filter(isString)
          : null;
      const explicitSelectedIds = mode === "selected" ? Array.from(selectedIds) : null;
      const selected_game_ids = explicitSelectedIds ?? filteredLatestIds;
      if (mode === "selected" && (!selected_game_ids || selected_game_ids.length === 0)) {
        throw new Error("Select at least one game.");
      }
      if (resultFilter !== "all" && (!selected_game_ids || selected_game_ids.length === 0)) {
        throw new Error("No games match that result filter.");
      }
      const response = await analyzeMistakes({
        username,
        max_games: selected_game_ids ? Math.max(maxGames, games.length, selected_game_ids.length) : maxGames,
        selected_game_ids,
        engine_depth: engineDepth,
        max_punishment_plies: maxPunishmentPlies,
        ...apiFilters,
      });
      setAnalysis(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not analyze mistakes.");
    } finally {
      setAnalysisLoading(false);
    }
  }

  function toggleSelected(id: string | null) {
    if (!id) return;
    setMode("selected");
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectLosses() {
    setMode("selected");
    setSelectedIds(new Set(games.filter((game) => game.result === "loss").map((game) => game.id).filter(isString)));
  }

  function selectRecent(count: number) {
    setMode("selected");
    setSelectedIds(new Set(filteredGames.slice(0, count).map((game) => game.id).filter(isString)));
  }

  return (
    <main className="min-h-screen px-4 py-6" style={{ color: "var(--ink)" }}>
      <div className="mx-auto max-w-7xl">
        <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div className="flex items-center gap-3">
            <Link to={`/games/${encodeURIComponent(username)}`}>
              <Button variant="outline" size="icon" aria-label="Back to games">
                <ArrowLeft className="h-4 w-4" />
              </Button>
            </Link>
            <div>
              <p className="text-xs uppercase tracking-[0.22em]" style={{ color: "var(--accent)" }}>
                {username}
              </p>
              <h1 className="text-3xl font-semibold tracking-normal" style={{ fontFamily: "var(--font-display)" }}>
                Mistakes Analyzer
              </h1>
            </div>
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
            <Button onClick={runAnalysis} disabled={analysisLoading || gamesLoading}>
              {analysisLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Analyze
            </Button>
          </div>
        </div>

        {error ? (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">
            {error}
          </div>
        ) : null}

        <div className="grid gap-4 xl:grid-cols-[330px_minmax(0,1fr)]">
          <section className="space-y-4" aria-label="Analyzer controls">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Target className="h-4 w-4" />
                  Scope
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-2">
                  <ModeButton active={mode === "latest"} onClick={() => setMode("latest")} label="Latest" />
                  <ModeButton active={mode === "selected"} onClick={() => setMode("selected")} label="Selected" />
                </div>

                <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
                  <NumberField label="Games" value={maxGames} min={1} max={100} onChange={setMaxGames} />
                  <Button onClick={runAnalysis} disabled={analysisLoading || gamesLoading} className="self-end">
                    {analysisLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                    Analyze
                  </Button>
                </div>

                <button
                  type="button"
                  onClick={() => setSettingsOpen((current) => !current)}
                  className="flex w-full items-center justify-between rounded-md border px-3 py-2 text-sm font-semibold"
                  style={{ borderColor: "var(--line)", backgroundColor: "var(--paper-dark)" }}
                  aria-expanded={settingsOpen}
                >
                  <span className="flex items-center gap-2">
                    <SlidersHorizontal className="h-4 w-4" />
                    Advanced settings
                  </span>
                  {settingsOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </button>

                {settingsOpen ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-3">
                      <NumberField label="Engine depth" value={engineDepth} min={1} max={30} onChange={setEngineDepth} />
                      <NumberField label="PV plies" value={maxPunishmentPlies} min={1} max={20} onChange={setMaxPunishmentPlies} />
                      <SelectField
                        label="Rated"
                        value={ratedFilter}
                        onChange={(value) => setRatedFilter(value as RatedFilter)}
                        options={[
                          ["all", "All"],
                          ["rated", "Rated"],
                          ["unrated", "Unrated"],
                        ]}
                      />
                      <SelectField
                        label="Time"
                        value={timeClass}
                        onChange={setTimeClass}
                        options={[["all", "All"], ...TIME_CLASSES.map((item) => [item, title(item)] as [string, string])]}
                      />
                    </div>

                    <div>
                      <div className="mb-2 text-xs uppercase tracking-wider" style={{ color: "var(--ink-faint)" }}>
                        Result
                      </div>
                      <div className="grid grid-cols-4 gap-1.5">
                        {(["all", "loss", "draw", "win"] as ResultFilter[]).map((value) => (
                          <button
                            key={value}
                            type="button"
                            onClick={() => setResultFilter(value)}
                            className="h-8 rounded text-xs font-semibold transition-colors"
                            style={{
                              backgroundColor: resultFilter === value ? "var(--ink)" : "var(--paper-dark)",
                              color: resultFilter === value ? "var(--paper)" : "var(--ink)",
                              border: "1px solid var(--line)",
                            }}
                          >
                            {title(value)}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="flex items-center gap-2">
                    <Activity className="h-4 w-4" />
                    Records
                  </CardTitle>
                  <span className="text-xs" style={{ color: "var(--ink-soft)" }}>
                    {selectedIds.size} selected
                  </span>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-3 gap-1.5">
                  <Button variant="secondary" size="sm" onClick={selectLosses} type="button">Losses</Button>
                  <Button variant="secondary" size="sm" onClick={() => selectRecent(12)} type="button">Recent 12</Button>
                  <Button variant="outline" size="sm" onClick={() => setSelectedIds(new Set())} type="button">Clear</Button>
                </div>
                <div className="max-h-[560px] space-y-2 overflow-auto pr-1">
                  {gamesLoading ? (
                    <div className="flex h-24 items-center justify-center">
                      <Loader2 className="h-5 w-5 animate-spin" />
                    </div>
                  ) : filteredGames.length === 0 ? (
                    <div className="rounded-md border p-4 text-sm" style={{ borderColor: "var(--line)", color: "var(--ink-soft)" }}>
                      No games.
                    </div>
                  ) : (
                    filteredGames.map((game) => (
                      <GameRow
                        key={game.id ?? `${game.end_time}-${game.opponent_username}`}
                        game={game}
                        selected={Boolean(game.id && selectedIds.has(game.id))}
                        stats={game.id ? gameStats.get(game.id) ?? null : null}
                        onToggle={() => toggleSelected(game.id)}
                      />
                    ))
                  )}
                </div>
              </CardContent>
            </Card>
          </section>

          <section className="space-y-4" aria-label="Mistakes analysis results" aria-live="polite">
            <SummaryPanel
              analysis={analysis}
              loading={analysisLoading}
              topMistake={topMistake}
              selectedCount={selectedGames.length}
              mode={mode}
              maxGames={maxGames}
              username={username}
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
              <div className="grid gap-2">
                {mistakeGroups.map((group, groupIndex) => (
                  <MistakeGameSection
                    key={group.key}
                    group={group}
                    username={username}
                    groupIndex={groupIndex}
                    totalGroups={mistakeGroups.length}
                    detailMode={detailMode}
                  />
                ))}
              </div>
            ) : analysis && !analysisLoading ? (
              <div className="rounded-md border p-8 text-center" style={{ borderColor: "var(--line)", color: "var(--ink-soft)" }}>
                No candidate mistakes in this sample.
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </main>
  );
}

function MistakeGameSection({
  group,
  username,
  groupIndex,
  totalGroups,
  detailMode,
}: {
  group: MistakeGameGroup;
  username: string;
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
        backgroundColor: "color-mix(in srgb, var(--paper) 88%, white)",
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
            <MistakeRow key={`${mistake.game_uuid}-${mistake.ply}-${mistake.uci}-${rank}`} mistake={mistake} username={username} index={rank} detailMode={detailMode} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function SummaryPanel({
  analysis,
  loading,
  topMistake,
  selectedCount,
  mode,
  maxGames,
  username,
  activeTheme,
  onThemeSelect,
}: {
  analysis: MistakesAnalysisResponse | null;
  loading: boolean;
  topMistake: MistakeAnalysisItem | null;
  selectedCount: number;
  mode: Mode;
  maxGames: number;
  username: string;
  activeTheme: string | null;
  onThemeSelect: (theme: string | null) => void;
}) {
  const summary = analysis?.summary;
  const scopeText = mode === "selected" ? `${selectedCount} selected` : `latest ${maxGames}`;
  const topThemes = topThemeEntries(summary?.theme_counts ?? {});
  const worstLoss = analysis?.mistakes.reduce((max, mistake) => Math.max(max, mistake.cp_loss ?? 0), 0) ?? null;
  const recommendedTheme = topThemes[0]?.[0] ?? null;
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_250px]">
      <div
        className="rounded-md border p-5"
        style={{
          borderColor: "var(--line)",
          background:
            "linear-gradient(135deg, color-mix(in srgb, var(--accent) 11%, var(--paper)) 0%, var(--paper) 46%, color-mix(in srgb, #2d5016 10%, var(--paper)) 100%)",
        }}
      >
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
        <div className="mt-5 grid grid-cols-2 gap-2 md:grid-cols-4">
          <StatTile label="Blunders" value={summary?.severity_counts.blunder ?? "—"} />
          <StatTile label="Mistakes" value={summary?.severity_counts.mistake ?? "—"} />
          <StatTile label="Punished" value={summary ? `${summary.actual_punished_count}/${summary.mistake_count}` : "—"} />
          <StatTile label="Worst loss" value={worstLoss == null ? "—" : formatCp(worstLoss)} />
        </div>
        {summary ? (
          <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
            <div>
              <div className="mb-2 text-xs uppercase tracking-wider" style={{ color: "var(--ink-faint)" }}>
                Recommended focus
              </div>
              <div className="flex flex-wrap gap-2">
                {topThemes.slice(0, 5).map(([theme, count], index) => (
                  <button
                    key={theme}
                    type="button"
                    onClick={() => onThemeSelect(activeTheme === theme ? null : theme)}
                    className="rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors"
                    style={{
                      borderColor: activeTheme === theme ? "var(--accent)" : "var(--line)",
                      backgroundColor: activeTheme === theme ? "color-mix(in srgb, var(--accent) 12%, var(--paper))" : "var(--paper)",
                      color: activeTheme === theme ? "var(--accent)" : "var(--ink)",
                    }}
                  >
                    {index + 1}. {themeLabel(theme)} · {count}
                  </button>
                ))}
                {topThemes.length === 0 ? <Badge tone="ink">No themes yet</Badge> : null}
              </div>
            </div>
            <div className="flex flex-wrap gap-2 lg:justify-end">
              <Link to={topMistake ? `/mistakes/${encodeURIComponent(username)}/blunder/${encodeURIComponent(mistakeKey(topMistake, 0))}` : "#"} onClick={() => topMistake && sessionStorage.setItem(`${BLUNDER_STORAGE_PREFIX}:${username}:${mistakeKey(topMistake, 0)}`, JSON.stringify({ username, mistake: topMistake }))}>
                <Button variant="default" size="sm" type="button" disabled={!topMistake}>
                  <Target className="h-4 w-4" />
                  Review highest impact
                </Button>
              </Link>
              {recommendedTheme ? (
                <Button variant="outline" size="sm" type="button" onClick={() => onThemeSelect(recommendedTheme)}>
                  Train {themeLabel(recommendedTheme)}
                </Button>
              ) : null}
            </div>
          </div>
        ) : null}
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
  index,
  detailMode,
}: {
  mistake: MistakeAnalysisItem;
  username: string;
  index: number;
  detailMode: DetailMode;
}) {
  const allTags = [...mistake.tactics, ...mistake.actual_tactics];
  const blunderKey = mistakeKey(mistake, index);
  const bestMove = mistake.best_line[0] ?? null;

  function persistMistake() {
    sessionStorage.setItem(
      `${BLUNDER_STORAGE_PREFIX}:${username}:${blunderKey}`,
      JSON.stringify({ username, mistake }),
    );
  }

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
            <CheckCircle2 className="h-4 w-4" style={{ color: "#2d5016" }} aria-label="Punished" />
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

      <Link to={`/mistakes/${encodeURIComponent(username)}/blunder/${encodeURIComponent(blunderKey)}`} onClick={persistMistake}>
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
  stats,
  onToggle,
}: {
  game: GameSummary;
  selected: boolean;
  stats: GameMistakeStats | null;
  onToggle: () => void;
}) {
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
      <span className={cn("h-2.5 w-2.5 rounded-full", resultColor(game.result))} />
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
        backgroundColor: active ? "var(--ink)" : "var(--paper-dark)",
        color: active ? "var(--paper)" : "var(--ink)",
        border: "1px solid var(--line)",
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
            backgroundColor: value === optionValue ? "var(--ink)" : "transparent",
            color: value === optionValue ? "var(--paper)" : "var(--ink)",
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
    <div className="rounded-md border px-3 py-2" style={{ borderColor: "var(--line)", backgroundColor: "rgba(244,236,216,0.72)" }}>
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
    red: { backgroundColor: "color-mix(in srgb, var(--accent) 13%, var(--paper))", color: "var(--accent)", borderColor: "color-mix(in srgb, var(--accent) 36%, var(--paper))" },
    amber: { backgroundColor: "color-mix(in srgb, #8b6914 15%, var(--paper))", color: "#8b6914", borderColor: "#c4aa60" },
    green: { backgroundColor: "color-mix(in srgb, #2d5016 13%, var(--paper))", color: "#2d5016", borderColor: "#8ab578" },
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
  return Array.from(new Set([...mistake.tactics, ...mistake.actual_tactics].map((tag) => tag.theme)));
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

function mistakeKey(mistake: MistakeAnalysisItem, index: number) {
  return [
    mistake.game_uuid ?? "game",
    mistake.ply,
    mistake.uci,
    index,
  ].join("-").replace(/[^a-zA-Z0-9_-]/g, "_");
}

function analysisStorageKey(username: string) {
  return `${ANALYSIS_STORAGE_PREFIX}:${username}`;
}

function loadPersistedState(username: string): PersistedMistakesState | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(analysisStorageKey(username));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<PersistedMistakesState>;
    if (parsed.version !== 1) return null;
    if (!isMode(parsed.mode) || !isRatedFilter(parsed.ratedFilter) || !isResultFilter(parsed.resultFilter)) {
      return null;
    }
    return {
      version: 1,
      mode: parsed.mode,
      maxGames: numberOr(parsed.maxGames, 20),
      engineDepth: numberOr(parsed.engineDepth, 10),
      maxPunishmentPlies: numberOr(parsed.maxPunishmentPlies, 8),
      timeClass: typeof parsed.timeClass === "string" ? parsed.timeClass : "all",
      ratedFilter: parsed.ratedFilter,
      resultFilter: parsed.resultFilter,
      selectedIds: Array.isArray(parsed.selectedIds) ? parsed.selectedIds.filter(isString) : [],
      games: Array.isArray(parsed.games) ? parsed.games : [],
      analysis: parsed.analysis ?? null,
    };
  } catch {
    return null;
  }
}

function persistState(username: string, state: PersistedMistakesState) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(analysisStorageKey(username), JSON.stringify(state));
  } catch {
    // Session storage may be unavailable or full; the analyzer still works in memory.
  }
}

function numberOr(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function isMode(value: unknown): value is Mode {
  return value === "latest" || value === "selected";
}

function isRatedFilter(value: unknown): value is RatedFilter {
  return value === "all" || value === "rated" || value === "unrated";
}

function isResultFilter(value: unknown): value is ResultFilter {
  return value === "all" || value === "loss" || value === "draw" || value === "win";
}
