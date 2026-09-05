import { useParams } from "react-router";
import { InfiniteGamesScroller } from "~/components/games/infinite-games-scroller";
import { AppShell } from "~/components/layout/app-shell";

export default function GamesPage() {
  const params = useParams();
  const username = params.username ?? "";
  return <AppShell>{(
    <main id="main-content" className="page-shell min-h-screen px-5 py-8 sm:px-8 lg:px-12 lg:py-12" style={{ color: "var(--ink)" }}>
      <div className="mx-auto max-w-6xl">
        <InfiniteGamesScroller username={username} />
      </div>
    </main>
  )}</AppShell>;
}
