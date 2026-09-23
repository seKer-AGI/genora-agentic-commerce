"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Loader2, Plus, Trash2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";
import { toast } from "sonner";

import { ProductImage } from "@/components/product/product-bits";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, errorMessage } from "@/lib/api";
import { flattenCategories, useCategories } from "@/lib/queries";
import type { ProductDetail } from "@/lib/types";

type Attr = { key: string; value: string };

function parseValue(v: string): unknown {
  const t = v.trim();
  if (t === "true" || t === "false") return t === "true";
  if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t);
  if (t.includes(",")) return t.split(",").map((x) => x.trim()).filter(Boolean);
  return t;
}

export function ProductForm({ product }: { product?: ProductDetail }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: cats } = useCategories();
  const flat = flattenCategories(cats);
  const fileRef = useRef<HTMLInputElement>(null);
  const [f, setF] = useState({
    name: product?.name ?? "", sku: product?.sku ?? "", brand: product?.brand ?? "",
    category_id: product?.category?.id ?? "", price: product ? String(product.price) : "",
    sale_price: product?.sale_price != null ? String(product.sale_price) : "", stock: "0",
    description: product?.description ?? "", seo_description: product?.seo_description ?? "",
    tags: product?.tags.join(", ") ?? "", status: product?.status ?? "draft",
  });
  const [attrs, setAttrs] = useState<Attr[]>(
    Object.entries(product?.attributes ?? {}).map(([key, v]) => ({ key, value: Array.isArray(v) ? v.join(", ") : String(v) })),
  );
  const [images, setImages] = useState<string[]>(product?.images.map((i) => i.url) ?? []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [uploading, setUploading] = useState(false);

  const upload = async (file: File) => {
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api<{ url: string }>("/media/upload", { method: "POST", form });
      setImages((x) => [...x, r.url]);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setUploading(false);
    }
  };

  const save = useMutation({
    mutationFn: async () => {
      const attributes = Object.fromEntries(attrs.filter((a) => a.key.trim()).map((a) => [a.key.trim().toLowerCase().replace(/\s+/g, "_"), parseValue(a.value)]));
      const body: Record<string, unknown> = {
        name: f.name, sku: f.sku, brand: f.brand || null, category_id: f.category_id || null, price: f.price,
        description: f.description, seo_description: f.seo_description || null,
        tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean), attributes, images, status: f.status,
      };
      if (product) {
        if (f.sale_price) body.sale_price = f.sale_price;
        else if (product.sale_price != null) body.clear_sale_price = true;
        return api<ProductDetail>(`/products/${product.id}`, { method: "PATCH", body });
      }
      if (f.sale_price) body.sale_price = f.sale_price;
      body.stock = Number(f.stock) || 0;
      return api<ProductDetail>("/products", { method: "POST", body });
    },
    onSuccess: (p) => {
      toast.success(product ? "Product saved" : "Product created");
      qc.invalidateQueries({ queryKey: ["seller-products"] });
      qc.invalidateQueries({ queryKey: ["seller-product", p.id] });
      router.push("/seller/products");
    },
    onError: (e) => {
      if (e instanceof ApiError && Array.isArray(e.details)) {
        setErrors(Object.fromEntries((e.details as { field: string; message: string }[]).map((d) => [d.field, d.message])));
      }
      toast.error(errorMessage(e));
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (f.name.trim().length < 3) errs.name = "At least 3 characters";
    if (!/^[A-Za-z0-9._-]+$/.test(f.sku)) errs.sku = "Letters, digits, dot, dash or underscore";
    if (!(Number(f.price) > 0)) errs.price = "Enter a price";
    if (f.sale_price && Number(f.sale_price) > Number(f.price)) errs.sale_price = "Must not exceed the price";
    if (f.description.trim().length < 10) errs.description = "At least 10 characters";
    setErrors(errs);
    if (Object.keys(errs).length === 0) save.mutate();
  };

  const field = (k: keyof typeof f, label: string, props: React.ComponentProps<typeof Input> = {}) => (
    <div className="space-y-1.5">
      <Label htmlFor={k}>{label}</Label>
      <Input id={k} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} aria-invalid={!!errors[k]} {...props} />
      {errors[k] && <p className="text-xs text-destructive">{errors[k]}</p>}
    </div>
  );

  return (
    <form onSubmit={submit} className="grid gap-6 lg:grid-cols-[1fr_320px]" noValidate>
      <div className="space-y-6">
        <Card>
          <CardHeader><CardTitle className="text-base">Details</CardTitle></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">{field("name", "Product name")}</div>
            {field("sku", "SKU")}
            {field("brand", "Brand")}
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="description">Description</Label>
              <Textarea id="description" rows={6} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} aria-invalid={!!errors.description} />
              {errors.description && <p className="text-xs text-destructive">{errors.description}</p>}
            </div>
            <div className="sm:col-span-2">{field("seo_description", "SEO description (max 320 characters)", { maxLength: 320 })}</div>
            <div className="sm:col-span-2">{field("tags", "Tags (comma separated)")}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Specifications</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {attrs.map((a, i) => (
              <div key={i} className="flex gap-2">
                <Input placeholder="e.g. ram_gb" value={a.key} onChange={(e) => setAttrs(attrs.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))} />
                <Input placeholder="e.g. 16" value={a.value} onChange={(e) => setAttrs(attrs.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
                <Button type="button" variant="ghost" size="icon" aria-label="Remove attribute" onClick={() => setAttrs(attrs.filter((_, j) => j !== i))}><Trash2 /></Button>
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" onClick={() => setAttrs([...attrs, { key: "", value: "" }])}><Plus /> Add specification</Button>
            <p className="text-xs text-muted-foreground">Accurate specifications power search filters, GenOra comparisons and compatibility checks.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Images</CardTitle></CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {images.map((url, i) => (
                <div key={url} className="relative">
                  <ProductImage src={url} alt="" className="size-24 rounded-lg border" />
                  {i === 0 && <span className="absolute bottom-1 left-1 rounded bg-background/90 px-1 text-[10px]">Primary</span>}
                  <button type="button" aria-label="Remove image" onClick={() => setImages(images.filter((x) => x !== url))}
                    className="absolute -right-2 -top-2 rounded-full border bg-background p-0.5"><X className="size-3" /></button>
                </div>
              ))}
              <button type="button" onClick={() => fileRef.current?.click()} disabled={uploading || images.length >= 10}
                className="flex size-24 flex-col items-center justify-center gap-1 rounded-lg border border-dashed text-xs text-muted-foreground hover:bg-muted">
                {uploading ? <Loader2 className="size-5 animate-spin" /> : <ImagePlus className="size-5" />} Upload
              </button>
              <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
                onChange={(e) => { const file = e.target.files?.[0]; if (file) upload(file); e.target.value = ""; }} />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">JPEG, PNG or WebP up to 8 MB. Products without photos get generated artwork.</p>
          </CardContent>
        </Card>
      </div>
      <div className="space-y-6">
        <Card>
          <CardHeader><CardTitle className="text-base">Pricing & stock</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {field("price", "Price (USD)", { inputMode: "decimal" })}
            {field("sale_price", "Sale price (optional)", { inputMode: "decimal" })}
            {!product && field("stock", "Initial stock", { inputMode: "numeric" })}
            {product && <p className="text-xs text-muted-foreground">Manage stock on the Inventory page.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Organisation</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label>Category</Label>
              <Select value={f.category_id} items={Object.fromEntries(flat.map((c) => [c.id, c.name]))} onValueChange={(v) => setF({ ...f, category_id: (v as string) ?? "" })}>
                <SelectTrigger className="w-full"><SelectValue placeholder="Choose a category" /></SelectTrigger>
                <SelectContent>
                  {flat.map((c) => <SelectItem key={c.id} value={c.id}><span style={{ paddingLeft: c.depth * 12 }}>{c.name}</span></SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Status</Label>
              <Select value={f.status} items={{ draft: "Draft", active: "Active", archived: "Archived" }} onValueChange={(v) => setF({ ...f, status: v as string })}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  {product && <SelectItem value="archived">Archived</SelectItem>}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>
        <div className="flex gap-2">
          <Button type="submit" className="flex-1" disabled={save.isPending}>{save.isPending && <Loader2 className="animate-spin" />} {product ? "Save changes" : "Create product"}</Button>
          <Button type="button" variant="outline" onClick={() => router.back()}>Cancel</Button>
        </div>
      </div>
    </form>
  );
}
