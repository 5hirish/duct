"""Duct backend test suite.

Declared as a package so shared test-support code — notably the agent
evaluation harness in ``tests.eval`` and the fixtures in ``tests.conftest`` —
is importable from individual test modules as ``from tests.eval import ...``.

Because this is a package, pytest's default (prepend) import mode walks up past
it and puts the backend root on ``sys.path`` itself, so ``import config`` and
friends resolve with no per-module ``sys.path`` juggling. Do not add any back.
"""
