// Resolved values of the app tokens (app/src/app/styles/tokens.css) for the
// places the film needs a number, not a class: SVG fills, gradients, shadows.
// The CSS side of the film imports the sheet itself; these are the same
// values written out, and the comment on each says which token it is.
export const C = Object.freeze({
  orange: "#ff5c00", // --orange
  navy: "#0d0f1a", // --navy
  navy2: "#2a2d3e", // --navy-2
  navy3: "#6b6f82", // site --navy-3 (the app's is a shade darker)
  ink: "#0b111f", // --foreground
  muted: "#4d535f", // --muted-foreground
  hint: "#8a857e", // sidebar group labels
  border: "#e6e4e1", // --border
  surface: "#f3f1ee", // --muted / --secondary
  paper: "#fbfaf8", // brief pane
  sidebar: "#fefaf3", // --sidebar
  primary: "#3d53e5", // --primary
  success: "#10883c", // --success
  destructive: "#c9000c", // --destructive
  warning: "#9a6500", // --warning
  white: "#ffffff",
});

// The ground under every scene but the last: the README frame gradient
// (scripts/shots/shoot.mjs), so the film sits beside the screenshots as one
// family and a light app still separates from a light stage.
export const GROUND = "linear-gradient(135deg, #fff1e8 0%, #f7f4f0 55%, #e9ecf5 100%)";
export const LIFT = "0 20px 40px rgba(13,15,26,0.18)";

export const FONT = Object.freeze({
  sans: "'DM Sans', ui-sans-serif, system-ui, sans-serif",
  serif: "Georgia, 'Times New Roman', Times, serif",
  mono: "'JetBrains Mono', ui-monospace, Menlo, monospace",
});

export const MAC_DOTS = ["#ff5f57", "#febc2e", "#28c840"];
