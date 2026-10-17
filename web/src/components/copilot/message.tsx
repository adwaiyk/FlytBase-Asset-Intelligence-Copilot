"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BookOpen, BrainCircuit, ChevronDown, FileSearch, ShieldAlert, Sparkles, User2, Wrench, Database } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { VisualView } from "./visuals";
import { PumpJack } from "./pumpjack";
import type { Message, Overview, Source } from "@/lib/types";

function SourceChip({ s }: { s: Source }) {
  const icon = s.kind === "doc" ? <BookOpen className="size-3" /> : s.kind === "note" || s.kind === "feedback" ? <User2 className="size-3" /> : s.kind === "report" ? <FileSearch className="size-3" /> : <Database className="size-3" />;
  const name = s.id ?? (s.doc ? `${s.doc}${s.section ? ` § ${s.section}` : ""}` : s.kind);
  const detail = s.quote ?? s.text ?? s.file ?? "";
  return (
    <span title={detail} className="inline-flex max-w-full items-center gap-1 rounded-md border bg-background/60 px-2 py-0.5 text-[11px] text-muted-foreground">
      {icon}<span className="truncate">{name}</span>{s.author ? <span className="text-foreground/70">· {s.author}</span> : null}
    </span>
  );
}

export function MessageView({ m, overview }: { m: Message; overview?: Overview | null }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] break-words rounded-2xl rounded-br-sm bg-primary/15 px-4 py-2.5 text-sm leading-relaxed ring-1 ring-primary/25">{m.content}</div>
      </div>
    );
  }
  const p = m.payload ?? {};
  return (
    <div className="flex gap-3">
      <div className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 ring-1 ring-primary/30"><PumpJack className="h-5 w-6" /></div>
      <div className="min-w-0 flex-1">
        {m.pending ? (
          <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground"><Sparkles className="size-4 animate-pulse text-primary" /> Reading the records, manuals and notes…</div>
        ) : (
          <>
            {p.memory_writes?.map((w) => (
              <div key={w.id + w.kind} className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                <Badge variant={w.status === "applied" ? "success" : "warning"}><BrainCircuit /> Remembered {w.id !== "PREF" ? w.id : ""}</Badge>
                <span className="text-muted-foreground">{w.kind.replaceAll("_", " ")} · {w.status}{w.kind === "private_preference" ? " · only you" : " · shared with the team"}</span>
              </div>
            ))}
            <div className="prose-chat text-sm"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content || "_No answer._"}</ReactMarkdown></div>
            {p.conflicts?.map((c) => (
              <Alert key={c} variant="warning" className="mt-3"><ShieldAlert /><AlertDescription>{c}</AlertDescription></Alert>
            ))}
            <VisualView v={p.visual} overview={overview} />
            {!!p.sources?.length && (
              <Collapsible className="mt-3">
                <CollapsibleTrigger className="group flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                  <FileSearch className="size-3.5" /> Evidence · {p.sources.length} sources <ChevronDown className="size-3.5 transition group-data-[state=open]:rotate-180" />
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-2 flex flex-wrap gap-1.5">{p.sources.map((s, i) => <SourceChip key={i} s={s} />)}</CollapsibleContent>
              </Collapsible>
            )}
            {!!p.trace?.length && (
              <Collapsible className="mt-1.5">
                <CollapsibleTrigger className="group flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                  <Wrench className="size-3.5" /> How I answered · {p.trace.length} tool calls · {p.model} <ChevronDown className="size-3.5 transition group-data-[state=open]:rotate-180" />
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-2 grid gap-1">
                  {p.trace.map((t, i) => (
                    <code key={i} className="block overflow-x-auto rounded-md bg-muted/60 px-2 py-1 text-[11px]">
                      {t.tool}({JSON.stringify(t.args ?? {})}){t.error ? ` → ${t.error}` : ""}
                    </code>
                  ))}
                </CollapsibleContent>
              </Collapsible>
            )}
            {!!p.unverified_ids?.length && <div className="mt-1 text-[11px] text-warning">Not found in tool results: {p.unverified_ids.join(", ")}</div>}
          </>
        )}
      </div>
    </div>
  );
}
