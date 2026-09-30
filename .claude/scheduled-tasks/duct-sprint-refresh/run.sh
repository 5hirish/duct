#!/bin/zsh
# Weekly sprint refresh for GitHub Project 10, started by launchd
# (~/Library/LaunchAgents/ai.getduct.sprint-refresh.plist). Safe to run by
# hand too, as often as you like: every step is idempotent. Interactively,
# `/prioritize sprint` runs the same procedure and asks instead of listing.
#
# Local on purpose: cloud sessions reach GitHub through a proxy that refuses
# every Projects v2 GraphQL call, so the board can only be edited from here.
# The rule lives in .agents/skills/prioritize/SKILL.md ("The sprint").
set -euo pipefail

# launchd starts jobs with a bare PATH; claude, gh and git live outside it.
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd "${0:A:h}/../../.."   # repo root, whatever the checkout path

print -- "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) sprint refresh on $(git branch --show-current) ==="

# The terminal claude only self-updates when used interactively, and this
# machine runs Claude from VS Code and Desktop. On 2026-09-29 the first run
# failed because a stale 2.1.263 couldn't use Opus 5.5; update first, and run
# anyway if the update itself fails.
claude update >/dev/null 2>&1 || print -- "claude update failed; continuing"
print -- "claude $(claude --version)"
# Headless: nobody can answer a question, so decisions go in the readout.
prompt="Read .claude/scheduled-tasks/duct-sprint-refresh/SKILL.md and follow it. You are running headless from run.sh."

# No MCP servers: the job works through gh alone, and launchd's environment
# lacks the tokens they read, so they'd only fail to connect and cost RAM.
exec claude -p "$prompt" \
  --model claude-opus-5-5 \
  --permission-mode auto \
  --strict-mcp-config
