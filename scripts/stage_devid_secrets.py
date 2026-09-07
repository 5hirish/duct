#!/usr/bin/env python3
"""Turn a Developer ID certificate + its private key into the three secrets
`desktop-release.yml` wants, staged in `desktop/.env.test`.

Run this after downloading the .cer from the Apple Developer portal:

    python3 scripts/stage_devid_secrets.py \
        --cer ~/.config/duct-signing/devid.cer \
        --key ~/.config/duct-signing/devid.key

then push them with `scripts/push_env_to_github.py`.

Why a script rather than three openssl commands in a README
-----------------------------------------------------------
Because the obvious three commands produce a .p12 that fails, on a Mac, in CI,
inside a step whose error says nothing about encryption. OpenSSL 3 defaults
PKCS#12 to AES-256-CBC + PBKDF2; Apple's security(1) and codesign only read the
older PBE-SHA1-3DES form, so a bundle exported with the defaults imports with

    security: SecKeychainItemImport: MAC verification failed during PKCS12
    import (wrong password?)

which sends you looking for a typo in a password that is correct. `-legacy`
is the usual advice and needs the legacy provider present; naming the
algorithms explicitly does not, so that is what this does.

The other two values are derived rather than typed, because both are easy to
get subtly wrong: the base64 must be unwrapped (the workflow pipes it straight
into `base64 --decode`), and the identity string has to match the certificate's
common name exactly or codesign picks nothing and says only "no identity found".

Nothing is printed. The password is read without echo and written only to
`desktop/.env.test`, which is gitignored and created 0600.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "desktop" / ".env.test"

# Apple's toolchain reads only this PBE form; see the module docstring.
LEGACY_PBE = [
    "-keypbe", "PBE-SHA1-3DES",
    "-certpbe", "PBE-SHA1-3DES",
    "-macalg", "sha1",
]


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, check=True, **kw)


def _identity_from_cert(cer: Path) -> str:
    """The exact string codesign matches on, read out of the certificate."""
    for form in ("DER", "PEM"):
        try:
            out = _run(["openssl", "x509", "-in", str(cer), "-inform", form,
                        "-noout", "-subject", "-nameopt", "RFC2253"]).stdout
        except subprocess.CalledProcessError:
            continue
        m = re.search(r"CN=([^,]+)", out.decode())
        if m:
            return m.group(1).strip()
    raise SystemExit(f"error: could not read a Common Name out of {cer}")


def _to_pem(cer: Path, out: Path) -> None:
    """Apple hands out DER (.cer); openssl pkcs12 wants PEM."""
    for form in ("DER", "PEM"):
        try:
            pem = _run(["openssl", "x509", "-in", str(cer), "-inform", form]).stdout
            out.write_bytes(pem)
            return
        except subprocess.CalledProcessError:
            continue
    raise SystemExit(f"error: {cer} is not a certificate openssl can read")


def _upsert(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    if pattern.search(text):
        return pattern.sub(lambda _: line, text, count=1)
    return (text.rstrip("\n") + "\n" if text.strip() else "") + line + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cer", required=True, type=Path, help="certificate from Apple (.cer)")
    ap.add_argument("--key", required=True, type=Path, help="private key the CSR was made with")
    args = ap.parse_args()

    cer, key = args.cer.expanduser(), args.key.expanduser()
    for p in (cer, key):
        if not p.is_file():
            print(f"error: no such file: {p}", file=sys.stderr)
            return 1

    identity = _identity_from_cert(cer)
    print(f"certificate common name: {identity}")
    if "Developer ID Application" not in identity:
        print(
            "warning: that is not a Developer ID Application certificate. A Mac App\n"
            "         Store certificate cannot sign a DMG — Apple's notary service\n"
            "         rejects anything else. Continuing, but the build will fail.",
            file=sys.stderr,
        )

    password = getpass.getpass("New password to protect the .p12: ")
    if not password:
        print("error: refusing to export an unprotected .p12", file=sys.stderr)
        return 1
    if password != getpass.getpass("Repeat it: "):
        print("error: passwords did not match", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        pem, p12 = tmp / "cert.pem", tmp / "devid.p12"
        _to_pem(cer, pem)
        try:
            _run(["openssl", "pkcs12", "-export", "-legacy",
                  "-inkey", str(key), "-in", str(pem),
                  "-out", str(p12), "-passout", "pass:" + password, *LEGACY_PBE])
        except subprocess.CalledProcessError:
            # No legacy provider on this build; the explicit algorithms above
            # are what actually matter, so retry without the flag.
            _run(["openssl", "pkcs12", "-export",
                  "-inkey", str(key), "-in", str(pem),
                  "-out", str(p12), "-passout", "pass:" + password, *LEGACY_PBE])

        # Read it back before staging it. A .p12 that openssl cannot reopen is
        # one CI cannot import either, and finding that out here costs seconds
        # instead of a signing job.
        verify = ["openssl", "pkcs12", "-in", str(p12), "-noout",
                  "-passin", "pass:" + password]
        try:
            _run(verify)
        except subprocess.CalledProcessError:
            _run([*verify, "-legacy"])

        encoded = base64.b64encode(p12.read_bytes()).decode()

    text = ENV_PATH.read_text() if ENV_PATH.exists() else ""
    for k, v in (
        ("DUCT_DEVID_CERT_P12", encoded),
        ("DUCT_DEVID_CERT_PASSWORD", password),
        ("DUCT_DEVID_IDENTITY", identity),
    ):
        text = _upsert(text, k, v)
    ENV_PATH.write_text(text)
    ENV_PATH.chmod(0o600)

    print(f"staged 3 values in {ENV_PATH.relative_to(ROOT)} (0600, gitignored)")
    print("still needed there: DUCT_NOTARY_APPLE_ID, DUCT_NOTARY_PASSWORD,")
    print("                    TAURI_SIGNING_PRIVATE_KEY, TAURI_SIGNING_PRIVATE_KEY_PASSWORD")
    print("then: python3 scripts/push_env_to_github.py --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
