"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Truck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { OrderProgress, OrderStatusBadge } from "@/components/commerce/order-bits";
import { ErrorState } from "@/components/common/states";
import { ProductImage } from "@/components/product/product-bits";
import { Button } from "@/components/ui/button";
import {
  AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { api, errorMessage } from "@/lib/api";
import { dateTime, money } from "@/lib/format";
import type { Order } from "@/lib/types";

const ACTION_LABELS: Record<string, string> = {
  confirmed: "Confirm order", processing: "Start processing", shipped: "Mark as shipped", delivered: "Mark as delivered",
  cancelled: "Cancel order", refunded: "Refund order",
};

/** Order detail shared by buyers, sellers and admins. Available actions come from the server (`allowed_transitions`). */
export function OrderDetail({ orderId, backHref, backLabel }: { orderId: string; backHref: string; backLabel: string }) {
  const qc = useQueryClient();
  const [tracking, setTracking] = useState("");
  const q = useQuery({ queryKey: ["order", orderId], queryFn: () => api<Order>(`/orders/${orderId}`) });
  const change = useMutation({
    mutationFn: (status: string) => api<Order>(`/orders/${orderId}/status`, {
      method: "POST", body: { status, tracking_number: status === "shipped" && tracking ? tracking : null },
    }),
    onSuccess: (o) => {
      qc.setQueryData(["order", orderId], o);
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: ["seller-orders"] });
      qc.invalidateQueries({ queryKey: ["admin-orders"] });
      toast.success(`Order ${o.order_number} is now ${o.status}`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (q.isLoading) return <Skeleton className="h-96" />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const o = q.data;
  const addr = o.shipping_address ?? {};

  return (
    <div className="space-y-6">
      <Link href={backHref} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> {backLabel}</Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Order {o.order_number}</h2>
          <p className="text-sm text-muted-foreground">Placed {dateTime(o.placed_at)} · sold by {o.seller.store_name}{o.buyer && ` · buyer ${o.buyer.full_name}`}</p>
        </div>
        <OrderStatusBadge status={o.status} className="text-sm" />
      </div>
      <OrderProgress status={o.status} />

      {o.allowed_transitions.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-muted/30 p-3">
          {o.allowed_transitions.includes("shipped") && (
            <Input placeholder="Tracking number (optional)" value={tracking} onChange={(e) => setTracking(e.target.value)} className="w-56 bg-background" />
          )}
          {o.allowed_transitions.map((t) => t === "cancelled" || t === "refunded" ? (
            <AlertDialog key={t}>
              <AlertDialogTrigger render={<Button variant="destructive" size="sm" disabled={change.isPending} />}>{ACTION_LABELS[t]}</AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{ACTION_LABELS[t]}?</AlertDialogTitle>
                  <AlertDialogDescription>
                    {t === "cancelled" ? "The order will be cancelled, stock restored and the payment refunded." : "The full payment will be refunded to the buyer."} This cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Keep order</AlertDialogCancel>
                  <AlertDialogCancel variant="destructive" onClick={() => change.mutate(t)}>{ACTION_LABELS[t]}</AlertDialogCancel>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          ) : (
            <Button key={t} size="sm" disabled={change.isPending} onClick={() => change.mutate(t)}>{ACTION_LABELS[t] ?? t}</Button>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="rounded-xl border">
          <ul className="divide-y">
            {o.items.map((i) => (
              <li key={i.id} className="flex gap-3 p-4">
                <ProductImage src={i.image_url} alt={i.product_name} className="size-16 shrink-0 rounded-lg border" />
                <div className="min-w-0 flex-1">
                  {i.product_slug ? <Link href={`/products/${i.product_slug}`} className="text-sm font-medium hover:underline">{i.product_name}</Link>
                    : <p className="text-sm font-medium">{i.product_name}</p>}
                  <p className="text-xs text-muted-foreground">SKU {i.sku} · {i.quantity} × {money(i.unit_price)}</p>
                  {i.discount_amount > 0 && <p className="text-xs text-emerald-600">Discount −{money(i.discount_amount)}</p>}
                </div>
                <p className="text-sm font-medium">{money(i.line_total)}</p>
              </li>
            ))}
          </ul>
        </div>
        <div className="space-y-4">
          <div className="rounded-xl border p-4 text-sm">
            <dl className="space-y-1.5">
              <div className="flex justify-between"><dt className="text-muted-foreground">Subtotal</dt><dd>{money(o.subtotal)}</dd></div>
              {o.discount_total > 0 && <div className="flex justify-between text-emerald-600"><dt>Discounts</dt><dd>−{money(o.discount_total)}</dd></div>}
              <div className="flex justify-between"><dt className="text-muted-foreground">Shipping</dt><dd>{money(o.shipping_total)}</dd></div>
              <div className="flex justify-between"><dt className="text-muted-foreground">Tax</dt><dd>{money(o.tax_total)}</dd></div>
              <Separator />
              <div className="flex justify-between font-semibold"><dt>Total</dt><dd>{money(o.total)}</dd></div>
            </dl>
            {o.discounts.length > 0 && (
              <ul className="mt-3 space-y-0.5 text-xs text-muted-foreground">
                {o.discounts.map((d, i) => <li key={i}>{d.description}: −{money(d.amount)}</li>)}
              </ul>
            )}
          </div>
          <div className="rounded-xl border p-4 text-sm">
            <p className="mb-1 font-medium">Ship to</p>
            <p className="text-muted-foreground">
              {addr.recipient_name}<br />{addr.line1}{addr.line2 && <>, {addr.line2}</>}<br />{addr.city}{addr.state && `, ${addr.state}`} {addr.postal_code}, {addr.country}
            </p>
            {o.tracking_number && <p className="mt-2 flex items-center gap-1.5"><Truck className="size-4" /> {o.tracking_number}</p>}
          </div>
          <div className="rounded-xl border p-4 text-sm">
            <p className="mb-2 font-medium">Payment</p>
            {o.payments.map((p) => (
              <p key={p.id} className="flex justify-between text-muted-foreground"><span className="capitalize">{p.provider} · {p.status}</span><span>{money(p.amount)}</span></p>
            ))}
          </div>
          <div className="rounded-xl border p-4 text-sm">
            <p className="mb-2 font-medium">History</p>
            <ol className="space-y-2 border-l pl-4">
              {o.status_history.map((e, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[21px] top-1.5 size-2 rounded-full bg-primary" />
                  <p className="capitalize">{e.to_status}</p>
                  <p className="text-xs text-muted-foreground">{dateTime(e.created_at)}{e.note && ` · ${e.note}`}</p>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}
