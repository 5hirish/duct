---
name: feature
description: Start a new branch safely from main. Handles uncommitted changes, stashing, unfinished merges, and branch naming conventions automatically.
argument-hint: "<description of work>"
disable-model-invocation: true
---

# Start New Branch

Safely creates a new branch from main, handling all edge cases automatically. Uses proper branch naming conventions based on the type of work.

## Step 1: Get Work Description

If no argument was provided, ask the user:
- "What are you working on? (e.g., 'add user authentication', 'fix login bug', 'update docs')"

## Step 2: Check Git State

Run these commands to understand current state:

```bash
git status
git branch --show-current
git fetch origin main
git rev-list --count origin/main..HEAD 2>/dev/null || echo "0"
```

Check for:
1. Unfinished merge: Look for "You have unmerged paths" or check if `.git/MERGE_HEAD` exists
2. Unfinished rebase: Check if `.git/rebase-merge` or `.git/rebase-apply` exists
3. Uncommitted changes: Look for "Changes not staged" or "Changes to be committed"
4. Current branch name
5. Commits ahead of origin/main (the count from rev-list)

## Step 3: Handle Edge Cases (All Automatic)

### If unfinished merge detected:
```bash
git merge --abort
```
Tell user: "Aborted unfinished merge to start fresh."

### If unfinished rebase detected:
```bash
git rebase --abort
```
Tell user: "Aborted unfinished rebase to start fresh."

### If uncommitted changes exist:
```bash
git stash push -m "WIP: before {prefix}/{branch-name}"
```
Remember to restore these at the end. Tell user: "Stashed your uncommitted changes."

## Step 4: Determine Branch Type and Generate Name

First, determine the branch type based on keywords in the description:

| Keywords | Branch Prefix |
|----------|---------------|
| fix, bug, issue, error, broken, crash, patch | `bugfix/` |
| hotfix, urgent, critical, emergency | `hotfix/` |
| docs, documentation, readme, comment | `docs/` |
| refactor, cleanup, restructure, reorganize | `refactor/` |
| test, testing, spec, coverage | `test/` |
| chore, config, ci, build, dependency, deps | `chore/` |
| (default - new functionality) | `feat/` |

Then convert the description to a branch name:
- Lowercase everything
- Replace spaces with hyphens
- Remove special characters (keep letters, numbers, hyphens)
- Apply the appropriate prefix

Examples:
- "add user authentication" → `feat/add-user-authentication`
- "fix the login bug" → `bugfix/fix-the-login-bug`
- "hotfix payment crash" → `hotfix/payment-crash`
- "update API docs" → `docs/update-api-docs`
- "refactor database layer" → `refactor/database-layer`
- "add unit tests for auth" → `test/add-unit-tests-for-auth`
- "update CI pipeline" → `chore/update-ci-pipeline`

## Step 5: Create Branch Based on Situation

### Situation A: On main with commits ahead of origin/main

This means user accidentally committed to main. Move those commits to the new branch:

```bash
# Create branch from current HEAD (keeps the commits)
git checkout -b {prefix}/{branch-name}

# Now reset main back to origin/main so it's clean
git checkout main
git reset --hard origin/main

# Switch back to the feature branch
git checkout {prefix}/{branch-name}
```

Tell user: "Moved your commits from main to `{prefix}/{branch-name}`. Main is now clean."

### Situation B: On a different branch (not main)

First, check if the previous branch has unpushed commits:
```bash
git log origin/{previous-branch}..HEAD --oneline 2>/dev/null | wc -l
```

- If branch has unpushed commits: Do NOT offer to delete. Inform user the branch is preserved.
- If branch is fully pushed (or remote doesn't exist): Ask user "You're currently on `{previous-branch}`. Do you want to delete this branch after switching? (y/n)"

```bash
# Switch to main and pull latest
git checkout main
git pull origin main

# Create the new branch
git checkout -b {prefix}/{branch-name}

# If user chose to delete AND branch had no unpushed commits
git branch -D {previous-branch}
```

Tell user:
- If deleted: "Created `{prefix}/{branch-name}` from latest main. Deleted `{previous-branch}`."
- If preserved (unpushed): "Created `{prefix}/{branch-name}` from latest main. Preserved `{previous-branch}` (has unpushed commits)."
- If preserved (user choice): "Created `{prefix}/{branch-name}` from latest main. (You were on `{previous-branch}`)."

### Situation C: On main, clean and up-to-date

```bash
git checkout main
git pull origin main
git checkout -b {prefix}/{branch-name}
```

Tell user: "Created `{prefix}/{branch-name}` from latest main."

## Step 6: Restore Stashed Changes

If changes were stashed in Step 3:
```bash
git stash pop
```
Tell user: "Restored your uncommitted changes."

If stash pop fails due to conflicts:
```bash
git stash show -p
```
Tell user: "Your stashed changes had conflicts. Run `git stash show -p` to see them, then `git stash drop` after manually applying."

## Step 7: Confirm Success

Run and display:
```bash
git status
git log --oneline -3
```

Summary for user:
- Created branch `{prefix}/{branch-name}`
- [If applicable] Moved commits from main
- [If applicable] Restored uncommitted changes
- [If applicable] Aborted unfinished merge/rebase
- Ready to start working!
