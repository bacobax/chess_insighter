import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart } from "recharts";
import type { OpeningStudyTreeNode } from "~/lib/types";

// Fixed-size radar for use inside the hover card.
// Deliberately avoids ResponsiveContainer to prevent measure-on-mount flicker
// during the hover-reveal animation.

const AXES = [
  { key: "playerStyleMatch" as const, label: "Style" },
  { key: "aggressiveness" as const, label: "Aggro" },
  { key: "gambleness" as const, label: "Gamble" },
  { key: "memoryComplexity" as const, label: "Memory" },
  { key: "systemness" as const, label: "System" },
];

type Props = {
  stats: OpeningStudyTreeNode["stats"];
  width?: number;
  height?: number;
};

export function NodeRadarChart({ stats, width = 200, height = 150 }: Props) {
  const data = AXES.map(({ key, label }) => ({
    subject: label,
    value: Math.max(0, Math.min(1, stats[key])),
  }));

  return (
    <RadarChart width={width} height={height} data={data} cx="50%" cy="50%">
      <PolarGrid stroke="#c8b99a" />
      <PolarAngleAxis dataKey="subject" tick={{ fontSize: 9, fill: "#6b6358" }} />
      <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
      <Radar dataKey="value" stroke="#7c3a2d" fill="#b58863" fillOpacity={0.35} dot={false} />
    </RadarChart>
  );
}
