// The first client code Next.js runs, before hydration: the place to start
// listening for errors. The reporter itself loads when the page is idle
// (`lib/analytics/posthog.js`), so this adds a few listeners to the first
// load, not a library.
import { startErrorReporting } from "./lib/analytics";

startErrorReporting();
