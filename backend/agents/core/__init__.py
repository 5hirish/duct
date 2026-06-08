"""Shared, engine-agnostic agent layer.

Everything standard across agent types and engine versions lives here — events,
business context, output artifacts, request/runner contracts, prompt scaffolding,
and the Claude-SDK runtime plumbing. Only framework-specific glue belongs in an
agent's ``vN/`` engine directory.
"""
