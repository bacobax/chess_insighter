import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
import type { MetricPoint, OpeningCount } from "~/lib/types";
import { formatNumber, formatPercent } from "~/lib/utils";

const COLORS = ["#21e783", "#dcff42", "#ff6a4d", "#75c6ff", "#c68cff", "#75e6c2", "#ffc36a"];
const RESPONSIVE_INITIAL_DIMENSION = { width: 1, height: 1 };
const TOOLTIP_CONTENT_STYLE = {
  backgroundColor: "#0d1310",
  border: "1px solid #314139",
  borderRadius: 12,
  boxShadow: "0 16px 42px rgba(0,0,0,.42)",
  color: "#f2f7f0",
};
const TOOLTIP_ITEM_STYLE = { color: "#f2f7f0" };
const TOOLTIP_LABEL_STYLE = { color: "#a5b3aa" };
const TOOLTIP_CURSOR = { fill: "rgba(33,231,131,.055)" };

export function SkillRadarChart({ data }: { data: MetricPoint[] }) {
  const chartData = data
    .filter((item) => !(item.key === "game_analysis" && item.value == null))
    .map((item) => ({ subject: item.label, value: item.value ?? 0, missing: item.value == null }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Skill profile</CardTitle>
        <CardDescription>A balanced view of performance across the main phases and decisions of a game.</CardDescription>
      </CardHeader>
      <CardContent className="h-80">
        <ResponsiveContainer minWidth={0} initialDimension={RESPONSIVE_INITIAL_DIMENSION}>
          <RadarChart data={chartData}>
            <PolarGrid stroke="#314139" />
            <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11, fill: "#a5b3aa" }} />
            <PolarRadiusAxis domain={[0, 1]} tickFormatter={(value) => `${Number(value) * 100}`} tick={{ fill: "#6f8076", fontSize: 10 }} />
            <Radar dataKey="value" stroke="#21e783" fill="#21e783" fillOpacity={0.2} />
            <Tooltip contentStyle={TOOLTIP_CONTENT_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} formatter={(value) => formatPercent(Number(value))} />
          </RadarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export function FavouriteOpeningsChart({ data }: { data: OpeningCount[] }) {
  const barData = data.slice(0, 12).map((item) => ({ ...item, label: `${item.color}: ${item.name}` }));
  const [view, setView] = useState<"bar" | "pie">("bar");
  return (
    <Card>
      <CardHeader>
        <CardTitle>Most played openings</CardTitle>
        <CardDescription>Opening frequency from the games included in this report.</CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs value={view} onValueChange={(value) => setView(value as "bar" | "pie")}>
          <TabsList>
            <TabsTrigger value="bar">Bar</TabsTrigger>
            <TabsTrigger value="pie">Pie</TabsTrigger>
          </TabsList>
          <TabsContent value="bar" className="h-80">
            {view === "bar" ? (
              <ResponsiveContainer minWidth={0} initialDimension={RESPONSIVE_INITIAL_DIMENSION}>
                <BarChart data={barData} layout="vertical" margin={{ left: 32 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#222f28" />
                  <XAxis type="number" allowDecimals={false} tick={{ fill: "#a5b3aa", fontSize: 11 }} />
                  <YAxis type="category" dataKey="label" width={140} tick={{ fontSize: 11, fill: "#a5b3aa" }} />
                  <Tooltip cursor={TOOLTIP_CURSOR} contentStyle={TOOLTIP_CONTENT_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} />
                  <Bar dataKey="count" fill="#21e783" radius={[0, 6, 6, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : null}
          </TabsContent>
          <TabsContent value="pie" className="h-80">
            {view === "pie" ? (
              <ResponsiveContainer minWidth={0} initialDimension={RESPONSIVE_INITIAL_DIMENSION}>
                <PieChart>
                  <Pie data={barData} dataKey="count" nameKey="label" outerRadius={105} label>
                    {barData.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={TOOLTIP_CONTENT_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : null}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

export function MetricBarChart({
  title,
  data,
  percent = true,
  embedded = false,
  description,
  directional = true,
}: {
  title: string;
  data: MetricPoint[];
  percent?: boolean;
  embedded?: boolean;
  description?: string;
  directional?: boolean;
}) {
  const chartData = data.map((item) => ({
    ...item,
    displayValue: item.value ?? 0,
    directionLabel: directional ? (item.direction === "higher" ? "higher is better" : "lower is better") : "measured value",
  }));
  const chart = (
    <>
      <div className="h-72">
        <ResponsiveContainer minWidth={0} initialDimension={RESPONSIVE_INITIAL_DIMENSION}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#222f28" />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#a5b3aa" }} interval={0} angle={-20} textAnchor="end" height={70} />
            <YAxis domain={percent ? [0, 1] : undefined} tickFormatter={(value) => percent ? `${Number(value) * 100}` : String(value)} tick={{ fill: "#a5b3aa", fontSize: 11 }} />
            <Tooltip cursor={TOOLTIP_CURSOR} contentStyle={TOOLTIP_CONTENT_STYLE} itemStyle={TOOLTIP_ITEM_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} formatter={(value, _name, props) => [percent ? formatPercent(Number(value)) : formatNumber(Number(value)), props.payload.directionLabel]} />
            <Bar dataKey="displayValue" fill="#21e783" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="sr-only">
        {data.map((item) => (
          <li key={item.key}>
            {item.label}: {item.value == null ? "not available" : percent ? formatPercent(item.value) : formatNumber(item.value)}{directional ? `; ${item.direction === "higher" ? "higher is better" : "lower is better"}` : ""}.
          </li>
        ))}
      </ul>
    </>
  );

  if (embedded) {
    return (
      <div className="min-w-0">
        <div className="mb-3">
          <h4 className="text-sm font-semibold" style={{ color: "var(--ink)" }}>{title}</h4>
          {description ? <p className="mt-1 text-xs" style={{ color: "var(--ink-soft)" }}>{description}</p> : null}
        </div>
        {chart}
      </div>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent>{chart}</CardContent>
    </Card>
  );
}
