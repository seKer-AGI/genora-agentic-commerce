"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgePercent, ChevronRight, Handshake, Heart, Minus, Plus, ShieldCheck, ShoppingCart, Sparkles, Store, Truck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ErrorState, GridSkeleton } from "@/components/common/states";
import { ProductReviews } from "@/components/product/reviews";
import { ProductImage, Price, Rating, StockBadge } from "@/components/product/product-bits";
import { ProductGrid } from "@/components/product/product-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, money, titleCase } from "@/lib/format";
import { track, useAddBundleToCart, useAddToCart, useToggleWishlist } from "@/lib/queries";
import type { Bundle, Negotiation, ProductDetail, ProductOffer, Recommendations } from "@/lib/types";
import { cn } from "@/lib/utils";

function attrValue(v: unknown): string {
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

function Gallery({ product }: { product: ProductDetail }) {
  const [active, setActive] = useState(0);
  const images = product.images.length ? product.images : [{ id: "none", url: product.image_url ?? "", alt_text: product.name, is_primary: true, sort_order: 0 }];
  return (
    <div className="space-y-3">
      <div className="aspect-square overflow-hidden rounded-2xl border bg-muted">
        <ProductImage src={images[active]?.url} alt={images[active]?.alt_text ?? product.name} className="size-full" />
      </div>
      {images.length > 1 && (
        <div className="flex gap-2">
          {images.map((img, i) => (
            <button key={img.id} onClick={() => setActive(i)} aria-label={`Show image ${i + 1}`}
              className={cn("size-16 overflow-hidden rounded-lg border-2", i === active ? "border-primary" : "border-transparent")}>
              <ProductImage src={img.url} alt={img.alt_text ?? ""} className="size-full" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function OfferDialog({ product }: { product: ProductDetail }) {
  const { status } = useAuth();
  const [open, setOpen] = useState(false);
  const [price, setPrice] = useState(String(Math.round(product.final_price * 0.95)));
  const [result, setResult] = useState<Negotiation | null>(null);
  const qc = useQueryClient();
  const propose = useMutation({
    mutationFn: () => api<Negotiation>(`/products/${product.id}/negotiations`, { method: "POST", body: { offered_price: Number(price) } }),
    onSuccess: setResult,
    onError: (e) => toast.error(errorMessage(e)),
  });
  const accept = useMutation({
    mutationFn: (id: string) => api<Negotiation>(`/negotiations/${id}/accept`, { method: "POST" }),
    onSuccess: (n) => {
      setResult(n);
      qc.invalidateQueries({ queryKey: ["cart"] });
      toast.success(`Accepted — ${money(n.agreed_price)} is reserved for you`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (status !== "authenticated") {
    return <Button variant="outline" render={<Link href={`/login?next=/products/${product.slug}`} />} nativeButton={false}><Handshake /> Make an offer</Button>;
  }
  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setResult(null); }}>
      <DialogTrigger render={<Button variant="outline" />}><Handshake /> Make an offer</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Make an offer</DialogTitle>
          <DialogDescription>
            The seller&apos;s pricing rules respond instantly. An accepted price is reserved for one unit and applied automatically at checkout.
          </DialogDescription>
        </DialogHeader>
        {!result ? (
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); propose.mutate(); }}>
            <p className="text-sm">Current price: <b>{money(product.final_price)}</b></p>
            <div className="flex gap-2">
              <Input type="number" min={1} step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} aria-label="Your offer" />
              <Button type="submit" disabled={propose.isPending || !Number(price)}>Send offer</Button>
            </div>
          </form>
        ) : (
          <div className="space-y-3 text-sm">
            <div className={cn("rounded-lg p-3", result.status === "accepted" ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-200" : "bg-amber-50 text-amber-900 dark:bg-amber-950/50 dark:text-amber-200")}>
              <p className="font-medium capitalize">{result.status}</p>
              <p>{result.reason}</p>
            </div>
            {result.status === "accepted" && <p>Agreed price <b>{money(result.agreed_price)}</b>, valid until {dateTime(result.expires_at)}.</p>}
            {result.counter_price != null && result.status !== "accepted" && (
              <div className="flex items-center justify-between gap-2">
                <p>Counter-offer: <b>{money(result.counter_price)}</b></p>
                <Button size="sm" onClick={() => accept.mutate(result.id)} disabled={accept.isPending}>Accept counter-offer</Button>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function BundleCard({ bundle }: { bundle: Bundle }) {
  const add = useAddBundleToCart();
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium">{bundle.name}</p>
          <p className="text-xs text-muted-foreground">{bundle.description}</p>
        </div>
        <div className="text-right">
          <p className="font-semibold">{money(bundle.bundle_price)} <span className="text-xs font-normal text-muted-foreground line-through">{money(bundle.items_total)}</span></p>
          <p className="text-xs text-emerald-600">Save {money(bundle.savings)}</p>
        </div>
      </div>
      <div className="mt-3 flex gap-2 overflow-x-auto">
        {bundle.products.map((p) => (
          <Link key={p.id} href={`/products/${p.slug}`} className="w-24 shrink-0 text-xs">
            <ProductImage src={p.image_url} alt={p.name} className="aspect-square w-full rounded-lg border" />
            <p className="mt-1 line-clamp-2">{p.name}</p>
          </Link>
        ))}
      </div>
      <Button size="sm" className="mt-3" disabled={!bundle.available || add.isPending} onClick={() => add.mutate(bundle.id)}>
        {bundle.available ? "Add bundle to cart" : "Currently unavailable"}
      </Button>
    </div>
  );
}

export default function ProductPage() {
  const { slug } = useParams<{ slug: string }>();
  const [qty, setQty] = useState(1);
  const addToCart = useAddToCart();
  const wishlist = useToggleWishlist();
  const q = useQuery({ queryKey: ["product", slug], queryFn: () => api<ProductDetail>(`/products/${slug}`) });
  const p = q.data;
  const offers = useQuery({ queryKey: ["product-offers", p?.id], queryFn: () => api<ProductOffer[]>(`/products/${p!.id}/offers`), enabled: !!p });
  const bundles = useQuery({ queryKey: ["product-bundles", p?.id], queryFn: () => api<Bundle[]>(`/products/${p!.id}/bundles`), enabled: !!p });
  const similar = useQuery({ queryKey: ["similar", p?.id], queryFn: () => api<Recommendations>(`/recommendations/similar/${p!.id}`, { query: { limit: 4 } }), enabled: !!p });
  const also = useQuery({ queryKey: ["also", p?.id], queryFn: () => api<Recommendations>(`/recommendations/also-bought/${p!.id}`, { query: { limit: 4 } }), enabled: !!p });

  useEffect(() => {
    if (p?.id) track("product_view", { product_id: p.id, properties: { source: "product_page" } });
  }, [p?.id]);

  if (q.isLoading) {
    return (
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-8 sm:px-6 lg:grid-cols-2">
        <Skeleton className="aspect-square rounded-2xl" />
        <div className="space-y-4"><Skeleton className="h-8 w-3/4" /><Skeleton className="h-6 w-1/3" /><Skeleton className="h-32" /></div>
      </div>
    );
  }
  if (q.error || !p) return <div className="mx-auto max-w-3xl px-4 py-16"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;

  const attrs = Object.entries(p.attributes);
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <nav aria-label="Breadcrumb" className="mb-4 flex items-center gap-1 text-xs text-muted-foreground">
        <Link href="/" className="hover:text-foreground">Home</Link><ChevronRight className="size-3" />
        {p.category && <><Link href={`/products?category=${p.category.slug}`} className="hover:text-foreground">{p.category.name}</Link><ChevronRight className="size-3" /></>}
        <span className="truncate text-foreground">{p.name}</span>
      </nav>

      <div className="grid gap-8 lg:grid-cols-2 lg:gap-12">
        <Gallery product={p} />
        <div>
          <p className="text-sm font-medium text-primary">{p.brand}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">{p.name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <Rating value={p.rating_avg} count={p.rating_count} size="md" />
            <span className="text-xs text-muted-foreground">{p.sold_count} sold · SKU {p.sku}</span>
          </div>
          <Price price={p.price} salePrice={p.sale_price} finalPrice={p.final_price} size="lg" className="mt-4" />
          {p.offer && (
            <p className="mt-1 flex items-center gap-1.5 text-sm text-rose-600"><BadgePercent className="size-4" /> {p.offer.name} applied automatically</p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <StockBadge stock={p.stock} />
            {p.negotiable && <Badge variant="outline" className="gap-1"><Handshake className="size-3" /> Open to offers</Badge>}
          </div>
          {p.seo_description && <p className="mt-4 text-sm text-muted-foreground">{p.seo_description}</p>}

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <div className="flex items-center rounded-lg border">
              <Button variant="ghost" size="icon" aria-label="Decrease quantity" onClick={() => setQty((x) => Math.max(1, x - 1))}><Minus /></Button>
              <span className="w-8 text-center text-sm" aria-live="polite">{qty}</span>
              <Button variant="ghost" size="icon" aria-label="Increase quantity" onClick={() => setQty((x) => Math.min(Math.max(p.stock, 1), x + 1))}><Plus /></Button>
            </div>
            <Button size="lg" className="flex-1 sm:flex-none" disabled={!p.in_stock || addToCart.isPending}
              onClick={() => addToCart.mutate({ productId: p.id, quantity: qty, name: p.name })}>
              <ShoppingCart /> {p.in_stock ? "Add to cart" : "Out of stock"}
            </Button>
            <Button size="lg" variant="outline" aria-label="Add to wishlist" onClick={() => wishlist.mutate({ productId: p.id, add: true })}><Heart /></Button>
            {p.negotiable && <OfferDialog product={p} />}
          </div>

          <div className="mt-6 grid gap-2 rounded-xl border p-4 text-sm">
            <p className="flex items-center gap-2"><Store className="size-4 text-muted-foreground" /> Sold by <b>{p.seller.store_name}</b> · {p.seller.rating_avg.toFixed(1)}★</p>
            <p className="flex items-center gap-2"><Truck className="size-4 text-muted-foreground" /> Free shipping on orders over $75 from this seller</p>
            <p className="flex items-center gap-2"><ShieldCheck className="size-4 text-muted-foreground" /> Secure checkout · prices verified server-side</p>
          </div>

          {offers.data && offers.data.length > 0 && (
            <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50/50 p-4 dark:border-rose-900 dark:bg-rose-950/20">
              <p className="mb-2 text-sm font-medium">Active offers</p>
              <ul className="space-y-1.5 text-sm">
                {offers.data.map((o) => (
                  <li key={o.id} className="flex justify-between gap-3">
                    <span>{o.name}<span className="block text-xs text-muted-foreground">{o.conditions.slice(0, 2).join(" · ")}</span></span>
                    <span className="shrink-0 font-medium text-rose-600">−{money(o.discount_per_unit)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            {[`What are people saying about the ${p.name}?`, `What should I buy with the ${p.name}?`, `How much does the ${p.name} cost on other marketplaces?`].map((prompt, i) => (
              <Button key={prompt} variant="ghost" size="sm" className="text-primary" render={<Link href={`/nova?q=${encodeURIComponent(prompt)}`} />} nativeButton={false}>
                <Sparkles /> {["Summarise reviews", "What goes with it?", "Compare prices"][i]}
              </Button>
            ))}
          </div>
        </div>
      </div>

      <Tabs defaultValue="description" className="mt-12">
        <TabsList>
          <TabsTrigger value="description">Description</TabsTrigger>
          <TabsTrigger value="specs">Specifications</TabsTrigger>
          <TabsTrigger value="reviews">Reviews ({p.rating_count})</TabsTrigger>
        </TabsList>
        <TabsContent value="description" className="pt-4">
          <p className="max-w-3xl whitespace-pre-line text-sm leading-relaxed">{p.description}</p>
        </TabsContent>
        <TabsContent value="specs" className="pt-4">
          {attrs.length === 0 ? <p className="text-sm text-muted-foreground">The seller has not provided specifications.</p> : (
            <dl className="grid max-w-3xl overflow-hidden rounded-xl border sm:grid-cols-2">
              {attrs.map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 border-b px-4 py-2.5 text-sm odd:bg-muted/30">
                  <dt className="text-muted-foreground">{titleCase(k)}</dt><dd className="text-right font-medium">{attrValue(v)}</dd>
                </div>
              ))}
            </dl>
          )}
        </TabsContent>
        <TabsContent value="reviews" className="pt-4">
          <ProductReviews product={p} />
        </TabsContent>
      </Tabs>

      {bundles.data && bundles.data.length > 0 && (
        <section className="mt-12">
          <h2 className="mb-4 text-xl font-semibold tracking-tight">Frequently bundled</h2>
          <div className="grid gap-4 md:grid-cols-2">{bundles.data.map((b) => <BundleCard key={b.id} bundle={b} />)}</div>
        </section>
      )}
      {also.data && also.data.items.length > 0 && (
        <section className="mt-12">
          <h2 className="mb-4 text-xl font-semibold tracking-tight">Customers also bought</h2>
          <ProductGrid products={also.data.items} />
        </section>
      )}
      <section className="mt-12">
        <h2 className="mb-4 text-xl font-semibold tracking-tight">Similar products</h2>
        {similar.isLoading ? <GridSkeleton count={4} /> : <ProductGrid products={similar.data?.items ?? []} />}
      </section>
    </div>
  );
}
