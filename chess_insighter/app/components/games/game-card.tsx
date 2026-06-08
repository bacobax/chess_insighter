import { ExternalLink } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import type { GameSummary } from "~/lib/types";
import { cn } from "~/lib/utils";

export function GameCard({ game }: { game: GameSummary }) {
  const date = game.end_time_iso ? new Date(game.end_time_iso).toLocaleString() : "Date unavailable";
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <span className={cn("h-2.5 w-2.5 rounded-full", resultColor(game.result))} />
              {game.result}
            </CardTitle>
            <p className="mt-1 text-sm text-slate-500">
              {game.player_color} vs {game.opponent_username ?? "Unknown"}
            </p>
          </div>
          {game.url ? (
            <a className="text-slate-500 hover:text-slate-950" href={game.url} target="_blank" rel="noreferrer" aria-label="Open game">
              <ExternalLink className="h-4 w-4" />
            </a>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
        <Field label="Player Elo" value={elo(game.player_elo_before, game.player_elo_after)} />
        <Field label="Opponent Elo" value={elo(game.opponent_elo_before, game.opponent_elo_after)} />
        <Field label="Time" value={date} />
        <Field label="Time Control" value={game.time_control ?? "n/a"} />
        <Field label="Class" value={[game.time_class, game.rated == null ? null : game.rated ? "rated" : "unrated"].filter(Boolean).join(" · ")} />
        <Field label="Opening" value={game.opening_name ?? game.opening_eco ?? "n/a"} />
      </CardContent>
    </Card>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase text-slate-400">{label}</div>
      <div className="mt-0.5 font-medium text-slate-800">{value}</div>
    </div>
  );
}

function elo(before: number | null, after: number | null) {
  if (before != null && after != null) return `${before} -> ${after}`;
  if (after != null) return `${after}`;
  return "n/a";
}

function resultColor(result: GameSummary["result"]) {
  if (result === "win") return "bg-emerald-500";
  if (result === "loss") return "bg-red-500";
  if (result === "draw") return "bg-amber-500";
  return "bg-slate-400";
}
