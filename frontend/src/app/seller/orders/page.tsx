"use client";

import { OrdersTable } from "@/components/commerce/orders-table";
import { PageHeader } from "@/components/common/states";
import { DashboardPage } from "@/components/layout/dashboard-shell";

export default function SellerOrdersPage() {
  return (
    <DashboardPage>
      <PageHeader title="Orders" description="Confirm, process and ship your orders. Every status change is audited and the buyer is notified." />
      <OrdersTable endpoint="/sellers/me/orders" detailBase="/seller/orders" queryKey="seller-orders" />
    </DashboardPage>
  );
}
