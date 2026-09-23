"use client";

import { Heart, Trash2 } from "lucide-react";
import Link from "next/link";

import { EmptyState, GridSkeleton } from "@/components/common/states";
import { ProductCard } from "@/components/product/product-card";
import { Button } from "@/components/ui/button";
import { useToggleWishlist, useWishlist } from "@/lib/queries";

export default function WishlistPage() {
  const wishlist = useWishlist();
  const toggle = useToggleWishlist();
  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">Wishlist</h2>
      {wishlist.isLoading ? <GridSkeleton count={4} /> : !wishlist.data?.length ? (
        <EmptyState icon={Heart} title="Nothing saved yet" description="Tap the heart on any product to save it for later."
          action={<Button render={<Link href="/products" />} nativeButton={false}>Browse products</Button>} />
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
          {wishlist.data.map((p) => (
            <div key={p.id} className="relative">
              <ProductCard product={p} compact />
              <Button size="xs" variant="ghost" className="mt-1 w-full text-muted-foreground"
                onClick={() => toggle.mutate({ productId: p.id, add: false })}>
                <Trash2 /> Remove
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
