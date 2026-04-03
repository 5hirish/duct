"""LangChain tool definitions for the generate agent.

Follows the nomadtools StructuredTool.from_function() pattern:
a Pydantic args_schema validates the LLM's tool call, then a wrapper
function delegates to the real implementation with pre-resolved credentials.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class GoogleAdsFetchInput(BaseModel):
    """Input schema for the Google Ads campaign fetch tool."""

    customer_id: str = Field(description="Google Ads customer ID (digits only, no dashes)")
    date_from: str = Field(description="Start date in YYYY-MM-DD format")
    date_to: str = Field(description="End date in YYYY-MM-DD format")


def create_google_ads_tool(
    fetch_fn: Callable[..., Dict[str, Any]],
) -> StructuredTool:
    """Create a Google Ads fetch tool with pre-resolved credentials.

    ``fetch_fn`` should be a closure that already has developer_token,
    client_id, client_secret, and refresh_token baked in. The tool only
    exposes customer_id, date_from, and date_to to the LLM.
    """

    def _wrapper(**kwargs: Any) -> Dict[str, Any]:
        validated = GoogleAdsFetchInput(**kwargs)
        return fetch_fn(
            customer_id=validated.customer_id,
            date_from=validated.date_from,
            date_to=validated.date_to,
        )

    return StructuredTool.from_function(
        func=_wrapper,
        name="fetch_google_ads_campaigns",
        description=(
            "Fetch Google Ads campaign performance data for a customer account "
            "and date range. Returns raw campaign rows with spend, clicks, "
            "impressions, conversions, ROAS, and previous-period comparison data."
        ),
        args_schema=GoogleAdsFetchInput,
    )
