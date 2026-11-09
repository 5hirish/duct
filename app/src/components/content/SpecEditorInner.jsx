"use client";

import { Component, useCallback, useState } from "react";
import {
  BlockTypeSelect,
  BoldItalicUnderlineToggles,
  CodeToggle,
  CreateLink,
  DiffSourceToggleWrapper,
  InsertCodeBlock,
  InsertTable,
  InsertThematicBreak,
  ListsToggle,
  MDXEditor,
  Separator,
  UndoRedo,
  codeBlockPlugin,
  diffSourcePlugin,
  headingsPlugin,
  linkDialogPlugin,
  linkPlugin,
  listsPlugin,
  markdownShortcutPlugin,
  quotePlugin,
  tablePlugin,
  thematicBreakPlugin,
  toolbarPlugin,
  useCodeBlockEditorContext,
} from "@mdxeditor/editor";
import "@mdxeditor/editor/style.css";
import { Trans } from "@lingui/react/macro";

import { Textarea } from "@/components/ui/textarea";

// A code block edits as a plain text box. CodeMirror would add syntax colours
// and another quarter megabyte; a format spec's fenced blocks are prompt
// templates, where colours mean nothing.
function PlainCodeEditor({ code = "" }) {
  const { setCode } = useCodeBlockEditorContext();
  return (
    <Textarea
      className="spec-editor-code field-sizing-content max-h-none font-mono text-xs"
      value={code}
      spellCheck={false}
      onChange={(e) => setCode(e.target.value)}
      rows={Math.min(16, Math.max(3, code.split("\n").length))}
    />
  );
}

const plainCodeDescriptor = {
  priority: 0,
  match: () => true,
  Editor: PlainCodeEditor,
};

function Toolbar() {
  return (
    <DiffSourceToggleWrapper options={["rich-text", "source"]}>
      <UndoRedo />
      <Separator />
      <BlockTypeSelect />
      <Separator />
      <BoldItalicUnderlineToggles />
      <CodeToggle />
      <Separator />
      <ListsToggle options={["bullet", "number"]} />
      <Separator />
      <CreateLink />
      <InsertTable />
      <InsertThematicBreak />
      <InsertCodeBlock />
    </DiffSourceToggleWrapper>
  );
}

// Lexical throws during render on a document it cannot model (raw HTML, an
// unclosed JSX tag pasted from a skill file). The boundary turns that into
// the plain editor, with the text intact, instead of a white sheet.
class EditorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onFail?.();
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export default function SpecEditorInner({ value, onChange, placeholder, className = "" }) {
  const [fallback, setFallback] = useState(false);
  const fail = useCallback(() => setFallback(true), []);

  if (fallback) {
    return (
      <div className={className}>
        <p className="mb-1.5 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-2xs text-foreground/80">
          <Trans>
            This document uses markup the visual editor can’t show, so you’re editing it as
            text. Nothing was changed.
          </Trans>
        </p>
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
          className="field-sizing-fixed h-[48vh] max-h-none font-mono"
        />
      </div>
    );
  }

  return (
    <div className={`spec-editor ${className}`}>
      <EditorBoundary onFail={fail}>
        <MDXEditor
          markdown={value || ""}
          onChange={onChange}
          onError={fail}
          placeholder={placeholder}
          contentEditableClassName="spec-editor-content"
          plugins={[
            headingsPlugin({ allowedHeadingLevels: [1, 2, 3, 4] }),
            listsPlugin(),
            quotePlugin(),
            thematicBreakPlugin(),
            tablePlugin(),
            linkPlugin(),
            linkDialogPlugin(),
            codeBlockPlugin({ codeBlockEditorDescriptors: [plainCodeDescriptor] }),
            markdownShortcutPlugin(),
            diffSourcePlugin({ viewMode: "rich-text" }),
            toolbarPlugin({ toolbarContents: () => <Toolbar /> }),
          ]}
        />
      </EditorBoundary>
    </div>
  );
}
