"use client";

// Share a report with the team — the "it should reach someone" moment.
//
// A report is project-scoped, so sharing is membership: the link opens only
// for members, and inviting one is the Members page's job. This dialog is the
// join between the two, plus the one gate that matters for onboarding: a
// guest cannot invite anyone — their name on an invitation would be a
// synthetic install id — so for a guest this is the sign-in moment, with the
// report as the reason. Sign-in links their guest work to the account
// (lib/guest.js), so nothing is lost by saying yes.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, Copy, LogIn, Share2, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { AnalyticsEvent, AnalyticsParam, trackEvent } from "@/lib/analytics";
import { isGuestToken } from "@/lib/guest";

const POST_SIGNIN_REDIRECT_KEY = "duct_post_signin_redirect";
const COPIED_MS = 1800;

export function shareUrl({ conversationId, projectId, siteUrl }) {
  if (typeof window === "undefined" || !conversationId) return "";
  const qs = new URLSearchParams();
  if (projectId) qs.set("p", projectId);
  if (siteUrl) qs.set("u", siteUrl);
  const query = qs.toString();
  return `${window.location.origin}/open/audit/${encodeURIComponent(conversationId)}${query ? `?${query}` : ""}`;
}

export default function ShareReport({ conversationId, projectId, siteUrl }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [guest, setGuest] = useState(false);

  useEffect(() => {
    if (open) setGuest(isGuestToken());
  }, [open]);

  if (!conversationId) return null;
  const url = shareUrl({ conversationId, projectId, siteUrl });

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      trackEvent(AnalyticsEvent.AuditShared, { [AnalyticsParam.Method]: "link" });
      setTimeout(() => setCopied(false), COPIED_MS);
    } catch {
      /* the field below is selectable; the user can copy it by hand */
    }
  }

  function signIn() {
    try {
      sessionStorage.setItem(POST_SIGNIN_REDIRECT_KEY, `${window.location.pathname}${window.location.search}`);
    } catch {
      /* they land on the desk after sign-in instead */
    }
    router.push("/");
  }

  return (
    <>
      <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(true)}>
        <Share2 className="size-4" aria-hidden />
        Share
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          {guest ? (
            <>
              <DialogHeader>
                <DialogTitle>Sign in to share this</DialogTitle>
                <DialogDescription>
                  Sharing is by membership, and a member needs a name. Sign in with Google and this
                  project, the report and the conversation come with you — nothing is lost.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button type="button" onClick={signIn}>
                  <LogIn className="size-4" aria-hidden />
                  Sign in and share
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle>Share this report</DialogTitle>
                <DialogDescription>
                  Only members of this project can open the link. Nothing here is public.
                </DialogDescription>
              </DialogHeader>
              <div className="flex gap-2">
                <Input readOnly value={url} onFocus={(e) => e.target.select()} aria-label="Report link" />
                <Button type="button" variant="outline" onClick={copy} className="shrink-0">
                  {copied ? <Check className="size-4 text-success" aria-hidden /> : <Copy className="size-4" aria-hidden />}
                  {copied ? "Copied" : "Copy"}
                </Button>
              </div>
              <DialogFooter className="sm:justify-between">
                <p className="text-xs text-muted-foreground">Someone new? Invite them and send the link.</p>
                {projectId && (
                  <Button asChild variant="secondary" onClick={() => trackEvent(AnalyticsEvent.AuditShared, { [AnalyticsParam.Method]: "invite" })}>
                    <Link href={`/project/${encodeURIComponent(projectId)}/members`}>
                      <UserPlus className="size-4" aria-hidden />
                      Invite a teammate
                    </Link>
                  </Button>
                )}
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
