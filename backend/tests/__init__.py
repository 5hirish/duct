"""Duct backend test suite.

Declared as a package so shared test-support code — notably the agent
evaluation harness in ``tests.eval`` — is importable from individual test
modules as ``from tests.eval import ...``. ``tests/conftest.py`` puts the
backend root on ``sys.path`` so this resolves both under pytest and when the
harness is imported from a standalone script.
"""
