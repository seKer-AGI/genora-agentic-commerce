"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/common/states";
import { DashboardPage } from "@/components/layout/dashboard-shell";
import { ProductForm } from "@/components/seller/product-form";
import { Button } from "@/components/ui/button";

export default function NewProductPage() {
  const prompt = "Create a product listing for ";
  return (
    <DashboardPage>
      <PageHeader title="New product" description="Add a product to your catalog. Save as draft until you're ready to publish."
        actions={<Button variant="outline" render={<Link href={`/seller/astra?q=${encodeURIComponent(prompt)}`} />} nativeButton={false}>
          <Sparkles /> Draft with Astra
        </Button>} />
      <ProductForm />
    </DashboardPage>
  );
}
