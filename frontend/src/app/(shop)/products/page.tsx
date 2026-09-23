"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, SlidersHorizontal, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { EmptyState, ErrorState, GridSkeleton } from "@/components/common/states";
import { ProductGrid } from "@/components/product/product-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { flattenCategories, useCategories } from "@/lib/queries";
import type { SearchResponse } from "@/lib/types";

const SORTS = [
  ["relevance", "Best match"], ["popularity", "Most popular"], ["rating", "Top rated"],
  ["price_asc", "Price: low to high"], ["price_desc", "Price: high to low"], ["newest", "Newest"],
] as const;
const MODES = [["hybrid", "Hybrid"], ["keyword", "Keyword"], ["semantic", "Semantic"]] as const;

function useUrlState() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const set = (patch: Record<string, string | string[] | null>, resetPage = true) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      next.delete(k);
      if (Array.isArray(v)) v.forEach((x) => next.append(k, x));
      else if (v !== null && v !== "") next.set(k, v);
    }
    if (resetPage) next.delete("page");
    router.push(`${pathname}?${next.toString()}`, { scroll: false });
  };
  return { params, set };
}

function Filters({ data }: { data?: SearchResponse }) {
  const { params, set } = useUrlState();
  const { data: cats } = useCategories();
  const flat = flattenCategories(cats);
  const [minP, setMinP] = useState(params.get("min_price") ?? "");
  const [maxP, setMaxP] = useState(params.get("max_price") ?? "");
  const brands = params.getAll("brands");
  const rating = params.get("min_rating");
  useEffect(() => {
    setMinP(params.get("min_price") ?? "");
    setMaxP(params.get("max_price") ?? "");
  }, [params]);

  return (
    <div className="space-y-6 text-sm">
      <div>
        <h3 className="mb-2 font-medium">Category</h3>
        <div className="max-h-72 space-y-0.5 overflow-y-auto pr-1">
          <button onClick={() => set({ category: null })}
            className={`block w-full rounded px-2 py-1 text-left hover:bg-muted ${!params.get("category") ? "bg-muted font-medium" : ""}`}>
            All categories
          </button>
          {flat.map((c) => (
            <button key={c.id} onClick={() => set({ category: c.slug })} style={{ paddingLeft: `${0.5 + c.depth * 0.9}rem` }}
              className={`flex w-full justify-between rounded py-1 pr-2 text-left hover:bg-muted ${params.get("category") === c.slug ? "bg-muted font-medium" : ""}`}>
              <span>{c.name}</span><span className="text-xs text-muted-foreground">{c.product_count}</span>
            </button>
          ))}
        </div>
      </div>
      <div>
        <h3 className="mb-2 font-medium">Price</h3>
        <form className="flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); set({ min_price: minP, max_price: maxP }); }}>
          <Input inputMode="decimal" placeholder={data?.price_range.min != null ? `$${Math.floor(data.price_range.min)}` : "Min"}
            value={minP} onChange={(e) => setMinP(e.target.value.replace(/[^\d.]/g, ""))} aria-label="Minimum price" />
          <span className="text-muted-foreground">–</span>
          <Input inputMode="decimal" placeholder={data?.price_range.max != null ? `$${Math.ceil(data.price_range.max)}` : "Max"}
            value={maxP} onChange={(e) => setMaxP(e.target.value.replace(/[^\d.]/g, ""))} aria-label="Maximum price" />
          <Button type="submit" size="sm" variant="outline">Go</Button>
        </form>
      </div>
      <div>
        <h3 className="mb-2 font-medium">Customer rating</h3>
        <div className="space-y-1">
          {["4.5", "4", "3"].map((r) => (
            <label key={r} className="flex cursor-pointer items-center gap-2">
              <Checkbox checked={rating === r} onCheckedChange={(v) => set({ min_rating: v ? r : null })} />
              {r}★ & up
            </label>
          ))}
        </div>
      </div>
      {data && data.facets.brands.length > 0 && (
        <div>
          <h3 className="mb-2 font-medium">Brand</h3>
          <div className="space-y-1">
            {data.facets.brands.map((b) => (
              <label key={b.value} className="flex cursor-pointer items-center gap-2">
                <Checkbox checked={brands.includes(b.value)}
                  onCheckedChange={(v) => set({ brands: v ? [...brands, b.value] : brands.filter((x) => x !== b.value) })} />
                <span className="flex-1">{b.label}</span><span className="text-xs text-muted-foreground">{b.count}</span>
              </label>
            ))}
          </div>
        </div>
      )}
      <label className="flex items-center justify-between">
        <span className="font-medium">In stock only</span>
        <Switch checked={params.get("in_stock") === "true"} onCheckedChange={(v) => set({ in_stock: v ? "true" : null })} />
      </label>
    </div>
  );
}

function Results() {
  const { params, set } = useUrlState();
  const q = params.get("q") ?? "";
  const page = Number(params.get("page") ?? 1);
  const sort = params.get("sort") ?? (q ? "relevance" : "popularity");
  const mode = params.get("mode") ?? "hybrid";
  const query = {
    q: q || undefined, category: params.get("category") ?? undefined, min_price: params.get("min_price") ?? undefined,
    max_price: params.get("max_price") ?? undefined, brands: params.getAll("brands"), min_rating: params.get("min_rating") ?? undefined,
    in_stock: params.get("in_stock") ?? undefined, sort, mode, page, page_size: 24,
  };
  const res = useQuery({
    queryKey: ["search", query],
    queryFn: () => api<SearchResponse>(q ? "/search" : "/products", { query }),
    placeholderData: keepPreviousData,
  });
  const { data: cats } = useCategories();
  const category = flattenCategories(cats).find((c) => c.slug === params.get("category"));
  const pages = res.data ? Math.max(1, Math.ceil(res.data.total / res.data.page_size)) : 1;
  const active = [
    category && { key: "category", label: category.name },
    params.get("min_price") && { key: "min_price", label: `≥ $${params.get("min_price")}` },
    params.get("max_price") && { key: "max_price", label: `≤ $${params.get("max_price")}` },
    params.get("min_rating") && { key: "min_rating", label: `${params.get("min_rating")}★+` },
    params.get("in_stock") && { key: "in_stock", label: "In stock" },
    ...params.getAll("brands").map((b) => ({ key: "brands", label: b })),
  ].filter(Boolean) as { key: string; label: string }[];

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {q ? <>Results for “{q}”</> : category ? category.name : "All products"}
          </h1>
          <p className="text-sm text-muted-foreground">
            {res.data ? `${res.data.total} products` : "Loading…"}
            {res.data && q && ` · ${res.data.mode} search in ${res.data.latency_ms} ms`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Sheet>
            <SheetTrigger render={<Button variant="outline" size="sm" className="lg:hidden" />}>
              <SlidersHorizontal /> Filters
            </SheetTrigger>
            <SheetContent side="left" className="w-80 overflow-y-auto">
              <SheetHeader><SheetTitle>Filters</SheetTitle></SheetHeader>
              <div className="px-4 pb-6"><Filters data={res.data} /></div>
            </SheetContent>
          </Sheet>
          {q && (
            <Select value={mode} items={Object.fromEntries(MODES)} onValueChange={(v) => set({ mode: v as string })}>
              <SelectTrigger size="sm" className="w-32" aria-label="Search mode"><SelectValue /></SelectTrigger>
              <SelectContent>{MODES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
            </Select>
          )}
          <Select value={sort} items={Object.fromEntries(SORTS)} onValueChange={(v) => set({ sort: v as string })}>
            <SelectTrigger size="sm" className="w-44" aria-label="Sort by"><SelectValue /></SelectTrigger>
            <SelectContent>
              {SORTS.filter(([v]) => q || v !== "relevance").map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>
      {active.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {active.map((a) => (
            <Badge key={`${a.key}-${a.label}`} variant="secondary" className="gap-1">
              {a.label}
              <button aria-label={`Remove ${a.label}`} onClick={() => set({
                [a.key]: a.key === "brands" ? params.getAll("brands").filter((b) => b !== a.label) : null,
              })}><X className="size-3" /></button>
            </Badge>
          ))}
          <button className="text-xs text-muted-foreground hover:underline" onClick={() => set({
            category: null, min_price: null, max_price: null, min_rating: null, in_stock: null, brands: null,
          })}>Clear all</button>
        </div>
      )}
      <div className="mt-6 grid gap-8 lg:grid-cols-[240px_1fr]">
        <aside className="hidden lg:block"><Filters data={res.data} /></aside>
        <div>
          {q && (
            <Link href={`/nova?q=${encodeURIComponent(q)}`}
              className="mb-4 flex items-center gap-2 rounded-xl border border-primary/30 bg-primary/5 px-4 py-3 text-sm hover:bg-primary/10">
              <Sparkles className="size-4 text-primary" />
              <span>Not sure which to pick? <b>Ask Nova</b> to compare these results for “{q}”.</span>
            </Link>
          )}
          {res.isLoading ? <GridSkeleton count={12} className="lg:grid-cols-3 xl:grid-cols-4" />
            : res.error ? <ErrorState error={res.error} onRetry={() => res.refetch()} />
            : res.data!.items.length === 0 ? (
              <EmptyState title="No products found" description="Try different keywords, remove some filters or ask Nova for help."
                action={<Button render={<Link href={`/nova?q=${encodeURIComponent(q || "help me find a product")}`} />} nativeButton={false}><Sparkles /> Ask Nova</Button>} />
            ) : (
              <>
                <ProductGrid products={res.data!.items} className={res.isFetching ? "opacity-60 transition-opacity" : ""} />
                {pages > 1 && (
                  <div className="mt-8 flex items-center justify-center gap-2">
                    <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => set({ page: String(page - 1) }, false)}>
                      <ChevronLeft /> Previous
                    </Button>
                    <span className="text-sm text-muted-foreground">Page {page} of {pages}</span>
                    <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => set({ page: String(page + 1) }, false)}>
                      Next <ChevronRight />
                    </Button>
                  </div>
                )}
              </>
            )}
        </div>
      </div>
    </div>
  );
}

export default function ProductsPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-7xl px-4 py-6"><GridSkeleton count={12} /></div>}>
      <Results />
    </Suspense>
  );
}
