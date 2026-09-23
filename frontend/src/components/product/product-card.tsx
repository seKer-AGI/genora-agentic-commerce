"use client";

import { Heart, ShoppingCart, Sparkles } from "lucide-react";
import Link from "next/link";

import { ProductImage, Price, Rating } from "@/components/product/product-bits";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAddToCart, useToggleWishlist } from "@/lib/queries";
import type { ProductCard as Product } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ProductCard({ product, reason, className, compact = false }: {
  product: Product;
  reason?: string;
  className?: string;
  compact?: boolean;
}) {
  const addToCart = useAddToCart();
  const wishlist = useToggleWishlist();
  return (
    <div className={cn("group relative flex flex-col overflow-hidden rounded-xl border bg-card transition-shadow hover:shadow-md", className)}>
      <Link href={`/products/${product.slug}`} className="relative block aspect-square overflow-hidden bg-muted">
        <ProductImage src={product.image_url} alt={product.name} className="size-full transition-transform duration-300 group-hover:scale-[1.03]" />
        <div className="absolute left-2 top-2 flex flex-col gap-1">
          {product.offer && (
            <Badge className="bg-rose-600 text-white shadow-sm">
              {product.offer.discount_type === "percentage" ? `${product.offer.value}% off` : "Deal"}
            </Badge>
          )}
          {!product.in_stock && <Badge variant="secondary">Sold out</Badge>}
        </div>
      </Link>
      {!compact && (
        <Button
          size="icon-sm"
          variant="secondary"
          className="absolute right-2 top-2 rounded-full opacity-90 shadow-sm"
          aria-label={`Save ${product.name} to wishlist`}
          onClick={() => wishlist.mutate({ productId: product.id, add: true })}
        >
          <Heart className="size-4" />
        </Button>
      )}
      <div className="flex flex-1 flex-col gap-1.5 p-3">
        <p className="truncate text-xs text-muted-foreground">{product.brand ?? product.seller.store_name}</p>
        <Link href={`/products/${product.slug}`} className="line-clamp-2 text-sm font-medium leading-snug hover:underline">
          {product.name}
        </Link>
        <Rating value={product.rating_avg} count={product.rating_count} />
        <Price price={product.price} salePrice={product.sale_price} finalPrice={product.final_price} className="mt-auto pt-1" />
        {reason && (
          <p className="flex items-start gap-1 text-xs text-primary">
            <Sparkles className="mt-0.5 size-3 shrink-0" /> {reason}
          </p>
        )}
        {!compact && (
          <Button
            size="sm"
            variant="outline"
            className="mt-2 w-full"
            disabled={!product.in_stock || addToCart.isPending}
            onClick={() => addToCart.mutate({ productId: product.id, quantity: 1, name: product.name })}
          >
            <ShoppingCart /> {product.in_stock ? "Add to cart" : "Out of stock"}
          </Button>
        )}
      </div>
    </div>
  );
}

export function ProductGrid({ products, reasons, className }: {
  products: Product[];
  reasons?: Record<string, string>;
  className?: string;
}) {
  return (
    <div className={cn("grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 lg:grid-cols-4", className)}>
      {products.map((p) => (
        <ProductCard key={p.id} product={p} reason={reasons?.[p.id]} />
      ))}
    </div>
  );
}
