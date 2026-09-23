import { Badge } from "@/components/ui/badge";
import type { OrderStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STYLES: Record<OrderStatus, string> = {
  pending: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  confirmed: "bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300",
  processing: "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300",
  shipped: "bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300",
  delivered: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  cancelled: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
  refunded: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
};

export function OrderStatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <Badge variant="secondary" className={cn("capitalize", STYLES[status as OrderStatus], className)}>
      {status}
    </Badge>
  );
}

export const FLOW: OrderStatus[] = ["pending", "confirmed", "processing", "shipped", "delivered"];

export function OrderProgress({ status }: { status: OrderStatus }) {
  if (status === "cancelled" || status === "refunded") return null;
  const idx = FLOW.indexOf(status);
  return (
    <ol className="flex items-center gap-1" aria-label="Order progress">
      {FLOW.map((s, i) => (
        <li key={s} className="flex flex-1 flex-col gap-1">
          <span className={cn("h-1.5 rounded-full", i <= idx ? "bg-primary" : "bg-muted")} />
          <span className={cn("text-[10px] capitalize sm:text-xs", i <= idx ? "text-foreground" : "text-muted-foreground")}>{s}</span>
        </li>
      ))}
    </ol>
  );
}
