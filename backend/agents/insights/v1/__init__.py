"""V1 insights harness.

``agent.py`` (the two-call structured-output pipeline) and its goal-ranked tool
registry were deleted once ``runner.py`` served every route: they had been
frozen and routeless since the autonomous agent shipped, and a parallel system
nobody runs is a maintenance magnet — the goal-relevance scoring in particular
looked live enough to keep tuning.

``AutonomousInsightsRunner`` is imported from ``runner`` directly by its call
sites, so nothing is re-exported here.
"""
