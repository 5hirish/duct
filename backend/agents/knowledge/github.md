# GitHub

- **Merged is not deployed.** A pull request's `merged_at` is when the code
  reached a branch, not when users got it. Deploys trail merges by minutes on
  continuous delivery and by days behind a release train. A release's
  published time is closer to "users got it" when the project cuts releases.
  Say "merged on", never "went live on", unless the repository shows the deploy.
- **Anchor on `merged_at` and release times, not commit times.** A commit's
  author date is set by the author's machine and survives a rebase; the
  committer date is rewritten by every rebase and cherry-pick. Work written a
  week ago can land today. When lining a metric change up against a change,
  cite the merge or the release.
- **The window filters commits by commit date, not by when they landed.** A
  rebased commit carries the rebase time; a branch merged with a merge commit
  keeps its commits' original dates, so the work can sit outside the window
  while its merge sits inside it. Merged pull requests are the unit of "what
  shipped when"; commits are the detail under them.
- **Squash and merge commits change what a commit row means.** A squash merge
  is one commit per pull request, titled with the PR and `(#123)`. A merge
  commit reads "Merge pull request #123 from …" and the branch's commits come
  with it. Never count commits and pull requests as separate changes: the same
  work shows up in both.
- **Bots write a lot of the history.** Dependabot, Renovate and CI release
  bots (`dependabot[bot]`, `github-actions[bot]`) open, merge and tag. A
  dependency bump rarely explains a conversion drop; separate bot work from
  people's before calling a week busy or quiet.
- **Line counts are a floor.** File stats come from one call per commit, so
  only the newest commits carry them (every commit in a window of two days or
  less). The pull's `summary` says how many; `truncated` marks the totals.
- **Documentation rows are the window's net change**, one compare from the
  last commit before the window to the newest inside it, each file's patch
  cut to its first two thousand characters. A doc edited and reverted inside
  the window shows no change.
- **A closed issue is not a fixed issue.** `state` is `completed`,
  `not_planned` or `duplicate`; only `completed` means the work was done.
- Access is either the Duct GitHub App or a token the user pasted. A pasted
  token's reads come out of its owner's 5,000 requests an hour, shared with
  their other tools; the App reads on a budget of its own. A 404 means the
  repository is not granted to Duct (or was deleted), a 301 that it was
  renamed or moved.
