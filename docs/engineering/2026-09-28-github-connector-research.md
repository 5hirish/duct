# GitHub connector research

**Author:** Shirish Kadam · **Date:** 2026-09-28

Research for issue #268: a read-only GitHub connector that feeds the Insights
agent ("did the drop start with a deploy?") and, later, the Content Studio
daily reflection (#270). Written against GitHub's docs as of this date and
against `main` at `faf28967`.

**The short version.** GitHub connects through a **GitHub App**: one click,
GitHub's own screen for choosing repositories, read-only Contents, Pull
requests, Issues and Metadata, and no long-lived GitHub secret stored by
Duct. Each pull mints a one-hour installation token narrowed to the one
repository it reads. Where no App is registered (a self-hosted install,
which cannot ship the App's private key) the Connections page offers the
**fine-grained personal access token** instead, pasted as a manual
connector on the Mixpanel template. One repository per credential row,
whichever way in. Pull on demand through `FetchData`, using the requested
window as `since`/`until`; no webhook and no watermark table.

This record first recommended the token alone for v1 and the App later. The
App was built in the same change instead: the token's hand-made setup,
expiry and organisation blocking are costs every user pays, while the App's
cost (four settings, one registration, the verify step) is paid once. A8
records what shipped and the one security property it rests on.

## A1. Product fit

What Duct reads, all read-only, normalised into one `work_events` row shape
(below) so Insights and Content Studio consume the same thing:

- **Commits**: subject, body, author, date, trailers (`Co-authored-by`,
  `Refs`, `Closes`), and for a capped number of them the file list with
  additions and deletions.
- **Merged pull requests**: title, body, merged time, number. The headline
  unit for "what shipped when": this repository merged 138 first-parent
  changes in the last 30 days against 723 commits.
- **Closed issues**, with `state_reason` (completed, not planned, duplicate).
- **Releases**: tag, name, notes, published time.
- **Documentation changes**: the changed text of markdown under `docs/**` and
  of root `README`, `CHANGELOG`, `DECISIONS`, `ROADMAP`, capped per file.

Out of scope: any write; source file bodies (paths and stats only);
Discussions (the issue lists the permission, but nothing above reads it, so
v1 does not ask for it); GitLab and Bitbucket.

## A2. Authentication: the decision

| | (a) GitHub App installation | (b) OAuth App | (c) Fine-grained PAT | (d) App user access token |
|---|---|---|---|---|
| Read-only grant | `contents=read`, `metadata=read`, `pull_requests=read`, `issues=read` | none: `repo` is full read/write on every repo; `public_repo` is read/write | Repository permissions: Contents, Pull requests, Issues, Metadata, each **Read-only** | the App's permissions, intersected with the user's |
| Token life | 1 hour, minted on demand from an RS256 JWT (≤10 min, `iss` = client ID or app ID) signed with the App's private key; no refresh token | long-lived | chosen by the user; "no expiration" allowed for personal repos since Oct 2024, organisations cap at 366 days by default; no refresh | 8 hours, refresh token 6 months, rotated on use |
| Per-repo scope | chosen at install ("only select repositories"); a token can be narrowed further per request | none | "Only select repositories" at creation | repos where the App is installed and the user has access |
| Primary rate limit | 5,000/h per installation, +50/h per repo over 20 and per org member over 20, cap 12,500; 15,000 on Enterprise Cloud; not taken from the user's budget | the user's 5,000/h | the user's 5,000/h, shared with their other tools | the user's 5,000/h |
| Operator registers | a GitHub App: permissions, webhook off, setup or callback URL, private key, client secret | an OAuth App | nothing | the same App as (a), plus callback URLs (up to 10) |
| Hosted API | works | works | works | works |
| Desktop app on the hosted API | works through the existing system-browser round trip and single-use code relay | same | works: a paste form, nothing to redirect | same as (a) |
| Self-hosted sidecar | each self-hoster must register their own App; a private key cannot ship in a public binary | same problem | works unchanged; `residency=device` keeps it on the machine | same problem as (a) |
| New settings | 5 (below) | 2 | **0** | shares (a)'s |

**(b) is out.** The only OAuth App scope that reads a private repository,
`repo`, also writes to every repository the user can reach, which fails the
read-only rule every Duct connector follows.

**(d) is not a separate option.** It is the verification step (a) needs. The
setup URL GitHub redirects to after an install carries an `installation_id`,
and GitHub's docs say not to trust it: "generate a user access token for the
user who installed the GitHub App and then check that the installation is
associated with that user." So a correct (a) turns on "Request user
authorization (OAuth) during installation", exchanges the code, and checks the
installation against `GET /user/installations`.

**Recommendation at research time: (c) now, (a) when it earns its cost.**
Superseded the same day by (a) with (c) as the fallback; see A8. (c) is the smallest
thing that works in all three deployment shapes. It is the Stripe and Mixpanel
pattern Duct already runs: paste a key, verify it by listing what it can
reach, store it Fernet-encrypted, and let an expired or revoked key surface
through the existing `reauth_required` path. Its costs are real but
bounded: the user makes the token by hand; organisations can require approval
(until an owner approves, the token reads public resources only) or block
fine-grained tokens altogether; one token covers one owner, so repos in two
organisations mean two stored rows, which the credential table already
supports; and requests come out of the user's personal 5,000/h. (a) removes
the manual step and the expiry, adds GitHub's own permission screen and
revocation, and has its own rate budget, at the price of registering an App,
five settings, JWT signing (`pyjwt` and `cryptography` are already
dependencies), and an install-and-verify route. It also cannot reach
self-hosters without each of them registering an App, so (c) stays as the
fallback even after (a) ships.

**The path from (c) to (a)** is additive. The credential blob carries either
`token` or `installation_id`. The client's header function mints and caches
an installation token (1 hour) when it sees the latter, and every fetcher
stays as it is. The install flow gets a `github` branch beside the Google ones
in `routes/auth.py`. Install URL:
`https://github.com/apps/<slug>/installations/new?state=<signed state>`.

## A3. OAuth specifics (only for the App path)

- Authorize `https://github.com/login/oauth/authorize` (with `client_id`,
  `redirect_uri`, `state`, and a PKCE `code_challenge`, which GitHub strongly
  recommends), then token `https://github.com/login/oauth/access_token`.
- With "Request user authorization during installation" on, the setup URL is
  not used: GitHub sends the user to the first callback URL with a `code`.
- Webhooks can be switched off at registration ("Active" unchecked), so the
  App needs no webhook URL and no webhook secret.
- Permissions have no OAuth scope strings, so `ConnectorMeta.oauth_scope`
  stays `None` and the permissions are declared through `access`, the way
  manual connectors do today.

## A4. Permissions, limits and the account model

**What the user picks after connecting: a repository.** Listing:

| Auth | Endpoint |
|---|---|
| Fine-grained PAT | `GET /user/repos?sort=pushed&per_page=100` (Metadata read). Expected to return only the repositories the token was granted; confirm on the first live test. |
| App installation | `GET /installation/repositories` with the installation token |
| App user token | `GET /user/installations`, then `GET /user/installations/{id}/repositories` |

**Secondary limits**: at most 100 concurrent requests, 900 points a minute on
REST (a GET costs 1), and 90 seconds of CPU per 60 seconds. GitHub asks for
serial requests. A primary-limit hit is a 403 or 429 with
`x-ratelimit-remaining: 0` (wait until `x-ratelimit-reset`); a secondary hit
is a 403 or 429 whose message says so (honour `retry-after`, else wait at
least a minute, then back off exponentially). A conditional request
(`If-None-Match` with a stored ETag) that returns 304 does not count against
the primary limit.

**Sizing, on this repository**: 723 commits on `main` in 30 days, 56 in the
last day. The commit list costs 8 calls for 30 days. A detail call per commit
for file stats would be 723 serial calls, which is minutes of waiting and far
over the 60,000-character cap `FetchData` puts on one response. So file stats
are fetched for at most a fixed number of commits (30, newest first; all of
them when the window is two days or less), and documentation text comes from
one compare call for the whole window. A 30-day pull is then about 45 calls,
against 5,000 an hour.

**API version**: pin `X-GitHub-Api-Version: 2022-11-28`, the way the Stripe
client pins its version. It is the default and is supported until at least
2028-03-10. The newer `2026-03-10` drops `merge_commit_sha` from pull request
objects; migrating means linking a commit to its PR through
`GET /repos/{owner}/{repo}/commits/{sha}/pulls` instead.

## A5. Operator checklist

- **v1 (PAT)**: nothing to register, no settings. The user creates the token
  at <https://github.com/settings/personal-access-tokens/new> with resource
  owner, "Only select repositories", and the four read-only permissions.
- **App**: register one GitHub App ("Any account", webhook inactive, the four
  permissions read-only). Callback URL
  `{API_PUBLIC_URL}/auth/connectors/github/oauth/callback`; setup URL
  `{API_PUBLIC_URL}/auth/connectors/github/setup` with "Redirect on update"
  on; "Request user authorization during installation" **off** (A8 says
  why); user-token expiry on. Generate a private key and a client secret.
  Four settings, documented in `backend/.env.example`: `GITHUB_APP_SLUG`,
  `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_CLIENT_SECRET`, `GITHUB_APP_PRIVATE_KEY`.
  No app ID: the JWT's `iss` takes the client ID, which GitHub recommends.

## A6. Endpoints

All `https://api.github.com`, headers `Authorization: Bearer <token>`,
`Accept: application/vnd.github+json`, and the pinned version header.

| Data | Endpoint and parameters | Permission | Notes |
|---|---|---|---|
| Commits | `GET /repos/{o}/{r}/commits?since=&until=&per_page=100&page=` | Contents read | ISO 8601 bounds; default branch unless `sha`; no file list in the list response |
| One commit | `GET /repos/{o}/{r}/commits/{sha}` | Contents read | `stats` and `files[]` (`filename`, `status`, `additions`, `deletions`, `changes`, `patch`, `previous_filename`); 300 files a page, up to 3,000 |
| Docs over a window | `GET /repos/{o}/{r}/compare/{base}...{head}` | Contents read | one call: up to 300 files with `patch` and 250 commits; `base` is the last commit before `since` (`commits?until=<since>&per_page=1`) |
| Doc text at a commit | `GET /repos/{o}/{r}/contents/{path}?ref={sha}`, `Accept: application/vnd.github.raw+json` | Contents read | only when a patch is missing; raw up to 100 MB |
| Merged PRs | `GET /repos/{o}/{r}/pulls?state=closed&sort=updated&direction=desc&per_page=100` | Pull requests read | no `since`: stop paging once `updated_at` is before the window; merged means `merged_at` is set |
| Closed issues | `GET /repos/{o}/{r}/issues?state=closed&since=&per_page=100` | Issues read | `since` is last update; drop rows carrying `pull_request`; keep `closed_at` inside the window |
| Releases | `GET /repos/{o}/{r}/releases?per_page=100` | Contents read | newest first, no `since`; a read-only token never sees drafts |
| Trailers | none | | parsed from the commit message's trailer block |

**Pagination without headers.** `service/rest.py` returns the body only, so
the `Link` header GitHub documents is out of reach. Every endpoint above takes
`page`, so the client pages by number and stops on a short page or at the
window's edge. That keeps `service/rest.py` and the `FakeWire` test fake
unchanged. ETags are skipped for the same reason; at about 45 calls a pull
they would save nothing measurable.

**Poll, not webhook.** Pull on demand, when an agent asks. A webhook needs a
public HTTPS receiver, which a self-hosted sidecar on a loopback port does not
have. GitHub does not redeliver a failed delivery by itself (manual
redelivery covers three days), so a reconciling poll is needed anyway. It
would also add a webhook secret, signature checks and an events table, all to
save about 45 calls a day. Revisit if Duct ever alerts in real time on a
deploy.

**There is no "existing daily sync path" to plug into.** The issue assumes
one. Connectors are read on demand through `FetchData`, and nothing on the
server schedules a connector pull. So "since a watermark" becomes "the window
the caller asked for": Insights passes its analysis window, and #270 passes
today as both bounds. No watermark table.

## A7. Risks and open points

- **One repository per project.** `project_connectors` is unique on
  (project, connector type), and `FetchData` reads the bound credential's
  `account_id`. The issue's "Done means" needs one repository. Several would
  mean relaxing that constraint through a migration and teaching
  `bound_credential_row`, `list_data_sources` and SelectAccount to return a
  list. That is its own issue.
- **Observed while reading, not GitHub-specific**: the entity picker writes
  `project_connectors.entity_id`, but no code in the fetch path reads it. A
  grep finds readers only in `routes/project_connectors.py`, and
  `fetch_entity` uses the bound credential's `account_id`. GitHub v1 is not
  affected because its account is the repository. It deserves its own issue
  for GA4 and Search Console.
- **Renamed or transferred repositories answer 301.** `httpx` does not follow
  redirects by default and `Endpoint` does not ask it to, so the call fails.
  Either add a `follow_redirects` flag to `Endpoint` (one field, covered by
  `tests/test_rest_transport.py`) or return a hint to pick the repository
  again.
- **Commit dates are author-supplied**, and rebases rewrite committer dates.
  When lining up a metric change, the knowledge pack should anchor on
  `merged_at` and release `published_at`, not on commit time. A merge is also
  not a deploy.
- **Classic tokens** (`ghp_…`) work but carry `repo`, full write access. Warn
  when one is pasted, the way the Stripe card warns on a full `sk_` key.
- **GraphQL** could return per-commit additions, deletions and linked pull
  requests in one paged query, which would lift the 30-commit cap. It is a
  second API surface with errors inside a 200 response. Verify the `Commit`
  fields before adopting it; REST is enough for v1.

## B. Where it goes in the repo

**Template: Mixpanel** (`backend/service/mixpanel/`): a pasted credential,
`list_accounts` returning what the credential can reach, the picked id saved
under a credential key, catalog-driven `FetchData`. Stripe is the reference
for the classic-key warning and for isolating failures per section.

Backend, new:

- `service/github/__init__.py`, `service/github/client.py`: `Endpoint` plus
  an `ApiError` subclass that reads GitHub's `{"message": …}` and offers hints
  (401: expired or revoked; 403 "Resource not accessible": a missing
  permission; 403 or 429 naming a rate limit; 404: repository not granted to
  the token). Also `require_credentials`, `require_repo`, a page-number
  pager, and the classic-token warning.
- `service/github/fetch.py`: `fetch_github(creds, date_from, date_to)`
  returning `{api, repo, window, summary, data: {rows}, errors}`, where `rows`
  are work events (`kind` of commit, pull_request, issue, release or
  docs_change; `at`, `ref`, `title`, `body`, `author`, `url`,
  `files_changed`, `additions`, `deletions`, `trailers`). Named constants for
  the docs paths, `MAX_COMMIT_DETAILS` and `MAX_PATCH_CHARS`. Then
  `GitHubConnector.list_accounts` (`account_id` is `owner/name`,
  `entity_detail` the description, `entity_meta` the visibility and last
  push) and the registration:
  `ConnectorMeta(id="github", label="GitHub", oauth_scope=None,
  capabilities={CAP_ACCOUNTS}, entity_noun="repository",
  entity_noun_plural="repositories")`.
- `agents/insights/catalog/github.py`: one entity, `github_work_events`, with
  `fetch_fn="fetch_github"`; `additions`, `deletions` and `files_changed`
  declared as summed metrics, so `totals.summarise` adds them up in code
  rather than leaving it to the model.
- `agents/knowledge/github.md`: merged is not deployed; anchor on `merged_at`;
  squash versus merge commits; bots such as Dependabot; `since` filters by
  commit date.

Backend, edited:

- `service/connectors.py`: add `"service.github.fetch"` to `_ADAPTER_MODULES`.
- `routes/user_connectors.py`: add `"github"` to `ALLOWED_CONNECTOR_TYPES`,
  which also opens project binding (`routes/project_connectors.py` imports it).
- `agents/insights/catalog/base.py`: register the catalog in `_CATALOGS`.
- `agents/insights/fetchers.py`: a call adapter that hands the exact
  `date_from` and `date_to` through (`_manual` flattens them to a day count,
  which loses "today"), mapped as `"fetch_github"`, with `repo` as the account
  key.
- `agents/insights/data_tools.py`: a `KNOWLEDGE_INDEX["github"]` line.
- Leave `service/pipeline.py` alone. It serves the legacy report-refresh
  route only, and `tests/test_connector_clients.py` asserts
  `MANUAL_CREDENTIAL_CONNECTORS` equals an exact set, so adding GitHub there
  breaks a test for nothing.
- Not touched in v1: `config.py`, `.env.example`, `models/`, Alembic,
  `routes/auth.py`.

Tests:

- `tests/test_rest_connector_requests.py`: a GitHub section on `FakeWire`,
  following the convention for every read fetcher. Assert the wire (bearer
  header, version header, ISO `since` and `until`, `per_page=100`, the
  closed-and-sorted pulls query, paging stopping on a short page and at the
  window's edge), then the rows: PR-shaped issues dropped, merged versus
  closed-unmerged, trailers parsed, docs-path filter, patch and detail caps.
  Also one section failing (403 on pulls) while the others still return.
- `tests/test_github_connector.py`: registration (manual, `CAP_ACCOUNTS`,
  nouns), `list_accounts` mapping plus 401 to `ValueError` and 5xx to
  `RuntimeError`, the error hints, and the classic-token warning.
- `tests/test_insights_catalog_contract.py`: add
  `"github": ["service/github/fetch.py"]` to `FETCHER_SOURCES`.
- No change needed for `test_env_example.py` (no setting),
  `test_route_auth_boundaries.py` (no route), `test_harness_boundaries.py`
  (`service/github` imports no agent framework), or the live connector smoke
  test, which picks GitHub up through the catalog once the smoke user binds a
  repository.

App:

- `app/src/app/(app)/connections/page.jsx`: one `ManualConnectorCard` with
  `type="github"`, a single secret field `token` (placeholder `github_pat_…`,
  and a hint naming the four read-only permissions and "Only select
  repositories"), `accountField="repo"`, and the settings link above as
  `docsUrl`. The existing `ProjectBinding` and `ProjectEntitySelect` pick the
  repository with no new component, labelled "repository" from the server.
- `app/src/components/connections/logos.jsx`: `CONNECTOR_NAMES.github`,
  `LOGOS.github`. The mark is monochrome, so it needs `currentColor`, inline
  like the OpenAI knot, to show on the dark theme.
- Finish with `make i18n`.

Content Studio (#270) is out of scope here. The content runner mounts no data
tools today, so #270 either calls `service.github.fetch.fetch_github` from a
content tool or mounts the insights data tools.

## C. Handoff

- **Recommendation**: feasible for the MVP. Shipped as the GitHub App with
  the fine-grained token as the self-host fallback (A8), one repository per
  credential row, on-demand pull.
- **Connector id**: `github`.
- **Decided**: App first (the issue's proposal); self-host builds stay
  token-only; one repository per row; a classic token is accepted with a
  warning; the Discussions permission is dropped, since nothing reads it.
- **Still open**: which account owns the registered App, your personal
  account or an organisation (its name shows on GitHub's install screen);
  and a first live check that a fine-grained token scoped to selected
  repositories lists only those (A4).

## A8. What shipped: the App path

Code: `backend/service/github/app.py` (the flow in its docstring),
`routes/auth.py` (browser legs), `routes/user_connectors.py` (status, link,
claim). Tests: `backend/tests/test_github_app.py`.

1. The signed-in app mints a five-minute, single-use **connect link** naming
   its user (`POST /api/user/connectors/github/connect`). The authorize route
   is a bare navigation with no bearer token, so this is how it learns whose
   connect it is: the guest-link pattern from sign-in, in its own namespace.
2. **GitHub's OAuth screen** with state and PKCE. The state carries the user.
3. The **callback** trades the code for a user token and asks GitHub which
   installations of this App that user can reach, and which repositories in
   each (`/user/installations`, then `/user/installations/{id}/repositories`:
   the intersection of where the App is installed and what the user can open,
   so an organisation member never gets repositories an admin installed the
   App on that they cannot see themselves). None yet: on to GitHub's install
   screen, whose return through the setup URL resumes at step 2. A second
   empty answer ends the connect rather than looping.
4. The grant is parked behind a two-minute single-use code bound to the user
   from step 1, and the signed-in page **claims** it
   (`POST /api/user/connectors/github/claim`), writing one credential row per
   repository: `{installation_id, repo}`.

**The property all four steps protect.** Duct's private key mints a token for
any installation id it is handed. So an installation id is never read from a
request: `ConnectorMeta.server_only_keys` makes both routes that take
credentials from a body refuse `installation_id`, the setup route ignores the
one GitHub appends (its docs warn it can be spoofed), and the claim is the only
writer. Binding the claim to the user whose link started the connect closes the
forged-link case too: someone who mints a link for their own account and sends
it to a victim gets a grant only the sender's session could claim, delivered to
the victim's browser, where it is refused and spent.

**Why "Request user authorization during installation" is off.** With it on,
GitHub runs its own OAuth after an install and carries our state through only
unreliably (reported by GitHub's community for `installations/new`), and a
callback without state cannot tell whose install it was. With it off, every
OAuth leg starts from Duct with a state Duct saved, and the install screen
returns through the setup URL. When that return has no state (GitHub dropped
it, or "Redirect on update" after a change made on GitHub directly), the setup
route sends the browser to `/connections?connector=github&installed=1` and the
signed-in page restarts the connect, which GitHub answers without asking.

**Tokens.** Minted per pull with `repositories: [name]` and the four read
permissions, so a token reads one repository even when the installation covers
many and even if the App's registration is later widened; cached in process
until five minutes before expiry. A refused mint fails the pull once, with the
fix: uninstalled (404), repository no longer on the installation (422),
suspended (403), or this server's App settings wrong (401).

**Reconnecting** re-reads the grant: rows for repositories GitHub no longer
grants are removed if they came from the App; a pasted token's row is the
user's own and stays, unless the App now covers that repository, in which case
the App's row replaces it.

## Sources

- Rate limits: <https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api>
- Best practices (serial requests, conditional requests, redirects, webhooks): <https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api>
- Pagination: <https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api>
- API versions: <https://docs.github.com/en/rest/about-the-rest-api/api-versions>; breaking changes in 2026-03-10: <https://docs.github.com/en/rest/about-the-rest-api/breaking-changes>
- Fine-grained token permissions per endpoint: <https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens>
- Managing personal access tokens (select repositories, approval, blocking): <https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens>
- Optional expiry for fine-grained tokens, 366-day organisation default: <https://github.blog/changelog/2024-10-18-new-pat-rotation-policies-preview-and-optional-expiration-for-fine-grained-pats/>
- OAuth App scopes: <https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps>
- Registering a GitHub App: <https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app>; URL parameters (permission keys): <https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-using-url-parameters>
- Setup URL and why `installation_id` is not trusted: <https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/about-the-setup-url>
- Install URL and `state`: <https://docs.github.com/en/apps/sharing-github-apps/sharing-your-github-app>
- App JWT: <https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app>
- Installation token: <https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app>
- User access token: <https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app>
- Installations API: <https://docs.github.com/en/rest/apps/installations>
- Commits, compare, PRs for a commit: <https://docs.github.com/en/rest/commits/commits>
- Pull requests: <https://docs.github.com/en/rest/pulls/pulls>
- Issues: <https://docs.github.com/en/rest/issues/issues>
- Releases: <https://docs.github.com/en/rest/releases/releases>
- Repository contents: <https://docs.github.com/en/rest/repos/contents>
- Repositories for the authenticated user: <https://docs.github.com/en/rest/repos/repos#list-repositories-for-the-authenticated-user>
- Failed webhook deliveries: <https://docs.github.com/en/webhooks/using-webhooks/handling-failed-webhook-deliveries>
- GraphQL commits: <https://docs.github.com/en/graphql/reference/commits>
