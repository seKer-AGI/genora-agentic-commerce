"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

import { AgentWorkspace } from "@/components/genora/workspace";
import { track } from "@/lib/queries";

function AstraInner() {
  const params = useSearchParams();
  useEffect(() => track("astra_open"), []);
  return (
    <div className="-mt-0 lg:[&>div]:h-dvh">
      <AgentWorkspace
        agent="astra"
        initialPrompt={params.get("q")}
        title="GenOra Astra"
        subtitle="Listings · inventory · sales analytics · product performance · pricing strategy · forecasts"
      />
    </div>
  );
}

export default function AstraPage() {
  return <Suspense><AstraInner /></Suspense>;
}
