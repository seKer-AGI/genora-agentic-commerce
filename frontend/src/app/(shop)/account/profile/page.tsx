"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MapPin, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Address, Me } from "@/lib/types";

function ProfileForm() {
  const { user, refreshUser } = useAuth();
  const [name, setName] = useState(user?.full_name ?? "");
  const save = useMutation({
    mutationFn: () => api<Me>("/auth/me", { method: "PATCH", body: { full_name: name } }),
    onSuccess: async () => {
      await refreshUser();
      toast.success("Profile updated");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Profile</CardTitle><CardDescription>{user?.email}</CardDescription></CardHeader>
      <CardContent>
        <form className="flex max-w-md items-end gap-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <div className="flex-1 space-y-1.5"><Label htmlFor="name">Full name</Label><Input id="name" value={name} onChange={(e) => setName(e.target.value)} /></div>
          <Button type="submit" disabled={save.isPending || name.trim().length < 2}>Save</Button>
        </form>
        <div className="mt-3 flex flex-wrap gap-1.5">{user?.roles.map((r) => <Badge key={r} variant="secondary">{r}</Badge>)}</div>
      </CardContent>
    </Card>
  );
}

function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const change = useMutation({
    mutationFn: () => api("/auth/change-password", { method: "POST", body: { current_password: current, new_password: next } }),
    onSuccess: () => {
      toast.success("Password changed. Other sessions were signed out.");
      setCurrent("");
      setNext("");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Password</CardTitle><CardDescription>Changing your password signs out your other devices.</CardDescription></CardHeader>
      <CardContent>
        <form className="grid max-w-md gap-3" onSubmit={(e) => { e.preventDefault(); change.mutate(); }}>
          <div className="space-y-1.5"><Label htmlFor="cur">Current password</Label><Input id="cur" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="new">New password</Label><Input id="new" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} /></div>
          <Button type="submit" className="w-fit" disabled={change.isPending || !current || next.length < 8}>Change password</Button>
        </form>
      </CardContent>
    </Card>
  );
}

function Addresses() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["addresses"], queryFn: () => api<Address[]>("/addresses") });
  const [form, setForm] = useState({ recipient_name: "", line1: "", city: "", postal_code: "", country: "US", label: "" });
  const add = useMutation({
    mutationFn: () => api<Address>("/addresses", { method: "POST", body: { ...form, label: form.label || null } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["addresses"] });
      setForm({ recipient_name: "", line1: "", city: "", postal_code: "", country: "US", label: "" });
      toast.success("Address saved");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/addresses/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["addresses"] }),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate();
  };
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Addresses</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <ul className="grid gap-2 sm:grid-cols-2">
          {q.data?.map((a) => (
            <li key={a.id} className="flex justify-between gap-2 rounded-lg border p-3 text-sm">
              <span className="flex gap-2"><MapPin className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <span><b>{a.recipient_name}</b> {a.is_default && <Badge variant="secondary">Default</Badge>}<br />{a.line1}, {a.city} {a.postal_code}, {a.country}</span>
              </span>
              <Button variant="ghost" size="icon-sm" aria-label="Delete address" onClick={() => remove.mutate(a.id)}><Trash2 /></Button>
            </li>
          ))}
        </ul>
        <form onSubmit={submit} className="grid gap-2 sm:grid-cols-3">
          <Input placeholder="Full name" value={form.recipient_name} onChange={(e) => setForm({ ...form, recipient_name: e.target.value })} />
          <Input placeholder="Address" className="sm:col-span-2" value={form.line1} onChange={(e) => setForm({ ...form, line1: e.target.value })} />
          <Input placeholder="City" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
          <Input placeholder="Postal code" value={form.postal_code} onChange={(e) => setForm({ ...form, postal_code: e.target.value })} />
          <Input placeholder="Country (US)" maxLength={2} value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value.toUpperCase() })} />
          <Button type="submit" variant="outline" className="w-fit" disabled={add.isPending || !form.recipient_name || !form.line1 || !form.city || !form.postal_code}>
            Add address
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function ProfilePage() {
  const { status } = useAuth();
  if (status !== "authenticated") return null;
  return (
    <div className="space-y-6">
      <ProfileForm />
      <PasswordForm />
      <Addresses />
    </div>
  );
}
