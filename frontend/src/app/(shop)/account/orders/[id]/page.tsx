"use client";

import { useParams } from "next/navigation";

import { OrderDetail } from "@/components/commerce/order-detail";

export default function AccountOrderPage() {
  const { id } = useParams<{ id: string }>();
  return <OrderDetail orderId={id} backHref="/account/orders" backLabel="All orders" />;
}
