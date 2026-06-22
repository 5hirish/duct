"use client";

import { useEffect, useRef, useState } from "react";
import ContentChat from "./ContentChat";
import SplitWorkspace from "../workspace/SplitWorkspace";
import { Phase } from "./contentPhase";
import {
  answerContentQuestions,
  archiveContentConversation,
  closeContentSession,
  consumeSseStream,
  getContentConversation,
  getSlideRenderDoc,
  invalidatePosts,
  mediaUrl,
  openClonePostStream,
  openPlanStream,
  openPlannerStream,
  openPostStream,
  postSlideRender,
  reattachContentStream,
  sendContentChat,
} from "../../lib/contentApi";
import { ContentEvent } from "../../lib/contentEvents";
import { StepStatus } from "../../lib/agentSteps";
import { captureSlideDocToPng } from "../../lib/slideCapture";

/**
 * Universal split-pane workspace for the content agent.
 *
 * Props:
 *   - mode: 'plan_month' | 'draft_post' | 'update_plan' (Content Planner)
 *   - context: { projectId } | { projectId, planId, dayIndex, topic, pillar, postId }
 *   - renderViewport: ({ payload, mode, sessionId, phase, onSendMessage }) => ReactNode
 *     Called every render with the latest plan/post payload from the agent.
 *     onSendMessage(text) sends a chat turn into the live session (used by the
 *     viewport for "approve & generate images" / per-slide regenerate).
 */
export default function ContentWorkspace({ mode, context, renderViewport }) {
  const [phase,    setPhase]    = useState(Phase.STARTING);
  const [steps,    setSteps]    = useState([]);
  const [todos,    setTodos]    = useState([]);
  const [messages, setMessages] = useState([]);
  const [pendingQuestions, setPendingQuestions] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [retryCount, setRetryCount] = useState(0);
  const [payload, setPayload]   = useState(null);
  const [assessment, setAssessment] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [channelNote, setChannelNote] = useState(null);
  const [isAgentTyping, setIsAgentTyping] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [reconnecting, setReconnecting] = useState(false);
  // When set, overrides `context` for the next session open (used by Start fresh
  // to reopen with start_fresh instead of resume). null ⇒ use context as-is.
  const [openOverride, setOpenOverride] = useState(null);

  const abortRef = useRef(null);
  const pipelineEndedRef = useRef(false);
  const sessionIdRef     = useRef(null);
  const conversationIdRef = useRef(null);
  // Terminal = the run truly ended (PIPELINE_FAILED) — never auto-reconnect then.
  // A bare stream drop (network blip, server restart) is NOT terminal.
  const terminalRef = useRef(false);
  const reconnectAttemptRef = useRef(0);
  // On a resume the only turn is a one-line greeting; its extended-thinking is
  // pure noise (and narrates internal state), so we hide thinking until the user
  // takes their first action. Real work turns show thinking normally.
  const suppressThinkingRef = useRef(false);

  // The params we actually open with — context, unless Start fresh overrode it.
  const openContext = openOverride || context;

  // Which unified agent backs this mode. The Content Planner (update_plan) is a
  // distinct agent type; plan_month/draft_post are the Content Studio agent.
  const agentType = mode === "update_plan" ? "content_planner" : "tiktok_studio";

  // ---------------------------------------------------------------------------
  // Retry
  // ---------------------------------------------------------------------------

  function handleRetry() {
    setPhase(Phase.STARTING);
    setSteps([]);
    setTodos([]);
    setMessages([]);
    setPendingQuestions(null);
    setErrorMsg("");
    setPayload(null);
    setSessionId(null);
    setIsAgentTyping(false);
    setReconnecting(false);
    pipelineEndedRef.current = false;
    setRetryCount((c) => c + 1);
  }

  // ---------------------------------------------------------------------------
  // Start fresh — abandon the current conversation, keep the artifact.
  // ---------------------------------------------------------------------------

  async function handleStartFresh() {
    const convId = conversationIdRef.current;
    // Archive the old conversation now; start_fresh:true on reopen is the
    // backstop (it also archives any active conversation for the artifact).
    // Scope to this mode's agent type so the planner's conversation is archived
    // under content_planner (not tiktok_studio).
    if (convId) await archiveContentConversation(convId, agentType);
    abortRef.current?.abort();
    if (sessionIdRef.current) closeContentSession(sessionIdRef.current, agentType).catch(() => {});

    // Bind the new conversation to the same artifact so it stays the post's
    // active chat. artifact ids come straight off the context.
    const artifactType = (mode === "draft_post" || mode === "clone_post") ? "post" : "plan";
    const artifactId   = (mode === "draft_post" || mode === "clone_post") ? context.postId : context.planId;

    setMessages([]);
    setPayload(null);
    setSessionId(null);
    setConversationId(null);
    conversationIdRef.current = null;
    setPendingQuestions(null);
    setErrorMsg("");
    setIsAgentTyping(false);
    setReconnecting(false);
    setPhase(Phase.STARTING);
    pipelineEndedRef.current = false;
    // Changing openOverride re-triggers the SSE effect (deps include it).
    setOpenOverride({
      ...context,
      conversationId: undefined,
      resume: false,
      startFresh: true,
      ...(artifactType && artifactId ? { artifactType, artifactId } : {}),
    });
  }

  // ---------------------------------------------------------------------------
  // SSE lifecycle
  // ---------------------------------------------------------------------------

  useEffect(() => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    pipelineEndedRef.current = false;
    terminalRef.current = false;
    reconnectAttemptRef.current = 0;
    // Per-effect-instance state (closure, not refs) so a StrictMode double-mount
    // never lets one instance clobber or leak the other's backend session.
    let cancelled = false;
    let localSid = null;

    const MAX_RECONNECT = 5;

    const dead = () => cancelled || ctrl.signal.aborted;

    function handleSession({ sessionId: sid, conversationId: cid }) {
      localSid = sid;
      // Torn down before the stream opened (StrictMode remount / fast nav):
      // close the orphan so its worker is cancelled instead of racing the
      // surviving session on the shared CLI config dir.
      if (cancelled) {
        closeContentSession(sid, agentType).catch(() => {});
        return;
      }
      sessionIdRef.current = sid;
      setSessionId(sid);
      const next = cid || conversationIdRef.current || null;
      conversationIdRef.current = next;
      setConversationId(next);
    }

    // Jittered exponential backoff: ~1s, 2s, 4s, 8s, 15s (±50% jitter).
    function backoffDelay(attempt) {
      const base = Math.min(15000, 1000 * 2 ** (attempt - 1));
      return Math.round(base * (0.5 + Math.random() * 0.5));
    }

    function sleep(ms) {
      return new Promise((resolve) => {
        const t = setTimeout(resolve, ms);
        ctrl.signal.addEventListener("abort", () => { clearTimeout(t); resolve(); }, { once: true });
      });
    }

    // Re-establish a stream after an unexpected drop. Prefer re-attaching to the
    // SAME live session (within the backend grace window) so the in-flight run
    // continues gap-free; if it's gone, resume a fresh session from the
    // persisted conversation. Returns a stream body, or null on failure.
    async function reconnect() {
      const sid = sessionIdRef.current;
      if (sid) {
        try { return await reattachContentStream(sid, { signal: ctrl.signal, agentType }); }
        catch { /* session past grace → resume-create below */ }
      }
      if (dead()) return null;
      const artifactType = mode === "draft_post" ? "post" : "plan";
      const artifactId   = mode === "draft_post" ? context.postId : context.planId;
      const opener =
        mode === "update_plan" ? openPlannerStream
        : mode === "plan_month" ? openPlanStream
        : mode === "clone_post" ? openClonePostStream
        : openPostStream;
      const { body } = await opener(
        {
          ...openContext,
          conversationId: conversationIdRef.current,
          resume: true,
          ...(artifactType && artifactId ? { artifactType, artifactId } : {}),
        },
        { signal: ctrl.signal, onSession: handleSession },
      );
      return body;
    }

    async function start() {
      try {
        // Resume: rehydrate persisted chat history BEFORE the live stream so the
        // order is history → new turns (the SSE handler appends to the tail).
        suppressThinkingRef.current = Boolean(openContext?.conversationId);
        if (openContext?.conversationId) {
          try {
            const { events } = await getContentConversation(openContext.conversationId);
            if (cancelled) return;
            const hist = mapEventsToMessages(events);
            if (hist.length) setMessages(hist);
          } catch { /* non-fatal: server still resumes; UI just lacks history */ }
        }

        const opener =
        mode === "update_plan" ? openPlannerStream
        : mode === "plan_month" ? openPlanStream
        : mode === "clone_post" ? openClonePostStream
        : openPostStream;
        const { body } = await opener(openContext, { signal: ctrl.signal, onSession: handleSession });
        if (cancelled) return;

        // Stream → reconnect loop. consumeSseStream returns on a server-side end
        // and throws on a network error; both are drops unless the run is truly
        // terminal (PIPELINE_FAILED) or we've been torn down.
        let stream = body;
        while (true) {
          try {
            await consumeSseStream(stream, handleEvent, ctrl.signal);
          } catch { /* network drop → reconnect below */ }
          if (dead() || terminalRef.current) return;

          reconnectAttemptRef.current += 1;
          if (reconnectAttemptRef.current > MAX_RECONNECT) {
            setReconnecting(false);
            setErrorMsg("We lost the connection and couldn't reconnect. Please retry.");
            setPhase(Phase.FAILED);
            return;
          }
          setReconnecting(true);
          setIsAgentTyping(false);
          await sleep(backoffDelay(reconnectAttemptRef.current));
          if (dead()) return;

          let next = null;
          try { next = await reconnect(); } catch { next = null; }
          if (dead()) return;
          if (!next) continue;            // open failed → loop backs off again
          stream = next;
          setReconnecting(false);          // re-established; handleEvent resets the counter
        }
      } catch (err) {
        if (!dead()) {
          setReconnecting(false);
          setErrorMsg(err.message || "Stream error.");
          setPhase(Phase.FAILED);
        }
      }
    }

    start();
    return () => {
      cancelled = true;
      ctrl.abort();
      const sid = sessionIdRef.current || localSid;
      if (sid) {
        closeContentSession(sid, agentType).catch(() => {});
        if (sessionIdRef.current === sid) sessionIdRef.current = null;
      }
    };
  }, [retryCount, mode, JSON.stringify(openContext)]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------------------------------------------------------------------------
  // SSE event handler
  // ---------------------------------------------------------------------------

  function handleEvent(event) {
    // Any frame proves the stream is healthy → reset the reconnect backoff so a
    // single drop later in a long session starts counting from zero again.
    reconnectAttemptRef.current = 0;
    // PIPELINE_STARTED carries the resolved channel; note when we fell back.
    if (event.channel) {
      setChannelNote(
        event.channel_supported === false
          ? `Using the TikTok playbook — no dedicated ${event.channel_label || event.channel} agent yet.`
          : null,
      );
    }
    switch (event.event) {

      // Leave the "Starting session…" state the instant the backend responds —
      // before any step arrives — so the right-pane PipelineProgress skeleton
      // shows immediately instead of waiting on the first STEP_STARTED.
      case ContentEvent.PIPELINE_STARTED:
        setPhase((p) => (p === Phase.STARTING ? Phase.PIPELINE : p));
        break;

      case ContentEvent.STEP_STARTED:
        setPhase(Phase.PIPELINE);
        setSteps((prev) => {
          const existing = prev.find((s) => s.step_id === event.step_id);
          if (existing) {
            return prev.map((s) =>
              s.step_id === event.step_id
                ? { ...s, status: StepStatus.RUNNING, label: event.label || s.label, summary: event.summary }
                : s,
            );
          }
          return [
            ...prev,
            {
              step_id: event.step_id,
              label: event.label || event.step_id,
              status: StepStatus.RUNNING,
              summary: event.summary || "",
            },
          ];
        });
        break;

      case ContentEvent.STEP_FINISHED:
        setSteps((prev) =>
          prev.map((s) =>
            s.step_id === event.step_id
              ? { ...s, status: event.status || StepStatus.SUCCESS, summary: event.summary || s.summary }
              : s,
          ),
        );
        break;

      case ContentEvent.STEP_FAILED:
        setSteps((prev) =>
          prev.map((s) =>
            s.step_id === event.step_id
              ? { ...s, status: StepStatus.ERROR, summary: event.error || s.summary }
              : s,
          ),
        );
        break;

      case ContentEvent.THINKING_CHUNK:
        // Hide the resume greeting's thinking (see suppressThinkingRef).
        if (suppressThinkingRef.current) break;
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.streaming)
            return [...prev.slice(0, -1), { ...last, thinking: (last.thinking || "") + event.text }];
          return [...prev, { role: "assistant", text: "", thinking: event.text, streaming: true }];
        });
        break;

      case ContentEvent.QUESTIONS_REQUIRED:
        setPendingQuestions(event.questions);
        setPhase(Phase.QUESTIONS);
        if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
          new Notification("Duct — Your input is needed", {
            body: "The content agent has a question before continuing.",
            icon: "/favicon.ico",
          });
        }
        break;

      case ContentEvent.REPORT_CHUNK:
        // Stream tokens are accumulated inside <duct_report>; we don't render
        // them live in MVP (the close-tag PLAN_GENERATED / POST_DRAFT_UPDATED
        // gives us the structured payload). Future: render to a "streaming
        // preview" indicator.
        break;

      case ContentEvent.PLAN_GENERATED:
        setPayload({ type: "plan", ...event.payload });
        break;

      case ContentEvent.POST_DRAFT_UPDATED: {
        // The draft changed (copy, image regen, etc.) → the board's cached list
        // is now stale; clear it so the kanban re-fetches the latest thumbnail.
        invalidatePosts();
        const base = { type: "post", ...event.payload };
        const ip = event.inline_preview;
        if (ip?.data_uri) {
          // Instant first paint: render the inline data URI now, then preload the
          // real CDN image and drop the preview so the iframe shows full-res
          // (cached) — avoids a visible CDN round-trip on the freshly generated slide.
          setPayload(applyPreview(base, ip.slide_id, ip.item_index, ip.data_uri));
          const realUrl = findSlideImage(base, ip.slide_id, ip.item_index);
          if (realUrl && typeof window !== "undefined") {
            const pre = new window.Image();
            const drop = () => setPayload((prev) => applyPreview(prev, ip.slide_id, ip.item_index, null));
            pre.onload = drop;
            pre.onerror = drop;
            pre.src = mediaUrl(realUrl);
          }
          // Drop a clickable image bubble into the chat (iMessage-style). This
          // only runs on inline_preview, which the backend attaches solely when
          // generate_image produced + attached an image — never on copy edits.
          const slideIdx = (base.slides || []).findIndex(
            (s) => String(s.slide_id) === String(ip.slide_id),
          );
          const cap =
            (slideIdx >= 0 ? `Slide ${slideIdx + 1}` : "Generated image") +
            (ip.item_index != null ? ` · image ${ip.item_index + 1}` : "");
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              image: ip.data_uri,
              fullUrl: realUrl ? mediaUrl(realUrl) : ip.data_uri,
              caption: cap,
            },
          ]);
        } else {
          setPayload(base);
        }
        break;
      }

      case ContentEvent.PUBLISH_ASSESSMENT:
        // The pre-publish review from the review_post sub-agent. Held here and
        // threaded to the viewport, which renders it as a collapsible panel.
        setAssessment(event.payload || null);
        break;

      case ContentEvent.PIPELINE_FINISHED:
        pipelineEndedRef.current = true;
        setPhase(Phase.READY);
        break;

      case ContentEvent.PIPELINE_FAILED:
        pipelineEndedRef.current = true;
        terminalRef.current = true;  // a real run failure — don't auto-reconnect
        setReconnecting(false);
        setErrorMsg(friendlyErrorMessage(event.error));
        setPhase(Phase.FAILED);
        break;

      case ContentEvent.TODO_UPDATE:
        setTodos(event.todos || []);
        break;

      case ContentEvent.SLIDE_RENDER_REQUESTED:
        handleSlideRender(event);
        break;

      case ContentEvent.AGENT_MESSAGE_CHUNK:
        setIsAgentTyping(false);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.streaming)
            return [...prev.slice(0, -1), { ...last, text: last.text + event.text }];
          return [...prev, { role: "assistant", text: event.text, streaming: true }];
        });
        break;

      case ContentEvent.MESSAGE_STOP:
        setIsAgentTyping(false);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.streaming) return [...prev.slice(0, -1), { ...last, streaming: false }];
          return prev;
        });
        setPhase((prev) => (prev === Phase.CHATTING ? Phase.READY : prev));
        break;

      default:
        break;
    }
  }

  // ---------------------------------------------------------------------------
  // User actions
  // ---------------------------------------------------------------------------

  async function handleAnswerQuestions(answers) {
    setPendingQuestions(null);
    setPhase(Phase.PIPELINE);
    try {
      await answerContentQuestions(sessionIdRef.current, answers, agentType);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "send_error",
          text: `Failed to submit answers: ${err.message || "network error"}.`,
          content: null,
        },
      ]);
      setPendingQuestions(answers);
      setPhase(Phase.QUESTIONS);
    }
  }

  async function handleSendMessage(content) {
    // The user is engaging — show thinking normally from here on.
    suppressThinkingRef.current = false;
    const text = typeof content === "string" ? content : "[image attached]";
    setMessages((prev) => {
      const cleaned = prev[prev.length - 1]?.role === "send_error" ? prev.slice(0, -1) : prev;
      return [...cleaned, { role: "user", text }];
    });
    setPhase(Phase.CHATTING);
    setIsAgentTyping(true);
    try {
      await sendContentChat(sessionIdRef.current, content, agentType);
    } catch (err) {
      setIsAgentTyping(false);
      setMessages((prev) => [
        ...prev,
        { role: "send_error", text: err.message || "Failed to send message.", content },
      ]);
      setPhase(Phase.READY);
    }
  }

  function handleRetrySend(content) {
    handleSendMessage(content);
  }

  // The agent asked to SEE a composed slide: fetch the self-contained doc,
  // rasterize it in the browser (1080×1920), and POST the PNG back. On any
  // failure we POST an empty result so the agent's render_slide tool fails fast.
  async function handleSlideRender(event) {
    const sid = sessionIdRef.current;
    if (!sid) return;
    let png = "";
    try {
      const { html } = await getSlideRenderDoc(sid, event.post_id, event.slide_id);
      png = await captureSlideDocToPng(html);
    } catch {
      png = "";
    }
    try {
      await postSlideRender(sid, { render_id: event.render_id, image_base64: png });
    } catch { /* the tool will time out and degrade gracefully */ }
  }

  function handleStop() {
    abortRef.current?.abort();
    if (sessionIdRef.current) {
      closeContentSession(sessionIdRef.current, agentType).catch(() => {});
    }
    setIsAgentTyping(false);
    setPhase((prev) =>
      prev === Phase.CHATTING && payload ? Phase.READY : Phase.FAILED,
    );
  }

  // ---------------------------------------------------------------------------
  // Friendly error mapping — hide stack traces / status codes from users.
  // ---------------------------------------------------------------------------

  // ---------------------------------------------------------------------------
  // Render — split shell is shared (../workspace/SplitWorkspace); this component
  // only wires the agent-specific chat + viewport into it.
  // ---------------------------------------------------------------------------

  const hasPayload = Boolean(payload);
  const isRunning  = phase === Phase.STARTING || phase === Phase.PIPELINE;
  // The right viewport is mid-build whenever there's no payload yet and the run
  // hasn't failed — including while a question is pending. Drives the polished
  // PipelineProgress loading panel (synthesis spinner + bar) until the plan/post lands.
  const viewportBuilding = !hasPayload && phase !== Phase.FAILED;
  // True whenever the agent is actively producing tokens — drives ContentInput
  // Stop button + textarea disabling. Distinct from inputDisabled (which is
  // phase-based) so the user can stop in-flight chat without falling into a
  // FAILED state.
  const isStreaming = isRunning || (phase === Phase.CHATTING && isAgentTyping);
  const paneLabel =
    mode === "update_plan" ? "7-day plan"
    : mode === "plan_month" ? "30-day plan"
    : mode === "clone_post" ? "Cloned post"
    : "Post draft";
  const rightStatus = hasPayload ? "ready" : isRunning ? "busy" : "idle";

  const viewportEl = (
    <div className="flex h-full flex-col overflow-hidden">
      {channelNote && (
        <div className="shrink-0 border-b border-amber-400/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-600 dark:text-amber-400">
          {channelNote}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-hidden">
        {renderViewport
          ? renderViewport({ payload, assessment, mode, sessionId, phase, steps, building: viewportBuilding, onSendMessage: handleSendMessage })
          : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                No viewport configured.
              </div>
            )}
      </div>
    </div>
  );

  return (
    <SplitWorkspace
      storageKey="content_split_w"
      rightLabel={paneLabel}
      rightStatus={rightStatus}
      right={viewportEl}
      left={
        <ContentChat
          mode={mode}
          phase={phase}
          steps={steps}
          todos={todos}
          messages={messages}
          pendingQuestions={pendingQuestions}
          errorMsg={errorMsg}
          isAgentTyping={isAgentTyping}
          isStreaming={isStreaming}
          reconnecting={reconnecting}
          onAnswerQuestions={handleAnswerQuestions}
          onSendMessage={handleSendMessage}
          onRetrySend={handleRetrySend}
          onRetry={handleRetry}
          onStop={handleStop}
          onStartFresh={handleStartFresh}
          canStartFresh={Boolean(conversationId) && (phase === Phase.READY || phase === Phase.CHATTING)}
        />
      }
    />
  );
}


/** The real (CDN) image_url for a slide or one of its cells, from a post payload. */
function findSlideImage(payload, slideId, itemIndex) {
  const slide = (payload?.slides || []).find((s) => String(s.slide_id) === String(slideId));
  if (!slide) return null;
  if (itemIndex == null) return slide.image_url || null;
  return slide.items?.[itemIndex]?.image_url || null;
}

/** Set (or clear, when uri is null) the transient _preview_uri on a slide/cell —
 * the instant-paint inline data URI. Returns a new payload; leaves image_url
 * (the saved value) untouched. */
function applyPreview(payload, slideId, itemIndex, uri) {
  if (!payload?.slides) return payload;
  const apply = (obj) => {
    const next = { ...obj };
    if (uri) next._preview_uri = uri; else delete next._preview_uri;
    return next;
  };
  const slides = payload.slides.map((s) => {
    if (String(s.slide_id) !== String(slideId)) return s;
    if (itemIndex == null) return apply(s);
    const items = (s.items || []).map((it, i) => (i === itemIndex ? apply(it) : it));
    return { ...s, items };
  });
  return { ...payload, slides };
}

/**
 * Map persisted conversation events (kind + data) to the chat `messages` shape
 * used by ContentChat. Thinking rows are merged onto the assistant turn that
 * follows them (matching the live streaming shape); questions/answers render as
 * readable assistant/user lines.
 */
function mapEventsToMessages(events) {
  const out = [];
  let pendingThinking = "";
  const userText = (data) => {
    const c = data?.content;
    if (typeof c === "string") return c;
    if (Array.isArray(c))
      return c.filter((b) => b?.type === "text").map((b) => b.text).join(" ").trim() || "[image attached]";
    return "";
  };
  for (const e of events || []) {
    switch (e.kind) {
      case "user":
        out.push({ role: "user", text: userText(e.data) });
        break;
      case "thinking":
        pendingThinking = e.data?.text || "";
        break;
      case "assistant":
        out.push({ role: "assistant", text: e.data?.text || "", thinking: pendingThinking || undefined });
        pendingThinking = "";
        break;
      case "question": {
        const qs = (e.data?.questions || []).map((q) => q?.question).filter(Boolean).join(" · ");
        if (pendingThinking) { out.push({ role: "assistant", text: "", thinking: pendingThinking }); pendingThinking = ""; }
        if (qs) out.push({ role: "assistant", text: `**Quick question:** ${qs}` });
        break;
      }
      case "answer": {
        const ans = Object.values(e.data?.answers || {}).filter(Boolean).join(", ");
        if (ans) out.push({ role: "user", text: ans });
        break;
      }
      default:
        break;
    }
  }
  if (pendingThinking) out.push({ role: "assistant", text: "", thinking: pendingThinking });
  return out;
}


/**
 * Translate raw backend errors into actionable user-facing messages.
 * Hides stack traces, status codes, and internal terminology. Falls back
 * to a generic message when the input doesn't pattern-match.
 */
function friendlyErrorMessage(raw) {
  const msg = String(raw || "").trim();
  if (!msg) return "Something went wrong. Please try again.";

  // Configuration gaps
  if (/ANTHROPIC_API_KEY/i.test(msg)) {
    return "The assistant isn't connected. Ask your admin to finish setup.";
  }
  if (/GEMINI_API_KEY/i.test(msg)) {
    return "Image generation isn't connected yet. Ask your admin to finish setup.";
  }
  if (/uploads.*disabled/i.test(msg)) {
    return "Image uploads aren't enabled in this environment.";
  }
  if (/POSTBRIDGE|post.?bridge.*connect/i.test(msg)) {
    return "Publishing isn't connected. Ask your admin to set it up.";
  }

  // Common transient classes
  if (/rate limit|429/i.test(msg)) {
    return "We're hitting a rate limit — wait a minute and try again.";
  }
  if (/timeout|timed.?out/i.test(msg)) {
    return "That took longer than expected. Try again.";
  }
  if (/network|connection|fetch failed|ECONNREFUSED/i.test(msg)) {
    return "Couldn't reach the server. Check your internet and try again.";
  }

  // Validation
  if (/validation|invalid|missing/i.test(msg) && msg.length < 200) {
    return "Some input wasn't valid — please review and try again.";
  }

  // Don't leak status codes / file paths / stack traces.
  if (/^\d{3}\b/.test(msg) || /Traceback|line \d+/i.test(msg)) {
    return "Something went wrong on our end. Please try again in a moment.";
  }

  // Reasonably short, doesn't look technical → pass through.
  if (msg.length < 200 && !/^\w+Error:/.test(msg)) return msg;

  return "Something went wrong. Please try again.";
}
