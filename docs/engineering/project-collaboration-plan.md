# Project collaboration — invitations and members

Status: **shipped (v1)** · Scope: `backend/`, `app/`

Lets a project owner invite teammates by email and collaborate on the same
project. Deliberately the smallest thing that is still correct: one extra role,
one shareable object, no org layer.

## Decisions

### The project is the unit of sharing

There is no organisation or workspace entity in the product, and inventing one
to hold a member list would mean a migration for every existing user plus a
concept in the UI that nothing else uses. A project is already the thing people
name, configure, and generate against, so it is the thing they share.

Consequence: the member list lives **in project settings** (`/project/:id/members`),
reachable from the project setup screen and the projects list. The user-level
surface is deliberately thin — shared projects appear in the normal projects
list with a "Shared by …" badge, rather than in a separate account-settings
page. One list, one owner, and the invite button sits next to the project it
grants access to.

### Two roles, one of them implicit

- **owner** — the creator. Full control: invite, remove, delete the project,
  and their own connector credentials back the data pulls.
- **collaborator** — invited. Reads and edits project config, runs agents,
  works on content. Cannot manage members or delete the project.

Roles are a string column with a check constraint, not a join table. Adding
`viewer` or `admin` later widens the constraint; it does not reshape the schema.

Connector credentials stay owner-scoped (`connector_credentials.user_id`). A
collaborator uses the project, not the owner's Google tokens — those are the
owner's personal OAuth grants and sharing them is a different decision with a
different consent story.

### Invitations are addressed to an email, not a user

The recipient usually has no account yet. An invitation therefore names an
email address and is redeemed by whoever signs in with it:

1. Owner submits an address → a row in `project_invitations` with a random
   token; only its SHA-256 hash is stored.
2. The plaintext token exists solely inside the emailed link
   (`{frontend_origin}/invite/{token}`).
3. The landing page previews the invite unauthenticated (project name, inviter)
   so the recipient knows what they are signing in for.
4. After Google sign-in the app posts the token back and the membership row is
   created.

The signed-in address must equal the invited address. A forwarded link opened by
someone else gets a 403 naming the intended recipient, not access.

Re-inviting a pending address refreshes the existing row rather than stacking
duplicates. A resend mints a new token and invalidates the old one — a resend is
a replacement, not a second key.

## Schema

`project_members`
: `(project_id, user_id, role, invited_by_user_id, …)`, unique on
  `(project_id, user_id)`, plus a partial unique index enforcing one `owner`
  row per project. `projects.user_id` stays the owner column; the migration
  backfills an owner row for every existing project so route code can query
  membership uniformly.

`project_invitations`
: `(project_id, email, role, token_hash, status, expires_at, …)`. `token_hash`
  is unique so redemption is one indexed lookup. A partial unique index on
  `(project_id, email) WHERE status = 'pending'` keeps at most one live invite
  per address while leaving revoked/accepted rows as history.

Migration: `f1c7b4d92a08_project_members_and_invitations`.

## Access checks

All project routes resolve access through `service/membership.py` rather than
comparing `Project.user_id` inline:

- `get_project_for_user(project_id, user, session, require_owner=False)` —
  **404** when the caller is not a member at all (a stranger must not be able to
  distinguish a real project id from a fabricated one), **403** only once
  membership is established and the action is owner-only.
- `accessible_projects(user, session)` — owned plus invited, for the list route.

`GET /api/user/projects` now returns `role` and `owner_email` per project so the
app can label shared projects and hide owner-only controls.

## Endpoints

| Method | Path | Who |
| --- | --- | --- |
| `GET` | `/api/user/projects/{id}/members` | any member |
| `POST` | `/api/user/projects/{id}/invitations` | owner |
| `POST` | `/api/user/projects/{id}/invitations/{inv}/resend` | owner |
| `DELETE` | `/api/user/projects/{id}/invitations/{inv}` | owner |
| `DELETE` | `/api/user/projects/{id}/members/{user_id\|me}` | owner, or self (leave) |
| `GET` | `/api/invitations/{token}` | unauthenticated preview |
| `POST` | `/api/invitations/{token}/accept` | signed-in invitee |

The owner cannot be removed — deleting the project is the owner's exit. A
collaborator leaves via `DELETE …/members/me`.

## Email

`service/email/` is one seam (`send_email`) over two backends:

- **resend** when `RESEND_API_KEY` is set.
- **console** otherwise — the message is logged and reported as delivered, so
  local dev and CI need no vendor account. The members screen surfaces a banner
  when this backend is active so nobody assumes mail is going out.

Templates in `service/email/templates.py` are table-based HTML with inline
styles plus a plain-text alternative. Two today: the invitation, and a note to
the owner when someone joins.

Config: `RESEND_API_KEY`, `EMAIL_FROM` (must be on a Resend-verified domain),
`EMAIL_FROM_NAME`, `INVITATION_TTL_DAYS` (default 7).

## Sign-in round trip

The invite page stores its own path in `sessionStorage` under
`duct_post_signin_redirect` before sending the recipient to Google, and the
sign-in page consumes it afterwards. Same-origin paths only. This keeps the
invite token out of OAuth parameters entirely.

## Not built yet

- Roles beyond owner/collaborator (`viewer`, per-agent permissions).
- Transferring ownership.
- Sharing connector credentials with collaborators.
- Bulk invite, or invite-by-domain.
- An audit log of membership changes.
- Rate limiting on invite sends (currently bounded only by owner-only access and
  the one-pending-invite-per-address index).
