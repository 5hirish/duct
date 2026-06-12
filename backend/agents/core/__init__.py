"""Shared, engine-agnostic agent layer.

Everything standard across agent types and engine versions lives here — events,
business context, shared output components, prompt scaffolding, and the
Claude-SDK runtime plumbing (session registry, AskUserQuestion bridge,
<duct_report> parser, startup helpers). Only framework-specific glue belongs in
an agent's ``vN/`` engine directory.
"""
