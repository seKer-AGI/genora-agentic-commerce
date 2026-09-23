"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Trash2 } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { EmptyState, TableSkeleton } from "@/components/common/states";
import { Rating } from "@/components/product/product-bits";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, errorMessage } from "@/lib/api";
import { date } from "@/lib/format";
import type { Review } from "@/lib/types";

export default function MyReviewsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["my-reviews"], queryFn: () => api<Review[]>("/reviews/mine") });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/reviews/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Review deleted");
      qc.invalidateQueries({ queryKey: ["my-reviews"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">My reviews</h2>
      {q.isLoading ? <TableSkeleton /> : !q.data?.length ? (
        <EmptyState icon={MessageSquare} title="No reviews yet" description="You can review products from delivered orders." />
      ) : (
        <ul className="space-y-3">
          {q.data.map((r) => (
            <li key={r.id} className="rounded-xl border p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Link href={`/products/${r.product_id}`} className="font-medium hover:underline">{r.product_name}</Link>
                <Badge variant="secondary" className="capitalize">{r.status}</Badge>
              </div>
              <div className="mt-1 flex items-center gap-2"><Rating value={r.rating} /><span className="text-xs text-muted-foreground">{date(r.created_at)}</span></div>
              {r.title && <p className="mt-2 text-sm font-medium">{r.title}</p>}
              <p className="mt-1 text-sm text-muted-foreground">{r.body}</p>
              <Button variant="ghost" size="xs" className="mt-2 text-muted-foreground" onClick={() => remove.mutate(r.id)}>
                <Trash2 /> Delete
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
