import { notFound } from "next/navigation";

// One scene, alone in its own document.
//
// This is the route that matters for an agent: everything is in the URL, so a
// state is addressable without clicking anything —
//   /preview/frame?scene=tile-states&surface=dialog&theme=dark&inspect=outline
// Point a browser at it with the viewport set to the device you care about and
// the answer is on screen with no shell chrome in the way.
//
// The shell at /preview embeds these in iframes, which is the only honest way
// to show several devices at once: media queries read the viewport, and a
// resized <div> is not one.
export const metadata = { robots: { index: false, follow: false } };

export default async function PreviewFramePage() {
  if (process.env.NODE_ENV === "production") notFound();
  const { default: PreviewFrame } = await import("../PreviewFrame");
  return <PreviewFrame />;
}
