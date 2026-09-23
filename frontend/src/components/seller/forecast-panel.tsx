"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Info, LineChart, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ForecastChart } from "@/components/charts/charts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errorMessage } from "@/lib/api";
import { money, number } from "@/lib/format";
import type { Forecast } from "@/lib/types";

const TARGETS = { revenue: "Revenue", sales: "Orders" } as const;
const HORIZONS = { "7": "7 days", "14": "14 days", "30": "30 days", "60": "60 days" } as const;

/** Runs forecasts through the provider registry. Unavailable providers are shown, never faked. */
export function ForecastPanel({ scope = "seller" }: { scope?: "seller" | "marketplace" }) {
  const [target, setTarget] = useState<keyof typeof TARGETS>("revenue");
  const [horizon, setHorizon] = useState<keyof typeof HORIZONS>("30");
  const [provider, setProvider] = useState("baseline");
  const providers = useQuery({ queryKey: ["forecast-providers"], queryFn: () => api<{ name: string; description: string; available: boolean; unavailable_reason: string | null }[]>("/forecasting/providers") });
  const run = useMutation({
    mutationFn: () => api<Forecast>("/forecasting/run", { method: "POST", body: { target, horizon: Number(horizon), provider, scope } }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const f = run.data;
  const fmt = target === "revenue" ? money : (v: number) => number(v);
  const total = f?.points.reduce((s, p) => s + p.value, 0) ?? 0;
  const bt = f?.metrics.backtest as { smape: number | null; holdout: number } | undefined;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base"><LineChart className="size-4 text-primary" /> Forecast</CardTitle>
        <CardDescription>Statistical forecast from your historical orders, with an 80% prediction interval.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Select value={target} items={TARGETS} onValueChange={(v) => setTarget(v as keyof typeof TARGETS)}>
            <SelectTrigger size="sm" className="w-32" aria-label="Forecast target"><SelectValue /></SelectTrigger>
            <SelectContent>{Object.entries(TARGETS).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={horizon} items={HORIZONS} onValueChange={(v) => setHorizon(v as keyof typeof HORIZONS)}>
            <SelectTrigger size="sm" className="w-28" aria-label="Horizon"><SelectValue /></SelectTrigger>
            <SelectContent>{Object.entries(HORIZONS).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={provider} items={Object.fromEntries((providers.data ?? []).map((p) => [p.name, p.name]))} onValueChange={(v) => setProvider(v as string)}>
            <SelectTrigger size="sm" className="w-40" aria-label="Model"><SelectValue /></SelectTrigger>
            <SelectContent>
              {providers.data?.map((p) => (
                <SelectItem key={p.name} value={p.name} disabled={!p.available}>
                  {p.name}{!p.available && " (unavailable)"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size="sm" onClick={() => run.mutate()} disabled={run.isPending}>
            {run.isPending && <Loader2 className="animate-spin" />} Run forecast
          </Button>
        </div>
        {providers.data?.filter((p) => !p.available).map((p) => (
          <p key={p.name} className="flex items-start gap-1.5 text-xs text-muted-foreground"><Info className="mt-0.5 size-3" /> {p.name}: {p.unavailable_reason}</p>
        ))}
        {f && f.status === "failed" && (
          <p className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
            Forecast not produced: {f.error}
          </p>
        )}
        {f && f.status === "completed" && (
          <>
            <div className="flex flex-wrap gap-2 text-sm">
              <Badge variant="secondary">Next {f.horizon} days: {fmt(total)}</Badge>
              <Badge variant="outline">{f.model_name}</Badge>
              {bt?.smape != null && <Badge variant="outline">Backtest sMAPE {bt.smape}% ({bt.holdout}d)</Badge>}
              {typeof f.metrics.skill_vs_naive === "number" && (
                <Badge variant="outline">Skill vs naive {(Number(f.metrics.skill_vs_naive) * 100).toFixed(0)}%</Badge>
              )}
            </div>
            <ForecastChart history={f.history} points={f.points} format={target === "revenue" ? "money" : "number"} />
            <p className="text-xs text-muted-foreground">Forecasts are statistical estimates based on past orders, not guarantees.</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
