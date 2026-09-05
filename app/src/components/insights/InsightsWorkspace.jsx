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
import AgentChat from "@/components/workspace/AgentChat";
import SplitWorkspace from "@/components/workspace/SplitWorkspace";
import { MarkdownView } from "@/components/artifacts/ArtifactRenderer";
import { useAgentSession } from "../../hooks/useAgentSession";
import { getArtifactContent, listArtifactVersions } from "../../lib/artifactsApi";
import { InsightsEvent, InsightsStep } from "../../lib/insightsEvents";
import { frontMatterTitle, sniffFormat, stripFrontMatter } from "../../lib/brief";
import { loadPreferences } from "../../lib/userPreferences";

const AGENT_TYPE = "insights";

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
  // Streamed brief text also lives in a ref: the event callback would
  // otherwise close over a stale value on every chunk.
  const briefRef = useRef("");

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
        setPane("brief");
        break;
      }
      case InsightsEvent.STEP_FINISHED:
        // The runner emits one per data pull, labelled with the window it
        // covers. Anything else with a step_id is ignored rather than guessed at.
        if (event.step_id === InsightsStep.COLLECT_SOURCE_DATA) {
          setFetched((prev) => [...prev, { label: event.label || "", ok: event.status === "success" }]);
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
  });

  // A stored document in the right pane, from the desk, where opening a brief
  // means opening the thread that argued for it.
  useEffect(() => {
    if (!artifactId) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const rows = await listArtifactVersions(artifactId);
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
        if (cancelled) return;
        setVersions((prev) => {
          const byVersion = new Map(loaded.map((v) => [v.version, v]));
          for (const v of prev) byVersion.set(v.version, v);
          return [...byVersion.values()].sort((a, b) => a.version - b.version);
        });
        setSelected(-1);
        setPane("brief");
      } catch {
        /* the thread still opens; the pane just starts empty */
      }
    })();
    return () => { cancelled = true; };
  }, [artifactId]);

  function handleRetry() {
    setFetched([]);
    setWriting("");
    briefRef.current = "";
    agent.retry();
  }

  const shown = versions.length ? versions[selected < 0 ? versions.length - 1 : selected] : null;
  const hasBrief = Boolean(shown) || Boolean(writing);

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
      inputPlaceholder="Ask about your growth data…"
      inputAriaLabel="Message the insights agent"
      startingLabel="Opening the session…"
      headerExtra={<AutonomyBadge autonomy={agent.started} />}
    />
  );

  const viewport = (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-1 border-b border-border/60 px-2 py-1.5">
        <PaneTab active={pane === "brief"} onClick={() => setPane("brief")}>
          Brief
        </PaneTab>
        <PaneTab active={pane === "data"} onClick={() => setPane("data")}>
          Data{fetched.length ? ` · ${fetched.length}` : ""}
        </PaneTab>
        {pane === "brief" && versions.length > 1 && (
          <select
            value={selected < 0 ? versions.length - 1 : selected}
            aria-label="Brief version"
            onChange={(e) => setSelected(Number(e.target.value))}
            className="ml-auto rounded-md border border-input bg-background px-2 py-1 text-[11px]"
          >
            {versions.map((v, i) => (
              <option key={v.version} value={i}>
                v{v.version} — {v.label}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {pane === "brief" ? <BriefPane brief={shown} writing={writing} empty={!hasBrief} /> : <DataPane fetched={fetched} />}
      </div>
    </div>
  );

  return (
    <SplitWorkspace
      left={chat}
      right={viewport}
      storageKey="insights_split_w"
      leftLabel="Chat"
      rightLabel="Brief"
      rightStatus={writing || agent.isRunning ? "busy" : hasBrief ? "ready" : "idle"}
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
function AutonomyBadge({ autonomy }) {
  const level = autonomy?.autonomy || "";
  const configured = autonomy?.autonomy_configured || "";
  if (!level) return null;
  const steppedDown = configured && configured !== level;
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
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
function BriefPane({ brief, writing, empty }) {
  // While it streams there is no parsed version yet, so the front matter has
  // to come off here and the format has to be read from the bytes.
  const live = useMemo(() => stripFrontMatter(writing), [writing]);
  const liveTitle = useMemo(() => frontMatterTitle(writing), [writing]);

  if (writing) {
    return (
      <div>
        <BriefHeader title={liveTitle || "Writing…"} sub="being written" />
        <div className="px-1">
          {sniffFormat(live) === "markdown" ? (
            <MarkdownView source={live} />
          ) : (
            <pre className="whitespace-pre-wrap p-3 text-xs">{live}</pre>
          )}
        </div>
      </div>
    );
  }

  if (empty || !brief) {
    return (
      <p className="p-4 text-xs text-muted-foreground">
        Nothing written yet. When Duct has an answer worth keeping it writes a brief
        here — versioned, so you can see what changed between reads.
      </p>
    );
  }

  return (
    <div>
      <BriefHeader title={brief.title} sub={`v${brief.version} · ${brief.label}`} />
      {brief.format === "html" ? (
        <iframe
          title={brief.title}
          srcDoc={brief.content}
          sandbox="allow-modals allow-same-origin"
          className="h-[74vh] w-full border-0 bg-white"
        />
      ) : (
        <div className="px-1">
          <MarkdownView source={brief.content} />
        </div>
      )}
    </div>
  );
}

function BriefHeader({ title, sub }) {
  return (
    <div className="flex items-baseline gap-2 border-b border-border/40 px-4 py-2">
      <span className="truncate text-xs font-medium">{title}</span>
      <span className="shrink-0 text-[11px] text-muted-foreground">{sub}</span>
    </div>
  );
}

/** What the agent pulled, and the window each pull covers. */
function DataPane({ fetched }) {
  if (!fetched.length) {
    return (
      <p className="p-4 text-xs text-muted-foreground">
        Nothing yet. Duct pulls only what your question needs, and shows each source
        and the period it covers here.
      </p>
    );
  }
  return (
    <ul className="space-y-1.5 p-4">
      {fetched.map((f, i) => (
        <li key={i} className="flex items-start gap-2 text-xs">
          <span className={f.ok ? "text-green-500" : "text-destructive"} aria-hidden="true">
            {f.ok ? "✓" : "!"}
          </span>
          <span className={f.ok ? "" : "text-muted-foreground"}>{f.label}</span>
        </li>
      ))}
    </ul>
  );
}
