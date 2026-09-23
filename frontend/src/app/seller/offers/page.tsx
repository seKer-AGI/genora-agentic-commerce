"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, PageHeader, TableSkeleton } from "@/components/common/states";
import { DashboardPage } from "@/components/layout/dashboard-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, errorMessage } from "@/lib/api";
import { date, dateTime, money } from "@/lib/format";
import type { Bundle, Coupon, Negotiation, OfferOut, Page, ProductCard } from "@/lib/types";

const useOwnProducts = () =>
  useQuery({ queryKey: ["seller-products", "all-active"], queryFn: () => api<Page<ProductCard>>("/sellers/me/products", { query: { page_size: 100, status: "active" } }) });

function DiscountFields({ state, setState }: { state: { discount_type: string; value: string }; setState: (s: { discount_type: string; value: string }) => void }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="space-y-1.5">
        <Label>Type</Label>
        <Select value={state.discount_type} items={{ percentage: "Percentage", fixed: "Fixed amount" }} onValueChange={(v) => setState({ ...state, discount_type: v as string })}>
          <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="percentage">Percentage</SelectItem><SelectItem value="fixed">Fixed amount</SelectItem></SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label>{state.discount_type === "percentage" ? "Percent off (max 90)" : "Amount off (USD)"}</Label>
        <Input inputMode="decimal" value={state.value} onChange={(e) => setState({ ...state, value: e.target.value })} />
      </div>
    </div>
  );
}

function NewOffer() {
  const qc = useQueryClient();
  const products = useOwnProducts();
  const [open, setOpen] = useState(false);
  const [d, setD] = useState({ discount_type: "percentage", value: "10" });
  const [f, setF] = useState({ name: "", product_id: "", days: "14", min_quantity: "1" });
  const create = useMutation({
    mutationFn: () => api<OfferOut>("/offers", {
      method: "POST",
      body: {
        name: f.name, discount_type: d.discount_type, value: d.value, product_id: f.product_id || null,
        min_quantity: Number(f.min_quantity) || 1, starts_at: new Date().toISOString(),
        ends_at: new Date(Date.now() + Number(f.days) * 86400000).toISOString(),
      },
    }),
    onSuccess: () => { toast.success("Offer created"); qc.invalidateQueries({ queryKey: ["seller-offers"] }); setOpen(false); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}><Plus /> New offer</DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>New offer</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>Name</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Autumn keyboard sale" /></div>
          <div className="space-y-1.5">
            <Label>Applies to</Label>
            <Select value={f.product_id} items={{ "": "All my products", ...Object.fromEntries((products.data?.items ?? []).map((p) => [p.id, p.name])) }}
              onValueChange={(v) => setF({ ...f, product_id: (v as string) ?? "" })}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="">All my products</SelectItem>
                {products.data?.items.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <DiscountFields state={d} setState={setD} />
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Duration (days)</Label><Input inputMode="numeric" value={f.days} onChange={(e) => setF({ ...f, days: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Minimum quantity</Label><Input inputMode="numeric" value={f.min_quantity} onChange={(e) => setF({ ...f, min_quantity: e.target.value })} /></div>
          </div>
          <Button className="w-full" disabled={create.isPending || f.name.length < 3 || !Number(d.value)} onClick={() => create.mutate()}>Create offer</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function OffersTab() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["seller-offers"], queryFn: () => api<OfferOut[]>("/sellers/me/offers") });
  const toggle = useMutation({
    mutationFn: (o: OfferOut) => api(`/offers/${o.id}`, { method: "PATCH", body: { is_active: !o.is_active } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["seller-offers"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/offers/${id}`, { method: "DELETE" }),
    onSuccess: () => { toast.success("Offer deleted"); qc.invalidateQueries({ queryKey: ["seller-offers"] }); },
  });
  return (
    <div className="space-y-3">
      <div className="flex justify-end"><NewOffer /></div>
      {q.isLoading ? <TableSkeleton /> : !q.data?.length ? <EmptyState title="No offers yet" /> : (
        <div className="overflow-x-auto rounded-xl border">
          <Table>
            <TableHeader><TableRow><TableHead>Offer</TableHead><TableHead>Scope</TableHead><TableHead>Discount</TableHead><TableHead>Window</TableHead><TableHead>Status</TableHead><TableHead>Active</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {q.data.map((o) => (
                <TableRow key={o.id}>
                  <TableCell><p className="font-medium">{o.name}</p><p className="text-xs text-muted-foreground">{o.product_name ?? "All products"}{o.min_quantity > 1 && ` · min ${o.min_quantity}`}</p></TableCell>
                  <TableCell className="capitalize">{o.scope}</TableCell>
                  <TableCell>{o.discount_type === "percentage" ? `${o.value}%` : money(o.value)}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{date(o.starts_at)} – {o.ends_at ? date(o.ends_at) : "open"}</TableCell>
                  <TableCell><Badge variant={o.status === "active" ? "default" : "secondary"} className="capitalize">{o.status}</Badge></TableCell>
                  <TableCell><Switch checked={o.is_active} onCheckedChange={() => toggle.mutate(o)} aria-label="Toggle offer" /></TableCell>
                  <TableCell><Button variant="ghost" size="icon-sm" aria-label="Delete offer" onClick={() => remove.mutate(o.id)}><Trash2 /></Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}

function CouponsTab() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["seller-coupons"], queryFn: () => api<Coupon[]>("/offers/coupons") });
  const [d, setD] = useState({ discount_type: "percentage", value: "10" });
  const [code, setCode] = useState("");
  const [minSubtotal, setMinSubtotal] = useState("0");
  const create = useMutation({
    mutationFn: () => api<Coupon>("/offers/coupons", { method: "POST", body: { code, ...d, min_subtotal: minSubtotal || "0", per_user_limit: 1 } }),
    onSuccess: () => { toast.success("Coupon created"); setCode(""); qc.invalidateQueries({ queryKey: ["seller-coupons"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/offers/coupons/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["seller-coupons"] }),
  });
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div>
        {q.isLoading ? <TableSkeleton /> : !q.data?.length ? <EmptyState title="No coupons yet" /> : (
          <div className="overflow-x-auto rounded-xl border">
            <Table>
              <TableHeader><TableRow><TableHead>Code</TableHead><TableHead>Discount</TableHead><TableHead>Min. spend</TableHead><TableHead>Used</TableHead><TableHead /></TableRow></TableHeader>
              <TableBody>
                {q.data.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="font-mono font-medium">{c.code}</TableCell>
                    <TableCell>{c.discount_type === "percentage" ? `${c.value}%` : money(c.value)}</TableCell>
                    <TableCell>{money(c.min_subtotal)}</TableCell>
                    <TableCell>{c.used_count}{c.usage_limit ? ` / ${c.usage_limit}` : ""}</TableCell>
                    <TableCell><Button variant="ghost" size="icon-sm" aria-label="Delete coupon" onClick={() => remove.mutate(c.id)}><Trash2 /></Button></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
      <div className="space-y-3 rounded-xl border p-4">
        <p className="font-medium">New coupon</p>
        <div className="space-y-1.5"><Label>Code</Label><Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ""))} placeholder="SAVE10" /></div>
        <DiscountFields state={d} setState={setD} />
        <div className="space-y-1.5"><Label>Minimum spend (USD)</Label><Input inputMode="decimal" value={minSubtotal} onChange={(e) => setMinSubtotal(e.target.value)} /></div>
        <Button className="w-full" disabled={code.length < 3 || create.isPending} onClick={() => create.mutate()}>Create coupon</Button>
      </div>
    </div>
  );
}

function BundlesTab() {
  const qc = useQueryClient();
  const products = useOwnProducts();
  const q = useQuery({ queryKey: ["seller-bundles"], queryFn: () => api<Bundle[]>("/sellers/me/bundles") });
  const [name, setName] = useState("");
  const [d, setD] = useState({ discount_type: "percentage", value: "10" });
  const [selected, setSelected] = useState<string[]>([]);
  const create = useMutation({
    mutationFn: () => api<Bundle>("/bundles", { method: "POST", body: { name, ...d, product_ids: selected } }),
    onSuccess: () => { toast.success("Bundle created"); setName(""); setSelected([]); qc.invalidateQueries({ queryKey: ["seller-bundles"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/bundles/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["seller-bundles"] }),
  });
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="space-y-3">
        {q.isLoading ? <TableSkeleton /> : !q.data?.length ? <EmptyState title="No bundles yet" /> : q.data.map((b) => (
          <div key={b.id} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border p-4">
            <div>
              <p className="font-medium">{b.name} {!b.available && <Badge variant="secondary">Unavailable</Badge>}</p>
              <p className="text-xs text-muted-foreground">{b.products.map((p) => p.name).join(" + ")}</p>
            </div>
            <div className="flex items-center gap-3 text-right text-sm">
              <span>{money(b.bundle_price)}<span className="block text-xs text-emerald-600">save {money(b.savings)}</span></span>
              <Button variant="ghost" size="icon-sm" aria-label="Delete bundle" onClick={() => remove.mutate(b.id)}><Trash2 /></Button>
            </div>
          </div>
        ))}
      </div>
      <div className="space-y-3 rounded-xl border p-4">
        <p className="font-medium">New bundle</p>
        <div className="space-y-1.5"><Label>Name</Label><Input value={name} onChange={(e) => setName(e.target.value)} /></div>
        <DiscountFields state={d} setState={setD} />
        <div className="max-h-56 space-y-1 overflow-y-auto rounded-lg border p-2">
          {products.data?.items.map((p) => (
            <label key={p.id} className="flex cursor-pointer items-center gap-2 text-sm">
              <Checkbox checked={selected.includes(p.id)} onCheckedChange={(v) => setSelected(v ? [...selected, p.id] : selected.filter((x) => x !== p.id))} />
              <span className="truncate">{p.name}</span>
            </label>
          ))}
        </div>
        <Button className="w-full" disabled={name.length < 3 || selected.length < 2 || create.isPending} onClick={() => create.mutate()}>
          Create bundle ({selected.length} products)
        </Button>
      </div>
    </div>
  );
}

function NegotiationTab() {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["negotiation-rules"], queryFn: () => api<{ id: string; product_id: string | null; product_name: string | null; is_enabled: boolean; max_discount_percent: number; auto_accept_percent: number }[]>("/sellers/me/negotiation-rules") });
  const received = useQuery({ queryKey: ["seller-negotiations"], queryFn: () => api<Negotiation[]>("/sellers/me/negotiations") });
  const def = rules.data?.find((r) => r.product_id === null);
  const [maxPct, setMaxPct] = useState<string | null>(null);
  const [autoPct, setAutoPct] = useState<string | null>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const save = useMutation({
    mutationFn: () => api("/sellers/me/negotiation-rules", {
      method: "PUT",
      body: { product_id: null, is_enabled: enabled ?? def?.is_enabled ?? false, max_discount_percent: maxPct ?? def?.max_discount_percent ?? 10, auto_accept_percent: autoPct ?? def?.auto_accept_percent ?? 5 },
    }),
    onSuccess: () => { toast.success("Negotiation rules saved"); qc.invalidateQueries({ queryKey: ["negotiation-rules"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
      <div className="space-y-3 rounded-xl border p-4">
        <p className="font-medium">Store-wide negotiation rules</p>
        <p className="text-xs text-muted-foreground">Buyers (and GenOra Nova on their behalf) can send offers. Your rules decide instantly — your floor price is never revealed.</p>
        <label className="flex items-center justify-between text-sm">Accept price offers <Switch checked={enabled ?? def?.is_enabled ?? false} onCheckedChange={setEnabled} /></label>
        <div className="space-y-1.5"><Label>Maximum discount (%)</Label><Input inputMode="decimal" value={maxPct ?? String(def?.max_discount_percent ?? 10)} onChange={(e) => setMaxPct(e.target.value)} /></div>
        <div className="space-y-1.5"><Label>Auto-accept up to (%)</Label><Input inputMode="decimal" value={autoPct ?? String(def?.auto_accept_percent ?? 5)} onChange={(e) => setAutoPct(e.target.value)} /></div>
        <Button className="w-full" onClick={() => save.mutate()} disabled={save.isPending}>Save rules</Button>
        {rules.data?.filter((r) => r.product_id).map((r) => (
          <p key={r.id} className="text-xs text-muted-foreground">Override · {r.product_name}: {r.is_enabled ? `max ${r.max_discount_percent}%, auto ${r.auto_accept_percent}%` : "not negotiable"}</p>
        ))}
      </div>
      <div>
        <p className="mb-2 font-medium">Offers received</p>
        {received.isLoading ? <TableSkeleton /> : !received.data?.length ? <EmptyState title="No offers received yet" /> : (
          <div className="overflow-x-auto rounded-xl border">
            <Table>
              <TableHeader><TableRow><TableHead>Product</TableHead><TableHead className="text-right">List</TableHead><TableHead className="text-right">Offered</TableHead><TableHead className="text-right">Result</TableHead><TableHead>Status</TableHead><TableHead>When</TableHead></TableRow></TableHeader>
              <TableBody>
                {received.data.map((n) => (
                  <TableRow key={n.id}>
                    <TableCell className="max-w-48 truncate">{n.product_name}</TableCell>
                    <TableCell className="text-right">{money(n.list_price)}</TableCell>
                    <TableCell className="text-right">{money(n.offered_price)}</TableCell>
                    <TableCell className="text-right">{money(n.agreed_price ?? n.counter_price)}</TableCell>
                    <TableCell><Badge variant="secondary" className="capitalize">{n.status}</Badge></TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{dateTime(n.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}

export default function SellerOffersPage() {
  return (
    <DashboardPage>
      <PageHeader title="Offers & pricing" description="Automatic offers, coupon codes, bundles and negotiation rules." />
      <Tabs defaultValue="offers">
        <TabsList><TabsTrigger value="offers">Offers</TabsTrigger><TabsTrigger value="coupons">Coupons</TabsTrigger><TabsTrigger value="bundles">Bundles</TabsTrigger><TabsTrigger value="negotiation">Negotiation</TabsTrigger></TabsList>
        <TabsContent value="offers" className="pt-4"><OffersTab /></TabsContent>
        <TabsContent value="coupons" className="pt-4"><CouponsTab /></TabsContent>
        <TabsContent value="bundles" className="pt-4"><BundlesTab /></TabsContent>
        <TabsContent value="negotiation" className="pt-4"><NegotiationTab /></TabsContent>
      </Tabs>
    </DashboardPage>
  );
}
