"use client";

import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { useState } from "react";

import { HBarChart, KpiCard, TrendChart } from "@/components/charts/charts";
import { ErrorState, PageHeader } from "@/components/common/states";
import { DashboardPage } from "@/components/layout/dashboard-shell";
import { ForecastPanel } from "@/components/seller/forecast-panel";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { money, number, percent } from "@/lib/format";
import type { ProductPerf, SellerOverview } from "@/lib/types";

function PerfTable({ rows }: { rows: ProductPerf[] }) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader><TableRow><TableHead>Product</TableHead><TableHead className="text-right">Revenue</TableHead><TableHead className="text-right">Units</TableHead>
          <TableHead className="text-right">Views</TableHead><TableHead className="text-right">Conversion</TableHead><TableHead className="text-right">Stock</TableHead></TableRow></TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.product_id}>
              <TableCell className="max-w-56 truncate">{r.name}</TableCell>
              <TableCell className="text-right">{money(r.revenue)}</TableCell>
              <TableCell className="text-right">{number(r.units)}</TableCell>
              <TableCell className="text-right">{number(r.views)}</TableCell>
              <TableCell className="text-right">{percent(r.conversion_rate)}</TableCell>
              <TableCell className="text-right">{r.stock ?? "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export default function SellerAnalytics() {
  const [days, setDays] = useState("30");
  const q = useQuery({ queryKey: ["seller-overview", Number(days)], queryFn: () => api<SellerOverview>("/analytics/seller/overview", { query: { days } }) });
  const d = q.data;
  return (
    <DashboardPage>
      <PageHeader title="Analytics" description="Real-time store performance from your orders and product views."
        actions={
          <Tabs value={days} onValueChange={(v) => setDays(v as string)}>
            <TabsList><TabsTrigger value="7">7d</TabsTrigger><TabsTrigger value="30">30d</TabsTrigger><TabsTrigger value="90">90d</TabsTrigger><TabsTrigger value="180">180d</TabsTrigger></TabsList>
          </Tabs>
        } />
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        {!d ? Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-28" />) : <>
          <KpiCard label="Revenue" value={d.revenue.value} format="money" change={d.revenue.change_pct} />
          <KpiCard label="Orders" value={d.orders.value} change={d.orders.change_pct} />
          <KpiCard label="Units sold" value={d.units_sold.value} change={d.units_sold.change_pct} />
          <KpiCard label="AOV" value={d.average_order_value.value} format="money" change={d.average_order_value.change_pct} />
          <KpiCard label="Product views" value={d.views.value} change={d.views.change_pct} />
          <KpiCard label="Conversion" value={d.conversion_rate.value} format="percent" change={d.conversion_rate.change_pct} />
        </>}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card><CardHeader><CardTitle className="text-base">Revenue</CardTitle></CardHeader>
          <CardContent>{d ? <TrendChart data={d.series as unknown as Record<string, unknown>[]} /> : <Skeleton className="h-64" />}</CardContent></Card>
        <Card><CardHeader><CardTitle className="text-base">Orders & units</CardTitle></CardHeader>
          <CardContent>{d ? <TrendChart data={d.series as unknown as Record<string, unknown>[]} dataKey="orders" label="Orders" format="number" secondaryKey="units" secondaryLabel="Units" /> : <Skeleton className="h-64" />}</CardContent></Card>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card><CardHeader><CardTitle className="text-base">Top products by revenue</CardTitle></CardHeader>
          <CardContent>{d ? <HBarChart data={d.top_products as unknown as Record<string, unknown>[]} dataKey="revenue" nameKey="name" label="Revenue" /> : <Skeleton className="h-48" />}</CardContent></Card>
        <Card><CardHeader><CardTitle className="text-base">Order status mix</CardTitle></CardHeader>
          <CardContent>{d ? <HBarChart data={Object.entries(d.status_breakdown).map(([status, count]) => ({ status, count }))} dataKey="count" nameKey="status" label="Orders" format="number" /> : <Skeleton className="h-48" />}</CardContent></Card>
      </div>
      <ForecastPanel />
      <div className="grid gap-6 xl:grid-cols-2">
        <Card><CardHeader><CardTitle className="text-base">Best performers</CardTitle></CardHeader><CardContent>{d && <PerfTable rows={d.top_products} />}</CardContent></Card>
        <Card><CardHeader><CardTitle className="text-base">Underperforming products</CardTitle></CardHeader><CardContent>{d && <PerfTable rows={d.low_performers} />}</CardContent></Card>
      </div>
      {d && (
        <div className="space-y-1 rounded-xl border bg-muted/30 p-4 text-xs text-muted-foreground">
          {Object.entries(d.definitions).map(([k, v]) => <p key={k} className="flex gap-1.5"><Info className="mt-0.5 size-3 shrink-0" /><b className="capitalize">{k.replace(/_/g, " ")}:</b> {v}</p>)}
        </div>
      )}
    </DashboardPage>
  );
}
