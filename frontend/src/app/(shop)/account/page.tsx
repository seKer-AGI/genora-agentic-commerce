"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Handshake, Heart, Package, Sparkles } from "lucide-react";
import Link from "next/link";

import { OrderStatusBadge } from "@/components/commerce/order-bits";
import { ProductGrid } from "@/components/product/product-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date, dateTime, money } from "@/lib/format";
import { useWishlist } from "@/lib/queries";
import type { Negotiation, Order, Page, Recommendations } from "@/lib/types";

export default function AccountOverview() {
  const { user } = useAuth();
  const orders = useQuery({ queryKey: ["orders", 1, ""], queryFn: () => api<Page<Order>>("/orders", { query: { page_size: 5 } }) });
  const negotiations = useQuery({ queryKey: ["negotiations"], queryFn: () => api<Negotiation[]>("/negotiations") });
  const wishlist = useWishlist();
  const recs = useQuery({ queryKey: ["recs", "for-you"], queryFn: () => api<Recommendations>("/recommendations/for-you", { query: { limit: 4 } }) });
  const activeOffers = negotiations.data?.filter((n) => n.status === "accepted" && n.expires_at && new Date(n.expires_at) > new Date()) ?? [];

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-3">
        <Card className="py-4"><CardContent className="flex items-center gap-3 px-4"><Package className="size-5 text-primary" /><div><p className="text-2xl font-semibold">{orders.data?.total ?? "—"}</p><p className="text-xs text-muted-foreground">Orders</p></div></CardContent></Card>
        <Card className="py-4"><CardContent className="flex items-center gap-3 px-4"><Heart className="size-5 text-rose-500" /><div><p className="text-2xl font-semibold">{wishlist.data?.length ?? "—"}</p><p className="text-xs text-muted-foreground">Saved items</p></div></CardContent></Card>
        <Card className="py-4"><CardContent className="flex items-center gap-3 px-4"><Handshake className="size-5 text-emerald-600" /><div><p className="text-2xl font-semibold">{activeOffers.length}</p><p className="text-xs text-muted-foreground">Accepted price offers</p></div></CardContent></Card>
      </div>

      {!user?.is_email_verified && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          Please verify your e-mail address — check your inbox for the verification link.
        </div>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Recent orders</CardTitle>
          <Button variant="ghost" size="sm" render={<Link href="/account/orders" />} nativeButton={false}>All orders <ArrowRight /></Button>
        </CardHeader>
        <CardContent>
          {orders.isLoading ? <Skeleton className="h-32" /> : orders.data?.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">No orders yet.</p>
          ) : (
            <ul className="divide-y">
              {orders.data?.items.map((o) => (
                <li key={o.id}>
                  <Link href={`/account/orders/${o.id}`} className="flex items-center justify-between gap-3 py-3 text-sm hover:text-primary">
                    <span><b>{o.order_number}</b><span className="block text-xs text-muted-foreground">{date(o.placed_at)} · {o.seller.store_name} · {o.item_count} item(s)</span></span>
                    <span className="flex items-center gap-3"><OrderStatusBadge status={o.status} /><span className="font-medium">{money(o.total)}</span></span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {activeOffers.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Your accepted price offers</CardTitle></CardHeader>
          <CardContent>
            <ul className="divide-y text-sm">
              {activeOffers.map((n) => (
                <li key={n.id} className="flex items-center justify-between gap-3 py-2.5">
                  <Link href={`/products/${n.product_slug}`} className="hover:text-primary">{n.product_name}</Link>
                  <span className="text-right"><b>{money(n.agreed_price)}</b><span className="block text-xs text-muted-foreground">until {dateTime(n.expires_at)}</span></span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-semibold"><Sparkles className="size-4 text-primary" /> Picked for you</h2>
        </div>
        {recs.isLoading ? <Skeleton className="h-64" /> : <ProductGrid products={recs.data?.items ?? []} reasons={recs.data?.reasons} className="lg:grid-cols-4" />}
      </div>
    </div>
  );
}
