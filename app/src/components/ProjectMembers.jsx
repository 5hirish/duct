"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Mail, RotateCw, Trash2, TriangleAlert, UserPlus, X } from "lucide-react";
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
    <span className="flex size-9 shrink-0 items-center justify-center rounded-full border border-border bg-muted/50 text-[11px] font-semibold text-muted-foreground">
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
      setEmail("");
      setNotice(`Invitation sent to ${address.toLowerCase()}.`);
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
    await runRowAction(
      target.user_id,
      () => removeMember(projectId, leaving ? "me" : target.user_id),
      leaving ? "" : `${target.email} no longer has access.`
    );
    if (leaving) onLeft?.();
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Loading members…
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

  return (
    <div className="space-y-5">
      {/* Invite form — owner only */}
      {isOwner ? (
        <form onSubmit={handleInvite} className="space-y-2">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="teammate@company.com"
              aria-label="Email address to invite"
              autoComplete="off"
              className="sm:flex-1"
            />
            <Button type="submit" disabled={inviting || !email.trim()}>
              {inviting ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <UserPlus className="size-4" />
              )}
              Send invite
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            They&rsquo;ll get an email with a link that works only for this address. Collaborators
            can edit the project and run agents; only you can invite people or delete it.
          </p>
        </form>
      ) : (
        <p className="text-sm text-muted-foreground">
          You&rsquo;re a collaborator on this project. Only the owner can change who has access.
        </p>
      )}

      {inviteError && <p className="text-sm text-destructive">{inviteError}</p>}
      {notice && <p className="text-sm text-muted-foreground">{notice}</p>}

      {isOwner && data.email_delivery === "console" && (
        <p className="flex items-start gap-2 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-400">
          <TriangleAlert className="mt-px size-4 shrink-0" />
          <span>
            Email delivery isn&rsquo;t configured on this environment, so invitations are logged
            server-side instead of sent. Set <code>RESEND_API_KEY</code> to deliver them.
          </span>
        </p>
      )}

      {/* Members */}
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Members
        </h3>
        <ul>
          {data.members.map((member) => (
            <RowShell key={member.user_id}>
              <Avatar member={member} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">
                  {member.full_name || member.email}
                  {member.is_you && (
                    <span className="ml-1.5 text-xs font-normal text-muted-foreground">(you)</span>
                  )}
                </p>
                {member.full_name && (
                  <p className="truncate text-xs text-muted-foreground">{member.email}</p>
                )}
              </div>
              <Badge variant={member.role === "owner" ? "default" : "secondary"}>
                {member.role === "owner" ? "Owner" : "Collaborator"}
              </Badge>
              {member.role !== "owner" && (isOwner || member.is_you) && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8 shrink-0 rounded-full text-muted-foreground hover:text-destructive"
                  aria-label={member.is_you ? "Leave this project" : `Remove ${member.email}`}
                  disabled={busyId === member.user_id}
                  onClick={() => setPendingRemoval(member)}
                >
                  {busyId === member.user_id ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Trash2 className="size-4" />
                  )}
                </Button>
              )}
            </RowShell>
          ))}
        </ul>
      </div>

      {/* Pending invitations — only meaningful to the owner, who can act on them */}
      {isOwner && data.invitations.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Pending invitations
          </h3>
          <ul>
            {data.invitations.map((invitation) => (
              <RowShell key={invitation.id}>
                <span className="flex size-9 shrink-0 items-center justify-center rounded-full border border-dashed border-border text-muted-foreground">
                  <Mail className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">{invitation.email}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {invitation.is_expired
                      ? `Expired ${relativeDays(invitation.expires_at)}`
                      : `Invited · expires ${relativeDays(invitation.expires_at)}`}
                  </p>
                </div>
                <Badge variant={invitation.is_expired ? "destructive" : "outline"}>
                  {invitation.is_expired ? "Expired" : "Invited"}
                </Badge>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8 shrink-0 rounded-full text-muted-foreground hover:text-foreground"
                  aria-label={`Resend invitation to ${invitation.email}`}
                  disabled={busyId === invitation.id}
                  onClick={() =>
                    runRowAction(
                      invitation.id,
                      () => resendInvitation(projectId, invitation.id),
                      `New invitation sent to ${invitation.email}.`
                    )
                  }
                >
                  {busyId === invitation.id ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <RotateCw className="size-4" />
                  )}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8 shrink-0 rounded-full text-muted-foreground hover:text-destructive"
                  aria-label={`Revoke invitation to ${invitation.email}`}
                  disabled={busyId === invitation.id}
                  onClick={() =>
                    runRowAction(
                      invitation.id,
                      () => revokeInvitation(projectId, invitation.id),
                      `Invitation to ${invitation.email} revoked.`
                    )
                  }
                >
                  <X className="size-4" />
                </Button>
              </RowShell>
            ))}
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
                ? "Leave this project?"
                : `Remove ${pendingRemoval?.email || "this member"}?`}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingRemoval?.is_you
                ? "You'll lose access to this project immediately. The owner can invite you again."
                : "They lose access immediately. Anything they already created stays with the project. You can invite them again later."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel type="button">Cancel</AlertDialogCancel>
            <AlertDialogAction
              type="button"
              className={buttonVariants({ variant: "destructive" })}
              onClick={confirmRemoval}
            >
              {pendingRemoval?.is_you ? "Leave project" : "Remove"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
