"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Info, Star, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/states";
import { Rating } from "@/components/product/product-bits";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date } from "@/lib/format";
import type { Page, ProductDetail, Review, ReviewSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

const SORTS = { newest: "Newest", helpful: "Most helpful", highest: "Highest rating", lowest: "Lowest rating" };

function WriteReview({ product }: { product: ProductDetail }) {
  const qc = useQueryClient();
  const { status } = useAuth();
  const [rating, setRating] = useState(5);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const elig = useQuery({
    queryKey: ["review-eligibility", product.id],
    queryFn: () => api<{ can_review: boolean; reason: string | null }>(`/products/${product.id}/reviews/eligibility`),
    enabled: status === "authenticated",
  });
  const submit = useMutation({
    mutationFn: () => api<Review>(`/products/${product.id}/reviews`, { method: "POST", body: { rating, title: title || null, body } }),
    onSuccess: (r) => {
      toast.success(r.status === "approved" ? "Thanks! Your review is live." : "Thanks! Your review is awaiting moderation.");
      qc.invalidateQueries({ queryKey: ["reviews", product.id] });
      qc.invalidateQueries({ queryKey: ["review-eligibility", product.id] });
      qc.invalidateQueries({ queryKey: ["product"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (status !== "authenticated" || !elig.data) return null;
  if (!elig.data.can_review) return <p className="rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">{elig.data.reason}</p>;
  return (
    <form className="space-y-3 rounded-xl border p-4" onSubmit={(e) => { e.preventDefault(); submit.mutate(); }}>
      <p className="text-sm font-medium">Write a review <span className="text-xs font-normal text-muted-foreground">(verified purchase)</span></p>
      <div className="flex gap-1" role="radiogroup" aria-label="Rating">
        {[1, 2, 3, 4, 5].map((i) => (
          <button key={i} type="button" role="radio" aria-checked={rating === i} aria-label={`${i} stars`} onClick={() => setRating(i)}>
            <Star className={cn("size-6", i <= rating ? "fill-amber-400 text-amber-400" : "text-muted-foreground/40")} />
          </button>
        ))}
      </div>
      <Input placeholder="Title (optional)" value={title} maxLength={160} onChange={(e) => setTitle(e.target.value)} />
      <Textarea placeholder="What did you like or dislike? (min. 10 characters)" value={body} maxLength={5000} onChange={(e) => setBody(e.target.value)} />
      <Button type="submit" size="sm" disabled={body.trim().length < 10 || submit.isPending}>Submit review</Button>
    </form>
  );
}

export function ProductReviews({ product }: { product: ProductDetail }) {
  const qc = useQueryClient();
  const [sort, setSort] = useState<keyof typeof SORTS>("newest");
  const [ratingFilter, setRatingFilter] = useState<number | null>(null);
  const summary = useQuery({ queryKey: ["review-summary", product.id], queryFn: () => api<ReviewSummary>(`/products/${product.id}/reviews/summary`) });
  const list = useQuery({
    queryKey: ["reviews", product.id, sort, ratingFilter],
    queryFn: () => api<Page<Review>>(`/products/${product.id}/reviews`, { query: { sort, rating: ratingFilter, page_size: 20 } }),
  });
  const helpful = useMutation({
    mutationFn: (id: string) => api(`/reviews/${id}/helpful`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reviews", product.id] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const s = summary.data;
  const total = s?.rating.count ?? 0;

  return (
    <div className="grid gap-8 lg:grid-cols-[320px_1fr]">
      <div className="space-y-5">
        {summary.isLoading ? <Skeleton className="h-48" /> : s && (
          <>
            <div>
              <p className="text-4xl font-semibold">{s.rating.average.toFixed(1)}</p>
              <Rating value={s.rating.average} size="md" />
              <p className="mt-1 text-xs text-muted-foreground">{total} verified reviews</p>
            </div>
            <div className="space-y-1.5">
              {[5, 4, 3, 2, 1].map((r) => {
                const n = s.rating.distribution[String(r)] ?? 0;
                return (
                  <button key={r} onClick={() => setRatingFilter(ratingFilter === r ? null : r)}
                    className={cn("flex w-full items-center gap-2 rounded text-xs", ratingFilter === r && "font-semibold text-primary")}>
                    <span className="w-6">{r}★</span>
                    <Progress value={total ? (n / total) * 100 : 0} className="h-2 flex-1" />
                    <span className="w-6 text-right text-muted-foreground">{n}</span>
                  </button>
                );
              })}
            </div>
            {s.insights.review_count > 0 && (
              <div className="rounded-xl border bg-muted/30 p-4">
                <p className="mb-1 text-sm font-medium">Review highlights</p>
                <p className="text-xs leading-relaxed">{s.insights.summary}</p>
                <div className="mt-3 space-y-1.5 text-xs">
                  {s.insights.top_positive.map((t) => <p key={t} className="flex items-center gap-1.5"><ThumbsUp className="size-3 text-emerald-600" /> {t}</p>)}
                  {s.insights.top_negative.map((t) => <p key={t} className="flex items-center gap-1.5"><ThumbsDown className="size-3 text-rose-600" /> {t}</p>)}
                </div>
                <p className="mt-3 flex gap-1 text-[11px] text-muted-foreground"><Info className="mt-0.5 size-3 shrink-0" /> {s.disclaimer}</p>
              </div>
            )}
          </>
        )}
        <WriteReview product={product} />
      </div>
      <div>
        <div className="mb-4 flex items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">{list.data ? `${list.data.total} reviews${ratingFilter ? ` with ${ratingFilter}★` : ""}` : ""}</p>
          <Select value={sort} items={SORTS} onValueChange={(v) => setSort(v as keyof typeof SORTS)}>
            <SelectTrigger size="sm" className="w-40" aria-label="Sort reviews"><SelectValue /></SelectTrigger>
            <SelectContent>{Object.entries(SORTS).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        {list.isLoading ? <Skeleton className="h-64" /> : list.data?.items.length === 0 ? (
          <EmptyState title="No reviews yet" description="Customers who receive this product can review it." />
        ) : (
          <ul className="divide-y">
            {list.data?.items.map((r) => (
              <li key={r.id} className="py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Rating value={r.rating} />
                  {r.title && <span className="text-sm font-medium">{r.title}</span>}
                </div>
                <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                  {r.author_name} · {date(r.created_at)}
                  {r.is_verified_purchase && <span className="flex items-center gap-0.5 text-emerald-600"><BadgeCheck className="size-3" /> Verified purchase</span>}
                </p>
                <p className="mt-2 text-sm leading-relaxed">{r.body}</p>
                <Button variant="ghost" size="xs" className="mt-1 text-muted-foreground" onClick={() => helpful.mutate(r.id)}>
                  <ThumbsUp /> Helpful ({r.helpful_count})
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
