"use client";

import { ExternalLink, Loader2, LogOut, Menu, ShieldAlert, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useState } from "react";

import { EmptyState } from "@/components/common/states";
import { Logo } from "@/components/layout/site-header";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useRequireAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  badge?: string;
}

function Nav({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  const pathname = usePathname();
  const root = items[0]?.href;
  return (
    <nav className="grid gap-0.5 p-3 text-sm">
      {items.map(({ href, label, icon: Icon, badge }) => {
        const active = href === root ? pathname === href : pathname.startsWith(href);
        return (
          <Link key={href} href={href} onClick={onNavigate}
            className={cn("flex items-center gap-2.5 rounded-lg px-3 py-2 transition",
              active ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
            <Icon className="size-4" />
            <span className="flex-1">{label}</span>
            {badge && <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">{badge}</span>}
          </Link>
        );
      })}
    </nav>
  );
}

export function DashboardShell({ role, title, items, children }: {
  role: "SELLER" | "ADMIN";
  title: string;
  items: NavItem[];
  children: ReactNode;
}) {
  const { allowed, status, user, logout } = useRequireAuth(role);
  const router = useRouter();
  const [open, setOpen] = useState(false);

  if (status === "loading" || status === "anonymous") {
    return <div className="flex min-h-dvh items-center justify-center"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>;
  }
  if (!allowed) {
    return (
      <div className="flex min-h-dvh items-center justify-center p-4">
        <EmptyState icon={ShieldAlert} title="You don't have access to this area"
          description={role === "SELLER" ? "An active seller account is required." : "Administrator access is required."}
          action={<Button render={<Link href={role === "SELLER" ? "/register?type=seller" : "/"} />} nativeButton={false}>
            {role === "SELLER" ? "Become a seller" : "Back to the marketplace"}
          </Button>} />
      </div>
    );
  }

  const footer = (
    <div className="border-t p-3 text-sm">
      <p className="truncate px-2 font-medium">{user?.seller && role === "SELLER" ? user.seller.store_name : user?.full_name}</p>
      <p className="truncate px-2 text-xs text-muted-foreground">{user?.email}</p>
      <div className="mt-2 grid gap-0.5">
        <Link href="/" className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
          <ExternalLink className="size-4" /> View marketplace
        </Link>
        <button onClick={async () => { await logout(); router.push("/"); }}
          className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-muted-foreground hover:bg-muted hover:text-foreground">
          <LogOut className="size-4" /> Sign out
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r bg-sidebar lg:flex">
        <div className="flex h-16 items-center border-b px-4"><Logo href={items[0].href} suffix={title} /></div>
        <div className="flex-1 overflow-y-auto"><Nav items={items} /></div>
        {footer}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/90 px-4 backdrop-blur lg:hidden">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger render={<Button variant="ghost" size="icon" aria-label="Open navigation" />}><Menu /></SheetTrigger>
            <SheetContent side="left" className="flex w-64 flex-col p-0">
              <SheetHeader className="border-b"><SheetTitle><Logo href={items[0].href} suffix={title} /></SheetTitle></SheetHeader>
              <div className="flex-1 overflow-y-auto"><Nav items={items} onNavigate={() => setOpen(false)} /></div>
              {footer}
            </SheetContent>
          </Sheet>
          <Logo href={items[0].href} suffix={title} />
        </header>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}

export function DashboardPage({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto w-full max-w-7xl space-y-6 p-4 sm:p-6", className)}>{children}</div>;
}
