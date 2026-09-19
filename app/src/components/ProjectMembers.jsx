"use client";

import { useCallback, useEffect, useState } from "react";
import { Mail, RotateCw, Trash2, TriangleAlert, UserPlus, X } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Spinner } from "@/components/ui/spinner";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { initials, relativeDays } from "@/lib/format";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  fetchMembers,
  inviteMember,
  removeMember,
  resendInvitation,
  revokeInvitation,
} from "@/lib/membersApi";
import { trackEvent, AnalyticsEvent } from "@/lib/analytics";

function Avatar({ member }) {
  const label = member.full_name || member.email;
  if (member.avatar_url) {
    return (
      <img
        src={member.avatar_url}
        alt=""
        width={36}
        height={36}
        className="size-9 shrink-0 rounded-full border border-border object-cover"
      />
    );
  }
  return (
    <span className="flex size-9 shrink-0 items-center justify-center rounded-full border border-border bg-muted/50 text-2xs font-semibold text-muted-foreground">
      {initials(label)}
    </span>
  );
}

function RowShell({ children }) {
  return (
    <li className="flex items-center gap-3 border-b border-border/60 py-3 last:border-b-0">
      {children}
    </li>
  );
}

export default function ProjectMembers({ projectId, onLeft }) {
  const { t, i18n } = useLingui();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [email, setEmail] = useState("");
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState("");
  const [notice, setNotice] = useState("");

  // id of the row currently running an action, so only that row shows a spinner
  const [busyId, setBusyId] = useState("");
  const [pendingRemoval, setPendingRemoval] = useState(null);

  const load = useCallback(async () => {
    try {
      setData(await fetchMembers(projectId));
      setLoadError("");
    } catch (err) {
      setLoadError(err.message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const isOwner = data?.viewer_role === "owner";

  async function handleInvite(event) {
    event.preventDefault();
    const address = email.trim();
    if (!address || inviting) return;
    setInviting(true);
    setInviteError("");
    setNotice("");
    try {
      await inviteMember(projectId, address);
      // After the await: an invite that failed is not an invite. No email or
      // address in the params — who was invited is not ours to send to GA4.
      trackEvent(AnalyticsEvent.TeamMemberInvited);
      setEmail("");
      const sentTo = address.toLowerCase();
      setNotice(t`Invitation sent to ${sentTo}.`);
      await load();
    } catch (err) {
      setInviteError(err.message);
    } finally {
      setInviting(false);
    }
  }

  async function runRowAction(id, action, successMessage) {
    setBusyId(id);
    setInviteError("");
    setNotice("");
    try {
      await action();
      if (successMessage) setNotice(successMessage);
      await load();
    } catch (err) {
      setInviteError(err.message);
    } finally {
      setBusyId("");
    }
  }

  async function confirmRemoval() {
    const target = pendingRemoval;
    setPendingRemoval(null);
    if (!target) return;
    const leaving = target.is_you;
    const removed = target.email;
    await runRowAction(
      target.user_id,
      () => removeMember(projectId, leaving ? "me" : target.user_id),
      leaving ? "" : t`${removed} no longer has access.`
    );
    if (leaving) onLeft?.();
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
        <Spinner className="size-4" />
        <Trans>Loading members…</Trans>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
        {loadError}
      </div>
    );
  }

  const removalTarget = pendingRemoval?.email || t`this member`;

  return (
    <div className="space-y-5">
      {/* Invite form — owner only */}
      {isOwner ? (
        <form onSubmit={handleInvite} className="space-y-2">
          <div className="flex flex-col gap-2 @md:flex-row">
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t`teammate@company.com`}
              aria-label={t`Email address to invite`}
              autoComplete="off"
              className="@md:flex-1"
            />
            <Button type="submit" disabled={inviting || !email.trim()}>
              {inviting ? (
                <Spinner className="size-4" />
              ) : (
                <UserPlus className="size-4" />
              )}
              <Trans>Send invite</Trans>
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            <Trans>
              They’ll get an email with a link that works only for this address. Collaborators
              can edit the project and run agents; only you can invite people or delete it.
            </Trans>
          </p>
        </form>
      ) : (
        <p className="text-sm text-muted-foreground">
          <Trans>You’re a collaborator on this project. Only the owner can change who has access.</Trans>
        </p>
      )}

      {inviteError && <p className="text-sm text-destructive">{inviteError}</p>}
      {notice && <p className="text-sm text-muted-foreground">{notice}</p>}

      {isOwner && data.email_delivery === "console" && (
        <p className="flex items-start gap-2 rounded-2xl border border-warning/30 bg-warning/5 p-3 text-xs text-warning">
          <TriangleAlert className="mt-px size-4 shrink-0" />
          <span>
            <Trans>
              Email delivery isn’t configured on this environment, so invitations are logged
              server-side instead of sent. Set <code>RESEND_API_KEY</code> to deliver them.
            </Trans>
          </span>
        </p>
      )}

      {/* Members */}
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          <Trans>Members</Trans>
        </h3>
        <ul>
          {data.members.map((member) => {
            const memberEmail = member.email;
            return (
              <RowShell key={member.user_id}>
                <Avatar member={member} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">
                    {member.full_name || member.email}
                    {member.is_you && (
                      <span className="ml-1.5 text-xs font-normal text-muted-foreground"><Trans>(you)</Trans></span>
                    )}
                  </p>
                  {member.full_name && (
                    <p className="truncate text-xs text-muted-foreground">{member.email}</p>
                  )}
                </div>
                <Badge variant={member.role === "owner" ? "default" : "secondary"}>
                  {member.role === "owner" ? t`Owner` : t`Collaborator`}
                </Badge>
                {member.role !== "owner" && (isOwner || member.is_you) && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-8 shrink-0 rounded-full text-muted-foreground hover:text-destructive"
                    aria-label={member.is_you ? t`Leave this project` : t`Remove ${memberEmail}`}
                    disabled={busyId === member.user_id}
                    onClick={() => setPendingRemoval(member)}
                  >
                    {busyId === member.user_id ? (
                      <Spinner className="size-4" />
                    ) : (
                      <Trash2 className="size-4" />
                    )}
                  </Button>
                )}
              </RowShell>
            );
          })}
        </ul>
      </div>

      {/* Pending invitations — only meaningful to the owner, who can act on them */}
      {isOwner && data.invitations.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <Trans>Pending invitations</Trans>
          </h3>
          <ul>
            {data.invitations.map((invitation) => {
              const invitee = invitation.email;
              // relativeDays speaks English ("in 6 days"): the sentence around
              // it is translated, the fragment is not, until lib/format takes
              // a locale.
              const when = relativeDays(invitation.expires_at, { locale: i18n.locale });
              return (
                <RowShell key={invitation.id}>
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full border border-dashed border-border text-muted-foreground">
                    <Mail className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">{invitation.email}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {invitation.is_expired
                        ? t`Expired ${when}`
                        : t`Invited · expires ${when}`}
                    </p>
                  </div>
                  <Badge variant={invitation.is_expired ? "destructive" : "outline"}>
                    {invitation.is_expired ? t`Expired` : t`Invited`}
                  </Badge>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-8 shrink-0 rounded-full text-muted-foreground hover:text-foreground"
                    aria-label={t`Resend invitation to ${invitee}`}
                    disabled={busyId === invitation.id}
                    onClick={() =>
                      runRowAction(
                        invitation.id,
                        () => resendInvitation(projectId, invitation.id),
                        t`New invitation sent to ${invitee}.`
                      )
                    }
                  >
                    {busyId === invitation.id ? (
                      <Spinner className="size-4" />
                    ) : (
                      <RotateCw className="size-4" />
                    )}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-8 shrink-0 rounded-full text-muted-foreground hover:text-destructive"
                    aria-label={t`Revoke invitation to ${invitee}`}
                    disabled={busyId === invitation.id}
                    onClick={() =>
                      runRowAction(
                        invitation.id,
                        () => revokeInvitation(projectId, invitation.id),
                        t`Invitation to ${invitee} revoked.`
                      )
                    }
                  >
                    <X className="size-4" />
                  </Button>
                </RowShell>
              );
            })}
          </ul>
        </div>
      )}

      <AlertDialog
        open={Boolean(pendingRemoval)}
        onOpenChange={(open) => {
          if (!open) setPendingRemoval(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pendingRemoval?.is_you
                ? t`Leave this project?`
                : t`Remove ${removalTarget}?`}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingRemoval?.is_you
                ? t`You'll lose access to this project immediately. The owner can invite you again.`
                : t`They lose access immediately. Anything they already created stays with the project. You can invite them again later.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel type="button"><Trans>Cancel</Trans></AlertDialogCancel>
            <AlertDialogAction
              type="button"
              className={buttonVariants({ variant: "destructive" })}
              onClick={confirmRemoval}
            >
              {pendingRemoval?.is_you ? <Trans>Leave project</Trans> : <Trans>Remove</Trans>}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
