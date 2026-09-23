import { ImageOff, Star } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { discountPercent, money } from "@/lib/format";
import { cn } from "@/lib/utils";

export function ProductImage({ src, alt, className }: { src: string | null | undefined; alt: string; className?: string }) {
  if (!src) {
    return (
      <div className={cn("flex items-center justify-center bg-muted text-muted-foreground", className)} aria-label={alt}>
        <ImageOff className="size-8" />
      </div>
    );
  }
  // Product art is served by the API (SVG/uploaded images); next/image optimisation does not apply to SVG.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt} loading="lazy" className={cn("object-cover", className)} />;
}

export function Rating({ value, count, size = "sm", className }: {
  value: number;
  count?: number;
  size?: "sm" | "md";
  className?: string;
}) {
  const icon = size === "sm" ? "size-3.5" : "size-4.5";
  return (
    <div className={cn("flex items-center gap-1", className)} aria-label={`Rated ${value.toFixed(1)} out of 5`}>
      <div className="flex">
        {[1, 2, 3, 4, 5].map((i) => (
          <Star
            key={i}
            className={cn(icon, i <= Math.round(value) ? "fill-amber-400 text-amber-400" : "fill-muted text-muted-foreground/30")}
          />
        ))}
      </div>
      {count !== undefined && (
        <span className="text-xs text-muted-foreground">
          {count > 0 ? `${value.toFixed(1)} (${count})` : "No reviews"}
        </span>
      )}
    </div>
  );
}

export function Price({ price, salePrice, finalPrice, size = "md", className }: {
  price: number;
  salePrice?: number | null;
  finalPrice: number;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const reference = price;
  const off = discountPercent(reference, finalPrice);
  const sizes = { sm: "text-sm", md: "text-base", lg: "text-3xl" } as const;
  return (
    <div className={cn("flex flex-wrap items-baseline gap-x-2 gap-y-1", className)}>
      <span className={cn("font-semibold tracking-tight", sizes[size])}>{money(finalPrice)}</span>
      {off > 0 && (
        <>
          <span className="text-xs text-muted-foreground line-through">{money(reference)}</span>
          <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
            -{off}%
          </Badge>
        </>
      )}
      {off === 0 && salePrice != null && salePrice < price && (
        <span className="text-xs text-muted-foreground line-through">{money(price)}</span>
      )}
    </div>
  );
}

export function StockBadge({ stock }: { stock: number }) {
  if (stock <= 0) return <Badge variant="destructive">Out of stock</Badge>;
  if (stock <= 5) return <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-300">Only {stock} left</Badge>;
  return <Badge variant="outline" className="border-emerald-500/40 text-emerald-700 dark:text-emerald-300">In stock</Badge>;
}
