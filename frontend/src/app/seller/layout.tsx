"use client";

import { BarChart3, Boxes, LayoutDashboard, Package, ShoppingBag, Sparkles, Tag } from "lucide-react";

import { DashboardShell, type NavItem } from "@/components/layout/dashboard-shell";

const NAV: NavItem[] = [
  { href: "/seller", label: "Dashboard", icon: LayoutDashboard },
  { href: "/seller/products", label: "Products", icon: Package },
  { href: "/seller/inventory", label: "Inventory", icon: Boxes },
  { href: "/seller/orders", label: "Orders", icon: ShoppingBag },
  { href: "/seller/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/seller/offers", label: "Offers & pricing", icon: Tag },
  { href: "/seller/astra", label: "GenOra Astra", icon: Sparkles, badge: "AI" },
];

export default function SellerLayout({ children }: LayoutProps<"/seller">) {
  return <DashboardShell role="SELLER" title="Seller" items={NAV}>{children}</DashboardShell>;
}
