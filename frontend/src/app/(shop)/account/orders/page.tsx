"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Package } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { OrderStatusBadge } from "@/components/commerce/order-bits";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { date, money } from "@/lib/format";
import type { Order, Page } from "@/lib/types";
import { cn } from "@/lib/utils";

const FILTERS = ["", "confirmed", "processing", "shipped", "delivered", "cancelled"];

export default function OrdersPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const q = useQuery({
    queryKey: ["orders", page, status],
    queryFn: () => api<Page<Order>>("/orders", { query: { page, page_size: 10, status } }),
    placeholderData: keepPreviousData,
  });
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / q.data.page_size)) : 1;
  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">Orders</h2>
      <div className="mb-4 flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button key={f || "all"} onClick={() => { setStatus(f); setPage(1); }}
            className={cn("rounded-full border px-3 py-1 text-xs capitalize", status === f ? "border-primary bg-primary/10 text-primary" : "hover:bg-muted")}>
            {f || "All"}
          </button>
        ))}
      </div>
      {q.isLoading ? <TableSkeleton /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data!.items.length === 0 ? (
        <EmptyState icon={Package} title="No orders here" description="Orders you place will appear here." />
      ) : (
        <div className="divide-y rounded-xl border">
          {q.data!.items.map((o) => (
            <Link key={o.id} href={`/account/orders/${o.id}`} className="flex flex-wrap items-center justify-between gap-3 p-4 hover:bg-muted/40">
              <div>
                <p className="font-medium">{o.order_number}</p>
                <p className="text-xs text-muted-foreground">{date(o.placed_at)} · {o.seller.store_name} · {o.item_count} item(s)</p>
              </div>
              <div className="flex items-center gap-3">
                <OrderStatusBadge status={o.status} />
                <span className="w-24 text-right font-medium">{money(o.total)}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
      {pages > 1 && (
        <div className="mt-4 flex items-center justify-end gap-2 text-sm">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
          <span className="text-muted-foreground">{page} / {pages}</span>
          <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      )}
    </div>
  );
}
