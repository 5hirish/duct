#!/usr/bin/env python3
"""Fill the untranslated entries of a PO catalogue with a model, glossary in hand.

This is the whole reason the interface can stay translated while the copy keeps
moving: an English string changes, `lingui extract` (or `build_site_i18n.py`)
marks its translations missing, and this fills exactly those — nothing already
translated is touched, so a re-run is a no-op and the diff is the delta.

    python3 scripts/i18n/fill.py                      # every catalogue, every locale
    python3 scripts/i18n/fill.py app/src/locales/es/messages.po
    python3 scripts/i18n/fill.py --provider manual --export pending.json
    python3 scripts/i18n/fill.py --provider manual --import pending.json

Providers: `anthropic` (ANTHROPIC_API_KEY) and `gemini` (GEMINI_API_KEY),
picked from whichever key is set unless `--provider` says. `manual` writes
the pending entries to a JSON file for an agent or a person to translate and
reads the same file back — the path when no key is in the shell.

Before asking a model, an untranslated string is looked up in every other
catalogue of the same locale: the app and the site say "Download for desktop"
in the same words, and a phrase translated once should never come back
different the second time.

Three rules the prompt enforces and this script verifies:

* ICU placeholders (`{name}`, `{0}`), rich-text tags (`<0>…</0>`) and plural
  markers (`#`) come back exactly as sent. A missing placeholder is rejected,
  the batch is retried once, and a second failure leaves the entry empty and
  says so — `lingui compile --strict` then fails the build, which is the
  point. Never a silent half-translation.
* Glossary `keep` terms are never translated; `terms` render one way.
* Register per language, from the glossary, so "du" and "tú" are a decision
  made once and not per string.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import po  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GLOSSARY = Path(__file__).resolve().parent / "glossary.json"

#: Where catalogues live. Both trees write PO with the locale in the path.
CATALOG_GLOBS = ("app/src/locales/*/messages.po", "site/i18n/*.po")
SKIP_LOCALES = {"en", "pseudo"}

LOCALE_NAMES = {
    "es": "Spanish",
    "pt-BR": "Brazilian Portuguese",
    "de": "German",
    "ja": "Japanese",
}

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "gemini": "gemini-2.5-flash",
}

BATCH = 40
#: A batch is also capped by size: forty two-line paragraphs is a response the
#: proxy in front of the API has been seen to cut off halfway.
BATCH_CHARS = 5000
TAG_RE = re.compile(r"</?\d+/?>")


def _placeholders(text: str) -> list[str]:
    """What must survive translation, order-insensitive.

    Simple ICU arguments (`{name}`, `{0}`) and rich-text tags (`<0>…</0>`) must
    all come back. A plural or select argument is compared by its *name* only
    (`{count, plural}`): its forms are the translator's to change — Japanese
    has no `one`, Russian needs `few` — and the `#` inside them moves with the
    grammar. Nested braces are walked, not regexed, for the same reason.
    """
    out: list[str] = TAG_RE.findall(text)
    depth = 0
    start = -1
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                body = text[start + 1 : i]
                head = body.split(",", 2)
                name = head[0].strip()
                kind = head[1].strip() if len(head) > 1 else ""
                if kind in ("plural", "select", "selectordinal"):
                    out.append(f"{{{name}, {kind}}}")
                elif kind:
                    out.append(f"{{{name}, {kind}}}")
                else:
                    out.append(f"{{{name}}}")
        i += 1
    return sorted(out)


def locale_of(path: Path, catalog: po.Catalog) -> str:
    header = catalog.header
    if header is not None:
        match = re.search(r"Language:\s*([A-Za-z-]+)", header.msgstr)
        if match:
            return match.group(1)
    name = path.stem if path.suffix == ".po" and path.parent.name in ("i18n",) else path.parent.name
    return name


def memory_for(locale: str, catalogs: list[tuple[Path, po.Catalog]]) -> dict[tuple[str | None, str], str]:
    out: dict[tuple[str | None, str], str] = {}
    for _, catalog in catalogs:
        for entry in catalog.entries:
            if entry.msgstr and not entry.obsolete and not entry.is_header:
                out.setdefault(entry.key, entry.msgstr)
    return out


def build_prompt(locale: str, glossary: dict, items: list[dict]) -> tuple[str, str]:
    language = LOCALE_NAMES.get(locale, locale)
    terms = "\n".join(
        f'- "{term}" → "{spec[locale]}"' + (f" ({spec['note']})" if spec.get("note") else "")
        for term, spec in glossary.get("terms", {}).items()
        if spec.get(locale)
    )
    keep = ", ".join(glossary.get("keep", []))
    register = glossary.get("register", {}).get(locale, "")
    system = f"""You translate the interface of Duct, an open-source AI agent for product and marketing teams, from English into {language}.

Rules, in order of importance:
1. Return every placeholder exactly as given: ICU placeholders like {{name}} or {{0}}, rich-text tags like <0>…</0> or <1/>, and the # inside plural forms. Never translate, rename, reorder inside, or drop them. ICU plural syntax such as {{count, plural, one {{# item}} other {{# items}}}} keeps its structure; translate only the words inside the braces of each form, and use the plural categories {language} needs.
2. Never translate these names: {keep}.
3. Use these renderings and no others:
{terms}
4. Register: {register}
5. This is interface copy: labels, buttons, short sentences. Keep it as short as the English, or shorter. A button stays a button. Do not add politeness, punctuation or explanation the English does not have. Keep the English's capitalisation style (sentence case) unless the language forbids it.
6. Each item carries a "context" line naming the file and any note from the developer. Use it to disambiguate — "Post" as a noun versus a verb — and nothing else.

Answer with a JSON array only, one object per item, in the same order: [{{"id": <number>, "text": "<translation>"}}]. No prose, no code fence."""
    user = json.dumps(items, ensure_ascii=False, indent=1)
    return system, user


def call_anthropic(system: str, user: str, model: str) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 8000,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as res:
        payload = json.load(res)
    return "".join(block.get("text", "") for block in payload.get("content", []))


def call_gemini(system: str, user: str, model: str) -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    body = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }
    ).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=body,
        headers={"x-goog-api-key": key, "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as res:
        payload = json.load(res)
    parts = payload["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


PROVIDERS = {"anthropic": call_anthropic, "gemini": call_gemini}


def parse_answer(text: str) -> dict[int, str]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n|\n```$", "", text)
    start, end = text.find("["), text.rfind("]")
    data = json.loads(text[start : end + 1])
    return {int(item["id"]): str(item["text"]) for item in data}


def translate_batch(provider: str, model: str, locale: str, glossary: dict, batch: list[tuple[int, po.Entry]]) -> dict[int, str]:
    items = [
        {
            "id": idx,
            "text": entry.msgid,
            "context": " · ".join(
                [*entry.extracted_comments, *entry.references[:2]]
                + ([f"context: {entry.msgctxt}"] if entry.msgctxt else [])
            ),
        }
        for idx, entry in batch
    ]
    system, user = build_prompt(locale, glossary, items)
    for attempt in (1, 2, 3):
        try:
            raw = PROVIDERS[provider](system, user, model)
            answers = parse_answer(raw)
        except Exception as err:  # noqa: BLE001 — network, truncation, malformed JSON: all retryable
            print(f"  attempt {attempt}: {type(err).__name__}: {str(err)[:200]}", file=sys.stderr)
            time.sleep(3 * attempt)
            continue
        good, bad = {}, []
        for idx, entry in batch:
            text = answers.get(idx, "")
            if text and _placeholders(text) == _placeholders(entry.msgid):
                good[idx] = text
            else:
                bad.append(entry.msgid)
        if not bad:
            return good
        print(f"  attempt {attempt}: {len(bad)} rejected (placeholders): {bad[:3]}", file=sys.stderr)
        if attempt == 3:
            return good
    return {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("catalogs", nargs="*", help="PO files (default: every app and site catalogue)")
    ap.add_argument("--provider", choices=[*PROVIDERS, "manual"])
    ap.add_argument("--model")
    ap.add_argument("--export", help="manual: write pending entries to this JSON file")
    ap.add_argument("--import", dest="import_", help="manual: read translations from this JSON file")
    ap.add_argument("--limit", type=int, default=0, help="stop after N entries per catalogue")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    glossary = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    paths = [Path(p).resolve() for p in args.catalogs] or sorted(p for g in CATALOG_GLOBS for p in ROOT.glob(g))
    loaded = [(p, po.load(p)) for p in paths if p.exists()]

    provider = args.provider
    if provider is None:
        provider = next((name for name in PROVIDERS if os.environ.get(f"{name.upper()}_API_KEY")), None)
        if provider is None:
            print("no ANTHROPIC_API_KEY or GEMINI_API_KEY in the environment; use --provider manual", file=sys.stderr)
            return 2
    model = args.model or DEFAULT_MODELS.get(provider, "")

    imported: dict[str, dict] = {}
    if provider == "manual" and args.import_:
        imported = json.loads(Path(args.import_).read_text(encoding="utf-8"))
    pending_out: dict[str, list[dict]] = {}

    total_filled = total_left = 0
    for path, catalog in loaded:
        locale = locale_of(path, catalog)
        if locale in SKIP_LOCALES:
            continue
        pending = catalog.untranslated()
        if args.limit:
            pending = pending[: args.limit]
        if not pending:
            continue
        rel = path.relative_to(ROOT)
        memory = memory_for(locale, [(p, c) for p, c in loaded if locale_of(p, c) == locale and p != path])
        reused = 0
        for entry in list(pending):
            hit = memory.get(entry.key)
            if hit:
                entry.msgstr = hit
                reused += 1
                pending.remove(entry)
        print(f"{rel}: {len(pending)} to translate, {reused} reused from other catalogues")

        if provider == "manual":
            key = str(rel)
            if imported:
                for entry in pending:
                    text = imported.get(key, {}).get(entry.msgid) or imported.get(key, {}).get(f"{entry.msgctxt}\x04{entry.msgid}")
                    if text and _placeholders(text) == _placeholders(entry.msgid):
                        entry.msgstr = text
                        total_filled += 1
                    elif text:
                        print(f"  rejected (placeholders): {entry.msgid!r}", file=sys.stderr)
            else:
                pending_out[key] = [
                    {"msgid": e.msgid, "msgctxt": e.msgctxt, "context": " · ".join(e.extracted_comments + e.references[:2]), "locale": locale}
                    for e in pending
                ]
        else:
            batches: list[list[tuple[int, po.Entry]]] = []
            current: list[tuple[int, po.Entry]] = []
            size = 0
            for idx, entry in enumerate(pending):
                if current and (len(current) >= BATCH or size + len(entry.msgid) > BATCH_CHARS):
                    batches.append(current)
                    current, size = [], 0
                current.append((idx, entry))
                size += len(entry.msgid)
            if current:
                batches.append(current)
            done = 0
            for batch in batches:
                done += len(batch)
                if args.dry_run:
                    continue
                answers = translate_batch(provider, model, locale, glossary, batch)
                for idx, entry in batch:
                    if idx in answers:
                        entry.msgstr = answers[idx]
                        total_filled += 1
                # Saved after every batch: a run over a thousand strings that
                # dies at the last one should keep the first nine hundred.
                po.save(path, catalog)
                print(f"  {done}/{len(pending)}")

        left = len(catalog.untranslated())
        total_left += left
        if not args.dry_run and (provider != "manual" or imported or reused):
            po.save(path, catalog)
        if left:
            print(f"  {left} still untranslated in {rel}", file=sys.stderr)

    if pending_out:
        out = Path(args.export or "i18n-pending.json")
        out.write_text(json.dumps(pending_out, ensure_ascii=False, indent=1), encoding="utf-8")
        n = sum(len(v) for v in pending_out.values())
        print(f"wrote {n} pending entries to {out}; translate them and run with --import {out}")
        return 0
    print(f"filled {total_filled}; {total_left} untranslated remain")
    return 1 if total_left else 0


if __name__ == "__main__":
    sys.exit(main())
