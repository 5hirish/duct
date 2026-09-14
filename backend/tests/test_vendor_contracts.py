"""Every lazily imported vendor name and every GAQL field resolves against what is installed.

Two bug shapes that no faked-client test can catch:

* ``from vendor.types import X`` *inside a function body*. The GA4 fetcher
  imported ``StringFilter`` that way for its whole life; the library nests it
  as ``Filter.StringFilter``, and every filtered landing-page pull raised
  ``ImportError`` at the API call the tests had faked one layer up.
* A Google Ads query naming a field the API version no longer has. The
  protos for the library's default version are the contract; a removed or
  renamed field fails at the API and nowhere else.

Both are resolved here statically, against the installed packages, so a
dependency bump or a vendor rename fails in CI rather than in a session.
"""

from __future__ import annotations

import ast
import importlib
import re
import warnings
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
# Directories that never reach a running server, or that this test must not recurse into.
SKIP_DIRS = {"tests", ".venv", "dist", "build", "__pycache__", "alembic", "scripts", "data"}
LOCAL_PACKAGES = ("agents", "routes", "service", "models", "db", "utils", "config", "server", "local_server")
# Attributes that exist only in a frozen (PyInstaller) process.
FROZEN_ONLY = {"_MEIPASS"}


def _source_files() -> list[Path]:
    return [
        p for p in BACKEND.rglob("*.py")
        if not any(part in SKIP_DIRS for part in p.relative_to(BACKEND).parts)
    ]


def _is_local(module: str) -> bool:
    return module.split(".")[0] in LOCAL_PACKAGES


def _import(module: str):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return importlib.import_module(module)


def _static(obj) -> bool:
    """Only modules, classes and enums have attributes worth resolving statically."""
    return isinstance(obj, type) or hasattr(obj, "__path__") or hasattr(obj, "__members__")


def _lazy_nodes(tree: ast.AST):
    """Import statements nested in a def or class body — the ones no test's own
    ``import`` line has already executed. Module-level imports break the suite at
    collection; these break a session."""
    for scope in ast.walk(tree):
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for node in ast.walk(scope):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    yield node


def _resolve_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    bound: dict[str, object] = {}
    problems: list[str] = []
    rel = path.relative_to(BACKEND)

    for node in _lazy_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0 and not _is_local(node.module):
            try:
                mod = _import(node.module)
            except Exception as exc:  # noqa: BLE001 — the message is the finding
                problems.append(f"{rel}:{node.lineno}: import {node.module}: {type(exc).__name__}: {exc}")
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                obj = getattr(mod, alias.name, None)
                if obj is None:
                    try:
                        obj = _import(f"{node.module}.{alias.name}")
                    except Exception:  # noqa: BLE001
                        obj = None
                if obj is None:
                    problems.append(f"{rel}:{node.lineno}: cannot import name {alias.name!r} from {node.module!r}")
                else:
                    bound[alias.asname or alias.name] = obj
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_local(alias.name):
                    continue
                try:
                    if alias.asname:
                        bound[alias.asname] = _import(alias.name)
                    else:
                        bound[alias.name.split(".")[0]] = _import(alias.name.split(".")[0])
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"{rel}:{node.lineno}: import {alias.name}: {type(exc).__name__}: {exc}")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        chain: list[str] = []
        cur: ast.expr = node
        while isinstance(cur, ast.Attribute):
            chain.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name) or cur.id not in bound:
            continue
        chain.reverse()
        obj = bound[cur.id]
        for i, attr in enumerate(chain):
            if attr in FROZEN_ONLY:
                break
            nxt = getattr(obj, attr, None)
            if nxt is None and hasattr(obj, "__path__"):
                try:
                    nxt = _import(f"{obj.__name__}.{attr}")
                except Exception:  # noqa: BLE001
                    nxt = None
            if nxt is None:
                problems.append(f"{rel}:{node.lineno}: {cur.id}.{'.'.join(chain[:i + 1])} does not resolve")
                break
            obj = nxt
            if not _static(obj):
                break
    return problems


def test_every_vendor_import_and_attribute_chain_resolves():
    problems = sorted({p for path in _source_files() for p in _resolve_file(path)})
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# GAQL
# ---------------------------------------------------------------------------

_GAQL = re.compile(r"SELECT\s+(.+?)\s+FROM\s+([a-z_]+)", re.S | re.I)
_FIELD = re.compile(r"[a-z_]+(\.[a-z_]+)+")


def _default_ads_version() -> str:
    import google.ads.googleads.client as client_module

    version = getattr(client_module, "_DEFAULT_VERSION", None)
    if version:
        return version
    for line in Path(client_module.__file__).read_text().splitlines():
        if "_DEFAULT_VERSION" in line:
            return line.split('"')[1]
    raise AssertionError("google-ads client no longer declares _DEFAULT_VERSION")


def _field_exists(message_cls, parts: list[str]) -> bool:
    cur = message_cls
    for i, part in enumerate(parts):
        fields = getattr(getattr(cur, "meta", None), "fields", {})
        if part not in fields:
            return False
        field = fields[part]
        cur = field.message if field.message is not None else field.enum
        if cur is None and i != len(parts) - 1:
            return False
    return True


def _gaql_queries() -> list[tuple[str, str, list[str]]]:
    found = []
    for path in _source_files():
        text = path.read_text()
        for match in _GAQL.finditer(text):
            fields = [f.strip() for f in re.sub(r"[{}\"'\\+\n]", " ", match.group(1)).split(",") if f.strip()]
            where = f"{path.relative_to(BACKEND)}:{text[:match.start()].count(chr(10)) + 1}"
            found.append((where, match.group(2), [f for f in fields if _FIELD.fullmatch(f)]))
    return found


def _proto_class(version: str, head: str):
    """The message class for a GAQL prefix, importing only that resource's module —
    the ``resources.types`` package imports every resource and takes tens of seconds."""
    if head == "metrics":
        return _import(f"google.ads.googleads.{version}.common.types.metrics").Metrics
    if head == "segments":
        return _import(f"google.ads.googleads.{version}.common.types.segments").Segments
    try:
        module = _import(f"google.ads.googleads.{version}.resources.types.{head}")
    except ModuleNotFoundError:
        return None
    return getattr(module, "".join(p.capitalize() for p in head.split("_")), None)


def test_every_gaql_field_exists_in_the_default_api_version():
    version = _default_ads_version()
    queries = _gaql_queries()
    assert queries, "no GAQL found — the regex or the tree moved"
    unknown = []
    for where, resource, fields in queries:
        for field in fields:
            head, *rest = field.split(".")
            cls = _proto_class(version, head)
            ok = cls is not None and _field_exists(cls, rest)
            if not ok:
                unknown.append(f"{where}: FROM {resource}: unknown field {field}")
    assert not unknown, "\n".join(unknown)
