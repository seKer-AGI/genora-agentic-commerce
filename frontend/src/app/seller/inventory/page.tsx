"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, Check } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, PageHeader, TableSkeleton } from "@/components/common/states";
import { DashboardPage } from "@/components/layout/dashboard-shell";
import { ProductImage } from "@/components/product/product-bits";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import type { InventoryRow } from "@/lib/types";

function Row({ r }: { r: InventoryRow }) {
  const qc = useQueryClient();
  const [qty, setQty] = useState(String(r.quantity_on_hand));
  const [threshold, setThreshold] = useState(String(r.low_stock_threshold));
  const dirty = qty !== String(r.quantity_on_hand) || threshold !== String(r.low_stock_threshold);
  const save = useMutation({
    mutationFn: () => api<InventoryRow>(`/sellers/me/inventory/${r.product_id}`, {
      method: "PATCH", body: { quantity_on_hand: Number(qty), low_stock_threshold: Number(threshold) },
    }),
    onSuccess: () => { toast.success(`Stock updated for ${r.product_name}`); qc.invalidateQueries({ queryKey: ["inventory"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <TableRow>
      <TableCell>
        <div className="flex items-center gap-3">
          <ProductImage src={r.image_url} alt={r.product_name} className="size-9 shrink-0 rounded border" />
          <div className="min-w-0"><p className="max-w-60 truncate font-medium">{r.product_name}</p><p className="text-xs text-muted-foreground">{r.sku}</p></div>
        </div>
      </TableCell>
      <TableCell>{r.is_low ? <Badge variant="outline" className="border-amber-500 text-amber-700">Low</Badge> : <Badge variant="outline">OK</Badge>}</TableCell>
      <TableCell className="text-right">{r.available}</TableCell>
      <TableCell className="text-right text-muted-foreground">{r.quantity_reserved}</TableCell>
      <TableCell><Input className="ml-auto h-8 w-20 text-right" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value.replace(/\D/g, ""))} aria-label="On hand" /></TableCell>
      <TableCell><Input className="ml-auto h-8 w-16 text-right" inputMode="numeric" value={threshold} onChange={(e) => setThreshold(e.target.value.replace(/\D/g, ""))} aria-label="Low-stock threshold" /></TableCell>
      <TableCell className="hidden text-right md:table-cell">{r.sold_count}</TableCell>
      <TableCell>
        <Button size="icon-sm" variant={dirty ? "default" : "ghost"} disabled={!dirty || save.isPending} onClick={() => save.mutate()} aria-label="Save stock">
          <Check />
        </Button>
      </TableCell>
    </TableRow>
  );
}

function Inventory() {
  const params = useSearchParams();
  const [lowOnly, setLowOnly] = useState(params.get("low") === "1");
  const q = useQuery({ queryKey: ["inventory", lowOnly], queryFn: () => api<InventoryRow[]>("/sellers/me/inventory", { query: { low_only: lowOnly } }) });
  return (
    <DashboardPage>
      <PageHeader title="Inventory" description="Adjust on-hand stock and low-stock thresholds. Reserved units are held by open checkouts."
        actions={<label className="flex items-center gap-2 text-sm">Low stock only <Switch checked={lowOnly} onCheckedChange={setLowOnly} /></label>} />
      {q.isLoading ? <TableSkeleton /> : q.error ? <ErrorState error={q.error} /> : q.data!.length === 0 ? (
        <EmptyState icon={Boxes} title={lowOnly ? "Nothing is running low" : "No products yet"} />
      ) : (
        <div className="overflow-x-auto rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Available</TableHead>
                <TableHead className="text-right">Reserved</TableHead><TableHead className="text-right">On hand</TableHead>
                <TableHead className="text-right">Alert at</TableHead><TableHead className="hidden text-right md:table-cell">Sold</TableHead><TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>{q.data!.map((r) => <Row key={r.product_id} r={r} />)}</TableBody>
          </Table>
        </div>
      )}
    </DashboardPage>
  );
}

export default function InventoryPage() {
  return <Suspense><Inventory /></Suspense>;
}
