// The design system's components: every part in app/src/components/ui that a
// screen picks between, plus the canon patterns built from them. `scene` is the
// /preview scene the preview is captured from; `canon` names the rows of
// app/DESIGN.md's canon table whose rule becomes the README, word for word.
// `summary` is the README's first sentence, which the system's page shows as
// the component's one line.
export const COMPONENTS = [
  // Actions
  { name: "Button", group: "Actions", scene: "ui-button", canon: ["Destructive action (the button that opens that confirm)"], source: ["app/src/components/ui/button.tsx"], summary: "Six variants and four sizes, chosen by name at the call site: one primary per screen, destructive tinted red at rest." },

  // Forms
  { name: "Input", group: "Forms", scene: "ui-input", source: ["app/src/components/ui/input.tsx", "app/src/components/ui/label.tsx"], summary: "A single-line field: a rectangle at the control radius with a visible label above it, never a placeholder standing in for one." },
  { name: "Textarea", group: "Forms", scene: "ui-textarea", canon: ["Multi-line field"], source: ["app/src/components/ui/textarea.tsx"], summary: "The one multi-line field: the field radius, growing with its text to a cap and then scrolling." },
  { name: "Select", group: "Forms", scene: "ui-select", source: ["app/src/components/ui/select.tsx"], summary: "A Radix select drawn in the app's own surface, never the OS menu; opens as a popper below its trigger." },
  { name: "Checkbox", group: "Forms", scene: "ui-checkbox", source: ["app/src/components/ui/checkbox.tsx"], summary: "A square check filled with the primary orange when on, always beside its label." },
  { name: "Switch", group: "Forms", scene: "ui-switch", source: ["app/src/components/ui/switch.tsx"], summary: "An on/off setting that takes effect at once; the word beside it says what on means." },
  { name: "Slider", group: "Forms", scene: "ui-slider", source: ["app/src/components/ui/slider.tsx"], summary: "A stepped or continuous range; a stepped one shows a dot per stop and names the current stop beside its title." },

  // Navigation
  { name: "Tabs", group: "Navigation", scene: "ui-tabs", source: ["app/src/components/ui/tabs.tsx"], summary: "Views of one thing, side by side: a hub's sections (Content Studio) or a settings page's parts." },
  { name: "Breadcrumb", group: "Navigation", scene: "ui-breadcrumb", source: ["app/src/components/ui/breadcrumb.tsx"], summary: "The top bar's trail on a full-bleed workspace and the way back on a nested page; never a third copy of the page's title." },
  { name: "DropdownMenu", group: "Navigation", scene: "ui-menu", source: ["app/src/components/ui/dropdown-menu.tsx"], summary: "A list of commands under a trigger; it roves focus and swallows Tab, so a form goes in a Popover instead." },

  // Layout
  { name: "Page", group: "Layout", scene: "ui-page", canon: ["Page frame"], source: ["app/src/components/ui/page.jsx"], summary: "The page frame every routed screen is built from: Page, PageHeader (the one h1, one line of status, actions, help behind a \"?\") and Section." },
  { name: "TileGrid", group: "Layout", scene: "canon-grid-of-cards", canon: ["Grid of cards"], source: ["app/src/components/ui/page.jsx"], summary: "Every grid of cards: columns from the container, so a known set of four lands 2×2, never three and an orphan." },
  { name: "Card", group: "Layout", scene: "ui-card", canon: ["Card"], source: ["app/src/components/ui/card.tsx"], summary: "The one bordered group: rounded-xl, 24px padding, a footer pinned to the bottom so a row of cards shares a baseline." },
  { name: "Table", group: "Layout", scene: "ui-table", source: ["app/src/components/ui/table.tsx"], summary: "For comparing: tabular figures, right-aligned numbers, a sticky header inside its own scroll box." },

  // Overlays
  { name: "Popover", group: "Overlays", scene: "ui-popover", source: ["app/src/components/ui/popover.tsx"], summary: "A small form anchored to its trigger (a slider, a radio group), where Tab walks every control and Escape returns." },
  { name: "Tooltip", group: "Overlays", scene: "ui-tooltip", source: ["app/src/components/ui/tooltip.tsx"], summary: "The name of an icon-only button, or the whole of a clamped line; opens on hover and on keyboard focus." },
  { name: "Dialog", group: "Overlays", scene: "canon-dialog-actions", canon: ["Dialog actions"], source: ["app/src/components/ui/dialog.tsx", "app/src/components/ui/sheet.tsx"], summary: "A Radix dialog at rounded-2xl with its actions in the footer, below what they act on, primary rightmost." },
  { name: "ConfirmDialog", group: "Overlays", scene: "canon-destructive-confirm", canon: ["Destructive confirm"], source: ["app/src/components/ui/confirm-dialog.jsx", "app/src/components/ui/alert-dialog.tsx"], summary: "\"Are you sure?\" for anything that cannot be undone: the title quotes the object, the action is verb + noun." },
  { name: "Lightbox", group: "Overlays", scene: "ui-lightbox", source: ["app/src/components/ui/lightbox.jsx"], summary: "A picture at full size over a dimmed app, closed by Escape, a click outside or its close button." },
  { name: "CornerNotice", group: "Overlays", scene: "canon-corner-notification", canon: ["Corner notification"], source: ["app/src/components/ui/corner-notice.jsx"], summary: "The bottom-right card that tells you something without interrupting; a notice that tells outranks one that asks." },

  // Status
  { name: "Badge", group: "Status", scene: "ui-badge", canon: ["Status badge"], source: ["app/src/components/ui/badge.tsx"], summary: "A word of state in a capsule: success, warning, info or destructive tint the ground and colour the text." },
  { name: "Progress", group: "Status", scene: "ui-progress", source: ["app/src/components/ui/progress.tsx"], summary: "How far through a known amount of work, in the primary orange on a muted track." },
  { name: "Spinner", group: "Status", scene: "canon-busy-indicator", canon: ["Busy indicator"], source: ["app/src/components/ui/spinner.jsx"], summary: "A request in flight from an action (a button, a poll); never for content that has a shape." },
  { name: "Skeleton", group: "Status", scene: "canon-loading-a-page", canon: ["Loading a page or a pane", "Content reveal after a load"], source: ["app/src/components/ui/skeleton.tsx", "app/src/components/ui/reveal.jsx"], summary: "The loaded layout's shape in muted blocks under one sheen, swapped for the content with a short fade." },
  { name: "PipelineProgress", group: "Status", scene: "canon-long-running-agent-work", canon: ["Long-running agent work"], source: ["app/src/components/PipelineProgress.jsx"], summary: "An agent's run as a ladder of steps with a rotating subtitle: done steps dim, nothing moves." },
  { name: "InlineError", group: "Status", scene: "canon-inline-error", canon: ["Inline error"], source: ["app/DESIGN.md (a pattern of utilities; no component of its own)"], summary: "A failure said where it happened: one destructive line with role=\"alert\", or the boxed variant for a section." },

  // Empty and first-run
  { name: "EmptyState", group: "Empty states", scene: "canon-empty-state-whole-surface", canon: ["Empty state (whole surface)", "Empty state (inside a stable layout)"], source: ["app/src/components/ui/empty-state.jsx"], summary: "A dashed panel with one icon, one line and a verb-first action; its example slot shows the filled surface below." },
  { name: "FirstRun", group: "Empty states", scene: "canon-first-run", canon: ["First-run"], source: ["app/src/components/insights/desk/DeskDayOne.jsx", "app/src/components/content/ConnectorGate.jsx"], summary: "A first visit shows what Duct already knows and a short checklist, never \"No X yet\": an empty board teaches nothing." },

  // Agent
  { name: "QuestionsCard", group: "Agent", scene: "canon-agent-question-pick-from-options", canon: ["Agent question (pick from options)"], source: ["app/src/components/workspace/QuestionsCard.jsx", "app/src/components/workspace/PauseCard.jsx"], summary: "An agent's question as full-width option rows, a label and one clause each, with an Other row that opens in place." },

  // Text
  { name: "ClampText", group: "Text", scene: "canon-truncated-text-2-lines", canon: ["Truncated text (2+ lines)"], source: ["app/src/components/ui/clamp-text.tsx"], summary: "Model-written text held to N lines, with the whole string in a tooltip on hover and focus." },
];
