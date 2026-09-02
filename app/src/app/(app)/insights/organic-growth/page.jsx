import Desk from "@/components/insights/Desk";

// The desk is entirely client-side: everything on it is user-scoped and
// membership-gated, so there is nothing worth fetching on the server that the
// browser would not have to re-authenticate for anyway.
export const dynamic = "force-dynamic";

export default function OrganicGrowthPage() {
  return <Desk />;
}
