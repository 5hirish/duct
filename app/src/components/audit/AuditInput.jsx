"use client";

import { useRef, useState } from "react";

export default function AuditInput({ onSend, disabled, isStreaming, onStop }) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState([]);
  const fileRef = useRef(null);

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
      })
    );
    setAttachments(prev => [...prev, ...newAtts]);
    e.target.value = "";
  }

  async function handlePaste(e) {
    const items = Array.from(e.clipboardData?.items || []);
    const imageItems = items.filter(it => it.kind === "file" && it.type.startsWith("image/"));
    if (imageItems.length === 0) return;
    e.preventDefault();
    const newAtts = await Promise.all(
      imageItems.map(async (item) => {
        const file = item.getAsFile();
        const data = await fileToBase64(file);
        return { name: file.name || "pasted-image.png", mediaType: file.type, data };
      })
    );
    setAttachments(prev => [...prev, ...newAtts]);
  }

  return (
    <div className="border-t border-border/60 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom,0.75rem))]">
      {attachments.length > 0 && (
        <div className="flex gap-2 mb-2 flex-wrap">
          {attachments.map((att, i) => (
            <div key={i} className="flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-xs">
              <span className="truncate max-w-[120px]">{att.name}</span>
              <button
                type="button"
                onClick={() => setAttachments(prev => prev.filter((_, j) => j !== i))}
                className="text-muted-foreground hover:text-foreground ml-1"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-end gap-2">
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={disabled}
          title="Attach image or file"
          className="shrink-0 text-muted-foreground hover:text-foreground disabled:opacity-40 p-1"
        >
          📎
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*,.pdf"
          multiple
          className="hidden"
          onChange={handleFileChange}
        />

        <textarea
          rows={1}
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          disabled={disabled || isStreaming}
          placeholder={isStreaming ? "Agent is working…" : disabled ? "Waiting for agent…" : "Ask a follow-up question…"}
          className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-base md:text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 min-h-[38px] max-h-[120px] overflow-y-auto"
          style={{ height: "38px" }}
          onInput={e => {
            e.target.style.height = "38px";
            e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
          }}
        />

        {isStreaming ? (
          <button
            type="button"
            onClick={onStop}
            className="shrink-0 rounded-md bg-destructive px-3 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90"
          >
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSend}
            disabled={disabled || (!text.trim() && attachments.length === 0)}
            className="shrink-0 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40"
          >
            Send
          </button>
        )}
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
