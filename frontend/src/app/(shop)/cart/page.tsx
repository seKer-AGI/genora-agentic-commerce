"use client";

import { AlertTriangle, Minus, Plus, ShoppingCart, Tag, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EmptyState, ErrorState, PageHeader } from "@/components/common/states";
import { ProductImage } from "@/components/product/product-bits";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useRequireAuth } from "@/lib/auth";
import { OrderSummary } from "@/components/commerce/order-summary";
import { money } from "@/lib/format";
import { useCart, useCartMutations } from "@/lib/queries";

export default function CartPage() {
  const { allowed } = useRequireAuth();
  const cart = useCart();
  const m = useCartMutations();
  const [code, setCode] = useState("");

  if (!allowed || cart.isLoading) {
    return <div className="mx-auto grid max-w-6xl gap-6 px-4 py-8 lg:grid-cols-[1fr_360px]"><Skeleton className="h-96" /><Skeleton className="h-72" /></div>;
  }
  if (cart.error) return <div className="mx-auto max-w-3xl px-4 py-12"><ErrorState error={cart.error} onRetry={() => cart.refetch()} /></div>;
  const c = cart.data!;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <PageHeader title="Your cart" description={c.item_count ? `${c.item_count} item(s) from ${c.sellers.length} seller(s)` : undefined} />
      {c.items.length === 0 ? (
        <EmptyState icon={ShoppingCart} className="mt-8" title="Your cart is empty" description="Find something you love, or ask Nova for ideas."
          action={<Button render={<Link href="/products" />} nativeButton={false}>Start shopping</Button>} />
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_360px]">
          <div className="space-y-4">
            {c.issues.length > 0 && (
              <div className="flex gap-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                <ul>{c.issues.map((i) => <li key={i}>{i}</li>)}</ul>
              </div>
            )}
            {c.sellers.map((s) => (
              <div key={s.seller_id} className="rounded-2xl border bg-card">
                <div className="flex items-center justify-between border-b px-4 py-2.5 text-sm">
                  <span className="font-medium">{s.store_name}</span>
                  <span className="text-muted-foreground">Shipping: {s.shipping === 0 ? "Free" : money(s.shipping)}</span>
                </div>
                <ul className="divide-y">
                  {c.items.filter((i) => i.seller_id === s.seller_id).map((i) => (
                    <li key={i.id} className="flex gap-4 p-4">
                      <Link href={`/products/${i.product_slug}`} className="shrink-0">
                        <ProductImage src={i.image_url} alt={i.product_name} className="size-20 rounded-lg border" />
                      </Link>
                      <div className="min-w-0 flex-1">
                        <Link href={`/products/${i.product_slug}`} className="line-clamp-2 text-sm font-medium hover:underline">{i.product_name}</Link>
                        <p className="text-xs text-muted-foreground">{money(i.unit_price)} each{i.bundle_id && " · bundle item"}</p>
                        {i.discounts.map((d) => (
                          <p key={d.description} className="mt-0.5 flex items-center gap-1 text-xs text-emerald-600"><Tag className="size-3" />{d.description}: −{money(d.amount)}</p>
                        ))}
                        {i.issues.map((iss) => <p key={iss} className="text-xs text-destructive">{iss}</p>)}
                        <div className="mt-2 flex items-center gap-2">
                          <div className="flex items-center rounded-lg border">
                            <Button variant="ghost" size="icon-sm" aria-label="Decrease quantity" disabled={i.quantity <= 1 || m.update.isPending}
                              onClick={() => m.update.mutate({ itemId: i.id, quantity: i.quantity - 1 })}><Minus /></Button>
                            <span className="w-7 text-center text-sm">{i.quantity}</span>
                            <Button variant="ghost" size="icon-sm" aria-label="Increase quantity" disabled={i.quantity >= i.available || m.update.isPending}
                              onClick={() => m.update.mutate({ itemId: i.id, quantity: i.quantity + 1 })}><Plus /></Button>
                          </div>
                          <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => m.remove.mutate(i.id)}>
                            <Trash2 /> Remove
                          </Button>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold">{money(i.total)}</p>
                        {i.total < i.subtotal && <p className="text-xs text-muted-foreground line-through">{money(i.subtotal)}</p>}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="space-y-4 lg:sticky lg:top-20 lg:self-start">
            <OrderSummary cart={c}>
              <div className="mt-4">
                {c.coupon_code ? (
                  <div className="flex items-center justify-between rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">
                    <span><b>{c.coupon_code}</b> · −{money(c.coupon_discount)}</span>
                    <button aria-label="Remove coupon" onClick={() => m.removeCoupon.mutate()}><X className="size-4" /></button>
                  </div>
                ) : (
                  <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (code.trim()) m.applyCoupon.mutate(code.trim()); }}>
                    <Input placeholder="Coupon code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} aria-label="Coupon code" />
                    <Button type="submit" variant="outline" disabled={m.applyCoupon.isPending}>Apply</Button>
                  </form>
                )}
              </div>
              <Button size="lg" className="mt-4 w-full" disabled={c.issues.length > 0} render={<Link href="/checkout" />} nativeButton={false}>
                Proceed to checkout
              </Button>
            </OrderSummary>
            <p className="px-1 text-xs text-muted-foreground">Prices, discounts and taxes are calculated by the server and re-verified at checkout.</p>
          </div>
        </div>
      )}
    </div>
  );
}
