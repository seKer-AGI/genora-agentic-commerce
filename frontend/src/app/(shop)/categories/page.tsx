"use client";

import Link from "next/link";

import { ErrorState, PageHeader } from "@/components/common/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useCategories } from "@/lib/queries";

export default function CategoriesPage() {
  const { data, isLoading, error, refetch } = useCategories();
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader title="Categories" description="Browse the full catalog by department." />
      {isLoading && <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-40" />)}</div>}
      {error && <ErrorState error={error} onRetry={() => refetch()} className="mt-6" />}
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data?.map((c) => (
          <div key={c.id} className="rounded-2xl border bg-card p-5">
            <Link href={`/products?category=${c.slug}`} className="group">
              <h2 className="text-lg font-semibold group-hover:text-primary">{c.name}</h2>
              <p className="text-sm text-muted-foreground">{c.description}</p>
              <p className="mt-1 text-xs text-muted-foreground">{c.product_count} products</p>
            </Link>
            {c.children.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-1.5">
                {c.children.map((ch) => (
                  <Link key={ch.id} href={`/products?category=${ch.slug}`}
                    className="rounded-full border px-3 py-1 text-xs transition hover:border-primary/40 hover:text-primary">
                    {ch.name} <span className="text-muted-foreground">{ch.product_count}</span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
