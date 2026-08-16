# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Duct desktop sidecar.

Packages the FastAPI backend (`local_server.py`) as a binary the Tauri shell
spawns — see docs/engineering/agent-engine-consolidation-review.md §7.6, §8.2.

Build:
    cd backend && poetry run pyinstaller duct_sidecar.spec --noconfirm

**onedir, never onefile.** A onefile build unpacks itself to a temp directory at
startup, which does not survive macOS code-signing + notarization and is a known
failure mode under the App Store sandbox. onedir signs and notarizes cleanly.

The output is `dist/duct-sidecar/`, whose entry binary goes into Tauri's
`externalBin`. On macOS the whole directory must be signed with the same
Developer ID as the app bundle.
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Packages whose imports PyInstaller cannot see statically. Each is here for a
# reason — remove one only after a clean packaged run proves it is unnecessary.
_HIDDEN_PACKAGES = [
    # Dynamic provider/adapter loading: init_chat_model resolves provider
    # packages by string name at runtime.
    "langchain",
    "langchain_core",
    "langchain_openai",
    "langchain_google_genai",
    "langchain_anthropic",
    "langgraph",
    "deepagents",
    # Google API clients build service objects from discovery documents.
    "google.ads",
    "google.analytics",
    "googleapiclient",
    "google.genai",
    # HTML extraction pulls encodings/parsers lazily.
    "trafilatura",
    "selectolax",
    "extruct",
    # DB drivers are imported by URL scheme, not by import statement.
    "psycopg",
    "sqlmodel",
    "alembic",
    # ASGI server internals.
    "uvicorn",
]

hiddenimports: list[str] = []
datas: list = []
binaries: list = []

for package in _HIDDEN_PACKAGES:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        # An optional dependency that is not installed must not break the build;
        # the packaged app fails loudly at runtime instead, which is easier to
        # diagnose than a spec that silently skipped a required package.
        pass

# uvicorn resolves its protocol/loop implementations by string at startup.
hiddenimports += collect_submodules("uvicorn")

# Duct's own packages: routes and connectors self-register on import, so the
# static graph misses modules that are only reached through a registry.
for package in ("agents", "routes", "service", "models", "db", "utils"):
    hiddenimports += collect_submodules(package)

# The ASGI app itself. local_server imports it directly (not via uvicorn's
# "server:app" string, which cannot be resolved inside a frozen archive).
hiddenimports += ["server", "config"]

# Alembic migrations are data, not code — needed if a desktop build ever runs
# them instead of create_all.
datas += [("alembic", "alembic"), ("alembic.ini", ".")]


a = Analysis(
    ["local_server.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    runtime_hooks=[],
    # Desktop never runs the test suite or notebooks; excluding them keeps the
    # bundle smaller and avoids dragging in dev-only dependencies.
    excludes=[
        # Dev/test only.
        "pytest", "IPython", "notebook", "matplotlib", "tkinter",
        # The HubSpot ingest connector (service/hubspot/ingest.py) is the only
        # dlt user, and dlt drags in the scientific stack: pyarrow, pandas,
        # numpy and scipy total ~240 MB. Desktop does not run warehouse
        # ingestion, so the connector is unavailable there and fails loudly on
        # import if a future desktop feature needs it.
        "dlt", "pyarrow", "pandas", "numpy", "scipy",
        # boto3/botocore back the R2 storage backend only (service/storage.py
        # imports them lazily). Desktop stores uploads on local disk.
        "boto3", "botocore", "s3transfer",
        # Dev observability, never bundled.
        "phoenix", "arize",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="duct-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-compressed binaries fail macOS notarization.
    console=True,  # stdout carries the JSON handshake the Tauri shell reads.
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="duct-sidecar",
)


# ---------------------------------------------------------------------------
# Bundle size — measured on Linux, 2026-08-16
# ---------------------------------------------------------------------------
# 757 MB before the excludes above, 441 MB after. Remaining top contributors:
#
#   googleapiclient  95 MB  — discovery documents for EVERY Google API; only
#                             analyticsdata / searchconsole / ads are used.
#                             Trimmable with a custom hook if size matters.
#   google           87 MB  — protobuf + google-ads generated stubs.
#   babel            32 MB  — locale data pulled in transitively.
#   zstandard        23 MB
#
# A macOS build differs (universal2 doubles native libs), so re-measure there.
# If the signed bundle needs to be smaller, trimming googleapiclient's discovery
# cache is the single biggest win.
