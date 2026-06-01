import { redirect } from "next/navigation";

export default async function ProjectConfigPage({ params }) {
  const { projectId } = await params;
  redirect(`/onboarding?project_id=${encodeURIComponent(projectId)}`);
}
