"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUp, Bot, ImagePlus, Loader2, ShieldAlert, Sparkles, User, X } from "lucide-react";
import { Fragment, type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { AgentBlocks } from "@/components/genora/blocks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { API_BASE, api, ApiError, errorMessage, getAccessToken, refreshSession } from "@/lib/api";
import type { AgentMemory, AgentMessage, AgentName, AgentStatus, ConversationDetail, TurnResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const AGENT_META: Record<AgentName, { name: string; tagline: string; starters: string[] }> = {
  nova: {
    name: "GenOra Nova",
    tagline: "Your AI shopping agent",
    starters: [
      "I need a laptop under $1000 for programming",
      "Find me Nike running shoes",
      "What should I buy with the Aperture Lumix LX-7 Mirrorless Camera?",
      "Are there any discounts on the SonicWave Quiet 900 Headphones?",
      "Can I get the Aperture LX-9 Full-Frame Camera for $2150?",
      "What are people saying about the Voltrix AeroBook 14?",
    ],
  },
  astra: {
    name: "GenOra Astra",
    tagline: "Your AI seller assistant",
    starters: [
      "How did my sales perform this month?",
      "Which products are running low?",
      "Which products are underperforming?",
      "Suggest a discount strategy for my products",
      "Create a product listing for a Voltrix AeroBook 15 with 16GB RAM and 1TB SSD priced at $1099",
      "Forecast my revenue for the next 14 days",
    ],
  },
};

/** Minimal, safe markdown: **bold**, line breaks and bullets. No HTML is ever injected. */
export function RichText({ text }: { text: string }) {
  const lines = text.split("\n");
  const inline = (line: string): ReactNode[] =>
    line.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : <Fragment key={i}>{part}</Fragment>);
  return (
    <div className="space-y-1 text-sm leading-relaxed">
      {lines.map((line, i) => {
        const bullet = /^\s*(?:•|-|\d+\.)\s+/.exec(line);
        if (!line.trim()) return <div key={i} className="h-1" />;
        return bullet ? (
          <div key={i} className="flex gap-2 pl-1">
            <span className="text-muted-foreground">{/^\s*\d/.test(bullet[0]) ? bullet[0].trim() : "•"}</span>
            <span>{inline(line.slice(bullet[0].length))}</span>
          </div>
        ) : <p key={i}>{inline(line)}</p>;
      })}
    </div>
  );
}

async function streamTurn(conversationId: string, content: string, onStatus: (s: string) => void): Promise<TurnResponse> {
  const attempt = async (): Promise<Response> => {
    const token = getAccessToken();
    return fetch(`${API_BASE}/agents/conversations/${conversationId}/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ content }),
      credentials: "include",
    });
  };
  let res = await attempt();
  if (res.status === 401 && (await refreshSession())) res = await attempt();
  if (!res.ok || !res.body) {
    let msg = res.statusText;
    let code = "HTTP_ERROR";
    try {
      const body = await res.json();
      msg = body.error?.message ?? msg;
      code = body.error?.code ?? code;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, code, msg);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const event = /^event: (.+)$/m.exec(raw)?.[1];
      const data = /^data: (.+)$/m.exec(raw)?.[1];
      if (!event || !data) continue;
      const payload = JSON.parse(data);
      if (event === "status") onStatus(payload.text);
      else if (event === "result") return payload as TurnResponse;
      else if (event === "error") throw new ApiError(500, payload.code, payload.message);
    }
  }
  throw new ApiError(500, "STREAM_ENDED", "The assistant did not respond");
}

function MessageBubble({ m, children }: { m: AgentMessage; children?: ReactNode }) {
  const user = m.role === "user";
  const flags = m.payload.safety_flags ?? [];
  return (
    <div className={cn("flex gap-3", user && "flex-row-reverse")}>
      <div className={cn("flex size-8 shrink-0 items-center justify-center rounded-full", user ? "bg-muted" : "bg-genora text-white")}>
        {user ? <User className="size-4" /> : <Bot className="size-4" />}
      </div>
      <div className={cn("min-w-0 max-w-[92%] space-y-2 sm:max-w-[85%]", user && "items-end")}>
        <div className={cn("rounded-2xl px-4 py-2.5", user ? "ml-auto w-fit bg-primary text-primary-foreground" : "bg-muted/60")}>
          {m.payload.attachments?.length ? (
            <p className="mb-1 flex items-center gap-1 text-xs opacity-80"><ImagePlus className="size-3" /> {m.payload.attachments[0].name}</p>
          ) : null}
          {user ? <p className="whitespace-pre-wrap text-sm">{m.content}</p> : <RichText text={m.content} />}
        </div>
        {!user && flags.length > 0 && m.payload.status === "blocked" && (
          <p className="flex items-center gap-1 text-xs text-amber-700"><ShieldAlert className="size-3.5" /> Safety guard: request refused</p>
        )}
        {children}
        {!user && m.payload.workflow && (
          <p className="text-[11px] text-muted-foreground">
            {m.payload.steps?.length ? `${m.payload.steps.join(" → ")} · ` : ""}
            {m.payload.workflow.replace(/_/g, " ")}{m.payload.nlu_mode ? ` · ${m.payload.nlu_mode}` : ""}
          </p>
        )}
      </div>
    </div>
  );
}

export function GenoraChat({ agent, conversationId: initialId, initialPrompt, compact = false, onConversation, onMemory, className }: {
  agent: AgentName;
  onMemory?: (memory: AgentMemory | null) => void;
  conversationId?: string | null;
  initialPrompt?: string | null;
  compact?: boolean;
  onConversation?: (id: string) => void;
  className?: string;
}) {
  const meta = AGENT_META[agent];
  const [conversationId, setConversationId] = useState<string | null>(initialId ?? null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [memory, setMemory] = useState<AgentMemory | null>(null);
  const [input, setInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [live, setLive] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const sentInitial = useRef(false);

  const status = useQuery({ queryKey: ["agent-status"], queryFn: () => api<AgentStatus>("/agents/status"), staleTime: 60_000 });
  const rulesMode = status.data?.runtime.nlu_mode === "rules";

  const createdHere = useRef<string | null>(null);

  useEffect(() => {
    if (initialId && initialId === createdHere.current) return; // we just created it; state is already current
    setConversationId(initialId ?? null);
    if (!initialId) {
      setMessages([]);
      setMemory(null);
      return;
    }
    setLoadingHistory(true);
    api<ConversationDetail>(`/agents/conversations/${initialId}`)
      .then((c) => {
        setMessages(c.messages);
        setMemory(c.memory);
      })
      .catch((e) => toast.error(errorMessage(e)))
      .finally(() => setLoadingHistory(false));
  }, [initialId]);

  useEffect(() => {
    onMemory?.(memory);
  }, [memory, onMemory]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, live]);

  const ensureConversation = useCallback(async () => {
    if (conversationId) return conversationId;
    const c = await api<{ id: string }>(`/agents/${agent}/conversations`, { method: "POST" });
    createdHere.current = c.id;
    setConversationId(c.id);
    onConversation?.(c.id);
    return c.id;
  }, [agent, conversationId, onConversation]);

  const run = useCallback(async (text: string, opts: { image?: File; action?: { id: string; approve: boolean } } = {}) => {
    if (busy) return;
    setBusy(true);
    setLive([]);
    const tempId = `temp-${Date.now()}`;
    const shown = opts.action ? (opts.action.approve ? "Yes, confirm" : "No, cancel") : text || "Find products similar to this image";
    setMessages((m) => [...m, {
      id: tempId, role: "user", content: shown, created_at: new Date().toISOString(),
      payload: opts.image ? { attachments: [{ name: opts.image.name, mime: opts.image.type, size: opts.image.size }] } : {},
    }]);
    try {
      const id = await ensureConversation();
      let turn: TurnResponse;
      if (opts.action) {
        turn = await api<TurnResponse>(`/agents/conversations/${id}/actions/${opts.action.id}`, {
          method: "POST", body: { approve: opts.action.approve },
        });
      } else if (opts.image) {
        const form = new FormData();
        form.append("file", opts.image);
        form.append("content", text);
        setLive(["Analyzing the image…"]);
        turn = await api<TurnResponse>(`/agents/conversations/${id}/messages/image`, { method: "POST", form });
      } else {
        try {
          turn = await streamTurn(id, text, (s) => setLive((l) => (l.at(-1) === s ? l : [...l, s])));
        } catch (err) {
          if (err instanceof ApiError && err.status < 500) throw err;
          turn = await api<TurnResponse>(`/agents/conversations/${id}/messages`, { method: "POST", body: { content: text } });
        }
      }
      setMessages((m) => [...m.filter((x) => x.id !== tempId), turn.user_message, turn.message]);
      setMemory(turn.memory);
    } catch (err) {
      setMessages((m) => [...m, {
        id: `err-${Date.now()}`, role: "assistant", created_at: new Date().toISOString(),
        content: `Sorry — ${errorMessage(err)}`, payload: { status: "failed" },
      }]);
    } finally {
      setBusy(false);
      setLive([]);
    }
  }, [busy, ensureConversation]);

  useEffect(() => {
    if (initialPrompt && !initialId && !sentInitial.current) {
      sentInitial.current = true;
      run(initialPrompt);
    }
  }, [initialPrompt, initialId, run]);

  const submit = () => {
    const text = input.trim();
    if (!text && !file) return;
    const f = file;
    setInput("");
    setFile(null);
    run(text, f ? { image: f } : {});
  };

  const pendingId = memory?.pending_action?.id ?? null;
  const last = messages.at(-1);
  const suggestions = !busy && last?.role === "assistant" ? last.payload.suggestions ?? [] : [];

  return (
    <div className={cn("flex h-full min-h-0 flex-col", className)}>
      <div ref={scrollRef} className="flex-1 space-y-5 overflow-y-auto px-3 py-4 sm:px-5">
        {loadingHistory && <p className="text-center text-sm text-muted-foreground"><Loader2 className="mr-1 inline size-4 animate-spin" />Loading conversation…</p>}
        {!loadingHistory && messages.length === 0 && (
          <div className="mx-auto max-w-xl py-6 text-center">
            <div className="bg-genora mx-auto mb-3 flex size-12 items-center justify-center rounded-2xl text-white shadow">
              <Sparkles className="size-6" />
            </div>
            <h2 className="text-lg font-semibold">{meta.name}</h2>
            <p className="text-sm text-muted-foreground">{meta.tagline}. Actions that change anything always ask for your confirmation.</p>
            <div className={cn("mt-5 grid gap-2 text-left", !compact && "sm:grid-cols-2")}>
              {meta.starters.slice(0, compact ? 4 : 6).map((s) => (
                <button key={s} onClick={() => run(s)} className="rounded-xl border bg-card px-3 py-2.5 text-sm transition hover:border-primary/40 hover:bg-primary/5">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} m={m}>
            {m.role === "assistant" && m.payload.blocks && m.payload.blocks.length > 0 && (
              <AgentBlocks blocks={m.payload.blocks} onPrompt={(t) => run(t)} pendingId={pendingId} busy={busy}
                onDecide={(id, approve) => run("", { action: { id, approve } })} />
            )}
          </MessageBubble>
        ))}
        {busy && (
          <div className="flex gap-3">
            <div className="bg-genora flex size-8 shrink-0 items-center justify-center rounded-full text-white"><Bot className="size-4" /></div>
            <div className="rounded-2xl bg-muted/60 px-4 py-3" aria-live="polite">
              {(live.length ? live : ["Thinking…"]).map((s, i, arr) => (
                <p key={s} className={cn("flex items-center gap-2 text-sm", i < arr.length - 1 ? "text-muted-foreground" : "")}>
                  {i === arr.length - 1 ? <Loader2 className="size-3.5 animate-spin text-primary" /> : <span className="text-emerald-600">✓</span>}
                  {s}
                </p>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="border-t bg-background p-3">
        {suggestions.length > 0 && (
          <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1">
            {suggestions.map((s) => (
              <button key={s} onClick={() => run(s)} className="shrink-0 rounded-full border bg-card px-3 py-1 text-xs hover:border-primary/40 hover:text-primary">
                {s}
              </button>
            ))}
          </div>
        )}
        {file && (
          <div className="mb-2 flex w-fit items-center gap-2 rounded-lg border bg-muted/50 px-2 py-1 text-xs">
            <ImagePlus className="size-3.5" /> {file.name}
            <button onClick={() => setFile(null)} aria-label="Remove image"><X className="size-3.5" /></button>
          </div>
        )}
        <div className="flex items-end gap-2">
          {agent === "nova" && (
            <>
              <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <Button variant="ghost" size="icon" aria-label="Search by image" onClick={() => fileRef.current?.click()} disabled={busy}>
                <ImagePlus className="size-5" />
              </Button>
            </>
          )}
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={1}
            maxLength={2000}
            placeholder={agent === "nova" ? "Ask Nova to find, compare or negotiate…" : "Ask Astra about your store…"}
            className="max-h-32 min-h-10 resize-none"
            aria-label={`Message ${meta.name}`}
          />
          <Button size="icon" onClick={submit} disabled={busy || (!input.trim() && !file)} aria-label="Send message">
            {busy ? <Loader2 className="animate-spin" /> : <ArrowUp />}
          </Button>
        </div>
        <p className="mt-1.5 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
          {rulesMode && <Badge variant="outline" className="h-4 px-1.5 text-[10px]">Rule-based mode · no LLM configured</Badge>}
          Answers come from live marketplace data. Nova never completes purchases or changes without your confirmation.
        </p>
      </div>
    </div>
  );
}

export function MemoryPanel({ memory }: { memory: AgentMemory | null }) {
  if (!memory) return null;
  const slots = Object.entries(memory.slots).filter(([k, v]) => v !== null && v !== undefined && !k.startsWith("listing") && k !== "last_bundles");
  return (
    <div className="space-y-3 text-sm">
      <div>
        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Remembered</p>
        {slots.length === 0 ? <p className="text-xs text-muted-foreground">Nothing yet</p> : (
          <ul className="space-y-1">
            {slots.map(([k, v]) => (
              <li key={k} className="flex justify-between gap-2 text-xs">
                <span className="text-muted-foreground">{k.replace(/_/g, " ")}</span>
                <span className="truncate font-medium">{Array.isArray(v) ? v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join(", ") : String(v)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {memory.focus_product && (
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Discussing</p>
          <p className="text-xs">{memory.focus_product.name}</p>
        </div>
      )}
      {memory.pending_action && (
        <div className="rounded-lg border border-primary/40 bg-primary/5 p-2 text-xs">
          Awaiting confirmation: {memory.pending_action.summary}
        </div>
      )}
    </div>
  );
}
