// The build this deployment is serving.
//
// The first route handler in this app, and the reason is that it cannot be
// anything else: the client needs to learn the *currently deployed* build, and
// every other answer it could ask is baked into the bundle it already has.
// A static `public/version.json` would be written at build time and then served
// from the edge cache, which is the one failure that makes this check quietly
// useless. Everything else in `app/` still talks to the FastAPI backend through
// `lib/api.js`, and should — the backend deploys separately from this worker
// and does not know its build.
//
// `force-dynamic` because the whole point is to bypass every layer of caching
// between here and the tab.

export const dynamic = "force-dynamic";
export const revalidate = 0;

export function GET() {
  const build = process.env.NEXT_PUBLIC_BUILD_ID || "";
  return new Response(JSON.stringify({ build }), {
    headers: {
      "content-type": "application/json",
      // Read by lib/appVersion.js in preference to the body — a header costs no
      // parse and survives an error page that a JSON body would not.
      "x-duct-build": build,
      "cache-control": "no-store, no-cache, must-revalidate",
    },
  });
}
