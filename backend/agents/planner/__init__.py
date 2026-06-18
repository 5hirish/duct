"""Content Planner agent (content_planner).

A research-heavy content strategist that manages the project's canonical
rolling 7-day plan: trend research, competitor/market/gap analysis, best
post times per platform + geography, content-type sequencing, a long-term
narrative arc, and review of already-published posts' metrics.

Distinct from the Content Studio agent (tiktok_studio), which now owns only
post drafting + publishing. The planner is the sole producer of content plans.
It reuses the content domain shapes (PlanDraft / Day / PlanStrategy /
ContentBrandContext) and the shared agent framework (agents/core).
"""
