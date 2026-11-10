import type { TrainingCard, TrainingDay, TrainingOpeningPlayed } from "~/lib/types";

export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

export const HOURS_OPTIONS = [
  { key: "lite", label: "≈ 4 h / week", factor: 0.7 },
  { key: "standard", label: "5–6 h / week", factor: 1 },
  { key: "deep", label: "≈ 8 h / week", factor: 1.45 },
] as const;
export type HoursKey = (typeof HOURS_OPTIONS)[number]["key"];

export const VERDICTS: Record<TrainingOpeningPlayed["verdict"], { label: string; tone: string }> = {
  fix_first: { label: "Fix first", tone: "is-fix" },
  middlegame: { label: "Middlegame problem", tone: "is-mid" },
  keep: { label: "Keep", tone: "is-good" },
  consolidate: { label: "Consolidate", tone: "is-merge" },
  ignore: { label: "Too rare", tone: "is-muted" },
};

export const BLOCK_COLORS: { label: string; color: string }[] = [
  { label: "Weakness drills", color: "#ff6a4d" },
  { label: "Your own errors", color: "#21e783" },
  { label: "Puzzles", color: "#dcff42" },
  { label: "Openings / play", color: "#a5b3aa" },
];

export function todayKey(date = new Date()): (typeof WEEKDAYS)[number] {
  return WEEKDAYS[(date.getDay() + 6) % 7];
}

export function scaleMinutes(minutes: number, hours: HoursKey): number {
  const factor = HOURS_OPTIONS.find((option) => option.key === hours)?.factor ?? 1;
  return Math.max(5, Math.round((minutes * factor) / 5) * 5);
}

export function dayMinutes(day: TrainingDay, hours: HoursKey): number {
  return day.blocks.reduce((total, block) => total + scaleMinutes(block.minutes, hours), 0);
}

export function formatDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function formatShortDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function percent(value: number | null | undefined): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

export function signedPawns(cp: number | null | undefined): string {
  if (cp == null) return "—";
  const value = cp / 100;
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(1)}`;
}

export function isDue(card: TrainingCard, today = new Date()): boolean {
  if (card.retired) return false;
  return card.due_on <= localIsoDate(today);
}

export function localIsoDate(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function moveLabel(card: Pick<TrainingCard, "move_number" | "player_color">, san: string | null): string {
  if (!san) return "—";
  return card.player_color === "white" ? `${card.move_number}.${san}` : `${card.move_number}…${san}`;
}

/** Squares for a UCI move, e.g. "g1f3" → ["g1", "f3"]. */
export function uciSquares(uci: string | null): [string, string] | null {
  return uci && uci.length >= 4 ? [uci.slice(0, 2), uci.slice(2, 4)] : null;
}
