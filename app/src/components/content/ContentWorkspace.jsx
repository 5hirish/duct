"use client";

import { useMemo, useState } from "react";
import AgentChat from "../workspace/AgentChat";
import SplitWorkspace from "../workspace/SplitWorkspace";
import { useAgentSession } from "../../hooks/useAgentSession";
import { Phase } from "../../lib/agentPhase";
import { Row } from "../../lib/agentSession";
import {
  CONTENT_AGENT_TYPE,
  archiveContentConversation,
  contentSessionBody,
  getSlideRenderDoc,
  mediaUrl,
  postSlideRender,
} from "../../lib/contentApi";
import { ContentEvent, STEP_LABELS } from "../../lib/contentEvents";
import { captureSlideDocToPng } from "../../lib/slideCapture";

/**
 * Universal split-pane workspace for the content agent.
 *
 * The session lifecycle — create, stream, reconnect, resume, pauses, retry,
 * start fresh — is `useAgentSession`; this component only knows what a plan
 * or a post is: the artifact payload, the inline image preview, and the
 * slide-render round trip the agent asks the browser for.
 *
 * Props:
 *   - mode: 'plan_month' | 'draft_post'
 *   - context: { projectId } | { projectId, planId, dayIndex, topic, pillar, postId }
 *   - renderViewport: ({ payload, mode, sessionId, phase, steps, building, onSendMessage }) => ReactNode
 *     Called every render with the latest plan/post payload from the agent.
 *     onSendMessage(text) sends a chat turn into the live session (used by the
 *     viewport for "approve & generate images" / per-slide regenerate).
 */
export default function ContentWorkspace({ mode, context, renderViewport }) {
  const [payload, setPayload] = useState(null);
  const [channelNote, setChannelNote] = useState(null);

  const artifactType = mode === "plan_month" ? "plan" : "post";
  const artifactId = mode === "plan_month" ? context.planId : context.postId;
  const contextKey = JSON.stringify(context);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const body = useMemo(() => contentSessionBody(mode, context), [mode, contextKey]);

  const agent = useAgentSession({
    agentType: CONTENT_AGENT_TYPE,
    notifyAs: "Content Studio",
    body,
    // Scoped to the artifact so a reload of this post's workspace resumes
    // this post's run and never a different one's.
    handleKey: `${CONTENT_AGENT_TYPE}:${mode}:${artifactId || context.projectId || ""}`,
    onEvent: handleEvent,
  });

  function handleEvent(event, { appendMessage, sessionId }) {
    switch (event.event) {
      // PIPELINE_STARTED carries the resolved channel; note when we fell back.
      case ContentEvent.PIPELINE_STARTED:
        if (event.channel) {
          setChannelNote(
            event.channel_supported === false
              ? `Using the TikTok playbook — no dedicated ${event.channel_label || event.channel} agent yet.`
              : null,
          );
        }
        break;

      case ContentEvent.PLAN_GENERATED:
        setPayload({ type: "plan", ...event.payload });
        break;

      case ContentEvent.POST_DRAFT_UPDATED: {
        const base = { type: "post", ...event.payload };
        const ip = event.inline_preview;
        if (!ip?.data_uri) {
          setPayload(base);
          break;
        }
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
        // A clickable image bubble in the chat. Only on inline_preview, which
        // the backend attaches solely when generate_image produced + attached
        // an image — never on copy edits.
        const slideIdx = (base.slides || []).findIndex((s) => String(s.slide_id) === String(ip.slide_id));
        const caption =
          (slideIdx >= 0 ? `Slide ${slideIdx + 1}` : "Generated image") +
          (ip.item_index != null ? ` · image ${ip.item_index + 1}` : "");
        appendMessage({
          role: Row.IMAGE,
          image: ip.data_uri,
          fullUrl: realUrl ? mediaUrl(realUrl) : ip.data_uri,
          caption,
        });
        break;
      }

      case ContentEvent.SLIDE_RENDER_REQUESTED:
        handleSlideRender(event, sessionId);
        break;

      default:
        break;
    }
  }

  // The agent asked to SEE a composed slide: fetch the self-contained doc,
  // rasterize it in the browser (1080×1920), and POST the PNG back. On any
  // failure we POST an empty result so the agent's render_slide tool fails fast.
  async function handleSlideRender(event, sessionId) {
    if (!sessionId) return;
    let png = "";
    try {
      const { html } = await getSlideRenderDoc(sessionId, event.post_id, event.slide_id);
      png = await captureSlideDocToPng(html);
    } catch {
      png = "";
    }
    try {
      await postSlideRender(sessionId, { render_id: event.render_id, image_base64: png });
    } catch {
      /* the tool will time out and degrade gracefully */
    }
  }

  function handleRetry() {
    setPayload(null);
    setChannelNote(null);
    agent.retry();
  }

  // Abandon the current conversation, keep the artifact. The new conversation
  // binds to the same artifact so it stays the post's active chat; start_fresh
  // on the backend archives the old one as the backstop.
  async function handleStartFresh() {
    if (agent.conversationId) await archiveContentConversation(agent.conversationId);
    setPayload(null);
    agent.startFresh(artifactType && artifactId ? { artifact_type: artifactType, artifact_id: artifactId } : {});
  }

  function handleStop() {
    // Stopping mid-chat with a draft on screen is not a failure.
    agent.stop({ keepReady: agent.phase === Phase.CHATTING && Boolean(payload) });
  }

  const hasPayload = Boolean(payload);
  // The right viewport is mid-build whenever there's no payload yet and the run
  // hasn't failed — including while a question is pending.
  const viewportBuilding = !hasPayload && agent.phase !== Phase.FAILED;
  const paneLabel = mode === "plan_month" ? "30-day plan" : "Post draft";
  const rightStatus = hasPayload ? "ready" : agent.isRunning ? "busy" : "idle";

  const viewportEl = (
    <div className="flex h-full flex-col overflow-hidden">
      {channelNote && (
        <div className="shrink-0 border-b border-amber-400/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-600 dark:text-amber-400">
          {channelNote}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-hidden">
        {renderViewport ? (
          renderViewport({
            payload,
            mode,
            sessionId: agent.sessionId,
            phase: agent.phase,
            steps: agent.steps,
            building: viewportBuilding,
            onSendMessage: agent.send,
          })
        ) : (
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
        <AgentChat
          title={MODE_LABELS[mode] || "Content agent"}
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
          onStop={handleStop}
          onStartFresh={handleStartFresh}
          canStartFresh={Boolean(agent.conversationId) && (agent.phase === Phase.READY || agent.phase === Phase.CHATTING)}
          stepLabels={STEP_LABELS}
          questionsCopy={QUESTIONS_COPY}
          inputPlaceholder="Ask Duct to refine the plan or post…"
          inputAriaLabel="Message the content agent"
        />
      }
    />
  );
}

const MODE_LABELS = {
  plan_month: "Generating 30-day plan",
  draft_post: "Drafting post",
};

const QUESTIONS_COPY = {
  hint: "A clearer brief produces sharper content. Skip if you'd rather Duct decide.",
};

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
    if (uri) next._preview_uri = uri;
    else delete next._preview_uri;
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
