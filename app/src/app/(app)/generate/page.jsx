// The six-step insight wizard used to live here: sources → Ads account → GA4
// property → GSC site → goal → review, ~2,100 lines, every interesting
// decision made before the model was ever invoked. The autonomous session
// discovers or asks for all of it mid-run, so the form has no job left.
//
// The route survives only as a redirect: the old URL is in browser history,
// in bookmarks, and in links people have already sent each other.

import { redirect } from "next/navigation";

export default function GenerateRedirect() {
  redirect("/insights/session");
}
