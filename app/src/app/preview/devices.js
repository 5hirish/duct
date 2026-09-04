// The devices Duct actually runs on, and the widths its layout breaks at.
//
// Two rulers, and the harness needs both. `AGENTS.md` is right that components
// here size to their CONTAINER — but the app does keep viewport media queries
// for "genuine device concerns" (the sign-in page, the sidebar's mobile sheet,
// the pane toggle, `md:text-sm` on chat inputs so iOS stops zooming). A `<div>`
// resized to 390px answers the container question and gets the viewport one
// wrong, which is why every scene renders in an iframe: a real viewport, so
// `sm:`/`md:` and `dvh` behave the way they will on the device.
//
// Sizes are CSS pixels — the logical viewport, not the hardware one.

export const DEVICES = [
  {
    id: "phone",
    label: "Phone",
    platform: "web",
    w: 390,
    h: 844,
    note: "iPhone-class. Below `sm`, so the mobile sheet and pane toggle are live.",
  },
  {
    id: "ipad-portrait",
    label: "iPad ↕",
    platform: "ipad",
    w: 834,
    h: 1112,
    note: "Inside the 600–1100 band DESIGN.md calls the forgotten middle.",
  },
  {
    id: "ipad-landscape",
    label: "iPad ↔",
    platform: "ipad",
    w: 1112,
    h: 834,
    note: "Wide enough for the sidebar, short enough to expose vertical overflow.",
  },
  {
    id: "desktop-min",
    label: "Desktop min",
    platform: "desktop",
    w: 900,
    h: 620,
    note: "A deliberately small app window. Short viewport: dialogs must scroll, not clip.",
  },
  {
    id: "desktop",
    label: "Desktop",
    platform: "desktop",
    w: 1280,
    h: 800,
    note: "The default the app is usually seen at.",
  },
  {
    id: "wide",
    label: "Wide",
    platform: "web",
    w: 1680,
    h: 900,
    note: "Where measure caps and max-widths have to do their job.",
  },
];

export const DEFAULT_DEVICES = ["ipad-portrait", "desktop"];

export function device(id) {
  return DEVICES.find((d) => d.id === id) || DEVICES.find((d) => d.id === "desktop");
}
