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
import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { artifactLook, pinnedFirst } from "@/lib/desk";
import { capitalize } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useRelativeTime } from "./useRelativeTime";

// A document says what it is before you read its name.
const LOOKS = {
  brief: { Icon: FileText, className: "bg-primary/15 text-primary" },
  report: { Icon: FileBarChart2, className: "bg-[var(--orange)]/15 text-brand" },
  data: { Icon: Table2, className: "bg-success/15 text-success" },
  image: { Icon: ImageIcon, className: "bg-muted text-muted-foreground" },
};

// The words for artifactLook()'s codes; `kind` is the artifact's own kind
// string, an enum the catalogue does not translate.
const LOOK_LABEL = {
  brief: msg`Brief`,
  report: msg`Report`,
  data: msg`Data`,
  image: msg`Image`,
  document: msg`Document`,
};

function lookLabel(look, i18n) {
  if (look.code === "kind") return capitalize(look.kind);
  return LOOK_LABEL[look.code] ? i18n._(LOOK_LABEL[look.code]) : "";
}

/** A thread's state, in the words someone would use out loud. The run status
 *  comes from the list route, so a thread stuck on a question or a rejected
 *  key says so here, before anyone opens it. */
function threadState(conv, i18n) {
  if (conv.status === "archived") return { label: i18n._(msg`Closed`), className: "text-muted-foreground" };
  switch (conv.run_status) {
    case "running":
      return { label: i18n._(msg`Working…`), className: "text-primary animate-pulse" };
    case "paused":
      return { label: i18n._(msg`Needs you`), className: "text-warning font-medium" };
    case "failed":
      return { label: i18n._(msg`Failed`), className: "text-destructive font-medium" };
    case "cancelled":
      return { label: i18n._(msg`Stopped`), className: "text-muted-foreground" };
    default:
      break;
  }
  if (conv.last_seq === 0) return { label: i18n._(msg`Not started`), className: "text-muted-foreground" };
  return { label: i18n._(msg`Open`), className: "text-primary" };
}

function PinButton({ pinned, onToggle, label }) {
  const { t } = useLingui();
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
      aria-pressed={pinned}
      aria-label={pinned ? t`Unpin ${label}` : t`Pin ${label}`}
      className={cn(
        "rounded p-0.5 transition-opacity",
        pinned
          ? "text-brand opacity-100"
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
      className="group grid cursor-pointer grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-3 border-b border-border/60 py-3 last:border-0 hover:bg-accent/40 @lg:grid-cols-[20px_minmax(0,1fr)_130px_110px_150px]"
    >
      {children}
    </div>
  );
}

export default function DeskLists({ conversations, artifacts, onPinThread, onPinArtifact }) {
  const { t, i18n } = useLingui();
  const router = useRouter();
  const [tab, setTab] = useState("threads");

  const threads = pinnedFirst(conversations, (c) => c.last_active_at || c.created_at);
  const docs = pinnedFirst(artifacts, (a) => a.created_at);
  const ago = useRelativeTime();

  return (
    <Tabs value={tab} onValueChange={setTab} className="gap-3">
      <TabsList>
        <TabsTrigger value="threads"><Trans>Threads</Trans></TabsTrigger>
        <TabsTrigger value="artifacts"><Trans>Artifacts</Trans></TabsTrigger>
      </TabsList>

      <TabsContent value="threads">
        {threads.length === 0 ? (
          <p className="py-4 text-xs text-muted-foreground">
            <Trans>No threads yet. Ask something below and one starts.</Trans>
          </p>
        ) : (
          <div>
            {threads.map((conv) => {
              const state = threadState(conv, i18n);
              const title = conv.title || t`Untitled thread`;
              const messageCount = conv.last_seq;
              return (
                <Row
                  key={conv.id}
                  onClick={() => router.push(`/insights/session?conversation=${conv.id}`)}
                >
                  <PinButton
                    pinned={Boolean(conv.pinned)}
                    label={conv.title || t`thread`}
                    onToggle={() => onPinThread(conv)}
                  />
                  <span className="truncate text-sm font-medium" title={title}>
                    {title}
                  </span>
                  <span className={cn("hidden text-xs @lg:block", state.className)}>
                    {state.label}
                  </span>
                  <span className="hidden text-xs text-muted-foreground @lg:block">
                    {ago(conv.last_active_at || conv.created_at)}
                  </span>
                  <span className="hidden text-xs text-muted-foreground @lg:block">
                    {messageCount ? <Plural value={messageCount} one="# message" other="# messages" /> : "—"}
                  </span>
                </Row>
              );
            })}
          </div>
        )}
      </TabsContent>

      <TabsContent value="artifacts">
        {docs.length === 0 ? (
          <p className="py-4 text-xs text-muted-foreground">
            <Trans>Nothing written yet. Artifacts a thread produces collect here.</Trans>
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
              const title = doc.title || doc.filename || t`Untitled`;
              const version = doc.version;
              const versionCount = doc.version_count;
              return (
                <Row key={doc.id} onClick={() => router.push(href)}>
                  <PinButton
                    pinned={Boolean(doc.pinned)}
                    label={doc.title || t`document`}
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
                    <span
                      className="truncate text-sm font-medium"
                      title={title}
                    >
                      {title}
                    </span>
                  </span>
                  <span className="hidden text-xs text-muted-foreground @lg:block">
                    {lookLabel(look, i18n)}
                  </span>
                  <span className="hidden text-xs text-muted-foreground @lg:block">
                    {versionCount > 1 ? t`v${version} of ${versionCount}` : t`v${version}`}
                  </span>
                  <span className="hidden text-xs text-muted-foreground @lg:block">
                    {ago(doc.created_at)}
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
