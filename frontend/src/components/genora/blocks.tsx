"use client";

import {
  AlertTriangle, BadgeCheck, CheckCircle2, CircleAlert, ExternalLink, Handshake, Info, Lightbulb, Package, ShieldCheck,
  ShoppingBag, Sparkles, ThumbsDown, ThumbsUp,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { ForecastChart, formatValue, KpiCard, TrendChart, type ValueFormat } from "@/components/charts/charts";
import { ProductImage, Rating } from "@/components/product/product-bits";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { dateTime, money, titleCase } from "@/lib/format";
import type { AgentBlock } from "@/lib/types";
import { cn } from "@/lib/utils";

/* eslint-disable @typescript-eslint/no-explicit-any */
type P = Record<string, any>;

function BlockShell({ icon, title, children, className }: { icon?: ReactNode; title?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-xl border bg-card p-3 sm:p-4", className)}>
      {title && <div className="mb-3 flex items-center gap-2 text-sm font-medium">{icon}{title}</div>}
      {children}
    </div>
  );
}

export function MiniProduct({ p, reasons }: { p: P; reasons?: string[] }) {
  return (
    <Link href={p.url ?? `/products/${p.slug}`} className="group flex gap-3 rounded-lg border bg-background p-2.5 transition hover:border-primary/40 hover:shadow-sm">
      <ProductImage src={p.image_url} alt={p.name} className="size-16 shrink-0 rounded-md" />
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-sm font-medium leading-snug group-hover:text-primary">{p.name}</p>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
          <span className="font-semibold">{money(p.final_price)}</span>
          {p.final_price < p.price && <span className="text-muted-foreground line-through">{money(p.price)}</span>}
          {p.rating_count > 0 && <Rating value={p.rating_avg} count={p.rating_count} />}
        </div>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {p.seller_name}{!p.in_stock && " · Out of stock"}{p.offer_name && ` · ${p.offer_name}`}
        </p>
        {reasons && reasons.length > 0 && (
          <ul className="mt-1.5 space-y-0.5">
            {reasons.slice(0, 3).map((r) => (
              <li key={r} className="flex items-start gap-1 text-xs text-primary">
                <Sparkles className="mt-0.5 size-3 shrink-0" /> {r}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Link>
  );
}

function ProductListBlock({ b }: { b: P }) {
  return (
    <BlockShell icon={<ShoppingBag className="size-4 text-primary" />} title={b.title}>
      <div className="grid gap-2 sm:grid-cols-2">
        {b.products.map((p: P) => <MiniProduct key={p.id} p={p} reasons={b.reasons?.[p.id]} />)}
      </div>
      {b.note && <p className="mt-2 text-xs text-muted-foreground">{b.note}</p>}
    </BlockShell>
  );
}

function ComparisonBlock({ b }: { b: P }) {
  return (
    <BlockShell icon={<Package className="size-4 text-primary" />} title="Comparison">
      <div className="-mx-1 overflow-x-auto">
        <table className="w-full min-w-[520px] border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 w-32 bg-card p-2 text-left text-xs font-medium text-muted-foreground" />
              {b.products.map((p: P) => (
                <th key={p.id} className="p-2 text-left align-top font-medium">
                  <Link href={p.url} className="flex items-start gap-2 hover:text-primary">
                    <ProductImage src={p.image_url} alt={p.name} className="size-10 shrink-0 rounded" />
                    <span className="line-clamp-2 text-xs leading-snug">{p.name}</span>
                  </Link>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {b.rows.map((row: P) => (
              <tr key={row.label}>
                <td className="sticky left-0 z-10 border-t bg-card p-2 text-xs font-medium text-muted-foreground">
                  {row.label}
                  {row.source === "reviews" && <span className="ml-1 text-[10px] uppercase text-amber-600">reviews</span>}
                </td>
                {row.values.map((v: string, i: number) => (
                  <td key={i} className={cn("border-t p-2 text-xs", row.highlight === i && "bg-emerald-50 font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300")}>
                    {v}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="mt-2 space-y-0.5">
        {b.notes?.map((n: string) => <li key={n} className="text-xs text-muted-foreground">{n}</li>)}
      </ul>
    </BlockShell>
  );
}

function OffersBlock({ b }: { b: P }) {
  return (
    <BlockShell icon={<BadgeCheck className="size-4 text-rose-600" />} title={b.product ? `Offers for ${b.product.name}` : "Offers"}>
      {b.offers.length === 0 ? (
        <p className="text-sm text-muted-foreground">No active offers right now.</p>
      ) : (
        <div className="space-y-2">
          {b.offers.map((o: P) => (
            <div key={o.id} className="rounded-lg border bg-background p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium">{o.name}</p>
                <Badge className="shrink-0 bg-rose-600 text-white">-{money(o.discount_per_unit)}</Badge>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">Price with offer: <b className="text-foreground">{money(o.price_after_offer)}</b></p>
              <ul className="mt-1.5 list-inside list-disc text-xs text-muted-foreground">
                {o.conditions.map((c: string) => <li key={c}>{c}</li>)}
              </ul>
            </div>
          ))}
        </div>
      )}
      {b.note && <p className="mt-2 text-xs text-muted-foreground">{b.note}</p>}
    </BlockShell>
  );
}

function ReviewBlock({ b }: { b: P }) {
  const ins = b.insights;
  return (
    <BlockShell icon={<Sparkles className="size-4 text-amber-500" />} title={`What customers say — ${b.product.name}`}>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <Rating value={ins.average_rating} size="md" />
        <span className="font-medium">{ins.average_rating}/5</span>
        <span className="text-muted-foreground">{ins.review_count} reviews · {Math.round(ins.verified_share * 100)}% verified</span>
      </div>
      <p className="mt-2 text-sm">{ins.summary}</p>
      {ins.themes?.length > 0 && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {ins.themes.map((t: P) => (
            <div key={t.theme} className="rounded-lg border bg-background p-2.5 text-xs">
              <div className="mb-1 flex items-center justify-between">
                <span className="font-medium">{t.theme}</span>
                <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium uppercase",
                  t.sentiment === "positive" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                    : t.sentiment === "negative" ? "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300" : "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300")}>
                  {t.sentiment}
                </span>
              </div>
              {t.examples_positive[0] && <p className="flex gap-1 text-muted-foreground"><ThumbsUp className="mt-0.5 size-3 shrink-0 text-emerald-600" />“{t.examples_positive[0]}”</p>}
              {t.examples_negative[0] && <p className="mt-1 flex gap-1 text-muted-foreground"><ThumbsDown className="mt-0.5 size-3 shrink-0 text-rose-600" />“{t.examples_negative[0]}”</p>}
            </div>
          ))}
        </div>
      )}
      <p className="mt-3 flex items-center gap-1 text-xs text-muted-foreground"><Info className="size-3" /> {b.disclaimer}</p>
    </BlockShell>
  );
}

function BundlesBlock({ b, onPrompt }: { b: P; onPrompt?: (t: string) => void }) {
  return (
    <BlockShell icon={<Package className="size-4 text-primary" />} title={`Goes well with ${b.product.name}`}>
      {b.bundles.map((bundle: P) => (
        <div key={bundle.id} className="mb-3 rounded-lg border border-primary/30 bg-primary/5 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-medium">{bundle.name}</p>
            <div className="text-right text-sm">
              <span className="font-semibold">{money(bundle.bundle_price)}</span>{" "}
              <span className="text-xs text-muted-foreground line-through">{money(bundle.items_total)}</span>
              <p className="text-xs text-emerald-600">You save {money(bundle.savings)}</p>
            </div>
          </div>
          {bundle.description && <p className="mt-1 text-xs text-muted-foreground">{bundle.description}</p>}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {bundle.products.map((p: P) => <Badge key={p.id} variant="outline" className="bg-background">{p.name}</Badge>)}
          </div>
          {onPrompt && bundle.available && (
            <Button size="sm" className="mt-3" onClick={() => onPrompt(`Add the ${bundle.name} bundle to my cart`)}>
              Add bundle to cart
            </Button>
          )}
        </div>
      ))}
      {b.accessories.length > 0 && (
        <>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Compatible accessories</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {b.accessories.map((p: P) => <MiniProduct key={p.id} p={p} />)}
          </div>
        </>
      )}
      {b.note && <p className="mt-2 text-xs text-muted-foreground">Compatibility: {b.note}</p>}
    </BlockShell>
  );
}

function NegotiationBlock({ b }: { b: P }) {
  const o = b.outcome;
  const tone = o.status === "accepted" ? "bg-emerald-50 dark:bg-emerald-950/40"
    : o.status === "countered" ? "bg-amber-50 dark:bg-amber-950/40" : "bg-rose-50 dark:bg-rose-950/40";
  return (
    <BlockShell icon={<Handshake className="size-4 text-primary" />} title={`Price offer — ${b.product.name}`}>
      <div className="grid grid-cols-3 gap-2 text-center text-sm">
        <div className="rounded-lg bg-muted p-2"><p className="text-xs text-muted-foreground">Listed</p><p className="font-medium">{money(o.list_price)}</p></div>
        <div className="rounded-lg bg-muted p-2"><p className="text-xs text-muted-foreground">You offered</p><p className="font-medium">{money(o.offered_price)}</p></div>
        <div className={cn("rounded-lg p-2", tone)}>
          <p className="text-xs text-muted-foreground">{o.status === "accepted" ? "Agreed" : "Counter"}</p>
          <p className="font-semibold">{money(o.agreed_price ?? o.counter_price)}</p>
        </div>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Status: <b className="capitalize text-foreground">{o.status}</b>{o.expires_at && ` · valid until ${dateTime(o.expires_at)}`}
      </p>
    </BlockShell>
  );
}

function ExternalPricesBlock({ b }: { b: P }) {
  return (
    <BlockShell icon={<ExternalLink className="size-4 text-primary" />} title="Other marketplaces">
      <div className="flex items-center justify-between rounded-lg bg-primary/5 p-2.5 text-sm">
        <span>GenOra price</span><b>{money(b.our_price)}</b>
      </div>
      {b.quotes.length > 0 ? (
        <ul className="mt-2 divide-y text-sm">
          {b.quotes.map((q: P) => (
            <li key={q.provider} className="flex items-center justify-between py-2">
              <span>
                {q.marketplace}
                {q.is_test_data && <Badge variant="outline" className="ml-2 border-amber-500 text-[10px] text-amber-700">TEST DATA</Badge>}
              </span>
              <b>{money(q.price)}</b>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 flex items-start gap-1.5 text-sm text-muted-foreground"><CircleAlert className="mt-0.5 size-4 shrink-0" /> No external price data available.</p>
      )}
      <p className="mt-2 text-xs text-muted-foreground">{b.note}</p>
    </BlockShell>
  );
}

function ConfirmationBlock({ b, onDecide, pendingId, busy }: { b: P; onDecide?: (id: string, approve: boolean) => void; pendingId?: string | null; busy?: boolean }) {
  const active = pendingId === b.action_id;
  return (
    <div className={cn("rounded-xl border-2 p-4", active ? "border-primary/50 bg-primary/5" : "border-dashed bg-muted/30")}>
      <p className="flex items-center gap-2 text-sm font-medium"><ShieldCheck className="size-4 text-primary" /> Confirmation required</p>
      <p className="mt-1 text-sm">{b.summary}</p>
      <ul className="mt-2 list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
        {b.details.map((d: string) => <li key={d}>{d}</li>)}
      </ul>
      {active && onDecide ? (
        <div className="mt-3 flex gap-2">
          <Button size="sm" disabled={busy} onClick={() => onDecide(b.action_id, true)}>
            <CheckCircle2 /> Confirm
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => onDecide(b.action_id, false)}>Cancel</Button>
        </div>
      ) : (
        <p className="mt-2 text-xs text-muted-foreground">{active ? "" : "This request is no longer pending."}</p>
      )}
    </div>
  );
}

function ImageAnalysisBlock({ b }: { b: P }) {
  const a = b.analysis;
  return (
    <BlockShell icon={<Sparkles className="size-4 text-primary" />} title="What Nova sees in your photo">
      <div className="flex flex-wrap gap-1.5 text-xs">
        <Badge>{a.product_type}</Badge>
        {a.brand && <Badge variant="outline">{a.brand}</Badge>}
        {a.colors?.map((c: string) => <Badge key={c} variant="outline">{c}</Badge>)}
        {a.materials?.map((m: string) => <Badge key={m} variant="outline">{m}</Badge>)}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">Confidence {Math.round(a.confidence * 100)}% · analysed by {a.provider}</p>
    </BlockShell>
  );
}

function KpiBlock({ b }: { b: P }) {
  return (
    <BlockShell title={b.title}>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
        {b.kpis.map((k: P) => <KpiCard key={k.label} label={k.label} value={k.value} format={k.format} change={k.change_pct} hint="vs prior" />)}
      </div>
      {b.series?.length > 0 && <TrendChart data={b.series} className="mt-3 h-48" />}
    </BlockShell>
  );
}

function TableBlock({ b }: { b: P }) {
  return (
    <BlockShell title={b.title}>
      <div className="-mx-1 overflow-x-auto">
        <table className="w-full min-w-[480px] text-xs">
          <thead>
            <tr className="text-left text-muted-foreground">
              {b.columns.map((c: P) => <th key={c.key} className="px-2 py-1.5 font-medium">{c.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {b.rows.map((r: P, i: number) => (
              <tr key={i} className="border-t">
                {b.columns.map((c: P) => {
                  const v = r[c.key];
                  const shown = v === null || v === undefined ? "—" : typeof v === "number" && c.format ? formatValue(v, c.format as ValueFormat) : String(v);
                  return <td key={c.key} className="px-2 py-1.5">{shown}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {b.note && <p className="mt-2 text-xs text-muted-foreground">{b.note}</p>}
    </BlockShell>
  );
}

function ListingDraftBlock({ b }: { b: P }) {
  const d = b.draft;
  return (
    <BlockShell icon={<Sparkles className="size-4 text-primary" />} title="Listing draft">
      <div className="space-y-2 text-sm">
        <div><p className="text-xs text-muted-foreground">Title</p><p className="font-medium">{d.title}</p></div>
        <div><p className="text-xs text-muted-foreground">Description</p><p className="whitespace-pre-line text-xs">{d.description}</p></div>
        <div><p className="text-xs text-muted-foreground">SEO description</p><p className="text-xs">{d.seo_description}</p></div>
        <div className="flex flex-wrap gap-1">{d.tags.map((t: string) => <Badge key={t} variant="secondary">{t}</Badge>)}</div>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <p><span className="text-muted-foreground">Category:</span> {d.category_suggestions?.[0]?.name ?? "—"}</p>
          <p><span className="text-muted-foreground">SKU:</span> {d.suggested_sku}</p>
          <p><span className="text-muted-foreground">Price:</span> {d.price ? money(d.price) : "not set"}</p>
          <p><span className="text-muted-foreground">Written by:</span> {b.generated_by}</p>
        </div>
        {d.warnings?.map((w: string) => <p key={w} className="flex gap-1 text-xs text-amber-700"><AlertTriangle className="mt-0.5 size-3" />{w}</p>)}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{b.note}</p>
    </BlockShell>
  );
}

function ForecastBlock({ b }: { b: P }) {
  const f = b.forecast;
  const format: ValueFormat = f.target === "revenue" ? "money" : "number";
  const bt = f.metrics?.backtest;
  return (
    <BlockShell title={`${titleCase(f.target)} forecast · ${f.horizon} days`}>
      <ForecastChart history={f.history} points={f.points} format={format} />
      <p className="mt-2 text-xs text-muted-foreground">
        Model: {f.model_name} ({f.provider}) · 80% prediction interval shaded
        {bt?.smape != null && ` · backtest sMAPE ${bt.smape}% over ${bt.holdout} days`}
      </p>
    </BlockShell>
  );
}

function RecommendationsBlock({ b, onPrompt }: { b: P; onPrompt?: (t: string) => void }) {
  const icons: Record<string, ReactNode> = {
    discount: <Lightbulb className="size-4 text-amber-500" />,
    restock: <Package className="size-4 text-rose-600" />,
  };
  return (
    <BlockShell title={b.title}>
      <div className="space-y-2">
        {b.items.map((it: P, i: number) => (
          <div key={i} className="rounded-lg border bg-background p-3">
            <p className="flex items-center gap-2 text-sm font-medium">{icons[it.action] ?? <Lightbulb className="size-4 text-primary" />}{it.title}</p>
            <p className="mt-1 text-xs">{it.rationale}</p>
            <ul className="mt-1.5 list-inside list-disc text-xs text-muted-foreground">
              {it.evidence.map((e: string) => <li key={e}>{e}</li>)}
            </ul>
            {it.proposed_percent_off && onPrompt && (
              <Button size="xs" variant="outline" className="mt-2"
                onClick={() => onPrompt(`Create a ${it.proposed_percent_off}% offer on ${it.product_name} for 14 days`)}>
                Create {it.proposed_percent_off}% offer…
              </Button>
            )}
          </div>
        ))}
      </div>
    </BlockShell>
  );
}

function NoticeBlock({ b }: { b: P }) {
  const styles: Record<string, string> = {
    info: "border-sky-300/60 bg-sky-50 text-sky-800 dark:bg-sky-950/40 dark:text-sky-200",
    warning: "border-amber-300/60 bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200",
    error: "border-rose-300/60 bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-200",
    success: "border-emerald-300/60 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200",
  };
  return <div className={cn("rounded-lg border p-3 text-sm", styles[b.level] ?? styles.info)}>{b.text}</div>;
}

export function AgentBlocks({ blocks, onPrompt, onDecide, pendingId, busy }: {
  blocks: AgentBlock[];
  onPrompt?: (text: string) => void;
  onDecide?: (id: string, approve: boolean) => void;
  pendingId?: string | null;
  busy?: boolean;
}) {
  return (
    <div className="space-y-3">
      {blocks.map((b, i) => {
        const block = b as P;
        switch (b.type) {
          case "product_list": return <ProductListBlock key={i} b={block} />;
          case "comparison": return <ComparisonBlock key={i} b={block} />;
          case "offers": return <OffersBlock key={i} b={block} />;
          case "review_summary": return <ReviewBlock key={i} b={block} />;
          case "bundles": return <BundlesBlock key={i} b={block} onPrompt={onPrompt} />;
          case "negotiation": return <NegotiationBlock key={i} b={block} />;
          case "external_prices": return <ExternalPricesBlock key={i} b={block} />;
          case "confirmation": return <ConfirmationBlock key={i} b={block} onDecide={onDecide} pendingId={pendingId} busy={busy} />;
          case "image_analysis": return <ImageAnalysisBlock key={i} b={block} />;
          case "kpis": return <KpiBlock key={i} b={block} />;
          case "table": return <TableBlock key={i} b={block} />;
          case "listing_draft": return <ListingDraftBlock key={i} b={block} />;
          case "forecast": return <ForecastBlock key={i} b={block} />;
          case "recommendations": return <RecommendationsBlock key={i} b={block} onPrompt={onPrompt} />;
          case "notice": return <NoticeBlock key={i} b={block} />;
          default: return null;
        }
      })}
    </div>
  );
}
