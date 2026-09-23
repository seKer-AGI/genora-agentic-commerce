"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ErrorState, PageHeader } from "@/components/common/states";
import { DashboardPage } from "@/components/layout/dashboard-shell";
import { ProductStatusBadge } from "@/components/product/product-bits";
import { ProductForm } from "@/components/seller/product-form";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { ProductDetail } from "@/lib/types";

export default function EditProductPage() {
  const { id } = useParams<{ id: string }>();
  const q = useQuery({ queryKey: ["seller-product", id], queryFn: () => api<ProductDetail>(`/products/${id}`) });
  return (
    <DashboardPage>
      {q.isLoading ? <Skeleton className="h-96" /> : q.error || !q.data ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
        <>
          <PageHeader title={q.data.name} description={<span className="flex items-center gap-2">SKU {q.data.sku} <ProductStatusBadge status={q.data.status} /></span>}
            actions={q.data.status === "active" && (
              <Button variant="outline" render={<Link href={`/products/${q.data.slug}`} target="_blank" />} nativeButton={false}><ExternalLink /> View in store</Button>
            )} />
          <ProductForm product={q.data} />
        </>
      )}
    </DashboardPage>
  );
}
