"use client";

import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { api, errorMessage } from "@/lib/api";

function Verify() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<"loading" | "ok" | "error">(token ? "loading" : "error");
  const [message, setMessage] = useState(token ? "" : "This verification link is missing its token.");

  useEffect(() => {
    if (!token) return;
    api("/auth/verify-email", { method: "POST", body: { token } })
      .then(() => setState("ok"))
      .catch((e) => {
        setState("error");
        setMessage(errorMessage(e));
      });
  }, [token]);

  return (
    <div className="text-center">
      {state === "loading" && <Loader2 className="mx-auto size-10 animate-spin text-muted-foreground" />}
      {state === "ok" && <CheckCircle2 className="mx-auto size-10 text-emerald-600" />}
      {state === "error" && <XCircle className="mx-auto size-10 text-destructive" />}
      <h1 className="mt-3 text-xl font-semibold">
        {state === "loading" ? "Verifying…" : state === "ok" ? "E-mail verified" : "Verification failed"}
      </h1>
      {message && <p className="mt-2 text-sm text-muted-foreground">{message}</p>}
      <Button className="mt-4" render={<Link href="/" />} nativeButton={false}>Go to the marketplace</Button>
    </div>
  );
}

export default function VerifyEmailPage() {
  return <Suspense><Verify /></Suspense>;
}
