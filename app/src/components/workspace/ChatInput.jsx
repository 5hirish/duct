"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Paperclip, Square } from "lucide-react";

/**
 * The chat composer every agent shell uses: text, pasted or attached images,
 * Enter to send, a Stop button beside Send while the agent is producing
 * tokens. The box stays open while it works — a message then is queued for
 * the model's next step, which the caller's placeholder says — and closes
 * only when there is nothing to send to (`disabled`).
 *
 * The same object as the desk composer (insights/desk/DeskComposer.jsx): one
 * card, the text on top, a footer row with what the message runs with on the
 * left and its cost on the right. It was a bare input with a Send button,
 * and the person who had chosen a posture and a thinking level on the desk
 * lost sight of both the moment the conversation opened.
 *
 * `tools` is the shell's own chips for that left cluster (ComposerDials, or
 * nothing); `status` is the right one — the context ring, in practice.
 *
 * Images travel as content blocks ({type:"image", source:{base64…}}) beside
 * the text, which is the Messages API shape both harnesses accept.
 */
export default function ChatInput({
  onSend,
  disabled,
  isStreaming,
  onStop,
  placeholder = "Ask a follow-up question…",
  ariaLabel = "Message the agent",
  accept = "image/*",
  // { text, key }: text handed back by the session (a queued message the
  // user stopped before it was read). Applied once per `key`.
  draft = null,
  tools = null,
  status = null,
}) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState([]);
  const fileRef = useRef(null);

  useEffect(() => {
    if (draft?.text) setText((current) => (current.trim() ? `${current}\n\n${draft.text}` : draft.text));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft?.key]);

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleSend() {
    const trimmed = text.trim();
    if (!trimmed && attachments.length === 0) return;

    if (attachments.length > 0) {
      const blocks = [];
      if (trimmed) blocks.push({ type: "text", text: trimmed });
      for (const att of attachments) {
        blocks.push({
          type: "image",
          source: { type: "base64", media_type: att.mediaType, data: att.data },
        });
      }
      onSend(blocks);
    } else {
      onSend(trimmed);
    }
    setText("");
    setAttachments([]);
  }

  async function handleFileChange(e) {
    const files = Array.from(e.target.files || []);
    const newAtts = await Promise.all(
      files.map(async (file) => {
        const data = await fileToBase64(file);
        return { name: file.name, mediaType: file.type, data };
      }),
    );
    setAttachments((prev) => [...prev, ...newAtts]);
    e.target.value = "";
  }

  async function handlePaste(e) {
    const items = Array.from(e.clipboardData?.items || []);
    const imageItems = items.filter((it) => it.kind === "file" && it.type.startsWith("image/"));
    if (imageItems.length === 0) return;
    e.preventDefault();
    const newAtts = await Promise.all(
      imageItems.map(async (item) => {
        const file = item.getAsFile();
        const data = await fileToBase64(file);
        return { name: file.name || "pasted-image.png", mediaType: file.type, data };
      }),
    );
    setAttachments((prev) => [...prev, ...newAtts]);
  }

  const canSend = !disabled && (text.trim() || attachments.length > 0);

  return (
    <div className="border-t border-border/60 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom,0.75rem))]">
      <div className="rounded-xl border bg-card focus-within:border-ring">
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 px-3 pt-3">
            {attachments.map((att, i) => (
              <div key={i} className="flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-xs">
                <span className="max-w-[120px] truncate">{att.name}</span>
                <button
                  type="button"
                  onClick={() => setAttachments((prev) => prev.filter((_, j) => j !== i))}
                  aria-label={`Remove ${att.name}`}
                  className="ml-1 text-muted-foreground hover:text-foreground"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        <textarea
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          aria-label={ariaLabel}
          disabled={disabled}
          placeholder={disabled ? "Waiting for agent…" : placeholder}
          className="max-h-[160px] min-h-[44px] w-full resize-none overflow-y-auto bg-transparent px-4 pt-3 pb-1 text-base leading-relaxed outline-none placeholder:text-muted-foreground disabled:opacity-50 md:text-sm"
          style={{ height: "44px" }}
          onInput={(e) => {
            e.target.style.height = "44px";
            e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
          }}
        />

        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-2.5 pb-2.5">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={disabled}
              title="Attach image"
              aria-label="Attach image"
              className="flex size-8 shrink-0 items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40"
            >
              <Paperclip className="size-4" aria-hidden />
            </button>
            <input
              ref={fileRef}
              type="file"
              accept={accept}
              aria-label="Attach files"
              multiple
              className="hidden"
              onChange={handleFileChange}
            />
            {tools}
          </div>

          <div className="ml-auto flex shrink-0 items-center gap-3">
            {status}
            {isStreaming && (
              <button
                type="button"
                onClick={onStop}
                aria-label="Stop"
                title="Stop"
                className="flex h-7 items-center gap-1.5 rounded-full bg-destructive px-2.5 text-xs font-medium text-destructive-foreground hover:bg-destructive/90"
              >
                <Square className="size-3 fill-current" aria-hidden />
                Stop
              </button>
            )}
            <button
              type="button"
              onClick={handleSend}
              disabled={!canSend}
              aria-label="Send"
              title="Send"
              className="flex size-7 items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity hover:bg-primary/90 disabled:opacity-35"
            >
              <ArrowUp className="size-3.5" aria-hidden />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
