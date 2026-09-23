"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Heart, LayoutDashboard, LogOut, Menu, Moon, Package, Search, Shield, ShoppingCart, Sparkles, Store, Sun, Tag, User,
} from "lucide-react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useCart, useCategories } from "@/lib/queries";

export function Logo({ href = "/", suffix }: { href?: string; suffix?: string }) {
  return (
    <Link href={href} className="flex shrink-0 items-center gap-2 font-semibold tracking-tight">
      <span className="bg-genora flex size-7 items-center justify-center rounded-lg text-white shadow-sm">
        <Sparkles className="size-4" />
      </span>
      <span className="text-lg">
        Gen<span className="text-genora">Ora</span>
        {suffix && <span className="ml-1.5 text-sm font-normal text-muted-foreground">{suffix}</span>}
      </span>
    </Link>
  );
}

function SearchBox({ onDone }: { onDone?: () => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [debounced, setDebounced] = useState("");
  const ref = useRef<HTMLFormElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const suggest = useQuery({
    queryKey: ["suggest", debounced],
    queryFn: () => api<{ products: { name: string; slug: string }[]; categories: { name: string; slug: string }[] }>(
      "/search/suggest", { query: { q: debounced } }),
    enabled: debounced.length >= 2,
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    setOpen(false);
    onDone?.();
    router.push(`/products?q=${encodeURIComponent(q.trim())}`);
  };

  const hasSuggestions = !!suggest.data && (suggest.data.products.length > 0 || suggest.data.categories.length > 0);
  return (
    <form ref={ref} onSubmit={submit} role="search" className="relative w-full">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder="Search products, brands and categories"
        aria-label="Search products"
        className="h-10 rounded-full bg-muted/50 pl-9"
      />
      {open && hasSuggestions && debounced.length >= 2 && (
        <div className="absolute inset-x-0 top-12 z-50 overflow-hidden rounded-xl border bg-popover p-1 shadow-lg">
          {suggest.data!.categories.map((c) => (
            <Link key={c.slug} href={`/products?category=${c.slug}`} onClick={() => { setOpen(false); onDone?.(); }}
              className="flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted">
              <Tag className="size-3.5 text-muted-foreground" /> {c.name}
              <span className="ml-auto text-xs text-muted-foreground">Category</span>
            </Link>
          ))}
          {suggest.data!.products.map((p) => (
            <Link key={p.slug} href={`/products/${p.slug}`} onClick={() => { setOpen(false); onDone?.(); }}
              className="flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted">
              <Search className="size-3.5 text-muted-foreground" /> {p.name}
            </Link>
          ))}
        </div>
      )}
    </form>
  );
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <DropdownMenuItem onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
      {resolvedTheme === "dark" ? <Sun /> : <Moon />} {resolvedTheme === "dark" ? "Light mode" : "Dark mode"}
    </DropdownMenuItem>
  );
}

function AccountMenu() {
  const { user, status, logout } = useAuth();
  const router = useRouter();
  if (status !== "authenticated" || !user) {
    return (
      <div className="hidden items-center gap-1 sm:flex">
        <Button variant="ghost" size="sm" render={<Link href="/login" />} nativeButton={false}>Sign in</Button>
        <Button size="sm" render={<Link href="/register" />} nativeButton={false}>Join</Button>
      </div>
    );
  }
  const initials = user.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" size="icon" className="rounded-full" aria-label="Account menu" />}>
        <span className="flex size-8 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
          {initials}
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuGroup>
          <DropdownMenuLabel>
            <div className="truncate text-sm font-medium text-foreground">{user.full_name}</div>
            <div className="truncate text-xs font-normal">{user.email}</div>
          </DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => router.push("/account")}><User /> My account</DropdownMenuItem>
        <DropdownMenuItem onClick={() => router.push("/account/orders")}><Package /> Orders</DropdownMenuItem>
        <DropdownMenuItem onClick={() => router.push("/account/wishlist")}><Heart /> Wishlist</DropdownMenuItem>
        <DropdownMenuItem onClick={() => router.push("/nova")}><Sparkles /> GenOra Nova</DropdownMenuItem>
        {(user.seller || user.roles.includes("ADMIN")) && <DropdownMenuSeparator />}
        {user.seller && (
          <DropdownMenuItem onClick={() => router.push("/seller")}><Store /> Seller dashboard</DropdownMenuItem>
        )}
        {user.roles.includes("ADMIN") && (
          <DropdownMenuItem onClick={() => router.push("/admin")}><Shield /> Admin console</DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <ThemeToggle />
        <DropdownMenuItem
          onClick={async () => {
            await logout();
            router.push("/");
          }}
        >
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function CartButton() {
  const cart = useCart();
  const count = cart.data?.item_count ?? 0;
  return (
    <Button variant="ghost" size="icon" className="relative" render={<Link href="/cart" aria-label={`Cart, ${count} items`} />} nativeButton={false}>
      <ShoppingCart className="size-5" />
      {count > 0 && (
        <span className="absolute -right-0.5 -top-0.5 flex min-w-4.5 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold leading-4.5 text-primary-foreground">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Button>
  );
}

function CategoryMenu() {
  const { data } = useCategories();
  const router = useRouter();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" size="sm" />}>
        <LayoutDashboard /> Categories
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-64">
        {data?.map((c) => (
          <DropdownMenuItem key={c.id} onClick={() => router.push(`/products?category=${c.slug}`)}>
            <span className="flex-1">{c.name}</span>
            <span className="text-xs text-muted-foreground">{c.product_count}</span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => router.push("/categories")}>All categories</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function MobileMenu() {
  const [open, setOpen] = useState(false);
  const { data } = useCategories();
  const { status } = useAuth();
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger render={<Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu" />}>
        <Menu className="size-5" />
      </SheetTrigger>
      <SheetContent side="left" className="w-80 overflow-y-auto">
        <SheetHeader>
          <SheetTitle><Logo /></SheetTitle>
        </SheetHeader>
        <div className="space-y-6 px-4 pb-6">
          <SearchBox onDone={() => setOpen(false)} />
          <nav className="grid gap-1 text-sm">
            <Link onClick={() => setOpen(false)} href="/nova" className="flex items-center gap-2 rounded-md px-2 py-2 font-medium text-primary hover:bg-muted">
              <Sparkles className="size-4" /> Ask GenOra Nova
            </Link>
            <Link onClick={() => setOpen(false)} href="/deals" className="rounded-md px-2 py-2 hover:bg-muted">Deals & bundles</Link>
            <Link onClick={() => setOpen(false)} href="/products" className="rounded-md px-2 py-2 hover:bg-muted">All products</Link>
            {status !== "authenticated" && (
              <>
                <Link onClick={() => setOpen(false)} href="/login" className="rounded-md px-2 py-2 hover:bg-muted">Sign in</Link>
                <Link onClick={() => setOpen(false)} href="/register" className="rounded-md px-2 py-2 hover:bg-muted">Create account</Link>
              </>
            )}
          </nav>
          <div>
            <p className="mb-2 px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Categories</p>
            <nav className="grid gap-0.5 text-sm">
              {data?.map((c) => (
                <Link key={c.id} onClick={() => setOpen(false)} href={`/products?category=${c.slug}`}
                  className="flex justify-between rounded-md px-2 py-2 hover:bg-muted">
                  {c.name} <span className="text-muted-foreground">{c.product_count}</span>
                </Link>
              ))}
            </nav>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 sm:px-6">
        <MobileMenu />
        <Logo />
        <nav className="ml-2 hidden items-center gap-1 md:flex">
          <CategoryMenu />
          <Button variant="ghost" size="sm" render={<Link href="/deals" />} nativeButton={false}>Deals</Button>
        </nav>
        <div className="mx-auto hidden max-w-xl flex-1 md:block">
          <SearchBox />
        </div>
        <div className="ml-auto flex items-center gap-1 md:ml-0">
          <Button size="sm" className="bg-genora hidden text-white hover:opacity-90 sm:inline-flex" render={<Link href="/nova" />} nativeButton={false}>
            <Sparkles /> Ask Nova
          </Button>
          <Button size="icon" variant="ghost" className="sm:hidden" render={<Link href="/nova" aria-label="Ask GenOra Nova" />} nativeButton={false}>
            <Sparkles className="size-5 text-primary" />
          </Button>
          <CartButton />
          <AccountMenu />
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="mt-16 border-t bg-muted/30">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:grid-cols-2 sm:px-6 lg:grid-cols-4">
        <div className="space-y-3">
          <Logo />
          <p className="text-sm text-muted-foreground">
            An AI-powered marketplace for independent sellers. GenOra Nova helps you find, compare and negotiate.
          </p>
        </div>
        <div>
          <h3 className="mb-3 text-sm font-medium">Shop</h3>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link href="/products" className="hover:text-foreground">All products</Link></li>
            <li><Link href="/categories" className="hover:text-foreground">Categories</Link></li>
            <li><Link href="/deals" className="hover:text-foreground">Deals & bundles</Link></li>
            <li><Link href="/nova" className="hover:text-foreground">GenOra Nova</Link></li>
          </ul>
        </div>
        <div>
          <h3 className="mb-3 text-sm font-medium">Sell</h3>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link href="/register?type=seller" className="hover:text-foreground">Become a seller</Link></li>
            <li><Link href="/seller" className="hover:text-foreground">Seller dashboard</Link></li>
            <li><Link href="/seller/astra" className="hover:text-foreground">GenOra Astra</Link></li>
          </ul>
        </div>
        <div>
          <h3 className="mb-3 text-sm font-medium">Account</h3>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link href="/account/orders" className="hover:text-foreground">Orders</Link></li>
            <li><Link href="/account/wishlist" className="hover:text-foreground">Wishlist</Link></li>
            <li><Link href="/cart" className="hover:text-foreground">Cart</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t py-4 text-center text-xs text-muted-foreground">
        © {new Date().getFullYear()} GenOra. Demo marketplace with synthetic data — no real purchases are processed.
      </div>
    </footer>
  );
}
