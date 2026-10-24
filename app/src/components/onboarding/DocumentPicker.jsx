"use client";

// The files a person adds beside their website on the "Found it" card: a
// pitch deck, a positioning doc, a brief. The site says what a visitor should
// read; these say who buys and who the competition is, which is most of a
// project.
//
// It sits on the "Found it" card rather than beside the URL field because
// every path reaches that card, including the landing page's hand-off, which
// skips the field entirely. And it is an offer, not a step: nothing here
// blocks "continue" except a file still being read.
//
// Presentational. The page owns the upload (lib/onboardingApi.js) and hands
// each file's state back down, so /preview can draw every state from props.

import { useRef, useState } from "react";
import { AlertTriangle, Check, FileText, Plus, X } from "lucide-react";
import { msg, plural } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { DropHint } from "@/components/workspace/Attachments";
import { attachmentLabel } from "@/lib/attachments";
import { DOCUMENT_EXTENSIONS, DOCUMENT_MAX_FILES, DocumentError } from "@/lib/onboardingApi";

export const DocumentState = Object.freeze({
  READING: "reading",
  READY: "ready",
  FAILED: "failed",
});

// Each reason says what the person can do about it where there is something.
const ERROR_COPY = {
  [DocumentError.UNSUPPORTED]: msg`Duct can't read this type yet`,
  [DocumentError.TOO_LARGE]: msg`Over 10 MB`,
  [DocumentError.ENCRYPTED]: msg`Password-protected. Save a copy without one`,
  [DocumentError.NO_TEXT]: msg`No text in it. A scan?`,
  [DocumentError.DAMAGED]: msg`Couldn't open it`,
  [DocumentError.UPLOAD_FAILED]: msg`Didn't upload. Remove it and add it again`,
};

const ACCEPT = DOCUMENT_EXTENSIONS.map((ext) => `.${ext}`).join(",");

function DocumentStatus({ doc }) {
  const { i18n } = useLingui();
  if (doc.state === DocumentState.READING) {
    return (
      <span className="start-docs-status">
        <Spinner className="size-3" />
        <Trans>Reading…</Trans>
      </span>
    );
  }
  if (doc.state === DocumentState.FAILED) {
    return (
      <span className="start-docs-status start-docs-status-failed">
        <AlertTriangle className="size-3.5 shrink-0" aria-hidden />
        {i18n._(ERROR_COPY[doc.error] || ERROR_COPY[DocumentError.DAMAGED])}
      </span>
    );
  }
  // Plain identifiers, so the catalogue names them rather than numbering them.
  const pages = doc.pages;
  const read = pages ? plural(pages, { one: "# page", other: "# pages" }) : null;
  return (
    <span className="start-docs-status">
      <Check className="size-3.5 shrink-0 text-success" aria-hidden />
      {doc.truncated ? (
        read ? <Trans>{read}, partly read</Trans> : <Trans>Partly read</Trans>
      ) : (
        read || <Trans>Read</Trans>
      )}
    </span>
  );
}

function DocumentRow({ doc, onRemove }) {
  const { t } = useLingui();
  const name = doc.name;
  return (
    <li className="start-docs-row">
      <span className="start-docs-badge" aria-hidden>{attachmentLabel("", name)}</span>
      <span className="start-docs-name" title={name}>{name}</span>
      <DocumentStatus doc={doc} />
      <Button type="button" variant="ghost" size="icon-xs" onClick={onRemove} aria-label={t`Remove ${name}`}>
        <X aria-hidden />
      </Button>
    </li>
  );
}

/**
 * `documents`: `[{ key, name, state, pages?, truncated?, error? }]`.
 * `onAdd(files)` gets the picked or dropped files, already capped to the room
 * left; `onRemove(key)` takes one off.
 */
export default function DocumentPicker({ documents = [], onAdd, onRemove }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const room = DOCUMENT_MAX_FILES - documents.length;

  function add(fileList) {
    const files = Array.from(fileList || []).slice(0, Math.max(room, 0));
    if (files.length) onAdd?.(files);
  }

  return (
    <div
      className="start-docs"
      onDragOver={(e) => {
        if (room <= 0 || !e.dataTransfer?.types?.includes("Files")) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        add(e.dataTransfer?.files);
      }}
    >
      {dragging && <DropHint />}
      <div className="start-docs-head">
        <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0">
          <p className="text-sm font-medium">
            <Trans>Got a deck or a doc that says more?</Trans>
          </p>
          <p className="start-docs-hint">
            <Trans>
              Add a pitch deck, a positioning doc or a brief, and Duct drafts your project from those too.
            </Trans>
          </p>
        </div>
      </div>

      {documents.length > 0 && (
        <ul className="start-docs-list" aria-live="polite">
          {documents.map((doc) => (
            <DocumentRow key={doc.key} doc={doc} onRemove={() => onRemove?.(doc.key)} />
          ))}
        </ul>
      )}

      {room > 0 && (
        <div className="start-docs-actions">
          <Button type="button" variant="outline" size="sm" onClick={() => inputRef.current?.click()}>
            <Plus className="size-4" aria-hidden />
            <Trans>Add documents</Trans>
          </Button>
          <span className="start-docs-hint">
            <Trans>PDF, Word, PowerPoint, Markdown or text. Up to five.</Trans>
          </span>
        </div>
      )}
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          add(e.target.files);
          // The same file picked again after a remove must fire again.
          e.target.value = "";
        }}
      />
    </div>
  );
}
