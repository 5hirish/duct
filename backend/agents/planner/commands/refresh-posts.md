---
description: Sync all posts + latest metrics from PostBridge, then summarize what changed
allowed-tools: mcp__duct_planner__sync_all_posts, mcp__duct_planner__fetch_post_metrics
---

Refresh the project's content performance data before (re)planning:

1. Call `sync_all_posts` to pull the latest metrics for every published post
   from PostBridge (views, likes, saves, comments, shares + daily snapshots).
2. Call `fetch_post_metrics` to read the refreshed summary.
3. Tell me, briefly: what changed since last time, which pillars / content
   types / hooks are over- and under-performing, and whether that should shift
   the current 7-day plan.

This is the Content Planner's "refresh posts" command. The runner also accepts
the literal `/refresh-posts` typed in chat and routes it here, so it works
regardless of SDK filesystem command discovery.
