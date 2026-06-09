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
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
import type { MetricPoint, OpeningCount } from "~/lib/types";
import { formatNumber, formatPercent } from "~/lib/utils";

const COLORS = ["#7c3a2d", "#4a3728", "#8b6914", "#2d5016", "#b58863", "#6b5d4f", "#9a6b5a"];

export function SkillRadarChart({ data }: { data: MetricPoint[] }) {
  const chartData = data
    .filter((item) => !(item.key === "game_analysis" && item.value == null))
    .map((item) => ({ subject: item.label, value: item.value ?? 0, missing: item.value == null }));
  return (
    <Card>
      <CardHeader><CardTitle>Skill Profile</CardTitle></CardHeader>
      <CardContent className="h-80">
        <ResponsiveContainer>
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
  return (
    <Card>
      <CardHeader><CardTitle>Favourite Openings</CardTitle></CardHeader>
      <CardContent>
        <Tabs defaultValue="bar">
          <TabsList>
            <TabsTrigger value="bar">Bar</TabsTrigger>
            <TabsTrigger value="pie">Pie</TabsTrigger>
          </TabsList>
          <TabsContent value="bar" className="h-80">
            <ResponsiveContainer>
              <BarChart data={barData} layout="vertical" margin={{ left: 32 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#dfd2bb" />
                <XAxis type="number" allowDecimals={false} tick={{ fill: "#6b6358", fontSize: 11 }} />
                <YAxis type="category" dataKey="label" width={140} tick={{ fontSize: 11, fill: "#6b6358" }} />
                <Tooltip />
                <Bar dataKey="count" fill="#7c3a2d" />
              </BarChart>
            </ResponsiveContainer>
          </TabsContent>
          <TabsContent value="pie" className="h-80">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={barData} dataKey="count" nameKey="label" outerRadius={105} label>
                  {barData.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} />)}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

export function MetricBarChart({ title, data, percent = true }: { title: string; data: MetricPoint[]; percent?: boolean }) {
  const chartData = data.map((item) => ({
    ...item,
    displayValue: item.value ?? 0,
    directionLabel: item.direction === "higher" ? "higher is better" : "lower is better",
  }));
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="h-72">
        <ResponsiveContainer>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#dfd2bb" />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#6b6358" }} interval={0} angle={-20} textAnchor="end" height={70} />
            <YAxis domain={percent ? [0, 1] : undefined} tickFormatter={(value) => percent ? `${Number(value) * 100}` : String(value)} tick={{ fill: "#6b6358", fontSize: 11 }} />
            <Tooltip formatter={(value, _name, props) => [percent ? formatPercent(Number(value)) : formatNumber(Number(value)), props.payload.directionLabel]} />
            <Bar dataKey="displayValue" fill="#7c3a2d" />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
