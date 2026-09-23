"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, ShoppingBag, Store } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const schema = z.object({
  full_name: z.string().trim().min(2, "Enter your name").max(120),
  email: z.email("Enter a valid e-mail"),
  password: z.string().min(8, "At least 8 characters")
    .regex(/[a-z]/, "Include a lowercase letter").regex(/[A-Z]/, "Include an uppercase letter").regex(/\d/, "Include a digit"),
  account_type: z.enum(["buyer", "seller"]),
  store_name: z.string().trim().max(120).optional(),
}).refine((v) => v.account_type === "buyer" || (v.store_name && v.store_name.length >= 2), {
  path: ["store_name"], message: "Enter your store name",
});
type FormValues = z.infer<typeof schema>;

function RegisterForm() {
  const { register: signUp } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: "", email: "", password: "", account_type: params.get("type") === "seller" ? "seller" : "buyer", store_name: "" },
  });
  const type = form.watch("account_type");
  const err = form.formState.errors;

  const onSubmit = async (v: FormValues) => {
    setError(null);
    try {
      const user = await signUp({ ...v, store_name: v.account_type === "seller" ? v.store_name : undefined });
      toast.success("Account created. We've sent a verification e-mail.");
      router.push(user.seller ? "/seller" : "/");
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Create your account</h1>
      <p className="mt-1 text-sm text-muted-foreground">Shop with GenOra Nova, or open a store and sell with GenOra Astra.</p>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Account type">
          {([["buyer", "I want to shop", ShoppingBag], ["seller", "I want to sell", Store]] as const).map(([value, label, Icon]) => (
            <button key={value} type="button" role="radio" aria-checked={type === value}
              onClick={() => form.setValue("account_type", value)}
              className={cn("flex flex-col items-center gap-1 rounded-xl border p-3 text-sm transition",
                type === value ? "border-primary bg-primary/5 text-primary" : "hover:bg-muted")}>
              <Icon className="size-5" /> {label}
            </button>
          ))}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="full_name">Full name</Label>
          <Input id="full_name" autoComplete="name" {...form.register("full_name")} aria-invalid={!!err.full_name} />
          {err.full_name && <p className="text-xs text-destructive">{err.full_name.message}</p>}
        </div>
        {type === "seller" && (
          <div className="space-y-1.5">
            <Label htmlFor="store_name">Store name</Label>
            <Input id="store_name" {...form.register("store_name")} aria-invalid={!!err.store_name} />
            {err.store_name && <p className="text-xs text-destructive">{err.store_name.message}</p>}
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="email">E-mail</Label>
          <Input id="email" type="email" autoComplete="email" {...form.register("email")} aria-invalid={!!err.email} />
          {err.email && <p className="text-xs text-destructive">{err.email.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="new-password" {...form.register("password")} aria-invalid={!!err.password} />
          {err.password ? <p className="text-xs text-destructive">{err.password.message}</p>
            : <p className="text-xs text-muted-foreground">8+ characters with upper- and lowercase letters and a digit.</p>}
        </div>
        <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting && <Loader2 className="animate-spin" />} Create account
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-muted-foreground">
        Already have an account? <Link href="/login" className="font-medium text-primary hover:underline">Sign in</Link>
      </p>
    </div>
  );
}

export default function RegisterPage() {
  return <Suspense><RegisterForm /></Suspense>;
}
