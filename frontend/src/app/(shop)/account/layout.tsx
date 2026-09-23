"use client";

import { Heart, LayoutDashboard, Loader2, MessageSquare, Package, UserCog } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useRequireAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/account", label: "Overview", icon: LayoutDashboard },
  { href: "/account/orders", label: "Orders", icon: Package },
  { href: "/account/wishlist", label: "Wishlist", icon: Heart },
  { href: "/account/reviews", label: "Reviews", icon: MessageSquare },
  { href: "/account/profile", label: "Profile & security", icon: UserCog },
];

export default function AccountLayout({ children }: LayoutProps<"/account">) {
  const { allowed, user } = useRequireAuth();
  const pathname = usePathname();
  if (!allowed) return <div className="flex h-96 items-center justify-center"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>;
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="mb-6">
        <p className="text-sm text-muted-foreground">My account</p>
        <h1 className="text-2xl font-semibold tracking-tight">Hi, {user?.full_name.split(" ")[0]}</h1>
      </div>
      <div className="grid gap-8 lg:grid-cols-[220px_1fr]">
        <nav className="-mx-4 flex gap-1 overflow-x-auto px-4 lg:mx-0 lg:flex-col lg:px-0" aria-label="Account">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/account" ? pathname === href : pathname.startsWith(href);
            return (
              <Link key={href} href={href}
                className={cn("flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm transition",
                  active ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
                <Icon className="size-4" /> {label}
              </Link>
            );
          })}
        </nav>
        <div className="min-w-0">{children}</div>
      </div>
    </div>
  );
}
