import { useParams } from "react-router";
import { InfiniteGamesScroller } from "~/components/games/infinite-games-scroller";

export default function GamesPage() {
  const params = useParams();
  const username = params.username ?? "";
  return (
    <main className="min-h-screen px-4 py-8" style={{ color: "var(--ink)" }}>
      <div className="mx-auto max-w-6xl">
        <InfiniteGamesScroller username={username} />
      </div>
    </main>
  );
}
