"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, History, MessageSquarePlus, Trash2 } from "lucide-react";
import { useState } from "react";

import { GenoraChat, MemoryPanel } from "@/components/genora/chat";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { api } from "@/lib/api";
import { relative } from "@/lib/format";
import type { AgentMemory, AgentName, Conversation } from "@/lib/types";
import { cn } from "@/lib/utils";

function ConversationList({ agent, activeId, onSelect, onNew }: {
  agent: AgentName;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["conversations", agent], queryFn: () => api<Conversation[]>(`/agents/${agent}/conversations`) });
  const archive = async (id: string) => {
    await api(`/agents/conversations/${id}`, { method: "DELETE" });
    qc.invalidateQueries({ queryKey: ["conversations", agent] });
    if (id === activeId) onNew();
  };
  return (
    <div className="flex h-full flex-col">
      <Button variant="outline" className="m-3 justify-start" onClick={onNew}>
        <MessageSquarePlus /> New conversation
      </Button>
      <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {q.data?.length === 0 && <p className="px-2 py-4 text-xs text-muted-foreground">No conversations yet.</p>}
        {q.data?.map((c) => (
          <div key={c.id} className={cn("group flex items-center gap-1 rounded-md pr-1", c.id === activeId ? "bg-muted" : "hover:bg-muted/60")}>
            <button onClick={() => onSelect(c.id)} className="min-w-0 flex-1 px-2 py-2 text-left">
              <p className="truncate text-sm">{c.title ?? "New conversation"}</p>
              <p className="text-[11px] text-muted-foreground">{relative(c.updated_at)} · {c.message_count} messages</p>
            </button>
            <Button variant="ghost" size="icon-xs" className="opacity-0 group-hover:opacity-100" aria-label="Delete conversation"
              onClick={() => archive(c.id)}>
              <Trash2 />
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

export function AgentWorkspace({ agent, initialPrompt, title, subtitle }: {
  agent: AgentName;
  initialPrompt?: string | null;
  title: string;
  subtitle: string;
}) {
  const qc = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [chatKey, setChatKey] = useState(0);
  const [memory, setMemory] = useState<AgentMemory | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  const select = (id: string) => {
    setActiveId(id);
    setChatKey((k) => k + 1);
    setHistoryOpen(false);
  };
  const newChat = () => {
    setActiveId(null);
    setMemory(null);
    setChatKey((k) => k + 1);
    setHistoryOpen(false);
  };

  const list = <ConversationList agent={agent} activeId={activeId} onSelect={select} onNew={newChat} />;

  return (
    <div className="flex h-[calc(100dvh-4rem)] min-h-[520px] overflow-hidden">
      <aside className="hidden w-64 shrink-0 border-r bg-muted/20 lg:block">{list}</aside>
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between gap-2 border-b px-4 py-2.5">
          <div className="min-w-0">
            <h1 className="truncate font-semibold">{title}</h1>
            <p className="truncate text-xs text-muted-foreground">{subtitle}</p>
          </div>
          <div className="flex items-center gap-1">
            <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
              <SheetTrigger render={<Button variant="ghost" size="icon" className="lg:hidden" aria-label="Conversation history" />}>
                <History />
              </SheetTrigger>
              <SheetContent side="left" className="w-72 p-0">
                <SheetHeader><SheetTitle>Conversations</SheetTitle></SheetHeader>
                {list}
              </SheetContent>
            </Sheet>
            <Sheet>
              <SheetTrigger render={<Button variant="ghost" size="icon" className="xl:hidden" aria-label="What the agent remembers" />}>
                <Brain />
              </SheetTrigger>
              <SheetContent side="right" className="w-72">
                <SheetHeader><SheetTitle>Conversation memory</SheetTitle></SheetHeader>
                <div className="px-4"><MemoryPanel memory={memory} /></div>
              </SheetContent>
            </Sheet>
            <Button variant="outline" size="sm" onClick={newChat}><MessageSquarePlus /> New</Button>
          </div>
        </div>
        <GenoraChat
          key={chatKey}
          agent={agent}
          conversationId={activeId}
          initialPrompt={chatKey === 0 ? initialPrompt : null}
          onMemory={setMemory}
          onConversation={(id) => {
            setActiveId(id);
            qc.invalidateQueries({ queryKey: ["conversations", agent] });
          }}
          className="min-h-0 flex-1"
        />
      </section>
      <aside className="hidden w-64 shrink-0 border-l p-4 xl:block">
        <p className="mb-3 flex items-center gap-2 text-sm font-medium"><Brain className="size-4 text-primary" /> Memory</p>
        <MemoryPanel memory={memory} />
        <p className="mt-6 text-[11px] leading-relaxed text-muted-foreground">
          The agent only remembers shopping context from this conversation (budget, products discussed, pending actions).
        </p>
      </aside>
    </div>
  );
}
