"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ArrowUp, Paperclip, Square } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";

import { Button } from "@/components/ui/button";
import {
  ATTACH_MAX_BYTES,
  AttachmentKind,
  attachmentKind,
  contentBlocks,
  isLargePaste,
  mediaTypeFor,
  pastedAttachment,
} from "@/lib/attachments";
import { clearDraft, readDraft, writeDraft } from "@/lib/composerDraft";
import { matchesCombo, isComposing } from "@/lib/shortcuts";
import { AttachmentStrip, DropHint } from "./Attachments";

/**
 * The chat composer every agent shell uses: text, attached files, Enter to
 * send, a Stop button beside Send while the agent is producing tokens. The
 * box stays open while it works — a message then is queued for the model's
 * next step, which the caller's placeholder says — and closes only when
 * there is nothing to send to (`disabled`).
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
 * Files arrive three ways and become the same tile: the attach button, a
 * drop anywhere on the card (the whole card is the target, with a hint
 * while a file is over it), and a paste — an image from the clipboard, or a
 * block of text too long to read in the box, which becomes a file of
 * whatever it looks like (lib/attachments.js `sniffPaste`). What goes out is
 * `contentBlocks`: a plain string when nothing is attached, else the text
 * and one block per file.
 *
 * What was typed is kept. The text is saved under `draftKey` (the shell's
 * session key, so this thread's draft comes back on this thread) through
 * lib/composerDraft on every change, restored on mount and cleared on send;
 * a reload mid-sentence used to lose it. Per tab (sessionStorage), so it
 * survives the reload and nothing else: the key names a thread, not a user,
 * and a shared browser's next sign-in must not find it. Esc in the box
 * stops a streaming turn — scoped to the box on purpose, since a
 * window-level Escape would also fire while someone closes a popover — and
 * the footer names both that and Shift+Enter while the box has focus.
 */
export default function ChatInput({
  onSend,
  disabled,
  isStreaming,
  onStop,
  // Both default to the shell's own words, resolved below so they follow the
  // interface language.
  placeholder,
  ariaLabel,
  accept = DEFAULT_ACCEPT,
  // { text, key }: text handed back by the session (a queued message the
  // user stopped before it was read). Applied once per `key`.
  draft = null,
  // Where the unsent text is kept across a reload. Empty keeps nothing (the
  // preview gallery, a shell with no thread yet).
  draftKey = "",
  tools = null,
  status = null,
  // Tiles already on the card when it mounts — the preview gallery's seed.
  initialAttachments = [],
}) {
  const { t } = useLingui();
  const placeholderText = placeholder ?? t`Ask a follow-up question…`;
  const ariaLabelText = ariaLabel ?? t`Message the agent`;
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState(initialAttachments);
  // A file that could not be attached says why, under the tiles, until the
  // next successful attach; a silently dropped file is a message the model
  // never saw and the person thinks it did.
  const [notice, setNotice] = useState("");
  const [dragging, setDragging] = useState(false);
  // dragenter/dragleave fire for every child the pointer crosses; the depth
  // count is what keeps the hint from flickering on each one.
  const dragDepth = useRef(0);
  const fileRef = useRef(null);
  const pasteCount = useRef(0);
  const textareaRef = useRef(null);
  const [focused, setFocused] = useState(false);
  const hintId = useId();

  // Read in an effect, not in the state initialiser: the server render has
  // no storage, and a textarea whose value differs at hydration is a warning
  // and a flash. Only an empty box takes the saved text, so a handed-back
  // queued message that landed first is not overwritten.
  useEffect(() => {
    const saved = readDraft(draftKey);
    if (saved) setText((current) => current || saved);
  }, [draftKey]);

  useEffect(() => {
    if (!draft?.text) return;
    const merged = text.trim() ? `${text}\n\n${draft.text}` : draft.text;
    setText(merged);
    writeDraft(draftKey, merged);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft?.key]);

  // The box grows with its text up to a cap, whichever way the text arrived:
  // typed, restored, or handed back by Stop.
  useEffect(() => {
    fitHeight(textareaRef.current);
  }, [text]);

  function handleChange(e) {
    setText(e.target.value);
    writeDraft(draftKey, e.target.value);
  }

  function handleKeyDown(e) {
    if (isStreaming && onStop && matchesCombo(e, "escape")) {
      e.preventDefault();
      onStop();
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !isComposing(e)) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleSend() {
    const trimmed = text.trim();
    if (!trimmed && attachments.length === 0) return;
    onSend(contentBlocks(trimmed, attachments));
    clearDraft(draftKey);
    setText("");
    setAttachments([]);
    setNotice("");
  }

  async function addFiles(files) {
    const added = [];
    for (const file of files) {
      const mediaType = mediaTypeFor(file.name, file.type);
      const kind = attachmentKind(mediaType, file.name);
      const name = file.name || t`pasted image`;
      if (kind === AttachmentKind.FILE) {
        setNotice(t`${name} was not attached — send images, PDFs or text files.`);
        continue;
      }
      if (file.size > ATTACH_MAX_BYTES) {
        const max = Math.round(ATTACH_MAX_BYTES / 1024 / 1024);
        setNotice(t`${name} was not attached — the limit is ${max} MB per file.`);
        continue;
      }
      const att = { name, mediaType, kind, size: file.size };
      if (kind === AttachmentKind.TEXT) att.text = await file.text();
      else {
        att.data = await fileToBase64(file);
        if (kind === AttachmentKind.IMAGE) att.preview = `data:${mediaType};base64,${att.data}`;
      }
      added.push(att);
    }
    if (added.length) {
      setAttachments((prev) => [...prev, ...added]);
      setNotice("");
    }
  }

  async function handleFileChange(e) {
    await addFiles(Array.from(e.target.files || []));
    e.target.value = "";
  }

  async function handlePaste(e) {
    const items = Array.from(e.clipboardData?.items || []);
    const files = items.filter((it) => it.kind === "file").map((it) => it.getAsFile()).filter(Boolean);
    if (files.length) {
      e.preventDefault();
      await addFiles(files);
      return;
    }
    const pasted = e.clipboardData?.getData("text/plain") || "";
    if (!isLargePaste(pasted)) return;
    e.preventDefault();
    pasteCount.current += 1;
    setAttachments((prev) => [...prev, pastedAttachment(pasted, pasteCount.current)]);
    setNotice("");
  }

  function hasFiles(e) {
    return Array.from(e.dataTransfer?.types || []).includes("Files");
  }

  function handleDragEnter(e) {
    if (disabled || !hasFiles(e)) return;
    e.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  }

  function handleDragOver(e) {
    if (disabled || !hasFiles(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  }

  function handleDragLeave(e) {
    if (!hasFiles(e)) return;
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  }

  async function handleDrop(e) {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    if (disabled) return;
    await addFiles(Array.from(e.dataTransfer.files || []));
  }

  function removeAttachment(index) {
    setAttachments((prev) => prev.filter((_, j) => j !== index));
  }

  const canSend = !disabled && (text.trim() || attachments.length > 0);

  return (
    <div className="border-t border-border/60 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom,0.75rem))]">
      <div
        className={`relative mx-auto max-w-3xl rounded-xl border bg-card focus-within:border-ring ${dragging ? "border-ring" : ""}`}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {dragging && <DropHint />}

        <AttachmentStrip attachments={attachments} onRemove={removeAttachment} className="px-2 pt-2" />
        {notice && (
          <p role="status" className="px-4 pt-2 text-2xs text-warning">
            {notice}
          </p>
        )}

        <textarea
          ref={textareaRef}
          rows={1}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          aria-label={ariaLabelText}
          aria-describedby={focused ? hintId : undefined}
          disabled={disabled}
          placeholder={disabled ? t`Waiting for agent…` : placeholderText}
          className="max-h-[160px] min-h-[44px] w-full resize-none overflow-y-auto bg-transparent px-4 pt-3 pb-1 text-base leading-relaxed outline-none placeholder:text-muted-foreground disabled:opacity-50 md:text-sm"
          style={{ height: `${MIN_HEIGHT}px` }}
        />

        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-2.5 pb-2.5">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => fileRef.current?.click()}
              disabled={disabled}
              aria-label={t`Attach a file`}
              title={t`Attach a file — or drop one here`}
              className="text-muted-foreground"
            >
              <Paperclip aria-hidden />
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept={accept}
              aria-label={t`Attach files`}
              multiple
              className="hidden"
              onChange={handleFileChange}
            />
            {tools}
            {focused && (
              <span id={hintId} className="hidden text-2xs text-muted-foreground @md:inline">
                {isStreaming
                  ? <Trans>Shift+Enter for a new line · Esc to stop</Trans>
                  : <Trans>Shift+Enter for a new line</Trans>}
              </span>
            )}
          </div>

          <div className="ml-auto flex shrink-0 items-center gap-1.5">
            {status}
            {isStreaming && (
              <Button type="button" variant="destructive" size="xs" onClick={onStop}>
                <Square className="fill-current" aria-hidden />
                <Trans>Stop</Trans>
              </Button>
            )}
            <Button
              type="button"
              size="icon-xs"
              onClick={handleSend}
              disabled={!canSend}
              aria-label={t`Send`}
            >
              <ArrowUp className="size-3.5" aria-hidden />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// What the model can read: pictures, PDFs and anything that is text. The
// picker filters to these; a drop or a paste of something else gets the
// notice instead.
const DEFAULT_ACCEPT = "image/*,.pdf,.txt,.md,.csv,.tsv,.json,.html,.xml,.yaml,.yml";

// The box's height band. The classes on the textarea (`min-h-[44px]
// max-h-[160px]`) say the same numbers for the first paint, before the
// effect has measured anything.
const MIN_HEIGHT = 44;
const MAX_HEIGHT = 160;

function fitHeight(el) {
  if (!el) return;
  el.style.height = `${MIN_HEIGHT}px`;
  el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
