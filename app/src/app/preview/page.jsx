import { notFound } from "next/navigation";

// Never ships. `next build` runs with NODE_ENV=production, so the guard is
// statically true there and the route 404s.
//
// The import is dynamic and sits *after* the guard on purpose: a static one at
// the top of the file pulls the shell, every scene, and every component a
// scene imports into the build whether or not the route can be reached. The
// route 404ing is not the same as the code not being there.
export const metadata = { robots: { index: false, follow: false } };

export default async function PreviewPage() {
  if (process.env.NODE_ENV === "production") notFound();
  const { default: PreviewShell } = await import("./PreviewShell");
  return <PreviewShell />;
}
