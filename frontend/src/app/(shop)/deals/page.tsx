"use client";

import { useQuery } from "@tanstack/react-query";
import { Clock, Tag } from "lucide-react";
import Link from "next/link";

import { EmptyState, ErrorState, PageHeader } from "@/components/common/states";
import { ProductImage } from "@/components/product/product-bits";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useAddBundleToCart } from "@/lib/queries";
import type { Bundle, OfferOut } from "@/lib/types";

export default function DealsPage() {
  const offers = useQuery({ queryKey: ["offers"], queryFn: () => api<OfferOut[]>("/offers") });
  const bundles = useQuery({ queryKey: ["bundles"], queryFn: () => api<Bundle[]>("/bundles") });
  const addBundle = useAddBundleToCart();
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader title="Deals & bundles" description="Every active promotion on GenOra. Offers apply automatically at checkout — no codes needed." />

      <h2 className="mt-8 mb-3 text-lg font-semibold">Active offers</h2>
      {offers.isLoading ? <Skeleton className="h-40" /> : offers.error ? <ErrorState error={offers.error} /> : offers.data!.length === 0 ? (
        <EmptyState icon={Tag} title="No active offers right now" />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {offers.data!.map((o) => (
            <div key={o.id} className="flex flex-col rounded-xl border bg-card p-4">
              <div className="flex items-start justify-between gap-2">
                <p className="font-medium">{o.name}</p>
                <Badge className="shrink-0 bg-rose-600 text-white">{o.discount_type === "percentage" ? `${o.value}%` : money(o.value)} off</Badge>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{o.description}</p>
              <ul className="mt-2 flex-1 list-inside list-disc text-xs text-muted-foreground">
                {o.conditions.slice(1, 4).map((c) => <li key={c}>{c}</li>)}
              </ul>
              <div className="mt-3 flex items-center justify-between text-xs">
                <span className="flex items-center gap-1 text-muted-foreground"><Clock className="size-3" /> {o.ends_at ? `Ends ${date(o.ends_at)}` : "No end date"}</span>
                <Link className="font-medium text-primary hover:underline"
                  href={o.product_id ? `/products/${o.product_id}` : o.category_id ? `/products?category=${o.category_id}` : `/products?seller=${o.seller_id ?? ""}`}>
                  Shop now
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}

      <h2 className="mt-10 mb-3 text-lg font-semibold">Bundles & kits</h2>
      {bundles.isLoading ? <Skeleton className="h-60" /> : bundles.error ? <ErrorState error={bundles.error} /> : (
        <div className="grid gap-4 md:grid-cols-2">
          {bundles.data!.map((b) => (
            <div key={b.id} className="rounded-2xl border bg-card p-5">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-semibold">{b.name}</p>
                  <p className="text-xs text-muted-foreground">by {b.seller_name}</p>
                </div>
                <div className="text-right">
                  <p className="text-lg font-semibold">{money(b.bundle_price)}</p>
                  <p className="text-xs"><span className="text-muted-foreground line-through">{money(b.items_total)}</span> <span className="text-emerald-600">save {money(b.savings)}</span></p>
                </div>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">{b.description}</p>
              <div className="mt-3 grid grid-cols-4 gap-2">
                {b.products.map((p) => (
                  <Link key={p.id} href={`/products/${p.slug}`} className="text-xs">
                    <ProductImage src={p.image_url} alt={p.name} className="aspect-square w-full rounded-lg border" />
                    <p className="mt-1 line-clamp-2">{p.name}</p>
                  </Link>
                ))}
              </div>
              <Button className="mt-4" size="sm" disabled={!b.available || addBundle.isPending} onClick={() => addBundle.mutate(b.id)}>
                {b.available ? "Add bundle to cart" : "Unavailable"}
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
