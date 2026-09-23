"use client";

import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ComposedChart, Line, XAxis, YAxis } from "recharts";

import { Card, CardContent } from "@/components/ui/card";
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { compactMoney, money, number, percent, signedPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

export type ValueFormat = "money" | "number" | "percent";

export function formatValue(v: number, f: ValueFormat = "number") {
  return f === "money" ? money(v) : f === "percent" ? percent(v) : number(v);
}

export function KpiCard({ label, value, format = "number", change, hint, className }: {
  label: string;
  value: number;
  format?: ValueFormat;
  change?: number | null;
  hint?: string;
  className?: string;
}) {
  const up = (change ?? 0) >= 0;
  return (
    <Card className={cn("gap-1 py-4", className)}>
      <CardContent className="px-4">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <p className="mt-1 text-2xl font-semibold tracking-tight">{formatValue(value, format)}</p>
        {change !== undefined && (
          <p className={cn("mt-1 flex items-center gap-0.5 text-xs", change === null ? "text-muted-foreground" : up ? "text-emerald-600" : "text-rose-600")}>
            {change !== null && (up ? <ArrowUpRight className="size-3.5" /> : <ArrowDownRight className="size-3.5" />)}
            {signedPercent(change)} <span className="ml-1 text-muted-foreground">{hint ?? "vs previous period"}</span>
          </p>
        )}
      </CardContent>
    </Card>
  );
}

const shortDate = (d: string) => new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric" });

export function TrendChart({ data, dataKey = "revenue", label = "Revenue", format = "money", className, secondaryKey, secondaryLabel }: {
  data: Record<string, unknown>[];
  dataKey?: string;
  label?: string;
  format?: ValueFormat;
  className?: string;
  secondaryKey?: string;
  secondaryLabel?: string;
}) {
  const config: ChartConfig = {
    [dataKey]: { label, color: "var(--chart-1)" },
    ...(secondaryKey ? { [secondaryKey]: { label: secondaryLabel ?? secondaryKey, color: "var(--chart-2)" } } : {}),
  };
  return (
    <ChartContainer config={config} className={cn("aspect-auto h-64 w-full", className)}>
      <AreaChart data={data} margin={{ left: 4, right: 8, top: 8 }}>
        <defs>
          <linearGradient id={`fill-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={`var(--color-${dataKey})`} stopOpacity={0.35} />
            <stop offset="95%" stopColor={`var(--color-${dataKey})`} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="date" tickLine={false} axisLine={false} tickMargin={8} minTickGap={28} tickFormatter={shortDate} />
        <YAxis tickLine={false} axisLine={false} width={48}
          tickFormatter={(v: number) => (format === "money" ? compactMoney(v) : number(v))} />
        <ChartTooltip content={<ChartTooltipContent labelFormatter={(v) => shortDate(String(v))} />} />
        <Area dataKey={dataKey} type="monotone" stroke={`var(--color-${dataKey})`} fill={`url(#fill-${dataKey})`} strokeWidth={2} />
        {secondaryKey && (
          <Area dataKey={secondaryKey} type="monotone" stroke={`var(--color-${secondaryKey})`} fill="transparent" strokeWidth={1.5} />
        )}
      </AreaChart>
    </ChartContainer>
  );
}

export function HBarChart({ data, dataKey, nameKey, label, format = "money", className }: {
  data: Record<string, unknown>[];
  dataKey: string;
  nameKey: string;
  label: string;
  format?: ValueFormat;
  className?: string;
}) {
  const config: ChartConfig = { [dataKey]: { label, color: "var(--chart-1)" } };
  return (
    <ChartContainer config={config} className={cn("aspect-auto w-full", className)} style={{ height: Math.max(160, data.length * 36) }}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey={nameKey} tickLine={false} axisLine={false} width={130}
          tickFormatter={(v: string) => (v.length > 18 ? `${v.slice(0, 17)}…` : v)} />
        <ChartTooltip content={<ChartTooltipContent formatter={(v) => formatValue(Number(v), format)} />} />
        <Bar dataKey={dataKey} fill={`var(--color-${dataKey})`} radius={4} />
      </BarChart>
    </ChartContainer>
  );
}

export function ForecastChart({ history, points, format = "money", className }: {
  history: { date: string; value: number }[];
  points: { date: string; value: number; lower: number | null; upper: number | null }[];
  format?: ValueFormat;
  className?: string;
}) {
  const data = [
    ...history.slice(-45).map((h) => ({ date: h.date, actual: h.value })),
    ...points.map((p) => ({ date: p.date, forecast: p.value, band: [p.lower ?? p.value, p.upper ?? p.value] })),
  ];
  const config: ChartConfig = {
    actual: { label: "Actual", color: "var(--chart-2)" },
    forecast: { label: "Forecast", color: "var(--chart-1)" },
    band: { label: "80% interval", color: "var(--chart-1)" },
  };
  return (
    <ChartContainer config={config} className={cn("aspect-auto h-64 w-full", className)}>
      <ComposedChart data={data} margin={{ left: 4, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="date" tickLine={false} axisLine={false} tickMargin={8} minTickGap={28} tickFormatter={shortDate} />
        <YAxis tickLine={false} axisLine={false} width={48}
          tickFormatter={(v: number) => (format === "money" ? compactMoney(v) : number(v))} />
        <ChartTooltip content={<ChartTooltipContent labelFormatter={(v) => shortDate(String(v))} />} />
        <Area dataKey="band" type="monotone" stroke="none" fill="var(--color-band)" fillOpacity={0.15} />
        <Line dataKey="actual" type="monotone" stroke="var(--color-actual)" strokeWidth={1.5} dot={false} />
        <Line dataKey="forecast" type="monotone" stroke="var(--color-forecast)" strokeWidth={2} strokeDasharray="5 3" dot={false} />
      </ComposedChart>
    </ChartContainer>
  );
}
