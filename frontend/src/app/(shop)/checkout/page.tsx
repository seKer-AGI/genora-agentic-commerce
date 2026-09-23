"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CreditCard, Loader2, MapPin, Plus } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { OrderSummary } from "@/components/commerce/order-summary";
import { EmptyState, PageHeader } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import { qk, useCart } from "@/lib/queries";
import type { Address, CheckoutResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const TEST_CARDS = [
  { token: "pm_card_visa", label: "Visa •••• 4242", note: "Approves" },
  { token: "pm_card_declined", label: "Visa •••• 0002", note: "Declines (test)" },
];

const EMPTY_ADDR = { recipient_name: "", line1: "", line2: "", city: "", state: "", postal_code: "", country: "US" };

export default function CheckoutPage() {
  const { allowed } = useRequireAuth();
  const qc = useQueryClient();
  const cart = useCart();
  const addresses = useQuery({ queryKey: ["addresses"], queryFn: () => api<Address[]>("/addresses"), enabled: allowed });
  const [addressId, setAddressId] = useState<string | null>(null);
  const [newAddr, setNewAddr] = useState<typeof EMPTY_ADDR | null>(null);
  const [card, setCard] = useState(TEST_CARDS[0].token);
  const [notes, setNotes] = useState("");
  const [done, setDone] = useState<CheckoutResponse | null>(null);
  const idempotencyKey = useMemo(() => crypto.randomUUID(), []);

  const selected = addressId ?? addresses.data?.find((a) => a.is_default)?.id ?? addresses.data?.[0]?.id ?? null;

  const checkout = useMutation({
    mutationFn: () => api<CheckoutResponse>("/orders/checkout", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: {
        ...(newAddr ? { address: { ...newAddr, line2: newAddr.line2 || null, state: newAddr.state || null } } : { address_id: selected }),
        payment_method: card,
        notes: notes || null,
      },
    }),
    onSuccess: (r) => {
      setDone(r);
      qc.invalidateQueries({ queryKey: qk.cart });
      qc.invalidateQueries({ queryKey: ["orders"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (done) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center">
        <CheckCircle2 className="mx-auto size-14 text-emerald-600" />
        <h1 className="mt-4 text-2xl font-semibold">Thank you — your order is confirmed</h1>
        <p className="mt-2 text-muted-foreground">
          {done.orders.length} order{done.orders.length > 1 ? "s" : ""} placed · {money(done.total_charged)} charged ({done.payment_status})
        </p>
        <div className="mx-auto mt-6 max-w-md divide-y rounded-xl border text-left text-sm">
          {done.orders.map((o) => (
            <Link key={o.id} href={`/account/orders/${o.id}`} className="flex items-center justify-between px-4 py-3 hover:bg-muted/50">
              <span><b>{o.order_number}</b><span className="block text-xs text-muted-foreground">{o.seller.store_name} · {o.item_count} item(s)</span></span>
              <span className="font-medium">{money(o.total)}</span>
            </Link>
          ))}
        </div>
        <div className="mt-6 flex justify-center gap-2">
          <Button render={<Link href="/account/orders" />} nativeButton={false}>View orders</Button>
          <Button variant="outline" render={<Link href="/" />} nativeButton={false}>Continue shopping</Button>
        </div>
      </div>
    );
  }

  if (!allowed || cart.isLoading || addresses.isLoading) return <div className="mx-auto max-w-5xl px-4 py-8"><Skeleton className="h-96" /></div>;
  const c = cart.data;
  if (!c || c.items.length === 0) {
    return <div className="mx-auto max-w-3xl px-4 py-12"><EmptyState title="Your cart is empty" action={<Button render={<Link href="/products" />} nativeButton={false}>Browse products</Button>} /></div>;
  }
  const addrValid = newAddr ? newAddr.recipient_name && newAddr.line1 && newAddr.city && newAddr.postal_code && /^[A-Z]{2}$/.test(newAddr.country) : !!selected;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <PageHeader title="Checkout" />
      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <section className="rounded-2xl border bg-card p-5">
            <h2 className="mb-3 flex items-center gap-2 font-semibold"><MapPin className="size-4" /> Shipping address</h2>
            {!newAddr && (
              <div className="space-y-2">
                {addresses.data?.map((a) => (
                  <label key={a.id} className={cn("flex cursor-pointer gap-3 rounded-xl border p-3 text-sm", selected === a.id && "border-primary bg-primary/5")}>
                    <input type="radio" name="address" className="mt-1" checked={selected === a.id} onChange={() => setAddressId(a.id)} />
                    <span>
                      <b>{a.recipient_name}</b>{a.label && <span className="ml-1 text-xs text-muted-foreground">({a.label})</span>}<br />
                      {a.line1}{a.line2 && `, ${a.line2}`}, {a.city}{a.state && `, ${a.state}`} {a.postal_code}, {a.country}
                    </span>
                  </label>
                ))}
                <Button variant="outline" size="sm" onClick={() => setNewAddr(EMPTY_ADDR)}><Plus /> Use a new address</Button>
              </div>
            )}
            {newAddr && (
              <div className="grid gap-3 sm:grid-cols-2">
                {([
                  ["recipient_name", "Full name", "sm:col-span-2"], ["line1", "Address line 1", "sm:col-span-2"], ["line2", "Address line 2 (optional)", "sm:col-span-2"],
                  ["city", "City", ""], ["state", "State / region", ""], ["postal_code", "Postal code", ""], ["country", "Country (2-letter code)", ""],
                ] as const).map(([k, label, span]) => (
                  <div key={k} className={cn("space-y-1", span)}>
                    <Label htmlFor={k}>{label}</Label>
                    <Input id={k} value={newAddr[k]} maxLength={k === "country" ? 2 : 200}
                      onChange={(e) => setNewAddr({ ...newAddr, [k]: k === "country" ? e.target.value.toUpperCase() : e.target.value })} />
                  </div>
                ))}
                {addresses.data && addresses.data.length > 0 && (
                  <Button variant="ghost" size="sm" className="w-fit" onClick={() => setNewAddr(null)}>Use a saved address</Button>
                )}
              </div>
            )}
          </section>

          <section className="rounded-2xl border bg-card p-5">
            <h2 className="mb-1 flex items-center gap-2 font-semibold"><CreditCard className="size-4" /> Payment</h2>
            <p className="mb-3 text-xs text-muted-foreground">
              Sandbox payment provider — no real money moves. In production, a PCI-compliant provider (e.g. Stripe Elements) supplies a payment token here.
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {TEST_CARDS.map((t) => (
                <label key={t.token} className={cn("flex cursor-pointer items-center gap-3 rounded-xl border p-3 text-sm", card === t.token && "border-primary bg-primary/5")}>
                  <input type="radio" name="card" checked={card === t.token} onChange={() => setCard(t.token)} />
                  <span><b>{t.label}</b><span className="block text-xs text-muted-foreground">{t.note}</span></span>
                </label>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border bg-card p-5">
            <Label htmlFor="notes">Order notes (optional)</Label>
            <Textarea id="notes" className="mt-2" maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </section>
        </div>

        <div className="lg:sticky lg:top-20 lg:self-start">
          <OrderSummary cart={c}>
            <ul className="mt-4 max-h-48 space-y-1.5 overflow-y-auto border-t pt-3 text-xs">
              {c.items.map((i) => (
                <li key={i.id} className="flex justify-between gap-2"><span className="truncate">{i.quantity} × {i.product_name}</span><span>{money(i.total)}</span></li>
              ))}
            </ul>
            <Button size="lg" className="mt-4 w-full" disabled={!addrValid || checkout.isPending || c.issues.length > 0} onClick={() => checkout.mutate()}>
              {checkout.isPending && <Loader2 className="animate-spin" />} Place order · {money(c.total)}
            </Button>
          </OrderSummary>
        </div>
      </div>
    </div>
  );
}
