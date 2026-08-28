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

const COLORS = ["#7c3a2d", "#4a3728", "#8b6914", "#2d5016", "#b58863", "#6b5d4f", "#9a6b5a"];
const RESPONSIVE_INITIAL_DIMENSION = { width: 1, height: 1 };

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
            <PolarGrid stroke="#c8b99a" />
            <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11, fill: "#6b6358" }} />
            <PolarRadiusAxis domain={[0, 1]} tickFormatter={(value) => `${Number(value) * 100}`} tick={{ fill: "#a89e8e", fontSize: 10 }} />
            <Radar dataKey="value" stroke="#7c3a2d" fill="#b58863" fillOpacity={0.3} />
            <Tooltip formatter={(value) => formatPercent(Number(value))} />
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
                  <CartesianGrid strokeDasharray="3 3" stroke="#dfd2bb" />
                  <XAxis type="number" allowDecimals={false} tick={{ fill: "#6b6358", fontSize: 11 }} />
                  <YAxis type="category" dataKey="label" width={140} tick={{ fontSize: 11, fill: "#6b6358" }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#7c3a2d" />
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
                  <Tooltip />
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
            <CartesianGrid strokeDasharray="3 3" stroke="#dfd2bb" />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#6b6358" }} interval={0} angle={-20} textAnchor="end" height={70} />
            <YAxis domain={percent ? [0, 1] : undefined} tickFormatter={(value) => percent ? `${Number(value) * 100}` : String(value)} tick={{ fill: "#6b6358", fontSize: 11 }} />
            <Tooltip formatter={(value, _name, props) => [percent ? formatPercent(Number(value)) : formatNumber(Number(value)), props.payload.directionLabel]} />
            <Bar dataKey="displayValue" fill="#7c3a2d" />
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
