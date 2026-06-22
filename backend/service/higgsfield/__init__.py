"""Higgsfield video generation integration.

Video posts are generated through Higgsfield's hosted MCP server
(`https://mcp.higgsfield.ai/mcp`), wired into the content agent as a remote HTTP
MCP server for `post_type == "video"` runs. Auth is a bearer token resolved by
``auth.higgsfield_token_for_user`` (per-user OAuth token from the connect flow,
or the server-wide ``HIGGSFIELD_API_TOKEN`` fallback). Generated clips are
downloaded and persisted as ``content_assets`` rows by ``storage``.
"""
