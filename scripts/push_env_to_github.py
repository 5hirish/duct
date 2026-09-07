#!/usr/bin/env python3
"""Push allowlisted keys from gitignored .env.test files to GitHub repo secrets/variables.

Reads: backend/.env.test, app/.env.test, desktop/.env.test (later file wins on
duplicate keys). All three are gitignored by `**/.env.*`.

Does NOT bulk-upload backend secrets (DUCT_API_KEY, Google, LLM, etc.). Pushes optional
`NEXT_PUBLIC_*` variables and `CLOUDFLARE_*` secrets for tooling or legacy workflows — the
primary app deploy uses Cloudflare Workers Builds **build variables** in the dashboard, not GitHub.

It also pushes the desktop signing keys, which exist for a reason worth stating:
`desktop-release.yml` can only read GitHub secrets, so there is no way to hand a
runner a signing key except through `gh secret set`. Doing that by hand means
pasting seven secrets into a terminal, which is both tedious and the kind of
thing that ends up in shell history. This keeps them in one gitignored file.

Secret values go to `gh` on **stdin**, never as an argument, so they do not
appear in the process list — and `--dry-run` prints `(hidden)` in place of
every one. Repo *variables* are a different matter: `--dry-run` prints those
values in full, which is fine only because the allowlist admits `NEXT_PUBLIC_*`
alone and those already ship to the browser.

Requires: gh auth login, repo checkout as cwd.

See: the deployment runbook (duct-cloud, private)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from envfile import merge_dotenv_files  # noqa: E402

# Secrets vs repo variables (optional mirror; Workers Builds uses Cloudflare build vars).
#
# The desktop signing keys are here because `desktop-release.yml` can only read
# GitHub secrets — a runner never sees a local dotenv — and because these are
# the values nobody should paste into a terminal or a chat window twice. Put
# them in the gitignored `desktop/.env.test` once and let this push them.
GITHUB_SECRETS = frozenset(
    {
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "NEXT_PUBLIC_DUCT_API_KEY",  # browser-exposed but treat as sensitive in GH
        # Updater signing (minisign). Without these the Linux and Windows jobs
        # build their bundles and then die on the last line — `--bundles …,
        # updater` signs the update artifact, and an empty key reads as a
        # corrupt one: "failed to decode secret key: Missing comment in secret
        # key". These two alone make a release possible on those platforms.
        "TAURI_SIGNING_PRIVATE_KEY",
        "TAURI_SIGNING_PRIVATE_KEY_PASSWORD",
        # Developer ID signing (macOS DMG only). DUCT_DEVID_CERT_P12 is base64
        # of the .p12 — the workflow pipes it through `base64 --decode`, so
        # paste it encoded, not raw.
        #
        # NOT the App Store certificates (DUCT_MAS_*): Apple's notary service
        # rejects anything not signed with Developer ID, so those cannot stand
        # in here however similar they look.
        #
        # Notarization credentials are deliberately absent. It authenticates
        # with the App Store Connect API key (DUCT_ASC_API_KEY_ID /
        # _ISSUER_ID / _P8), which has been a repo secret since the TestFlight
        # channel and needs no staging. The alternative was an app-specific
        # password on a personal Apple ID — a second long-lived credential
        # granting the same thing, to avoid reusing one that already existed.
        "DUCT_DEVID_CERT_P12",
        "DUCT_DEVID_CERT_PASSWORD",
        "DUCT_DEVID_IDENTITY",
    }
)


def _is_github_variable(key: str) -> bool:
    if key in GITHUB_SECRETS:
        return False
    return key.startswith("NEXT_PUBLIC_")


def _gh_secret_set(key: str, value: str, *, dry_run: bool, cwd: Path) -> None:
    if dry_run:
        print(f"[dry-run] gh secret set {key} (hidden)")
        return
    subprocess.run(
        ["gh", "secret", "set", key],
        input=value.encode("utf-8"),
        cwd=cwd,
        check=True,
    )
    print(f"set secret {key}")


def _gh_variable_set(key: str, value: str, *, dry_run: bool, cwd: Path) -> None:
    if dry_run:
        print(f"[dry-run] gh variable set {key}={value!r}")
        return
    subprocess.run(
        ["gh", "variable", "set", key, "--body", value],
        cwd=cwd,
        check=True,
    )
    print(f"set variable {key}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync allowlisted env to GitHub Actions")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without calling gh",
    )
    args = parser.parse_args()

    paths = [
        ROOT / "backend" / ".env.test",
        ROOT / "app" / ".env.test",
        ROOT / "desktop" / ".env.test",
    ]
    merged = merge_dotenv_files(paths)
    if not merged:
        print("error: no values found (create backend/.env.test and/or app/.env.test)", file=sys.stderr)
        return 1

    touched_secret = False
    touched_var = False
    for key in sorted(merged.keys()):
        value = merged[key]
        if not value.strip():
            print(f"skip empty: {key}", file=sys.stderr)
            continue
        if key in GITHUB_SECRETS:
            _gh_secret_set(key, value, dry_run=args.dry_run, cwd=ROOT)
            touched_secret = True
        elif _is_github_variable(key):
            _gh_variable_set(key, value, dry_run=args.dry_run, cwd=ROOT)
            touched_var = True

    if not touched_secret and not touched_var:
        print(
            "error: no allowlisted keys found in .env.test files "
            f"(secrets={sorted(GITHUB_SECRETS)}, variables=NEXT_PUBLIC_*)",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
