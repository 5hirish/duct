"use client";

// Threads and the documents they produced, in two tabs.
//
// They are not the same list at two zoom levels: a THREAD has a state (paused,
// answered, ran unattended) and a DOCUMENT has a type and a version. Both are
// pinnable, and a pin means one thing in both places — float to the top of your
// own tab. Not a shared shelf: mixing types in one pinned strip makes "pinned"
// mean something different from the list it sits above.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { FileText, FileBarChart2, Table2, Image as ImageIcon, Pin } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { artifactLook, pinnedFirst, relativeTime } from "@/lib/desk";
import { cn } from "@/lib/utils";

// A document says what it is before you read its name.
const LOOKS = {
  brief: { Icon: FileText, className: "bg-primary/15 text-primary" },
  report: { Icon: FileBarChart2, className: "bg-[var(--orange)]/15 text-[var(--orange)]" },
  data: { Icon: Table2, className: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" },
  image: { Icon: ImageIcon, className: "bg-muted text-muted-foreground" },
};

/** A thread's state, in the words someone would use out loud. */
function threadState(conv) {
  if (conv.status === "archived") return { label: "Closed", className: "text-muted-foreground" };
  if (conv.last_seq === 0) return { label: "Not started", className: "text-muted-foreground" };
  return { label: "Open", className: "text-primary" };
}

function PinButton({ pinned, onToggle, label }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
      aria-pressed={pinned}
      aria-label={pinned ? `Unpin ${label}` : `Pin ${label}`}
      className={cn(
        "rounded p-0.5 transition-opacity",
        pinned
          ? "text-[var(--orange)] opacity-100"
          : "text-muted-foreground opacity-0 group-hover:opacity-70 focus-visible:opacity-100"
      )}
    >
      <Pin className="size-3.5" fill={pinned ? "currentColor" : "none"} />
    </button>
  );
}

function Row({ children, onClick }) {
  return (
    <div
      role="link"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className="group grid cursor-pointer grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-3 border-b border-border/60 py-3 last:border-0 hover:bg-accent/40 sm:grid-cols-[20px_minmax(0,1fr)_130px_110px_150px]"
    >
      {children}
    </div>
  );
}

export default function DeskLists({ conversations, artifacts, onPinThread, onPinArtifact }) {
  const router = useRouter();
  const [tab, setTab] = useState("threads");

  const threads = pinnedFirst(conversations, (c) => c.last_active_at || c.created_at);
  const docs = pinnedFirst(artifacts, (a) => a.created_at);

  return (
    <Tabs value={tab} onValueChange={setTab} className="gap-3">
      <TabsList>
        <TabsTrigger value="threads">Threads</TabsTrigger>
        <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
      </TabsList>

      <TabsContent value="threads">
        {threads.length === 0 ? (
          <p className="py-4 text-[12.5px] text-muted-foreground">
            No threads yet. Ask something below and one starts.
          </p>
        ) : (
          <div>
            {threads.map((conv) => {
              const state = threadState(conv);
              return (
                <Row
                  key={conv.id}
                  onClick={() => router.push(`/insights/session?conversation=${conv.id}`)}
                >
                  <PinButton
                    pinned={Boolean(conv.pinned)}
                    label={conv.title || "thread"}
                    onToggle={() => onPinThread(conv)}
                  />
                  <span className="truncate text-[13.5px] font-medium">
                    {conv.title || "Untitled thread"}
                  </span>
                  <span className={cn("hidden text-[12px] sm:block", state.className)}>
                    {state.label}
                  </span>
                  <span className="hidden text-[12px] text-muted-foreground sm:block">
                    {relativeTime(conv.last_active_at || conv.created_at)}
                  </span>
                  <span className="hidden text-[12px] text-muted-foreground sm:block">
                    {conv.last_seq ? `${conv.last_seq} messages` : "—"}
                  </span>
                </Row>
              );
            })}
          </div>
        )}
      </TabsContent>

      <TabsContent value="artifacts">
        {docs.length === 0 ? (
          <p className="py-4 text-[12.5px] text-muted-foreground">
            Nothing written yet. Briefs a thread produces collect here.
          </p>
        ) : (
          <div>
            {docs.map((doc) => {
              const look = artifactLook(doc);
              const { Icon, className } = LOOKS[look.tone] || LOOKS.data;
              // Opening a document opens the thread that wrote it, with the
              // document already on screen — a brief you cannot question is
              // just a PDF.
              const href = doc.conversation_id
                ? `/insights/session?conversation=${doc.conversation_id}&artifact=${doc.id}`
                : `/artifacts/${doc.id}`;
              return (
                <Row key={doc.id} onClick={() => router.push(href)}>
                  <PinButton
                    pinned={Boolean(doc.pinned)}
                    label={doc.title || "document"}
                    onToggle={() => onPinArtifact(doc)}
                  />
                  <span className="flex min-w-0 items-center gap-3">
                    <span
                      className={cn(
                        "flex size-7 shrink-0 items-center justify-center rounded-lg",
                        className
                      )}
                      aria-hidden
                    >
                      <Icon className="size-3.5" />
                    </span>
                    <span className="truncate text-[13.5px] font-medium">
                      {doc.title || doc.filename || "Untitled"}
                    </span>
                  </span>
                  <span className="hidden text-[12px] text-muted-foreground sm:block">
                    {look.label}
                  </span>
                  <span className="hidden text-[12px] text-muted-foreground sm:block">
                    {doc.version_count > 1 ? `v${doc.version} of ${doc.version_count}` : `v${doc.version}`}
                  </span>
                  <span className="hidden text-[12px] text-muted-foreground sm:block">
                    {relativeTime(doc.created_at)}
                  </span>
                </Row>
              );
            })}
          </div>
        )}
      </TabsContent>
    </Tabs>
  );
}
