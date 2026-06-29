import { redirect } from "next/navigation";

// `/content/posts` is not a standalone page — "Posts" is a tab on the Content
// Studio landing page. The breadcrumb (path-derived) and any direct link land
// here; send them to the real tab so it never 404s.
export default function PostsIndexRedirect() {
  redirect("/content?tab=posts");
}
