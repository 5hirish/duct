<!--
Keep this short. The commit messages carry the detail; this is the summary a
reviewer reads first. Delete any section that does not apply.
-->

## What and why

<!-- What changes, and the reason it is worth changing. The "why" matters more
     than the "what" — a diff already shows the what. -->

Closes #

## Area

<!-- Tick every stack this touches. -->

- [ ] `backend/` — FastAPI / Python
- [ ] `app/` — Next.js
- [ ] `desktop/` — Tauri shell / sidecar
- [ ] `site/` — static marketing site
- [ ] CI / tooling / docs

## Verification

<!-- What you ran, and what it said. "CI will tell us" is not verification. -->

```
# e.g. make check-backend
```

- [ ] I ran the checks for the areas I touched (see [CONTRIBUTING.md](../CONTRIBUTING.md))
- [ ] I added or updated tests covering the behaviour that changed
- [ ] I read the `AGENTS.md` for each directory I edited
- [ ] I read my own diff back looking for the reason to reject it, and read it
      against the code around it ([STYLE.md](../STYLE.md))

## Things that need a second look

<!-- Delete the ones that do not apply. These are the changes that have bitten
     us before, so calling them out explicitly speeds up review rather than
     slowing it down. -->

- [ ] Touches an endpoint that reads or writes project-scoped data — it has
      `get_current_user` **plus** a membership check, and returns 404 (not 403)
      for a non-member
- [ ] Adds a setting to `config.py` — `.env.example` updated to match
- [ ] Adds a database migration — `downgrade` written and tested
- [ ] Adds a dependency — noted below why an existing one would not do
- [ ] Changes a convention documented in a `CLAUDE.md` — that file updated too

## AI assistance

<!-- Agent-written contributions are welcome. This is not a disclosure tax and
     nothing is rejected for ticking it; it just tells the reviewer where to
     look hardest, because agents and humans make different mistakes. -->

- [ ] An AI coding agent wrote or substantially shaped this change
- [ ] I have read every line of this diff and can explain why each part is there
