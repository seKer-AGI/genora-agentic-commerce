"use client";

import { Loader2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

import { AgentWorkspace } from "@/components/genora/workspace";
import { useRequireAuth } from "@/lib/auth";
import { track } from "@/lib/queries";

function NovaInner() {
  const params = useSearchParams();
  const { allowed } = useRequireAuth();
  useEffect(() => {
    if (allowed) track("nova_open");
  }, [allowed]);
  if (!allowed) {
    return <div className="flex h-96 items-center justify-center"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>;
  }
  return (
    <AgentWorkspace
      agent="nova"
      initialPrompt={params.get("q")}
      title="GenOra Nova"
      subtitle="Discovery · search · comparison · photo search · bundles · offers · negotiation · reviews"
    />
  );
}

export default function NovaPage() {
  return (
    <Suspense>
      <NovaInner />
    </Suspense>
  );
}
