import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { queryGames } from "~/lib/api";
import type { GameSummary } from "~/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";

const WIN_COLOR = "#2d5016";
const DRAW_COLOR = "#8b6914";
const LOSS_COLOR = "#7c3a2d";
const ELO_COLOR = "#7c3a2d";

interface TCRow {
  name: string;
  wins: number;
  losses: number;
  draws: number;
  total: number;
}

interface Stats {
  total: number;
  wins: number;
  losses: number;
  draws: number;
  winRate: number;
  currentElo: number | null;
  peakElo: number | null;
  eloSeries: { n: number; elo: number; date: string }[];
  byTimeControl: TCRow[];
}

function computeStats(games: GameSummary[]): Stats {
  const sorted = [...games].sort((a, b) => (a.end_time ?? 0) - (b.end_time ?? 0));

  let wins = 0, losses = 0, draws = 0;
  const eloSeries: { n: number; elo: number; date: string }[] = [];
  let peakElo: number | null = null;
  const byTC: Record<string, TCRow> = {};

  sorted.forEach((g, i) => {
    if (g.result === "win") wins++;
    else if (g.result === "loss") losses++;
    else if (g.result === "draw") draws++;

    const elo = g.player_elo_after ?? g.player_elo_before;
    if (elo != null) {
      eloSeries.push({
        n: i + 1,
        elo,
        date: g.end_time_iso ? new Date(g.end_time_iso).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "",
      });
      if (peakElo == null || elo > peakElo) peakElo = elo;
    }

    const tc = g.time_class ?? "other";
    if (!byTC[tc]) byTC[tc] = { name: tc, wins: 0, losses: 0, draws: 0, total: 0 };
    byTC[tc].total++;
    if (g.result === "win") byTC[tc].wins++;
    else if (g.result === "loss") byTC[tc].losses++;
    else byTC[tc].draws++;
  });

  const total = wins + losses + draws;
  const latest = sorted[sorted.length - 1];
  const currentElo = latest?.player_elo_after ?? latest?.player_elo_before ?? null;

  const byTimeControl = Object.values(byTC).sort((a, b) => b.total - a.total);

  // thin elo series to max 60 points for chart readability
  const thin = thinSeries(eloSeries, 60);

  return { total, wins, losses, draws, winRate: total > 0 ? wins / total : 0, currentElo, peakElo, eloSeries: thin, byTimeControl };
}

function thinSeries<T>(arr: T[], max: number): T[] {
  if (arr.length <= max) return arr;
  const step = arr.length / max;
  return Array.from({ length: max }, (_, i) => arr[Math.round(i * step)] as T);
}

function StatChip({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div
      className="flex flex-col items-center rounded-md px-4 py-3"
      style={{ background: "var(--paper-dark)", border: "1px solid var(--line)" }}
    >
      <span className="text-xs uppercase tracking-wider" style={{ color: "var(--ink-faint)", fontFamily: "var(--font-sans)" }}>
        {label}
      </span>
      <span className="mt-1 text-2xl font-semibold leading-none" style={{ fontFamily: "var(--font-display)", color: "var(--ink)" }}>
        {value}
      </span>
      {sub && (
        <span className="mt-0.5 text-xs" style={{ color: "var(--ink-soft)" }}>{sub}</span>
      )}
    </div>
  );
}

function ResultBar({ wins, draws, losses, total }: { wins: number; draws: number; losses: number; total: number }) {
  if (total === 0) return null;
  const wp = (wins / total) * 100;
  const dp = (draws / total) * 100;
  const lp = (losses / total) * 100;
  return (
    <div className="space-y-2">
      <div className="flex h-3 w-full overflow-hidden rounded-full" style={{ background: "var(--line-faint)" }}>
        <div style={{ width: `${wp}%`, background: WIN_COLOR }} className="transition-all duration-700" />
        <div style={{ width: `${dp}%`, background: DRAW_COLOR }} className="transition-all duration-700" />
        <div style={{ width: `${lp}%`, background: LOSS_COLOR }} className="transition-all duration-700" />
      </div>
      <div className="flex justify-between text-xs" style={{ color: "var(--ink-soft)" }}>
        <span><span className="inline-block h-2 w-2 rounded-full mr-1.5" style={{ background: WIN_COLOR }} />{wins} W · {wp.toFixed(0)}%</span>
        <span><span className="inline-block h-2 w-2 rounded-full mr-1.5" style={{ background: DRAW_COLOR }} />{draws} D</span>
        <span><span className="inline-block h-2 w-2 rounded-full mr-1.5" style={{ background: LOSS_COLOR }} />{losses} L · {lp.toFixed(0)}%</span>
      </div>
    </div>
  );
}

function EloChart({ data, current }: { data: { n: number; elo: number; date: string }[]; current: number | null }) {
  if (data.length < 3) return null;
  const elos = data.map((d) => d.elo);
  const mn = Math.min(...elos);
  const mx = Math.max(...elos);
  const pad = Math.max(20, Math.round((mx - mn) * 0.15));

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-baseline justify-between">
          <CardTitle className="text-sm">Elo Progression</CardTitle>
          {current != null && (
            <span className="text-lg font-semibold" style={{ fontFamily: "var(--font-display)", color: "var(--ink)" }}>
              {current}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="h-32">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
              <defs>
                <linearGradient id="eloGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={ELO_COLOR} stopOpacity={0.18} />
                  <stop offset="95%" stopColor={ELO_COLOR} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line-faint)" vertical={false} />
              <XAxis dataKey="date" hide tick={{ fontSize: 10, fill: "var(--ink-faint)" }} />
              <YAxis domain={[mn - pad, mx + pad]} tick={{ fontSize: 10, fill: "var(--ink-faint)" }} />
              <Tooltip
                contentStyle={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 6, fontSize: 12 }}
                labelStyle={{ color: "var(--ink-soft)" }}
                itemStyle={{ color: "var(--ink)" }}
                formatter={(v) => [v, "Elo"]}
              />
              <Area
                type="monotone"
                dataKey="elo"
                stroke={ELO_COLOR}
                strokeWidth={1.8}
                fill="url(#eloGrad)"
                dot={false}
                activeDot={{ r: 3, fill: ELO_COLOR }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function TimeControlBreakdown({ rows }: { rows: TCRow[] }) {
  if (rows.length === 0) return null;
  const top = rows.slice(0, 4);
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">By Time Control</CardTitle>
      </CardHeader>
      <CardContent className="pt-0 space-y-2.5">
        {top.map((row) => {
          const wp = row.total > 0 ? (row.wins / row.total) * 100 : 0;
          return (
            <div key={row.name}>
              <div className="flex justify-between text-xs mb-1" style={{ color: "var(--ink-soft)" }}>
                <span className="capitalize font-medium" style={{ color: "var(--ink)" }}>{row.name}</span>
                <span>{row.total} games · {wp.toFixed(0)}% W</span>
              </div>
              <div className="flex h-1.5 w-full overflow-hidden rounded-full" style={{ background: "var(--line-faint)" }}>
                <div style={{ width: `${(row.wins / row.total) * 100}%`, background: WIN_COLOR }} />
                <div style={{ width: `${(row.draws / row.total) * 100}%`, background: DRAW_COLOR }} />
                <div style={{ width: `${(row.losses / row.total) * 100}%`, background: LOSS_COLOR }} />
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

export function PlayerStatsPanel({ username }: { username: string }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setStats(null);
    setLoading(true);
    queryGames({ username, page: 1, page_size: 100 })
      .then((res) => setStats(computeStats(res.items)))
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, [username]);

  if (loading) {
    return (
      <div className="h-6 w-32 rounded animate-pulse" style={{ background: "var(--line-faint)" }} />
    );
  }
  if (!stats || stats.total === 0) return null;

  return (
    <div className="space-y-4 mb-2">
      {/* Stat chips */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatChip label="Games" value={String(stats.total)} sub="last 100" />
        <StatChip label="Win Rate" value={`${Math.round(stats.winRate * 100)}%`} sub={`${stats.wins}W ${stats.draws}D ${stats.losses}L`} />
        <StatChip label="Current Elo" value={stats.currentElo != null ? String(stats.currentElo) : "—"} />
        <StatChip label="Peak Elo" value={stats.peakElo != null ? String(stats.peakElo) : "—"} sub="in sample" />
      </div>

      {/* Result distribution */}
      <Card>
        <CardContent className="py-4">
          <ResultBar wins={stats.wins} draws={stats.draws} losses={stats.losses} total={stats.total} />
        </CardContent>
      </Card>

      {/* Charts row */}
      <div className="grid gap-4 lg:grid-cols-2">
        <EloChart data={stats.eloSeries} current={stats.currentElo} />
        <TimeControlBreakdown rows={stats.byTimeControl} />
      </div>
    </div>
  );
}
