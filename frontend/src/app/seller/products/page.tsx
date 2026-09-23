"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Package, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, PageHeader, TableSkeleton } from "@/components/common/states";
import { DashboardPage } from "@/components/layout/dashboard-shell";
import { ProductImage, ProductStatusBadge } from "@/components/product/product-bits";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { money } from "@/lib/format";
import type { Page, ProductCard } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUSES = ["", "active", "draft", "archived", "blocked"];

export default function SellerProducts() {
  const qc = useQueryClient();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const list = useQuery({
    queryKey: ["seller-products", q, status, page],
    queryFn: () => api<Page<ProductCard>>("/sellers/me/products", { query: { q, status, page, page_size: 20 } }),
    placeholderData: keepPreviousData,
  });
  const update = useMutation({
    mutationFn: (v: { id: string; body: Record<string, unknown> }) => api(`/products/${v.id}`, { method: "PATCH", body: v.body }),
    onSuccess: () => { toast.success("Product updated"); qc.invalidateQueries({ queryKey: ["seller-products"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/products/${id}`, { method: "DELETE" }),
    onSuccess: () => { toast.success("Product deleted"); qc.invalidateQueries({ queryKey: ["seller-products"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / list.data.page_size)) : 1;

  return (
    <DashboardPage>
      <PageHeader title="Products" description={list.data ? `${list.data.total} products` : undefined}
        actions={<Button render={<Link href="/seller/products/new" />} nativeButton={false}><Plus /> New product</Button>} />
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-8" placeholder="Search name or SKU" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </div>
        {STATUSES.map((s) => (
          <button key={s || "all"} onClick={() => { setStatus(s); setPage(1); }}
            className={cn("rounded-full border px-3 py-1 text-xs capitalize", status === s ? "border-primary bg-primary/10 text-primary" : "hover:bg-muted")}>
            {s || "All"}
          </button>
        ))}
      </div>
      {list.isLoading ? <TableSkeleton /> : list.error ? <ErrorState error={list.error} /> : list.data!.items.length === 0 ? (
        <EmptyState icon={Package} title="No products" description="Create your first product or ask Astra to draft a listing."
          action={<Button render={<Link href="/seller/products/new" />} nativeButton={false}>New product</Button>} />
      ) : (
        <div className="overflow-hidden rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow><TableHead>Product</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Price</TableHead>
                <TableHead className="text-right">Stock</TableHead><TableHead className="hidden text-right md:table-cell">Sold</TableHead><TableHead className="w-10" /></TableRow>
            </TableHeader>
            <TableBody>
              {list.data!.items.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <Link href={`/seller/products/${p.id}`} className="flex items-center gap-3 hover:text-primary">
                      <ProductImage src={p.image_url} alt={p.name} className="size-10 shrink-0 rounded-md border" />
                      <span className="max-w-xs truncate font-medium">{p.name}</span>
                    </Link>
                  </TableCell>
                  <TableCell><ProductStatusBadge status={p.status} /></TableCell>
                  <TableCell className="text-right">{money(p.final_price)}{p.final_price < p.price && <span className="block text-xs text-muted-foreground line-through">{money(p.price)}</span>}</TableCell>
                  <TableCell className={cn("text-right", p.stock <= 5 && "font-medium text-amber-600")}>{p.stock}</TableCell>
                  <TableCell className="hidden text-right md:table-cell">{p.sold_count}</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label="Product actions" />}><MoreHorizontal /></DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => router.push(`/seller/products/${p.id}`)}>Edit</DropdownMenuItem>
                        {p.status === "active" && <DropdownMenuItem onClick={() => router.push(`/products/${p.slug}`)}>View in store</DropdownMenuItem>}
                        {p.status === "draft" && <DropdownMenuItem onClick={() => update.mutate({ id: p.id, body: { status: "active" } })}>Publish</DropdownMenuItem>}
                        {p.status === "active" && <DropdownMenuItem onClick={() => update.mutate({ id: p.id, body: { status: "archived" } })}>Archive</DropdownMenuItem>}
                        <DropdownMenuSeparator />
                        <DropdownMenuItem variant="destructive" onClick={() => { if (confirm(`Delete ${p.name}? This cannot be undone.`)) remove.mutate(p.id); }}>Delete</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
          <span className="text-muted-foreground">{page} / {pages}</span>
          <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      )}
    </DashboardPage>
  );
}
