"use client";

import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, onSessionChange, refreshSession, setSession } from "./api";
import type { Me, TokenResponse } from "./types";

interface AuthState {
  user: Me | null;
  status: "loading" | "authenticated" | "anonymous";
  login: (email: string, password: string) => Promise<Me>;
  register: (data: RegisterInput) => Promise<Me>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  hasRole: (...roles: Me["roles"]) => boolean;
  can: (permission: string) => boolean;
}

export interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
  account_type: "buyer" | "seller";
  store_name?: string;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const queryClient = useQueryClient();

  useEffect(() => {
    const off = onSessionChange((s) => {
      setUser(s?.user ?? null);
      setStatus(s ? "authenticated" : "anonymous");
    });
    // Restore the session from the httpOnly refresh cookie.
    refreshSession().then((s) => {
      if (!s) setStatus("anonymous");
    });
    return off;
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const s = await api<TokenResponse>("/auth/login", { method: "POST", body: { email, password } });
    setSession(s);
    queryClient.invalidateQueries();
    return s.user;
  }, [queryClient]);

  const register = useCallback(async (data: RegisterInput) => {
    const s = await api<TokenResponse>("/auth/register", { method: "POST", body: data });
    setSession(s);
    return s.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      setSession(null);
      queryClient.clear();
    }
  }, [queryClient]);

  const refreshUser = useCallback(async () => {
    const me = await api<Me>("/auth/me");
    setUser(me);
  }, []);

  const value = useMemo<AuthState>(() => ({
    user,
    status,
    login,
    register,
    logout,
    refreshUser,
    hasRole: (...roles) => !!user && roles.some((r) => user.roles.includes(r)),
    can: (permission) => !!user?.permissions.includes(permission),
  }), [user, status, login, register, logout, refreshUser]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Client-side route guard. The API enforces authorization; this only improves UX. */
export function useRequireAuth(role?: "SELLER" | "ADMIN") {
  const auth = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    if (auth.status === "anonymous") {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [auth.status, router, pathname]);
  const allowed =
    auth.status === "authenticated" &&
    (!role || (role === "SELLER" ? !!auth.user?.seller && auth.user.seller.status === "active" : auth.hasRole("ADMIN")));
  return { ...auth, allowed };
}
