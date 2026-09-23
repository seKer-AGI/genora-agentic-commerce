"use client";

import { useParams } from "next/navigation";

import { OrderDetail } from "@/components/commerce/order-detail";
import { DashboardPage } from "@/components/layout/dashboard-shell";

export default function SellerOrderPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <DashboardPage>
      <OrderDetail orderId={id} backHref="/seller/orders" backLabel="All orders" />
    </DashboardPage>
  );
}
