"""MCP servers a user connects, so Duct's agent can reach tools it has no connector for.

Claude's connector directory and ChatGPT's plugins cannot be consumed by a
third-party app; what both ecosystems are made of is public Streamable HTTP MCP
servers with OAuth (Notion, Linear, OpenSEO, PostHog). Duct is a client of the
same servers. Anthropic's ``mcp_servers`` parameter and OpenAI's Responses
``mcp`` tool were the other way in, and both work only with their own models,
which is the rule ``backend/AGENTS.md`` already states for capabilities: a Duct
tool, not a provider feature (issue #345).

* ``http``    — every request goes to a public https address, redirects included.
* ``presets`` — the curated servers the Connections page offers by name.
* ``oauth``   — discovery, client registration (a client metadata document
                where the server takes one, dynamic registration otherwise),
                the code exchange and refresh.
* ``store``   — the ``connector_credentials`` rows, ``connector_type = "mcp"``.
* ``client``  — open a session, list tools, call one.

What is deliberately not here: stdio servers (a process on our machine, which
the hosted API never runs), and mounting a server's tools on the agent one by
one. The agent reaches all of them through two fixed tools in
``agents/core/mcp_tools.py``.
"""
