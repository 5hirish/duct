"""The MCP servers the Connections page offers by name.

A short, curated list rather than the official MCP Registry: searching the
registry for "hubspot" returns eight servers and none of them is HubSpot's.
Each entry here is the vendor's own hosted server, at the address the vendor
publishes. Anything else connects by URL.

``key_url`` is where the vendor issues a key for clients that cannot sign in,
or empty when one-click sign-in is the only way. Copy about each server lives
in the app, which translates it; this module holds facts only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class McpPreset:
    id: str
    label: str
    url: str
    home: str  # the vendor's site: the favicon the card shows, and the link
    key_url: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


PRESETS: tuple[McpPreset, ...] = (
    # Keyword volume, difficulty and backlinks: the data #216 needed without
    # Duct reselling any of it.
    McpPreset(
        id="openseo",
        label="OpenSEO",
        url="https://app.openseo.so/mcp",
        home="https://openseo.so",
        key_url="https://app.openseo.so/settings",
    ),
    McpPreset(
        id="notion",
        label="Notion",
        url="https://mcp.notion.com/mcp",
        home="https://www.notion.so",
    ),
    McpPreset(
        id="linear",
        label="Linear",
        url="https://mcp.linear.app/mcp",
        home="https://linear.app",
    ),
    McpPreset(
        id="posthog",
        label="PostHog",
        url="https://mcp.posthog.com/mcp",
        home="https://posthog.com",
        key_url="https://app.posthog.com/settings/user-api-keys",
    ),
)

_BY_ID = {p.id: p for p in PRESETS}
_BY_URL = {p.url: p for p in PRESETS}


def preset(preset_id: str) -> McpPreset | None:
    return _BY_ID.get((preset_id or "").strip().lower())


def preset_for_url(url: str) -> McpPreset | None:
    return _BY_URL.get(url)
