import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart } from "recharts";
import type { OpeningStudyTreeNode } from "~/lib/types";

// Fixed-size radar for use inside the hover card.
// Deliberately avoids ResponsiveContainer to prevent measure-on-mount flicker
// during the hover-reveal animation.

const AXES = [
  { key: "playerStyleMatch" as const, label: "Style" },
  { key: "aggressiveness" as const, label: "Aggro" },
  { key: "practicalGamble" as const, label: "Practical" },
  { key: "memoryComplexity" as const, label: "Memory" },
  { key: "systemness" as const, label: "System" },
];

type Props = {
  stats: OpeningStudyTreeNode["stats"];
  width?: number;
  height?: number;
};

export function NodeRadarChart({ stats, width = 200, height = 150 }: Props) {
  const data = AXES.filter(({ key }) => stats[key] != null).map(({ key, label }) => ({
    subject: label,
    value: Math.max(0, Math.min(1, stats[key] as number)),
  }));

  return (
    <RadarChart width={width} height={height} data={data} cx="50%" cy="50%">
      <PolarGrid stroke="#314139" />
      <PolarAngleAxis dataKey="subject" tick={{ fontSize: 9, fill: "#a5b3aa" }} />
      <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
      <Radar dataKey="value" stroke="#21e783" fill="#21e783" fillOpacity={0.25} dot={false} />
    </RadarChart>
  );
}
