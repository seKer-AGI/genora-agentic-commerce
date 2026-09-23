"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Plus, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { KpiCard, TrendChart } from "@/components/charts/charts";
import { OrderStatusBadge } from "@/components/commerce/order-bits";
import { ErrorState, PageHeader } from "@/components/common/states";
import { DashboardPage } from "@/components/layout/dashboard-shell";
import { ProductImage } from "@/components/product/product-bits";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, money, number } from "@/lib/format";
import type { Order, Page, SellerOverview } from "@/lib/types";

const ASTRA_PROMPTS = ["How did my sales perform this month?", "Which products are running low?", "Suggest a discount strategy for my products"];

export default function SellerDashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const ov = useQuery({ queryKey: ["seller-overview", 30], queryFn: () => api<SellerOverview>("/analytics/seller/overview", { query: { days: 30 } }) });
  const orders = useQuery({ queryKey: ["seller-orders", "recent"], queryFn: () => api<Page<Order>>("/sellers/me/orders", { query: { page_size: 6 } }) });
  const d = ov.data;

  return (
    <DashboardPage>
      <PageHeader title={user?.seller?.store_name ?? "Dashboard"} description="Performance over the last 30 days"
        actions={<>
          <Button variant="outline" render={<Link href="/seller/astra" />} nativeButton={false}><Sparkles /> Ask Astra</Button>
          <Button render={<Link href="/seller/products/new" />} nativeButton={false}><Plus /> New product</Button>
        </>} />
      {ov.error && <ErrorState error={ov.error} onRetry={() => ov.refetch()} />}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {!d ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />) : <>
          <KpiCard label="Revenue" value={d.revenue.value} format="money" change={d.revenue.change_pct} />
          <KpiCard label="Orders" value={d.orders.value} change={d.orders.change_pct} />
          <KpiCard label="Avg. order value" value={d.average_order_value.value} format="money" change={d.average_order_value.change_pct} />
          <KpiCard label="Conversion" value={d.conversion_rate.value} format="percent" change={d.conversion_rate.change_pct} />
        </>}
      </div>
      {d && d.low_stock_count > 0 && (
        <Link href="/seller/inventory?low=1" className="flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 hover:bg-amber-100 dark:bg-amber-950/40 dark:text-amber-200">
          <AlertTriangle className="size-4" /> {d.low_stock_count} product(s) at or below their low-stock threshold <ArrowRight className="ml-auto size-4" />
        </Link>
      )}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle className="text-base">Revenue</CardTitle></CardHeader>
          <CardContent>{d ? <TrendChart data={d.series as unknown as Record<string, unknown>[]} /> : <Skeleton className="h-64" />}</CardContent>
        </Card>
        <Card className="bg-genora border-0 text-white">
          <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Sparkles className="size-4" /> GenOra Astra</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <p className="text-sm text-white/85">Your AI seller assistant — analytics, listings, pricing and forecasts on your real store data.</p>
            {ASTRA_PROMPTS.map((p) => (
              <button key={p} onClick={() => router.push(`/seller/astra?q=${encodeURIComponent(p)}`)}
                className="block w-full rounded-lg bg-white/15 px-3 py-2 text-left text-sm hover:bg-white/25">{p}</button>
            ))}
          </CardContent>
        </Card>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Top products</CardTitle>
            <Button variant="ghost" size="sm" render={<Link href="/seller/analytics" />} nativeButton={false}>Analytics <ArrowRight /></Button>
          </CardHeader>
          <CardContent>
            {!d ? <Skeleton className="h-48" /> : (
              <ul className="divide-y">
                {d.top_products.map((p) => (
                  <li key={p.product_id} className="flex items-center gap-3 py-2.5 text-sm">
                    <ProductImage src={p.image_url} alt={p.name} className="size-10 rounded-md border" />
                    <span className="min-w-0 flex-1 truncate">{p.name}</span>
                    <span className="text-right"><b>{money(p.revenue)}</b><span className="block text-xs text-muted-foreground">{number(p.units)} units</span></span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Recent orders</CardTitle>
            <Button variant="ghost" size="sm" render={<Link href="/seller/orders" />} nativeButton={false}>All orders <ArrowRight /></Button>
          </CardHeader>
          <CardContent>
            {orders.isLoading ? <Skeleton className="h-48" /> : (
              <ul className="divide-y">
                {orders.data?.items.map((o) => (
                  <li key={o.id}>
                    <Link href={`/seller/orders/${o.id}`} className="flex items-center justify-between gap-2 py-2.5 text-sm hover:text-primary">
                      <span><b>{o.order_number}</b><span className="block text-xs text-muted-foreground">{date(o.placed_at)} · {o.buyer?.full_name}</span></span>
                      <span className="flex items-center gap-2"><OrderStatusBadge status={o.status} /><span className="w-20 text-right">{money(o.total)}</span></span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </DashboardPage>
  );
}
