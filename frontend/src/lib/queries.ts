"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { api, errorMessage, getAccessToken } from "./api";
import { useAuth } from "./auth";
import type { Cart, CategoryNode, ProductCard } from "./types";

export const qk = {
  categories: ["categories"] as const,
  cart: ["cart"] as const,
  wishlist: ["wishlist"] as const,
  orders: (page: number, status?: string) => ["orders", page, status ?? ""] as const,
};

export function useCategories() {
  return useQuery({ queryKey: qk.categories, queryFn: () => api<CategoryNode[]>("/categories"), staleTime: 5 * 60_000 });
}

export function flattenCategories(nodes: CategoryNode[] = [], depth = 0): (CategoryNode & { depth: number })[] {
  return nodes.flatMap((n) => [{ ...n, depth }, ...flattenCategories(n.children, depth + 1)]);
}

export function useCart() {
  const { status } = useAuth();
  return useQuery({ queryKey: qk.cart, queryFn: () => api<Cart>("/cart"), enabled: status === "authenticated" });
}

function useRequireLogin() {
  const router = useRouter();
  return () => {
    if (!getAccessToken()) {
      toast.info("Please sign in to continue");
      router.push(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      return false;
    }
    return true;
  };
}

export function useAddToCart() {
  const qc = useQueryClient();
  const requireLogin = useRequireLogin();
  return useMutation({
    mutationFn: async (v: { productId: string; quantity: number; name?: string }) => {
      if (!requireLogin()) throw new Error("login-required");
      return api<Cart>("/cart/items", { method: "POST", body: { product_id: v.productId, quantity: v.quantity } });
    },
    onSuccess: (cart, v) => {
      qc.setQueryData(qk.cart, cart);
      toast.success(v.name ? `Added ${v.name} to your cart` : "Added to cart", {
        action: { label: "View cart", onClick: () => (window.location.href = "/cart") },
      });
    },
    onError: (err) => {
      if ((err as Error).message !== "login-required") toast.error(errorMessage(err));
    },
  });
}

export function useAddBundleToCart() {
  const qc = useQueryClient();
  const requireLogin = useRequireLogin();
  return useMutation({
    mutationFn: async (bundleId: string) => {
      if (!requireLogin()) throw new Error("login-required");
      return api<Cart>(`/cart/bundles/${bundleId}`, { method: "POST" });
    },
    onSuccess: (cart) => {
      qc.setQueryData(qk.cart, cart);
      toast.success("Bundle added to your cart");
    },
    onError: (err) => {
      if ((err as Error).message !== "login-required") toast.error(errorMessage(err));
    },
  });
}

export function useCartMutations() {
  const qc = useQueryClient();
  const onSuccess = (cart: Cart) => qc.setQueryData(qk.cart, cart);
  const onError = (err: unknown) => toast.error(errorMessage(err));
  return {
    update: useMutation({
      mutationFn: (v: { itemId: string; quantity: number }) =>
        api<Cart>(`/cart/items/${v.itemId}`, { method: "PATCH", body: { quantity: v.quantity } }),
      onSuccess, onError,
    }),
    remove: useMutation({
      mutationFn: (itemId: string) => api<Cart>(`/cart/items/${itemId}`, { method: "DELETE" }),
      onSuccess, onError,
    }),
    applyCoupon: useMutation({
      mutationFn: (code: string) => api<Cart>("/cart/coupon", { method: "POST", body: { code } }),
      onSuccess: (cart: Cart) => {
        onSuccess(cart);
        toast.success(cart.coupon_message ?? "Coupon applied");
      },
      onError,
    }),
    removeCoupon: useMutation({
      mutationFn: () => api<Cart>("/cart/coupon", { method: "DELETE" }),
      onSuccess, onError,
    }),
  };
}

export function useWishlist() {
  const { status } = useAuth();
  return useQuery({
    queryKey: qk.wishlist,
    queryFn: () => api<ProductCard[]>("/wishlist"),
    enabled: status === "authenticated",
  });
}

export function useToggleWishlist() {
  const qc = useQueryClient();
  const requireLogin = useRequireLogin();
  return useMutation({
    mutationFn: async (v: { productId: string; add: boolean }) => {
      if (!requireLogin()) throw new Error("login-required");
      return api<ProductCard[]>(`/wishlist/${v.productId}`, { method: v.add ? "POST" : "DELETE" });
    },
    onSuccess: (items, v) => {
      qc.setQueryData(qk.wishlist, items);
      toast.success(v.add ? "Saved to your wishlist" : "Removed from your wishlist");
    },
    onError: (err) => {
      if ((err as Error).message !== "login-required") toast.error(errorMessage(err));
    },
  });
}

/** Fire-and-forget behavioural analytics (whitelisted event types only). */
export function track(event: "product_view" | "category_view" | "search_click" | "recommendation_click" | "bundle_view" | "nova_open" | "astra_open",
                      data: { product_id?: string; category_id?: string; properties?: Record<string, string | number | boolean> } = {}) {
  let key = "";
  try {
    key = sessionStorage.getItem("genora_sk") ?? "";
    if (!key) {
      key = crypto.randomUUID().replace(/-/g, "");
      sessionStorage.setItem("genora_sk", key);
    }
  } catch {
    /* storage unavailable */
  }
  api("/analytics/events", { method: "POST", body: { event_type: event, session_key: key || undefined, ...data } }).catch(() => {});
}
