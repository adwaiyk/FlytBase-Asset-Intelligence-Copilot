"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Activity, CalendarDays, Droplet, Flame, KeyRound, LogOut, MessageSquarePlus, Plus, RotateCcw, SendHorizonal, ShieldCheck, Wrench, Loader2, Gauge, Banknote } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { MessageView } from "./message";
import { PumpJack } from "./pumpjack";
import type { Conversation, Me, Message, Overview } from "@/lib/types";
import { cn } from "@/lib/utils";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api/bff/${path}`, { ...init, headers: { "content-type": "application/json", ...(init?.headers ?? {}) } });
  const d = await r.json().catch(() => ({}));
  if (r.status === 401) { window.location.href = "/login"; throw new Error("Session expired"); }
  if (!r.ok) throw new Error(d.detail ?? `Request failed (${r.status})`);
  return d as T;
}

const SUGGESTIONS = [
  "Which wells in Northeast Block 8 are not producing oil right now, and why? Show a table.",
  "Show a heatmap of 2026 spills by geographic area and month.",
  "Which recalled pumps are still in the ground right now?",
  "Is WELL-0001 producing oil right now? Show its status card.",
];

const initials = (n: string) => n.split(" ").map((p) => p[0]).join("").slice(0, 2);

export function AppShell({ me }: { me: Me }) {
  const router = useRouter();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [simDate, setSimDate] = useState("");
  const [pwOpen, setPwOpen] = useState(false);
  const [pw, setPw] = useState({ old: "", next: "" });
  const bottom = useRef<HTMLDivElement>(null);

  const loadConvs = useCallback(async () => {
    const c = await api<Conversation[]>("conversations");
    setConvs(c);
    return c;
  }, []);

  useEffect(() => {
    api<Overview>("overview").then((o) => { setOverview(o); setSimDate(o.as_of); }).catch((e) => toast.error(e.message));
    loadConvs().then((c) => c[0] && setActive(c[0].conv_id)).catch(() => null);
  }, [loadConvs]);

  useEffect(() => {
    if (!active) { setMessages([]); return; }
    api<Message[]>(`conversations/${active}/messages`).then(setMessages).catch((e) => toast.error(e.message));
  }, [active]);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function newChat() {
    const c = await api<Conversation>("conversations", { method: "POST", body: JSON.stringify({ sim_date: simDate || undefined }) });
    setConvs((p) => [c, ...p]);
    setActive(c.conv_id);
    setMessages([]);
  }

  async function send(q?: string) {
    const question = (q ?? text).trim();
    if (!question || busy) return;
    let conv = active;
    if (!conv) {
      const c = await api<Conversation>("conversations", { method: "POST", body: JSON.stringify({ sim_date: simDate || undefined }) });
      conv = c.conv_id; setActive(conv); setConvs((p) => [c, ...p]);
    }
    setText("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", content: question }, { role: "assistant", content: "", pending: true }]);
    try {
      const out = await api<{ content: string } & Message["payload"]>("chat", { method: "POST", body: JSON.stringify({ conv_id: conv, text: question }) });
      setMessages((m) => [...m.slice(0, -1), { role: "assistant", content: out.content, payload: out }]);
      loadConvs();
    } catch (e) {
      setMessages((m) => [...m.slice(0, -1), { role: "assistant", content: `⚠️ ${(e as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }

  async function changePassword() {
    try {
      await api("auth/password", { method: "POST", body: JSON.stringify({ old: pw.old, new: pw.next }) });
      toast.success("Password changed. Other sessions were signed out.");
      setPwOpen(false); setPw({ old: "", next: "" });
    } catch (e) { toast.error((e as Error).message); }
  }

  async function resetMemory() {
    if (!confirm("Clear all feedback and every user's conversations?")) return;
    try { await api("admin/reset", { method: "POST" }); toast.success("Memory reset"); setConvs([]); setActive(null); setMessages([]); }
    catch (e) { toast.error((e as Error).message); }
  }

  const kpis = overview ? [
    { icon: Activity, label: "Producing", value: `${overview.producing}/${overview.wells}`, tone: "text-success" },
    { icon: Gauge, label: "Not producing", value: overview.not_producing, tone: "text-destructive" },
    { icon: Droplet, label: "Spills · 90 d", value: `${overview.spills_90d} · ${overview.spill_bbl_90d} bbl`, tone: "text-primary" },
    { icon: Wrench, label: "Open repairs", value: overview.open_repairs, tone: "text-info" },
    { icon: Banknote, label: "Open fines", value: `$${overview.open_fines_usd.toLocaleString()}`, tone: "text-warning" },
  ] : [];

  return (
    <div className="flex h-dvh overflow-hidden">
      <aside className="hidden w-72 shrink-0 flex-col border-r bg-card/40 md:flex">
        <div className="flex items-center gap-2.5 px-4 py-4">
          <PumpJack className="h-9 w-11" />
          <div><div className="font-semibold tracking-tight">WellWise</div><div className="text-[11px] text-muted-foreground">Asset Intelligence Copilot</div></div>
        </div>
        <div className="grid gap-2 px-4">
          <Button onClick={newChat} className="w-full"><MessageSquarePlus /> New chat</Button>
          <div className="flex items-center gap-2">
            <CalendarDays className="size-4 text-muted-foreground" />
            <Input type="date" value={simDate} onChange={(e) => setSimDate(e.target.value)} className="h-8 text-xs" aria-label="Session date for new chats" />
          </div>
          <p className="text-[11px] text-muted-foreground">Session date lets you simulate &ldquo;yesterday&rdquo; in a same-day demo.</p>
        </div>
        <Separator className="my-3" />
        <div className="px-4 pb-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Your private chats</div>
        <ScrollArea className="min-h-0 flex-1 px-2">
          <div className="grid gap-0.5 pb-2">
            {convs.length === 0 && <div className="px-2 py-3 text-xs text-muted-foreground">No conversations yet.</div>}
            {convs.map((c) => (
              <button key={c.conv_id} onClick={() => setActive(c.conv_id)}
                className={cn("w-full rounded-md px-2.5 py-2 text-left text-sm transition hover:bg-accent", active === c.conv_id && "bg-accent ring-1 ring-primary/30")}>
                <div className="truncate">{c.title}</div>
                <div className="text-[11px] text-muted-foreground">{c.sim_date}</div>
              </button>
            ))}
          </div>
        </ScrollArea>
        <div className="border-t p-3">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex w-full items-center gap-2.5 rounded-md p-2 text-left hover:bg-accent">
                <Avatar><AvatarFallback className="bg-primary/20 text-primary">{initials(me.name)}</AvatarFallback></Avatar>
                <div className="min-w-0"><div className="truncate text-sm font-medium">{me.name}</div><div className="truncate text-[11px] capitalize text-muted-foreground">{me.role.replaceAll("_", " ")} · {me.team_name}</div></div>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-60">
              <DropdownMenuLabel className="flex items-center gap-2"><ShieldCheck className="size-4 text-success" /> Signed in securely</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setPwOpen(true)}><KeyRound /> Change password</DropdownMenuItem>
              <DropdownMenuItem onSelect={resetMemory}><RotateCcw /> Reset demo memory</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onSelect={logout}><LogOut /> Sign out</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="border-b bg-card/30 px-5 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm">
              <Flame className="size-4 text-primary" />
              <span className="font-medium">Field overview</span>
              {overview && <Badge variant="secondary">data as of {overview.as_of_label}</Badge>}
              {overview && <Badge variant="outline" className="hidden sm:inline-flex">{overview.well_types.join(" · ")}</Badge>}
            </div>
            {overview && <Badge variant="default"><Flame /> {overview.model.replace("google/", "")}</Badge>}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            {kpis.length ? kpis.map(({ icon: Icon, label, value, tone }) => (
              <div key={label} className="rounded-lg border bg-card/70 px-3 py-2">
                <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground"><Icon className={cn("size-3.5", tone)} />{label}</div>
                <div className="mt-0.5 font-semibold tabular-nums">{value}</div>
              </div>
            )) : Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-14 animate-pulse rounded-lg bg-muted/50" />)}
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
          <div className="mx-auto grid w-full max-w-4xl min-w-0 gap-6 px-5 py-6">
            {messages.length === 0 && (
              <div className="mt-6 grid place-items-center text-center">
                <PumpJack className="h-24 w-28" />
                <h2 className="mt-4 text-2xl font-semibold tracking-tight">Ask anything about the field, {me.name.split(" ")[0]}.</h2>
                <p className="mt-1 max-w-lg text-sm text-muted-foreground">Answers are computed from inspections, repairs, regulator events, manuals and your team&apos;s notes, with the evidence attached. Tell me a correction and every teammate will see it.</p>
                <div className="mt-6 grid w-full max-w-2xl gap-2 sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => send(s)} className="rounded-lg border bg-card/60 p-3 text-left text-sm transition hover:border-primary/50 hover:bg-accent">{s}</button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) => <MessageView key={i} m={m} overview={overview} />)}
            <div ref={bottom} />
          </div>
        </div>

        <div className="border-t bg-card/30 px-5 py-4">
          <form className="mx-auto flex max-w-4xl items-end gap-2 rounded-xl border bg-background/60 p-2 focus-within:ring-2 focus-within:ring-ring/40"
            onSubmit={(e) => { e.preventDefault(); send(); }}>
            <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={1} placeholder="Ask about wells, spills, repairs, compliance… or tell me a correction"
              className="max-h-40 min-h-10 resize-none border-0 bg-transparent"
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
            <Button type="submit" size="icon" disabled={busy || !text.trim()} aria-label="Send">{busy ? <Loader2 className="animate-spin" /> : <SendHorizonal />}</Button>
          </form>
          <div className="mx-auto mt-1.5 max-w-4xl text-center text-[11px] text-muted-foreground">Numbers come from deterministic tools over the records; Gemma 4 plans the tool calls and writes the answer.</div>
        </div>
      </main>

      <Dialog open={pwOpen} onOpenChange={setPwOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Change password</DialogTitle><DialogDescription>At least 8 characters. Your other sessions will be signed out.</DialogDescription></DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-1.5"><Label htmlFor="old">Current password</Label><Input id="old" type="password" autoComplete="current-password" value={pw.old} onChange={(e) => setPw({ ...pw, old: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="new">New password</Label><Input id="new" type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setPwOpen(false)}>Cancel</Button><Button onClick={changePassword} disabled={pw.next.length < 8}><Plus className="hidden" />Update</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
