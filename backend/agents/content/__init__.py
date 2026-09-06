"""Content Studio agent package.

Architecture: an orchestrator on ``deepagents`` (``agents/content/v1/runner.py``)
plus two sub-agents dispatched through the harness's ``task`` tool
(``agents/content/subagents/``: research_pillar, draft_post). The tools
(``tools.py``), prompts, schema, artifact parsing and enrichment are plain
Python; only the runner and the tool binder import the harness.
"""
