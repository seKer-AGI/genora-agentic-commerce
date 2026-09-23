import type { ReactNode } from "react";

import { Separator } from "@/components/ui/separator";
import { money } from "@/lib/format";
import type { Cart } from "@/lib/types";

export function OrderSummary({ cart, children }: { cart: Cart; children?: ReactNode }) {
  return (
    <div className="rounded-2xl border bg-card p-5">
      <h2 className="font-semibold">Order summary</h2>
      <dl className="mt-4 space-y-2 text-sm">
        <div className="flex justify-between"><dt className="text-muted-foreground">Subtotal ({cart.item_count} items)</dt><dd>{money(cart.subtotal)}</dd></div>
        {cart.discount_total > 0 && (
          <div className="flex justify-between text-emerald-600"><dt>Discounts</dt><dd>−{money(cart.discount_total)}</dd></div>
        )}
        <div className="flex justify-between"><dt className="text-muted-foreground">Shipping</dt><dd>{cart.shipping_total === 0 ? "Free" : money(cart.shipping_total)}</dd></div>
        <div className="flex justify-between"><dt className="text-muted-foreground">Estimated tax</dt><dd>{money(cart.tax_total)}</dd></div>
        <Separator />
        <div className="flex justify-between text-base font-semibold"><dt>Total</dt><dd>{money(cart.total)}</dd></div>
      </dl>
      {cart.sellers.length > 1 && (
        <p className="mt-3 text-xs text-muted-foreground">Ships from {cart.sellers.length} sellers — you&apos;ll receive one order per seller.</p>
      )}
      {children}
    </div>
  );
}
