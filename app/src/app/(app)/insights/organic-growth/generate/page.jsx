// Was a re-export of the deleted wizard. Same redirect, same reason: the URL
// outlives the page.

import { redirect } from "next/navigation";

export default function OrganicGrowthGenerateRedirect() {
  redirect("/insights/session");
}
