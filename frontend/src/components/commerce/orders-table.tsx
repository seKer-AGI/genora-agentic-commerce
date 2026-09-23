"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search, ShoppingBag } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { OrderStatusBadge } from "@/components/commerce/order-bits";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { dateTime, money } from "@/lib/format";
import type { Order, Page } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUSES = ["", "pending", "confirmed", "processing", "shipped", "delivered", "cancelled", "refunded"];

/** Paginated, filterable orders table used by the seller and admin consoles. */
export function OrdersTable({ endpoint, detailBase, queryKey, showSeller = false }: {
  endpoint: string;
  detailBase: string;
  queryKey: string;
  showSeller?: boolean;
}) {
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const list = useQuery({
    queryKey: [queryKey, status, q, page],
    queryFn: () => api<Page<Order>>(endpoint, { query: { status, q, page, page_size: 20 } }),
    placeholderData: keepPreviousData,
  });
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / list.data.page_size)) : 1;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-8" placeholder="Order number" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </div>
        {STATUSES.map((s) => (
          <button key={s || "all"} onClick={() => { setStatus(s); setPage(1); }}
            className={cn("rounded-full border px-3 py-1 text-xs capitalize", status === s ? "border-primary bg-primary/10 text-primary" : "hover:bg-muted")}>
            {s || "All"}
          </button>
        ))}
      </div>
      {list.isLoading ? <TableSkeleton /> : list.error ? <ErrorState error={list.error} /> : list.data!.items.length === 0 ? (
        <EmptyState icon={ShoppingBag} title="No orders found" />
      ) : (
        <div className="overflow-x-auto rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Order</TableHead><TableHead>Placed</TableHead><TableHead>Buyer</TableHead>
                {showSeller && <TableHead>Seller</TableHead>}
                <TableHead className="text-right">Items</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.data!.items.map((o) => (
                <TableRow key={o.id} className="cursor-pointer">
                  <TableCell><Link href={`${detailBase}/${o.id}`} className="font-medium hover:text-primary">{o.order_number}</Link></TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">{dateTime(o.placed_at)}</TableCell>
                  <TableCell>{o.buyer?.full_name ?? "—"}</TableCell>
                  {showSeller && <TableCell>{o.seller.store_name}</TableCell>}
                  <TableCell className="text-right">{o.item_count}</TableCell>
                  <TableCell><OrderStatusBadge status={o.status} /></TableCell>
                  <TableCell className="text-right font-medium">{money(o.total)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <span className="mr-auto text-muted-foreground">{list.data?.total} orders</span>
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
          <span className="text-muted-foreground">{page} / {pages}</span>
          <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      )}
    </div>
  );
}
