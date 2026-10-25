"""The MCP servers the Connections page offers by name.

A short, curated list rather than the official MCP Registry: searching the
registry for "hubspot" returns eight servers and none of them is HubSpot's.
Each entry here is the vendor's own hosted server, at the address the vendor
publishes. Anything else connects by URL.

``key_url`` is where the vendor issues a key for clients that cannot sign in,
or empty when one-click sign-in is the only way. ``publisher`` is who runs the
server, shown on its card beside "MCP" the way a native connector shows Duct:
the vendor, for every entry here, since each is the vendor's own. Copy about
each server lives in the app, which translates it; this module holds facts
only.

``trust_read_only`` is a separate decision from being offered by name: it is
whether a tool the vendor marks ``readOnlyHint`` may run without the approval
card. Off by default, and off for infrastructure accounts, whose "read-only"
tools hand back environment variables and API tokens. Those land in the
model's context, and from there an unasked read on another server can carry
them out, so every call to such a server shows the card.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class McpPreset:
    id: str
    label: str
    url: str
    home: str  # the vendor's site: the favicon the card shows, and the link
    publisher: str
    key_url: str = ""
    trust_read_only: bool = False

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
        publisher="OpenSEO",
        key_url="https://app.openseo.so/settings",
        trust_read_only=True,
    ),
    McpPreset(
        id="notion",
        label="Notion",
        url="https://mcp.notion.com/mcp",
        home="https://www.notion.so",
        publisher="Notion",
        trust_read_only=True,
    ),
    McpPreset(
        id="linear",
        label="Linear",
        url="https://mcp.linear.app/mcp",
        home="https://linear.app",
        publisher="Linear",
        trust_read_only=True,
    ),
    McpPreset(
        id="posthog",
        label="PostHog",
        url="https://mcp.posthog.com/mcp",
        home="https://posthog.com",
        publisher="PostHog",
        key_url="https://app.posthog.com/settings/user-api-keys",
        trust_read_only=True,
    ),
    # Deploys, services, logs and variables. Its reads include the variables,
    # secrets among them, so every call shows the approval card.
    McpPreset(
        id="railway",
        label="Railway",
        url="https://mcp.railway.com",
        home="https://railway.com",
        publisher="Railway",
    ),
    # Cloudflare's one server for its whole API, the replacement it names for
    # the per-product servers (bindings, builds, observability). Account-wide,
    # tokens included, so every call shows the approval card.
    McpPreset(
        id="cloudflare",
        label="Cloudflare",
        url="https://mcp.cloudflare.com/mcp",
        home="https://www.cloudflare.com",
        publisher="Cloudflare",
    ),
)

_BY_ID = {p.id: p for p in PRESETS}
_BY_URL = {p.url: p for p in PRESETS}


def preset(preset_id: str) -> McpPreset | None:
    return _BY_ID.get((preset_id or "").strip().lower())


def preset_for_url(url: str) -> McpPreset | None:
    return _BY_URL.get(url)
