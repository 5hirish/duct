"""Text out of the documents a person hands Duct about their business.

Onboarding reads a website, and a website says what a visitor should read. A
pitch deck or a positioning doc says who buys, what it costs and who the
competition is, which is most of a project. This module turns one uploaded
file into plain text and nothing more: no model, no storage, no network.

Text, not the file, is what moves on, because the run that reads it may be on
any provider and several (DeepSeek among them) read no PDF. A capability the
model may not have is Duct's to provide, the same rule as web search.

Every limit here is a defence as much as a budget. A PDF is a program for a
parser and an OOXML file is a zip archive, so a hostile upload can ask for
unbounded pages, memory or decompression; each reader stops at a cap and says
so (``truncated``) rather than reading to the end.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
import zlib
from dataclasses import dataclass
from enum import StrEnum
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

#: How many files one person hands over at once: a deck, a positioning doc, a
#: brief or two. The upload route and the audit request both hold to it.
MAX_DOCUMENTS = 5
#: A deck exported at print resolution is a few MB; past this it is a scan or
#: a video someone renamed, and neither has text worth the upload.
MAX_BYTES = 10 * 1024 * 1024
#: The first pages of a document carry its pitch; page 51 of a manual does not.
MAX_PAGES = 50
#: About 10k tokens. Past this a file stops adding to a project draft and only
#: adds to the bill on the user's key.
MAX_CHARS = 40_000
#: The decompressed size of one XML part we are willing to parse. A 10 MB
#: .docx that inflates past this is a zip bomb, not a long document.
_MAX_XML_BYTES = 40 * 1024 * 1024


class DocumentKind(StrEnum):
    PDF = "pdf"
    WORD = "docx"
    SLIDES = "pptx"
    MARKDOWN = "md"
    TEXT = "txt"


class Unreadable(StrEnum):
    """Why a file gave no text. The app words each one; never a message here."""

    UNSUPPORTED = "unsupported"  # a type this module does not read
    TOO_LARGE = "too_large"
    ENCRYPTED = "encrypted"      # a password-protected PDF
    NO_TEXT = "no_text"          # read fine, nothing in it: a scan, or images only
    DAMAGED = "damaged"          # claims to be a type and does not parse as it


class DocumentError(ValueError):
    def __init__(self, reason: Unreadable, detail: str = "") -> None:
        super().__init__(detail or reason.value)
        self.reason = reason


@dataclass(frozen=True)
class Extracted:
    name: str
    kind: DocumentKind
    text: str
    #: Pages for a PDF, slides for a deck, None where the format has no pages.
    pages: int | None
    truncated: bool


_EXTENSIONS: dict[str, DocumentKind] = {
    "pdf": DocumentKind.PDF,
    "docx": DocumentKind.WORD,
    "pptx": DocumentKind.SLIDES,
    "md": DocumentKind.MARKDOWN,
    "markdown": DocumentKind.MARKDOWN,
    "txt": DocumentKind.TEXT,
}

# The type is read from the name and then checked against the bytes, because
# the name is whatever the browser was told. A .pdf that is not a PDF is
# DAMAGED, not parsed on trust.
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_SLIDE_PART = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
_BLANK_RUNS = re.compile(r"\n{3,}")


def kind_of(name: str) -> DocumentKind | None:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _EXTENSIONS.get(ext)


def extract_document(name: str, data: bytes) -> Extracted:
    """The text of one file, or ``DocumentError`` saying why there is none.

    Synchronous and CPU-bound: call it from a thread, never on the event loop.
    """
    kind = kind_of(name)
    if kind is None:
        raise DocumentError(Unreadable.UNSUPPORTED)
    if len(data) > MAX_BYTES:
        raise DocumentError(Unreadable.TOO_LARGE)

    try:
        if kind is DocumentKind.PDF:
            text, pages, truncated = _read_pdf(data)
        elif kind is DocumentKind.WORD:
            text, pages, truncated = _read_docx(data)
        elif kind is DocumentKind.SLIDES:
            text, pages, truncated = _read_pptx(data)
        else:
            text, pages, truncated = _decode(data), None, False
    except (zipfile.BadZipFile, ElementTree.ParseError, RuntimeError, NotImplementedError, EOFError, zlib.error):
        # A member the archive cannot inflate (encrypted, a codec zipfile lacks,
        # cut short) or XML that does not parse: the file is not what it says.
        raise DocumentError(Unreadable.DAMAGED) from None

    text = _BLANK_RUNS.sub("\n\n", text).strip()
    if len(text) > MAX_CHARS:
        text, truncated = text[:MAX_CHARS], True
    if not text:
        raise DocumentError(Unreadable.NO_TEXT)
    return Extracted(name=name, kind=kind, text=text, pages=pages, truncated=truncated)


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Windows-1252 is what a .txt saved by an older editor most likely is;
        # latin-1 would decode it too, and mangle every curly quote.
        return data.decode("cp1252", errors="replace")


def _read_pdf(data: bytes) -> tuple[str, int, bool]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    if not data.startswith(_PDF_MAGIC):
        raise DocumentError(Unreadable.DAMAGED)
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # Many "protected" PDFs only restrict printing and open with an
            # empty password; anything else is the user's to unlock.
            try:
                if not reader.decrypt(""):
                    raise DocumentError(Unreadable.ENCRYPTED)
            except DocumentError:
                raise
            except Exception:  # noqa: BLE001 — AES needs an optional extra; either way it stays locked
                raise DocumentError(Unreadable.ENCRYPTED) from None
        total = len(reader.pages)
        parts: list[str] = []
        size = 0
        for page in reader.pages[:MAX_PAGES]:
            chunk = page.extract_text() or ""
            parts.append(chunk)
            size += len(chunk)
            if size > MAX_CHARS:
                break
    except DocumentError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        # pypdf raises a spread of types for a malformed file, not only its own.
        logger.info("documents: unreadable PDF: %s", exc)
        raise DocumentError(Unreadable.DAMAGED) from None
    return "\n\n".join(parts), total, total > MAX_PAGES or size > MAX_CHARS


def _xml_part(archive: zipfile.ZipFile, name: str) -> ElementTree.Element:
    info = archive.getinfo(name)
    if info.file_size > _MAX_XML_BYTES:
        raise DocumentError(Unreadable.TOO_LARGE)
    raw = archive.read(info)
    # Entity tricks (billion laughs, external entities) all need a DTD, and an
    # Office part never carries one. Refusing any DOCTYPE closes them whatever
    # the expat underneath, without defusedxml as a dependency for one call.
    if b"<!DOCTYPE" in raw:
        raise DocumentError(Unreadable.DAMAGED)
    return ElementTree.fromstring(raw)


def _open_zip(data: bytes) -> zipfile.ZipFile:
    if not data.startswith(_ZIP_MAGIC):
        raise DocumentError(Unreadable.DAMAGED)
    return zipfile.ZipFile(io.BytesIO(data))


def _paragraphs(root: ElementTree.Element, para_tag: str, text_tag: str) -> list[str]:
    out = []
    for para in root.iter(para_tag):
        line = "".join(node.text or "" for node in para.iter(text_tag)).strip()
        if line:
            out.append(line)
    return out


def _read_docx(data: bytes) -> tuple[str, None, bool]:
    with _open_zip(data) as archive:
        try:
            root = _xml_part(archive, "word/document.xml")
        except KeyError:
            raise DocumentError(Unreadable.DAMAGED) from None
    return "\n".join(_paragraphs(root, f"{_W}p", f"{_W}t")), None, False


def _read_pptx(data: bytes) -> tuple[str, int, bool]:
    with _open_zip(data) as archive:
        # Slide parts are numbered in deck order; the archive lists them in
        # whatever order they were written.
        numbered = sorted(
            (int(m.group(1)), name)
            for name in archive.namelist()
            if (m := _SLIDE_PART.match(name))
        )
        if not numbered:
            raise DocumentError(Unreadable.DAMAGED)
        slides: list[str] = []
        size = 0
        for _, name in numbered[:MAX_PAGES]:
            root = _xml_part(archive, name)
            text = "\n".join(_paragraphs(root, f"{_A}p", f"{_A}t"))
            slides.append(text)
            size += len(text)
            if size > MAX_CHARS:
                break
    total = len(numbered)
    return "\n\n".join(s for s in slides if s), total, total > MAX_PAGES or size > MAX_CHARS
