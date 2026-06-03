"""Apify integration — TikTok content discovery for the content agent.

Lets the agent (and the user via the Discover page) find real
high-performing TikTok posts in the target audience's niche. Discovered
posts get persisted as `ContentAsset(asset_type='discovered_reference',
source='apify')` so the orchestrator's research_pillar sub-agent can
cite real-world signal instead of inventing topics from web search alone.

Public surface:
  - ApifyClient            async client; start_run / poll / fetch_dataset
  - ApifyAPIError          raised on non-2xx
  - ScrapedPost / DiscoveredReferenceRecord (schema)
  - get_default_actor_ids  helper for the two MVP actors
"""

from service.apify.client import ApifyAPIError, ApifyClient, get_default_actor_ids
from service.apify.schema import (
    ApifyRun,
    ApifyRunStatus,
    DiscoveredReferenceRecord,
    ScrapedPost,
    ScrapedPostAuthor,
    ScrapedPostMusic,
)

__all__ = [
    "ApifyAPIError",
    "ApifyClient",
    "ApifyRun",
    "ApifyRunStatus",
    "DiscoveredReferenceRecord",
    "ScrapedPost",
    "ScrapedPostAuthor",
    "ScrapedPostMusic",
    "get_default_actor_ids",
]
