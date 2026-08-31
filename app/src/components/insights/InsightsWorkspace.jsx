"use client";

/**
 * The insights session UI — one chat, no wizard.
 *
 * What it replaces: a six-step form (sources → Ads account → GA4 property →
 * GSC site → goal → review) that had to be completed before the agent ran at
 * all. Everything that form collected, the agent now discovers or asks for
 * mid-run, which is why this component's job is mostly *rendering a pause*:
 * a question, a connect offer, or an account choice, inline in the transcript.
 *
 * All three pauses resolve through the same endpoint (`type: "answer"`), so
 * `answerPending` is one function and the card decides the payload shape.
 *
 * The right pane is the deliverable. The agent writes its brief inside
 * `<duct_artifact>`, which streams — so the pane fills in as the brief is
 * written, then settles into a stored version when the tag closes. Versions
 * accumulate within a session; the picker appears once there is a second one.
 *
 * Streaming is the shared `consumeSseStream`; the split shell, todo strip,
 * question card and markdown renderer are all components other agents use.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import AuditQuestions from "@/components/audit/AuditQuestions";
import AuditTodos from "@/components/audit/AuditTodos";
import SplitWorkspace from "@/components/workspace/SplitWorkspace";
import { MarkdownView } from "@/components/artifacts/ArtifactRenderer";
import ChangeSetCard from "@/components/execution/ChangeSetCard";
import {
  createAgentSession,
  openAgentStream,
  sendAgentMessage,
} from "../../lib/api";
import { consumeSseStream } from "../../lib/sse";
import { InsightsEvent, InsightsStep } from "../../lib/insightsEvents";
import { frontMatterTitle, sniffFormat, stripFrontMatter } from "../../lib/brief";
import { loadPreferences } from "../../lib/userPreferences";
import AccountSelect from "./AccountSelect";
import ConnectionRequest from "./ConnectionRequest";

const AGENT_TYPE = "insights";

export default function InsightsWorkspace({ projectId, initialPrompt = "" }) {
  // Turns are the transcript. A change set is a turn too — it belongs in
  // reading order beside the sentence that proposed it, not in a side panel
  // the user has to go looking for.
  const [turns, setTurns] = useState([]);        // [{role, text} | {role:"change_set", card}]
  const [streaming, setStreaming] = useState(""); // the assistant turn in flight
  const [todos, setTodos] = useState([]);
  const [pending, setPending] = useState(null);   // the pause we are showing, if any
  const [status, setStatus] = useState("idle");   // idle | running | ready | failed
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [memories, setMemories] = useState([]);
  // What the agent pulled, in order.
  const [fetched, setFetched] = useState([]);
  // The brief: every version this session produced, plus the one being written.
  const [versions, setVersions] = useState([]);
  const [selected, setSelected] = useState(-1);   // -1 = follow the latest
  const [writing, setWriting] = useState("");
  const [pane, setPane] = useState("brief");      // brief | data
  // What the run is actually operating at, and what the project is set to.
  // They differ when the model is not on the allowlist for `auto`.
  const [autonomy, setAutonomy] = useState(null);

  const sessionRef = useRef(null);
  const abortRef = useRef(null);
  // Streamed text also lives in refs: the SSE callback is created once and
  // would otherwise close over a stale value on every chunk.
  const bufferRef = useRef("");
  const briefRef = useRef("");

  const onEvent = useCallback((event) => {
    switch (event.event) {
      case InsightsEvent.AGENT_MESSAGE_CHUNK:
        bufferRef.current += event.text || "";
        setStreaming(bufferRef.current);
        break;
      case InsightsEvent.MESSAGE_STOP: {
        const text = bufferRef.current.trim();
        bufferRef.current = "";
        setStreaming("");
        if (text) setTurns((prev) => [...prev, { role: "assistant", text }]);
        break;
      }
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
          ...prev,
          {
            version: event.version_id,
            label: event.label || `Version ${event.version_id}`,
            title: payload.title || "Growth brief",
            format: payload.format || "markdown",
            content: payload.content || "",
          },
        ]);
        setSelected(-1);  // a new version is what you want to be looking at
        setPane("brief");
        break;
      }
      case InsightsEvent.TODO_UPDATE:
        setTodos(event.todos || []);
        break;
      case InsightsEvent.MEMORY_RECALLED:
        setMemories(event.memories || []);
        break;
      case InsightsEvent.STEP_FINISHED:
        // The runner emits one per data pull, labelled with the window it
        // covers. Anything else with a step_id is ignored rather than guessed at.
        if (event.step_id === InsightsStep.COLLECT_SOURCE_DATA) {
          setFetched((prev) => [
            ...prev,
            { label: event.label || "", ok: event.status === "success" },
          ]);
        }
        break;
      // The three pauses. Each carries what its card needs to render; the
      // `kind` is what tells this component which card that is.
      case InsightsEvent.QUESTIONS_REQUIRED:
        setPending({ kind: "questions", questions: event.questions || [] });
        break;
      case InsightsEvent.CONNECTION_REQUIRED:
        setPending({ kind: "connection", ...event });
        break;
      case InsightsEvent.ACCOUNT_SELECTION_REQUIRED:
        setPending({ kind: "account", ...event });
        break;
      case InsightsEvent.EXECUTION_PROPOSED: {
        const card = event.change_set;
        if (!card) break;
        // The card lands mid-turn, after the sentence that introduced it and
        // before the rest. Close the streaming text off first so the two read
        // in the order they were written, rather than the card jumping above
        // the prose explaining it.
        const said = bufferRef.current.trim();
        if (said) {
          bufferRef.current = "";
          setStreaming("");
        }
        setTurns((prev) => {
          // Upsert by id: the same set arrives again when it is rolled back or
          // its state otherwise changes, and two cards for one change set is a
          // way to approve something twice.
          const at = prev.findIndex(
            (t) => t.role === "change_set" && t.card?.change_set_id === card.change_set_id
          );
          if (at !== -1) {
            const next = [...prev];
            next[at] = { role: "change_set", card };
            return next;
          }
          const base = said ? [...prev, { role: "assistant", text: said }] : prev;
          return [...base, { role: "change_set", card }];
        });
        break;
      }
      case InsightsEvent.PIPELINE_STARTED:
        setAutonomy({
          level: event.autonomy || "",
          configured: event.autonomy_configured || "",
        });
        break;
      case InsightsEvent.PIPELINE_FINISHED:
        setStatus("ready");
        break;
      case InsightsEvent.PIPELINE_FAILED:
        setStatus("failed");
        setError(event.error || "The session failed.");
        break;
      case InsightsEvent.STEP_FAILED:
        // A single bad turn — the session is still alive and the user can retry.
        setError(event.error || "That turn failed.");
        break;
      default:
        break;
    }
  }, []);

  const start = useCallback(
    async (prompt) => {
      setStatus("running");
      setError("");
      try {
        const { session_id: sessionId } = await createAgentSession(AGENT_TYPE, {
          project_id: projectId || null,
          prompt,
          // Carries the deliverable format the agent should write in, among
          // the rest of the profile.
          user_preferences: loadPreferences(),
        });
        sessionRef.current = sessionId;
        const controller = new AbortController();
        abortRef.current = controller;
        const body = await openAgentStream(AGENT_TYPE, sessionId, {
          signal: controller.signal,
        });
        await consumeSseStream(body, onEvent, controller.signal);
      } catch (err) {
        setStatus("failed");
        setError(err?.message || "Could not start the session.");
      }
    },
    [projectId, onEvent]
  );

  useEffect(() => {
    if (sessionRef.current) return;      // StrictMode double-mount guard
    start(initialPrompt);
    return () => abortRef.current?.abort();
  }, [start, initialPrompt]);

  /** Resolve whatever the session is parked on. One endpoint, three shapes. */
  async function answerPending(answers) {
    const sessionId = sessionRef.current;
    if (!sessionId) return;
    setPending(null);
    try {
      await sendAgentMessage(AGENT_TYPE, sessionId, { type: "answer", answers });
    } catch (err) {
      setError(err?.message || "Could not send that answer.");
    }
  }

  async function send() {
    const text = draft.trim();
    const sessionId = sessionRef.current;
    if (!text || !sessionId) return;
    setDraft("");
    setTurns((prev) => [...prev, { role: "user", text }]);
    try {
      await sendAgentMessage(AGENT_TYPE, sessionId, { type: "chat", content: text });
    } catch (err) {
      setError(err?.message || "Could not send that message.");
    }
  }

  const shown = versions.length
    ? versions[selected < 0 ? versions.length - 1 : selected]
    : null;
  const hasBrief = Boolean(shown) || Boolean(writing);

  const chat = (
    <div className="flex h-full min-h-0 flex-col">
      <AutonomyBadge autonomy={autonomy} />
      <AuditTodos todos={todos} />

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {memories.length > 0 && (
          <p className="text-[11px] text-muted-foreground">
            Recalled {memories.length} thing{memories.length === 1 ? "" : "s"} Duct already
            knew about this project.
          </p>
        )}

        {turns.map((turn, i) =>
          turn.role === "change_set" ? (
            <ChangeSetCard key={turn.card.change_set_id} changeSet={turn.card} />
          ) : (
            <Turn key={i} role={turn.role} text={turn.text} />
          )
        )}
        {streaming && <Turn role="assistant" text={streaming} />}

        {pending?.kind === "questions" && (
          <AuditQuestions questions={pending.questions} onSubmit={answerPending} />
        )}
        {pending?.kind === "connection" && (
          <ConnectionRequest request={pending} onAnswer={answerPending} />
        )}
        {pending?.kind === "account" && (
          <AccountSelect request={pending} onAnswer={answerPending} />
        )}

        {error && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
            {error}
          </p>
        )}
      </div>

      <div className="flex shrink-0 items-end gap-2 border-t border-border/60 p-3">
        <textarea
          rows={2}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder="Ask about your growth data…"
          className="min-h-[2.5rem] flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <Button size="sm" onClick={send} disabled={!draft.trim() || status === "running"}>
          Send
        </Button>
      </div>
    </div>
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
        {pane === "brief" ? (
          <BriefPane brief={shown} writing={writing} empty={!hasBrief} />
        ) : (
          <DataPane fetched={fetched} />
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
      rightLabel="Brief"
      rightStatus={writing || status === "running" ? "busy" : hasBrief ? "ready" : "idle"}
    />
  );
}

const AUTONOMY_LABELS = {
  ask: "Asks freely · nothing applies without you",
  assisted: "Asks when it matters · allowlisted changes apply on their own",
  auto: "Interrupts rarely · same allowlist as Assisted",
};

/** Which mode this run is in, said before the first token.
 *
 * `configured` is what the project is set to and `level` is what the run got.
 * They differ when the model driving it is not on the allowlist for `auto`,
 * and saying so is the difference between a considered step-down and an agent
 * that mysteriously keeps asking questions. */
function AutonomyBadge({ autonomy }) {
  if (!autonomy?.level) return null;
  const steppedDown = autonomy.configured && autonomy.configured !== autonomy.level;
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-2 gap-y-1 border-b border-border/60 px-4 py-1.5 text-[11px]">
      <span className="rounded-full bg-muted px-2 py-0.5 font-medium uppercase tracking-wide">
        {autonomy.level}
      </span>
      <span className="text-muted-foreground">{AUTONOMY_LABELS[autonomy.level] || ""}</span>
      {steppedDown && (
        <span className="text-muted-foreground">
          · set to <strong>{autonomy.configured}</strong>, stepped down for this model
        </span>
      )}
    </div>
  );
}

function PaneTab({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
        active
          ? "bg-muted text-foreground"
          : "text-muted-foreground hover:text-foreground"
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
          <span className={f.ok ? "text-green-500" : "text-destructive"}>
            {f.ok ? "✓" : "!"}
          </span>
          <span className={f.ok ? "" : "text-muted-foreground"}>{f.label}</span>
        </li>
      ))}
    </ul>
  );
}

function Turn({ role, text }) {
  const isUser = role === "user";
  return (
    <div className={isUser ? "flex justify-end" : ""}>
      <div
        className={`whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
          isUser ? "max-w-[85%] bg-primary/10" : "text-foreground"
        }`}
      >
        {text}
      </div>
    </div>
  );
}
