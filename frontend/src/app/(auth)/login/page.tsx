"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const schema = z.object({
  email: z.email("Enter a valid e-mail"),
  password: z.string().min(1, "Enter your password"),
});
type FormValues = z.infer<typeof schema>;

const DEMO = [
  { label: "Buyer", email: "buyer@genora.dev", password: "Buyer#2026!" },
  { label: "Seller", email: "seller@genora.dev", password: "Seller#2026!" },
  { label: "Admin", email: "admin@genora.dev", password: "Admin#2026!" },
];

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });

  const onSubmit = async (v: FormValues) => {
    setError(null);
    try {
      const user = await login(v.email, v.password);
      const next = params.get("next");
      const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : null;
      router.push(safeNext ?? (user.roles.includes("ADMIN") ? "/admin" : user.seller ? "/seller" : "/"));
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
      <p className="mt-1 text-sm text-muted-foreground">Sign in to shop, sell or manage the marketplace.</p>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        <div className="space-y-1.5">
          <Label htmlFor="email">E-mail</Label>
          <Input id="email" type="email" autoComplete="email" {...form.register("email")} aria-invalid={!!form.formState.errors.email} />
          {form.formState.errors.email && <p className="text-xs text-destructive">{form.formState.errors.email.message}</p>}
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link href="/forgot-password" className="text-xs text-muted-foreground hover:underline">Forgot password?</Link>
          </div>
          <Input id="password" type="password" autoComplete="current-password" {...form.register("password")} aria-invalid={!!form.formState.errors.password} />
          {form.formState.errors.password && <p className="text-xs text-destructive">{form.formState.errors.password.message}</p>}
        </div>
        <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting && <Loader2 className="animate-spin" />} Sign in
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-muted-foreground">
        New to GenOra? <Link href="/register" className="font-medium text-primary hover:underline">Create an account</Link>
      </p>
      <div className="mt-8 rounded-xl border border-dashed p-3">
        <p className="mb-2 text-xs font-medium text-muted-foreground">Demo accounts (synthetic seed data)</p>
        <div className="flex flex-wrap gap-2">
          {DEMO.map((d) => (
            <Button key={d.label} type="button" variant="outline" size="sm"
              onClick={() => { form.setValue("email", d.email); form.setValue("password", d.password); }}>
              {d.label}
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
