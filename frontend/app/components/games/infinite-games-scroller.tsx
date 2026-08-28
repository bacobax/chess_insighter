import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { ArrowLeft, BarChart3, Loader2, Sparkles } from "lucide-react";
import { Button } from "~/components/ui/button";
import { queryGames } from "~/lib/api";
import type { GameSummary } from "~/lib/types";
import { GameCard } from "./game-card";
import { PlayerStatsPanel } from "./player-stats-panel";

export function InfiniteGamesScroller({ username }: { username: string }) {
  const [games, setGames] = useState<GameSummary[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sentinel = useRef<HTMLDivElement | null>(null);

  const loadPage = useCallback(async (nextPage: number) => {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const response = await queryGames({ username, page: nextPage, page_size: 20 });
      setGames((current) => (nextPage === 1 ? response.items : [...current, ...response.items]));
      setHasMore(response.has_more);
      setPage(nextPage);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load games.");
    } finally {
      setLoading(false);
    }
  }, [loading, username]);

  useEffect(() => {
    setGames([]);
    setPage(1);
    setHasMore(true);
    void loadPage(1);
  }, [username]);

  useEffect(() => {
    if (!sentinel.current || !hasMore) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && !loading) void loadPage(page + 1);
    }, { rootMargin: "500px" });
    observer.observe(sentinel.current);
    return () => observer.disconnect();
  }, [hasMore, loadPage, loading, page]);

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-6 border-b border-[var(--line)] pb-8 sm:flex-row sm:items-end">
        <div>
          <Link to="/" className="mb-8 inline-flex items-center gap-2 text-xs font-bold text-[var(--ink-soft)] transition-colors hover:text-[var(--accent)]">
            <ArrowLeft className="h-3.5 w-3.5" /> New player
          </Link>
          <p className="eyebrow mb-3 flex items-center gap-2"><Sparkles className="h-3.5 w-3.5" /> Match archive / Live profile</p>
          <h1 className="font-[var(--font-display)] text-[clamp(3rem,8vw,6.5rem)] font-medium leading-[.84] tracking-[-.065em]">{username}</h1>
          <p className="mt-4 text-sm text-slate-500">Chess.com games · the latest 100 shape the snapshot below.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to={`/report/${encodeURIComponent(username)}`}>
            <Button className="px-6">
              <BarChart3 className="h-4 w-4" />
              Build player report
            </Button>
          </Link>
        </div>
      </div>
      <PlayerStatsPanel username={username} />
      {error ? <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
      {!loading && games.length === 0 && !error ? <div className="rounded-md border bg-white p-8 text-center text-slate-500">No games found.</div> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {games.map((game, index) => <GameCard key={game.id ?? `${game.end_time}-${index}`} game={game} />)}
      </div>
      <div ref={sentinel} className="flex h-16 items-center justify-center">
        {loading ? <Loader2 className="h-5 w-5 animate-spin text-slate-500" /> : hasMore ? null : <span className="text-sm text-slate-400">End of games</span>}
      </div>
    </div>
  );
}
