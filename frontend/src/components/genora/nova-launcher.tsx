"use client";

import { Maximize2, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { GenoraChat } from "@/components/genora/chat";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useAuth } from "@/lib/auth";
import { track } from "@/lib/queries";

/** Floating GenOra Nova entry point available on every shop page. */
export function NovaLauncher() {
  const pathname = usePathname();
  const { status } = useAuth();
  const [open, setOpen] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  if (pathname.startsWith("/nova") || pathname.startsWith("/login") || pathname.startsWith("/register")) return null;
  return (
    <Sheet open={open} onOpenChange={(o) => { setOpen(o); if (o) track("nova_open"); }}>
      <SheetTrigger
        render={<Button className="bg-genora fixed bottom-5 right-5 z-40 h-12 rounded-full px-5 text-white shadow-lg hover:opacity-95" aria-label="Open GenOra Nova" />}
      >
        <Sparkles className="size-5" /> <span className="hidden sm:inline">Ask Nova</span>
      </SheetTrigger>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-md">
        <SheetHeader className="border-b">
          <SheetTitle className="flex items-center justify-between pr-8">
            <span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> GenOra Nova</span>
            <Button variant="ghost" size="icon-sm" render={<Link href="/nova" aria-label="Open full screen" />} nativeButton={false}
              onClick={() => setOpen(false)}>
              <Maximize2 />
            </Button>
          </SheetTitle>
        </SheetHeader>
        {status === "authenticated" ? (
          <GenoraChat agent="nova" compact conversationId={conversationId} onConversation={setConversationId} className="min-h-0 flex-1" />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
            <Sparkles className="size-8 text-primary" />
            <p className="font-medium">Sign in to chat with Nova</p>
            <p className="text-sm text-muted-foreground">Nova uses your cart, orders and preferences, so it needs an account.</p>
            <Button render={<Link href="/login?next=/nova" />} nativeButton={false} onClick={() => setOpen(false)}>Sign in</Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
