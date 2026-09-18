"use client";

/**
 * The insights session UI — one chat, no wizard.
 *
 * What it replaces: a six-step form (sources → Ads account → GA4 property →
 * GSC site → goal → review) that had to be completed before the agent ran at
 * all. Everything that form collected, the agent now discovers or asks for
 * mid-run, so most of what this component renders is *a pause*: a question, a
 * connect offer, or an account choice, inline in the transcript.
 *
 * The session itself — create, stream, reconnect, resume, the pause cards,
 * retry — is `useAgentSession`, the same hook the content and audit
 * workspaces run on. Opening a stored thread resumes it: the transcript is
 * rehydrated, a question the thread is still parked on comes back as its
 * card, and a run that was cut mid-turn picks up where it stopped. Nothing
 * here re-runs a prompt because the tab was reloaded.
 *
 * The right pane is the deliverable. The agent writes its brief inside
 * `<duct_artifact>`, which streams — so the pane fills in as the brief is
 * written, then settles into a stored version when the tag closes. Versions
 * accumulate within a session; the picker appears once there is a second one.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Database, FileText } from "lucide-react";
import AgentChat from "@/components/workspace/AgentChat";
import EmptyState from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton, SkeletonDocument } from "@/components/ui/skeleton";
import ComposerDials from "@/components/workspace/ComposerDials";
import SplitWorkspace from "@/components/workspace/SplitWorkspace";
import { AUTONOMY_ASK } from "@/lib/projectsApi";
import { getProjectById } from "@/lib/projects";
import { MarkdownView } from "@/components/artifacts/ArtifactRenderer";
import { ArtifactGallery } from "@/components/artifacts/ArtifactCards";
import { useAgentSession } from "../../hooks/useAgentSession";
import { getArtifactContent, listArtifacts, listArtifactVersions } from "../../lib/artifactsApi";
import { InsightsEvent, InsightsStep } from "../../lib/insightsEvents";
import { frontMatterTitle, sniffFormat, stripFrontMatter } from "../../lib/brief";
import { fetchedFromEvents } from "../../lib/insightsHistory";
import { loadPreferences } from "../../lib/userPreferences";

const AGENT_TYPE = "insights";
// `openedGroup` for the brief being written in this session, which has no
// stored group id until its first version lands.
const LIVE_GROUP = "live";

export default function InsightsWorkspace({
  projectId,
  initialPrompt = "",
  conversationId = "",
  artifactId = "",
}) {
  // What the agent pulled, in order.
  const [fetched, setFetched] = useState([]);
  // The brief: every version this session produced, plus the one being written.
  const [versions, setVersions] = useState([]);
  const [selected, setSelected] = useState(-1);   // -1 = follow the latest
  const [writing, setWriting] = useState("");
  const [pane, setPane] = useState("brief");      // brief | data
  // Every document this thread has written (latest version per group), and
  // which one the pane is showing: null is the gallery, LIVE_GROUP is the
  // one being written in this session, otherwise a stored group's id.
  const [docs, setDocs] = useState([]);
  const [openedGroup, setOpenedGroup] = useState(null);
  const openedGroupRef = useRef(null);
  openedGroupRef.current = openedGroup;
  // Bumped when a version lands, so the gallery learns about the new group.
  const [docsRefresh, setDocsRefresh] = useState(0);
  // A later open supersedes an earlier one still loading.
  const openTokenRef = useRef(0);
  // What the pane is waiting on. `opening` is a document's versions on their
  // way in; `docsPending` is the thread's document list on a reopen, before
  // we know whether there is anything to show at all. Either way the pane
  // shows the shape of a brief rather than "Nothing written yet", which used
  // to flash for the half-second before the brief you came back for arrived.
  const [opening, setOpening] = useState(false);
  const [docsPending, setDocsPending] = useState(Boolean(conversationId));
  // Streamed brief text also lives in a ref: the event callback would
  // otherwise close over a stale value on every chunk.
  const briefRef = useRef("");
  // The posture this conversation runs at. Seeded from the stored project,
  // corrected by PIPELINE_STARTED (the backend may step it down for the
  // model), and changed from the composer chip — which writes the project
  // and reaches the agent at its next message.
  const [autonomy, setAutonomy] = useState(
    () => (projectId && getProjectById(projectId)?.autonomyLevel) || AUTONOMY_ASK,
  );

  const body = useMemo(
    () => ({
      project_id: projectId || null,
      prompt: initialPrompt,
      // Resuming extends the stored thread rather than opening a second one,
      // so the brief keeps versioning up from where it left off.
      ...(conversationId ? { conversation_id: conversationId, resume: true } : {}),
      // Carries the deliverable format the agent should write in, among the
      // rest of the profile.
      user_preferences: loadPreferences(),
    }),
    [projectId, initialPrompt, conversationId],
  );

  const onEvent = useCallback((event) => {
    switch (event.event) {
      case InsightsEvent.ARTIFACT_CHUNK:
        // The brief, arriving. Show it being written rather than waiting for
        // the closing tag — a long brief is a long silence otherwise.
        briefRef.current += event.text || "";
        setWriting(briefRef.current);
        setPane("brief");
        break;
      case InsightsEvent.ARTIFACT_VERSION: {
        briefRef.current = "";
        setWriting("");
        const payload = event.payload || {};
        setVersions((prev) => [
          ...prev.filter((v) => v.version !== event.version_id),
          {
            version: event.version_id,
            label: event.label || `Version ${event.version_id}`,
            title: payload.title || "Growth brief",
            format: payload.format || "markdown",
            content: payload.content || "",
          },
        ].sort((a, b) => a.version - b.version));
        setSelected(-1);  // a new version is what you want to be looking at
        setOpenedGroup(LIVE_GROUP);
        setDocsRefresh((n) => n + 1);
        setPane("brief");
        break;
      }
      case InsightsEvent.STEP_FINISHED:
        // The runner emits one per data pull, labelled with the window it
        // covers. Anything else with a step_id is ignored rather than guessed at.
        if (event.step_id === InsightsStep.COLLECT_SOURCE_DATA) {
          const row = { label: event.label || "", ok: event.status === "success", error: event.error || "" };
          // A reattached run replays pulls the stored history already listed.
          setFetched((prev) => (prev.some((f) => f.label === row.label && f.ok === row.ok) ? prev : [...prev, row]));
        }
        break;
      default:
        break;
    }
  }, []);

  const agent = useAgentSession({
    agentType: AGENT_TYPE,
    notifyAs: "Insights",
    body,
    // A thread by its id, a fresh question by its text: a different question
    // in the same tab is a different run, and a reload of this one is this one.
    handleKey: `${AGENT_TYPE}:${projectId || ""}:${conversationId || `q:${initialPrompt}`}`,
    hydrateThreadState: true,
    onEvent,
    // The Data pane on a reopened thread: every pull is in the stored tool
    // traffic, so it lists the same rows it showed live.
    onHydrate: (events) => setFetched(fetchedFromEvents(events)),
  });

  useEffect(() => {
    const level = agent.started?.autonomy;
    if (level) setAutonomy(level);
  }, [agent.started?.autonomy]);

  // Put a stored document in the right pane: every version of its group,
  // newest selected. `id` is any version's id; the route resolves the group.
  const openGroup = useCallback(async (id) => {
    const token = ++openTokenRef.current;
    setOpening(true);
    try {
      const rows = await listArtifactVersions(id);
      const ordered = [...rows].sort((a, b) => a.version - b.version);
      const loaded = await Promise.all(
        ordered.map(async (row) => {
          let content = "";
          try {
            content = row.has_content ? await getArtifactContent(row.id) : "";
          } catch {
            /* a version whose bytes are gone still belongs in the picker */
          }
          return {
            version: row.version,
            label: `Version ${row.version}`,
            title: row.title || "Growth brief",
            // The stored MIME type is authoritative; sniffing is the fallback
            // for rows written before content_type was recorded.
            format: (row.content_type || "").includes("html") ? "html" : sniffFormat(content),
            content,
          };
        }),
      );
      if (token !== openTokenRef.current) return;
      setVersions(loaded);
      setSelected(-1);
      setOpenedGroup(ordered[0]?.group_id || id);
      setPane("brief");
    } catch {
      /* the thread still opens; the pane just starts empty */
    } finally {
      // Only the newest open owns the flag; a superseded one must not clear
      // it under the load that replaced it.
      if (token === openTokenRef.current) setOpening(false);
    }
  }, []);

  // From the desk, where opening a brief means opening the thread that
  // argued for it: the named document goes straight into the pane.
  useEffect(() => {
    if (artifactId) openGroup(artifactId);
  }, [artifactId, openGroup]);

  // Reopening a thread by id alone used to leave the pane empty however many
  // briefs the thread had written — only the desk's ?artifact= link loaded
  // one. Now the thread's documents are listed on open: one is shown as it
  // was, several become the gallery, and nothing needs a click to see the
  // brief you came back for.
  useEffect(() => {
    if (!conversationId || !projectId) {
      setDocsPending(false);
      return undefined;
    }
    let cancelled = false;
    listArtifacts({ projectId, agentType: AGENT_TYPE, conversationId })
      .then((rows) => {
        if (cancelled) return;
        const list = Array.isArray(rows) ? rows : [];
        setDocs(list);
        if (!artifactId && list.length === 1 && openedGroupRef.current === null) {
          openGroup(list[0].id);
        }
      })
      .catch(() => {
        /* the list is a convenience; the thread still opens */
      })
      .finally(() => {
        if (!cancelled) setDocsPending(false);
      });
    return () => { cancelled = true; };
  }, [conversationId, projectId, artifactId, docsRefresh, openGroup]);

  function showGallery() {
    openTokenRef.current += 1;  // drop a load still in flight
    setOpening(false);
    setOpenedGroup(null);
    setVersions([]);
    setSelected(-1);
    setPane("brief");
  }

  function handleRetry() {
    setFetched([]);
    setWriting("");
    briefRef.current = "";
    agent.retry();
  }

  const shown = versions.length ? versions[selected < 0 ? versions.length - 1 : selected] : null;
  const hasBrief = Boolean(shown) || Boolean(writing);
  // A document on its way in, or a reopened thread whose list has not come
  // back yet: the pane keeps a brief's shape rather than declaring it empty.
  const loadingBrief = !writing && (opening || (docsPending && !hasBrief));
  // The gallery is for choosing between several; a single document, or one
  // being written right now, is simply shown.
  const gallery = docs.length > 1 && openedGroup === null && !writing && !opening;

  // A connect asked for mid-run comes back to this thread, resumed — never to
  // the ?q= form of this page, which would ask the question again from scratch.
  const connectReturnTo = useMemo(() => {
    const cid = agent.conversationId || conversationId;
    if (!cid) return "";
    const qs = new URLSearchParams({ conversation: cid });
    if (projectId) qs.set("project", projectId);
    return `/insights/session?${qs}`;
  }, [agent.conversationId, conversationId, projectId]);

  const chat = (
    <AgentChat
      title="Insights"
      phase={agent.phase}
      steps={agent.steps}
      todos={agent.todos}
      messages={agent.messages}
      pending={agent.pending}
      errorMsg={agent.error}
      errorCode={agent.errorCode}
      errorRetryable={agent.errorRetryable}
      retrying={agent.retrying}
      tierStepDown={agent.tierStepDown}
      usage={agent.usage}
      compacting={agent.compacting}
      draft={agent.draft}
      isAgentTyping={agent.isAgentTyping}
      isStreaming={agent.isStreaming}
      reconnecting={agent.reconnecting}
      inputDisabled={agent.inputDisabled}
      answerDisabled={!agent.attached}
      onAnswer={agent.answer}
      onSendMessage={agent.send}
      onRetrySend={agent.send}
      onRetry={handleRetry}
      onStop={() => agent.stop({ keepReady: agent.opened })}
      questionsCopy={QUESTIONS_COPY}
      connectReturnTo={connectReturnTo}
      composerTools={
        <ComposerDials projectId={projectId} autonomy={autonomy} onAutonomyChange={setAutonomy} deferred />
      }
      inputPlaceholder="Ask about your growth data…"
      inputAriaLabel="Message the insights agent"
      startingLabel="Opening the session…"
      headerExtra={<AutonomyBadge autonomy={agent.started} level={autonomy} />}
    />
  );

  const viewport = (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-1 border-b border-border/60 px-2 py-1.5">
        <PaneTab active={pane === "brief"} onClick={() => setPane("brief")}>
          Artifact
        </PaneTab>
        <PaneTab active={pane === "data"} onClick={() => setPane("data")}>
          Data{fetched.length ? ` · ${fetched.length}` : ""}
        </PaneTab>
        {pane === "brief" && docs.length > 1 && openedGroup !== null && (
          <button
            type="button"
            onClick={showGallery}
            className="ml-auto rounded-md px-2 py-1 text-2xs text-muted-foreground hover:text-foreground"
          >
            All documents · {docs.length}
          </button>
        )}
        {pane === "brief" && versions.length > 1 && (
          <select
            value={selected < 0 ? versions.length - 1 : selected}
            aria-label="Artifact version"
            onChange={(e) => setSelected(Number(e.target.value))}
            className={`rounded-md border border-input bg-background px-2 py-1 text-2xs ${
              docs.length > 1 ? "ml-1" : "ml-auto"
            }`}
          >
            {versions.map((v, i) => (
              <option key={v.version} value={i}>
                v{v.version} — {v.label}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* The brief sits on a muted ground, as a document rather than as
          more of the page: the chat and the pane were the same white, and
          the artifact read as a continuation of the transcript. */}
      <div className={`min-h-0 flex-1 overflow-y-auto ${pane === "brief" ? "bg-muted/40" : ""}`}>
        {pane !== "brief" ? (
          <DataPane fetched={fetched} />
        ) : gallery ? (
          <ArtifactGallery docs={docs} onOpen={(doc) => openGroup(doc.id)} />
        ) : (
          <BriefPane brief={shown} writing={writing} empty={!hasBrief} loading={loadingBrief} />
        )}
      </div>
    </div>
  );

  return (
    <SplitWorkspace
      left={chat}
      right={viewport}
      storageKey="insights_split_w"
      leftLabel="Chat"
      rightLabel="Artifact"
      rightStatus={writing || agent.isRunning || loadingBrief ? "busy" : hasBrief ? "ready" : "idle"}
    />
  );
}

const QUESTIONS_COPY = {
  hint: "Your answer decides what Duct looks at. Skip if you'd rather it choose.",
};

const AUTONOMY_LABELS = {
  ask: "Asks freely · nothing applies without you",
  assisted: "Asks when it matters · allowlisted changes apply on their own",
  auto: "Interrupts rarely · same allowlist as Assisted",
};

/** Which mode this run is in, said before the first token.
 *
 * PIPELINE_STARTED carries `autonomy` (what the run got) and
 * `autonomy_configured` (what the project is set to). They differ when the
 * model driving it is not on the allowlist for `auto`, and saying so is the
 * difference between a considered step-down and an agent that mysteriously
 * keeps asking questions. */
function AutonomyBadge({ autonomy, level: current = "" }) {
  // The composer chip is the live value once the person touches it; the
  // event is what the run opened with.
  const level = current || autonomy?.autonomy || "";
  const configured = autonomy?.autonomy_configured || "";
  if (!level) return null;
  const steppedDown = configured && configured !== level && current === (autonomy?.autonomy || "");
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-2xs">
      <span className="rounded-full bg-muted px-2 py-0.5 font-medium uppercase tracking-wide">{level}</span>
      <span className="hidden text-muted-foreground @md:inline">{AUTONOMY_LABELS[level] || ""}</span>
      {steppedDown && (
        <span className="text-muted-foreground">
          · set to <strong>{configured}</strong>, stepped down for this model
        </span>
      )}
    </span>
  );
}

function PaneTab({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
        active ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

/** The deliverable. A finished version when there is one, otherwise the one
 *  being written — which is the same document a few seconds earlier. */
// Exported for /preview only, the UsagePanel/UsageEmpty precedent: these two
// panes' empty states are the states a reviewer most needs to open and the
// ones no fixture-free gallery could otherwise reach.
export function BriefPane({ brief, writing, empty, loading }) {
  // While it streams there is no parsed version yet, so the front matter has
  // to come off here and the format has to be read from the bytes.
  const live = useMemo(() => stripFrontMatter(writing), [writing]);
  const liveTitle = useMemo(() => frontMatterTitle(writing), [writing]);

  if (writing) {
    return (
      <div>
        <BriefHeader title={liveTitle || "Writing…"} sub="being written" />
        <div className="m-4 rounded-xl border border-border bg-card px-3 shadow-sm">
          {sniffFormat(live) === "markdown" ? (
            <MarkdownView source={live} />
          ) : (
            <pre className="whitespace-pre-wrap p-3 text-xs">{live}</pre>
          )}
        </div>
      </div>
    );
  }

  if (loading && !brief) {
    return (
      // The pane's own anatomy, drawn in skeleton: the header strip, then a
      // document card. It swaps texture for words when the bytes land, and
      // never claims the thread is empty while the answer is still on its way.
      <div>
        <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2.5">
          <Skeleton className="h-3 w-40 rounded" />
          <Skeleton className="h-2.5 w-16 rounded" />
        </div>
        <div className="m-4 rounded-xl border border-border bg-card p-4 shadow-sm">
          <SkeletonDocument label="Loading the brief" />
        </div>
      </div>
    );
  }

  if (empty || !brief) {
    return (
      // No CTA on purpose, which is the one case ui/empty-state allows. What
      // fills this pane is the agent deciding an answer is worth keeping, and
      // the control for that is the composer already on screen beside it — a
      // button here could only say "go and type over there".
      <div className="p-4">
        <EmptyState icon={FileText} title="Nothing written yet">
          An answer worth keeping becomes an artifact here, and versions pile up as it is
          rewritten.
        </EmptyState>
      </div>
    );
  }

  return (
    <div>
      <BriefHeader title={brief.title} sub={`v${brief.version} · ${brief.label}`} />
      <div className="m-4 overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        {brief.format === "html" ? (
          <iframe
            title={brief.title}
            srcDoc={brief.content}
            sandbox="allow-modals allow-same-origin"
            className="block h-[74vh] w-full border-0 bg-white"
          />
        ) : (
          <div className="px-3">
            <MarkdownView source={brief.content} />
          </div>
        )}
      </div>
    </div>
  );
}

function BriefHeader({ title, sub }) {
  return (
    <div className="flex items-baseline gap-2 border-b border-border/40 px-4 py-2">
      <span className="truncate text-xs font-medium">{title}</span>
      <span className="shrink-0 text-2xs text-muted-foreground">{sub}</span>
    </div>
  );
}

/** What the agent pulled, and the window each pull covers. */
export function DataPane({ fetched }) {
  if (!fetched.length) {
    return (
      // This one does get a CTA, because its most common cause is actionable:
      // the pane stays empty for a whole thread when nothing is connected, and
      // that is the state the agent spends the conversation apologising for.
      <div className="p-4">
        <EmptyState
          icon={Database}
          title="No sources pulled yet"
          actions={
            <Button size="sm" variant="outline" asChild>
              <Link href="/connections">Check connections</Link>
            </Button>
          }
        >
          Each source Duct reads shows up here with the period it covers, and the provider&rsquo;s
          own words when a pull fails.
        </EmptyState>
      </div>
    );
  }
  return (
    <ul className="space-y-1.5 p-4">
      {fetched.map((f, i) => (
        <li key={i} className="flex items-start gap-2 text-xs">
          <span className={f.ok ? "text-success" : "text-destructive"} aria-hidden="true">
            {f.ok ? "✓" : "!"}
          </span>
          <span className={f.ok ? "" : "text-muted-foreground"}>
            {f.label}
            {/* The provider's own sentence. The chat paraphrases a failure;
                this is where the person debugging it reads the real one. */}
            {!f.ok && f.error && (
              <span className="mt-0.5 block break-words font-mono text-2xs text-destructive/80">{f.error}</span>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}
