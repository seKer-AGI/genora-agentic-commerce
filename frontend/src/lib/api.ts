// Typed client for the GenOra REST API.
//
// * All requests go to same-origin `/api/v1/*`, which Next.js rewrites to the FastAPI backend, so the
//   httpOnly refresh cookie is first-party.
// * The short-lived access token lives only in memory (never localStorage).
// * A 401 caused by an expired/invalid access token triggers ONE single-flight refresh, then a retry.

import type { ApiErrorBody, TokenResponse } from "./types";

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type TokenListener = (session: TokenResponse | null) => void;

let accessToken: string | null = null;
let refreshInFlight: Promise<TokenResponse | null> | null = null;
const listeners = new Set<TokenListener>();

export function getAccessToken() {
  return accessToken;
}

export function setSession(session: TokenResponse | null) {
  accessToken = session?.access_token ?? null;
  listeners.forEach((l) => l(session));
}

export function onSessionChange(listener: TokenListener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Exchange the httpOnly refresh cookie for a new access token (single-flight). */
export function refreshSession(): Promise<TokenResponse | null> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_BASE}/auth/refresh`, { method: "POST", credentials: "include" })
      .then(async (r) => {
        if (!r.ok) {
          setSession(null);
          return null;
        }
        const session = (await r.json()) as TokenResponse;
        setSession(session);
        return session;
      })
      .catch(() => null)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

type Query = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  form?: FormData;
  query?: Query;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** internal: prevents infinite refresh loops */
  _retried?: boolean;
}

export function buildQuery(query?: Query): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => params.append(k, String(x)));
    else params.set(k, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as ApiErrorBody;
    if (body?.error) return new ApiError(res.status, body.error.code, body.error.message, body.error.details);
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, "HTTP_ERROR", res.statusText || "Request failed");
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...opts.headers };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(`${API_BASE}${path}${buildQuery(opts.query)}`, {
    method: opts.method ?? (body ? "POST" : "GET"),
    headers,
    body,
    credentials: "include",
    signal: opts.signal,
  });
  if (res.status === 401 && !opts._retried && !path.startsWith("/auth/")) {
    const err = await parseError(res.clone());
    if (["TOKEN_EXPIRED", "TOKEN_INVALID", "UNAUTHENTICATED"].includes(err.code)) {
      const session = await refreshSession();
      if (session) return api<T>(path, { ...opts, _retried: true });
    }
    throw err;
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong";
}
