"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BadgePercent, GitCompare, ImageIcon, MessageSquareQuote, Sparkles, Tag } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { ErrorState, GridSkeleton } from "@/components/common/states";
import { ProductGrid } from "@/components/product/product-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import { useCategories } from "@/lib/queries";
import type { Bundle, OfferOut, Recommendations } from "@/lib/types";

const PROMPTS = [
  "I need a laptop under $1000 for programming",
  "Find waterproof trail running shoes",
  "What should I buy with a mirrorless camera?",
  "Best noise cancelling headphones for travel",
];

function NovaHero() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const ask = (text: string) => router.push(`/nova?q=${encodeURIComponent(text)}`);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim()) ask(q.trim());
  };
  return (
    <section className="relative overflow-hidden border-b">
      <div className="bg-genora absolute inset-0 opacity-[0.07]" />
      <div className="relative mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[1.2fr_1fr] lg:py-20">
        <div className="flex flex-col justify-center">
          <Badge variant="outline" className="mb-4 w-fit gap-1.5 border-primary/30 bg-background text-primary">
            <Sparkles className="size-3.5" /> Meet GenOra Nova, your shopping agent
          </Badge>
          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
            Tell us what you need.
            <br />
            <span className="text-genora">Nova finds, compares & negotiates.</span>
          </h1>
          <p className="mt-4 max-w-xl text-muted-foreground">
            Thousands of products from independent sellers. Describe your needs and budget — Nova searches the catalog,
            explains its picks, checks real offers and can even make price offers for you.
          </p>
          <form onSubmit={submit} className="mt-6 flex max-w-xl gap-2">
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="e.g. a lightweight laptop for travel under $900"
              className="h-11 bg-background"
              aria-label="Ask GenOra Nova"
            />
            <Button type="submit" size="lg" className="bg-genora h-11 px-5 text-white hover:opacity-90">
              Ask Nova <ArrowRight />
            </Button>
          </form>
          <div className="mt-3 flex flex-wrap gap-2">
            {PROMPTS.map((p) => (
              <button key={p} onClick={() => ask(p)}
                className="rounded-full border bg-background px-3 py-1 text-xs text-muted-foreground transition hover:border-primary/40 hover:text-foreground">
                {p}
              </button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 self-center">
          {[
            { icon: Sparkles, title: "Needs-based discovery", text: "Budget, use case and specs understood." },
            { icon: GitCompare, title: "Side-by-side compare", text: "Specs, ratings and review pros & cons." },
            { icon: BadgePercent, title: "Real deals only", text: "Active offers, bundles and negotiation." },
            { icon: ImageIcon, title: "Search by photo", text: "Find similar items from an image." },
          ].map(({ icon: Icon, title, text }) => (
            <div key={title} className="rounded-xl border bg-background/80 p-4 shadow-sm backdrop-blur">
              <Icon className="mb-2 size-5 text-primary" />
              <p className="text-sm font-medium">{title}</p>
              <p className="mt-1 text-xs text-muted-foreground">{text}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Section({ title, href, children, subtitle }: { title: string; href?: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="mx-auto max-w-7xl px-4 pt-12 sm:px-6">
      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
          {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
        </div>
        {href && (
          <Link href={href} className="flex items-center gap-1 text-sm font-medium text-primary hover:underline">
            View all <ArrowRight className="size-4" />
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

function Categories() {
  const { data, isLoading } = useCategories();
  if (isLoading) return <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">{Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
      {data?.map((c) => (
        <Link key={c.id} href={`/products?category=${c.slug}`}
          className="group rounded-xl border bg-card p-4 transition hover:border-primary/40 hover:shadow-sm">
          <p className="font-medium group-hover:text-primary">{c.name}</p>
          <p className="mt-1 text-xs text-muted-foreground">{c.product_count} products</p>
        </Link>
      ))}
    </div>
  );
}

function Recs({ path }: { path: string }) {
  const q = useQuery({ queryKey: ["recs", path], queryFn: () => api<Recommendations>(path, { query: { limit: 8 } }) });
  if (q.isLoading) return <GridSkeleton count={4} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return <ProductGrid products={q.data!.items} reasons={q.data!.reasons} />;
}

function Deals() {
  const offers = useQuery({ queryKey: ["offers"], queryFn: () => api<OfferOut[]>("/offers") });
  const bundles = useQuery({ queryKey: ["bundles"], queryFn: () => api<Bundle[]>("/bundles") });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-xl border bg-card p-5">
        <h3 className="mb-3 flex items-center gap-2 font-medium"><Tag className="size-4 text-rose-600" /> Live offers</h3>
        {offers.isLoading ? <Skeleton className="h-40" /> : (
          <ul className="divide-y">
            {offers.data?.slice(0, 5).map((o) => (
              <li key={o.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium">{o.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {o.product_name ?? o.seller_name ?? "Marketplace-wide"} · {o.conditions[0]}
                  </p>
                </div>
                <Badge className="shrink-0 bg-rose-600 text-white">
                  {o.discount_type === "percentage" ? `${o.value}%` : money(o.value)} off
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="rounded-xl border bg-card p-5">
        <h3 className="mb-3 flex items-center gap-2 font-medium"><MessageSquareQuote className="size-4 text-primary" /> Bundles & kits</h3>
        {bundles.isLoading ? <Skeleton className="h-40" /> : (
          <ul className="divide-y">
            {bundles.data?.slice(0, 5).map((b) => (
              <li key={b.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium">{b.name}</p>
                  <p className="truncate text-xs text-muted-foreground">{b.products.length} items · {b.seller_name}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="font-medium">{money(b.bundle_price)}</p>
                  <p className="text-xs text-emerald-600">save {money(b.savings)}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
        <Button variant="link" className="mt-1 px-0" render={<Link href="/deals" />} nativeButton={false}>
          See all deals <ArrowRight />
        </Button>
      </div>
    </div>
  );
}

export default function HomePage() {
  const { status } = useAuth();
  return (
    <>
      <NovaHero />
      <Section title="Shop by category" href="/categories">
        <Categories />
      </Section>
      {status === "authenticated" && (
        <Section title="Picked for you" subtitle="Based on your purchases, views and searches">
          <Recs path="/recommendations/for-you" />
        </Section>
      )}
      <Section title="Trending now" subtitle="Best sellers of the last 30 days" href="/products?sort=popularity">
        <Recs path="/recommendations/popular" />
      </Section>
      <Section title="Deals & bundles" href="/deals">
        <Deals />
      </Section>
    </>
  );
}
