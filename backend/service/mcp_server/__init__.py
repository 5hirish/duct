"""Duct as an MCP server, for agents outside Duct (Claude Code, Codex, Cursor).

``protocol`` is the transport and the JSON-RPC dispatch; ``tools`` is what an
agent may do. The HTTP route is ``routes/mcp_server.py`` and the tokens it
accepts are ``service/mcp_tokens.py``. The other direction, Duct's own agent
calling someone else's MCP server, is a separate client (#345).
"""
