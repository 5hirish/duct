"""Text out of the files a person adds at onboarding.

Every reader stops at a cap and says so, and every file that gives no text
says why with a reason the app can word. The PDFs are made here with
reportlab and pypdf, so the parser reads real files, not a stub of one; the
Office files are the zip-of-XML they are on disk.

No network.
"""

from __future__ import annotations

import io
import zipfile

import pytest

import service.documents as documents
from service.documents import DocumentError, DocumentKind, Unreadable, extract_document

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _pdf(pages: list[str]) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    for text in pages:
        if text:
            pdf.drawString(72, 720, text)
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


def _encrypted(pdf: bytes, *, user_password: str) -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    # RC4 is the one pypdf implements without an optional crypto extra.
    writer.encrypt(user_password=user_password, owner_password="fake-owner", algorithm="RC4-128")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _docx(paragraphs: list[str], *, doctype: str = "") -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<?xml version="1.0"?>{doctype}<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return buf.getvalue()


def _pptx(slides: dict[int, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        for number, text in slides.items():
            archive.writestr(
                f"ppt/slides/slide{number}.xml",
                f'<p:sld xmlns:p="p" xmlns:a="{A}"><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:sld>',
            )
    return buf.getvalue()


def _reason(name: str, data: bytes) -> Unreadable:
    with pytest.raises(DocumentError) as caught:
        extract_document(name, data)
    return caught.value.reason


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def test_a_pdf_gives_its_text_and_its_page_count():
    doc = extract_document("deck.pdf", _pdf(["Acme plans weeknight dinners", "For busy parents"]))
    assert doc.kind is DocumentKind.PDF
    assert doc.pages == 2
    assert "Acme plans weeknight dinners" in doc.text
    assert "For busy parents" in doc.text
    assert not doc.truncated


def test_a_long_pdf_is_read_to_the_page_cap_and_says_it_stopped(monkeypatch):
    monkeypatch.setattr(documents, "MAX_PAGES", 3)
    doc = extract_document("manual.pdf", _pdf([f"Page {n}" for n in range(1, 6)]))
    assert doc.pages == 5
    assert "Page 3" in doc.text and "Page 4" not in doc.text
    assert doc.truncated


def test_a_pdf_that_only_restricts_printing_opens_without_a_password():
    doc = extract_document("deck.pdf", _encrypted(_pdf(["Pricing starts at $49"]), user_password=""))
    assert "Pricing starts at $49" in doc.text


def test_a_password_protected_pdf_is_encrypted_not_damaged():
    assert _reason("deck.pdf", _encrypted(_pdf(["secret"]), user_password="fake-user")) is Unreadable.ENCRYPTED


def test_a_pdf_of_blank_pages_has_no_text():
    """A scan is images on pages; to the reader it is the same as blank."""
    assert _reason("scan.pdf", _pdf(["", ""])) is Unreadable.NO_TEXT


def test_a_file_named_pdf_that_is_not_one_is_damaged():
    assert _reason("deck.pdf", b"<html>not a pdf</html>") is Unreadable.DAMAGED
    assert _reason("deck.pdf", b"%PDF-1.7 and then garbage") is Unreadable.DAMAGED


# ---------------------------------------------------------------------------
# Word and PowerPoint
# ---------------------------------------------------------------------------

def test_a_word_document_gives_one_line_per_paragraph():
    doc = extract_document("positioning.docx", _docx(["Who we serve", "Agencies with five clients"]))
    assert doc.kind is DocumentKind.WORD
    assert doc.pages is None
    assert doc.text == "Who we serve\nAgencies with five clients"


def test_slides_are_read_in_deck_order_not_archive_order():
    """slide10 sorts before slide2 as a string; the deck does not."""
    doc = extract_document("deck.pptx", _pptx({10: "Ask", 2: "Problem", 1: "Acme"}))
    assert doc.kind is DocumentKind.SLIDES
    assert doc.pages == 3
    assert doc.text.split("\n\n") == ["Acme", "Problem", "Ask"]


def test_an_office_part_with_a_doctype_is_refused():
    """Every entity trick needs a DTD, and no Office part carries one."""
    laughs = '<!DOCTYPE w [<!ENTITY lol "lol">]>'
    assert _reason("brief.docx", _docx(["&lol;"], doctype=laughs)) is Unreadable.DAMAGED


def test_an_office_part_that_inflates_past_the_cap_is_too_large(monkeypatch):
    monkeypatch.setattr(documents, "_MAX_XML_BYTES", 64)
    assert _reason("brief.docx", _docx(["x" * 200])) is Unreadable.TOO_LARGE


def test_a_zip_that_is_not_a_word_document_is_damaged():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("notes.txt", "hello")
    assert _reason("brief.docx", buf.getvalue()) is Unreadable.DAMAGED
    assert _reason("deck.pptx", buf.getvalue()) is Unreadable.DAMAGED
    assert _reason("brief.docx", b"PK\x03\x04 cut short") is Unreadable.DAMAGED


# ---------------------------------------------------------------------------
# Text, types and caps
# ---------------------------------------------------------------------------

def test_plain_text_and_markdown_decode_with_a_windows_fallback():
    assert extract_document("notes.md", "# Acme\n\nDinner, planned.".encode()).text == "# Acme\n\nDinner, planned."
    # cp1252's curly quotes, which latin-1 would turn into control characters.
    assert extract_document("notes.txt", b"\x93Acme\x94").text == "“Acme”"


def test_text_past_the_character_cap_is_cut_and_says_so(monkeypatch):
    monkeypatch.setattr(documents, "MAX_CHARS", 10)
    doc = extract_document("notes.txt", b"0123456789abcdef")
    assert doc.text == "0123456789"
    assert doc.truncated


def test_types_it_does_not_read_and_files_over_the_size_cap(monkeypatch):
    assert _reason("old.doc", b"\xd0\xcf\x11\xe0") is Unreadable.UNSUPPORTED
    assert _reason("sheet.xlsx", b"PK\x03\x04") is Unreadable.UNSUPPORTED
    assert _reason("no-extension", b"hello") is Unreadable.UNSUPPORTED
    monkeypatch.setattr(documents, "MAX_BYTES", 4)
    assert _reason("notes.txt", b"hello") is Unreadable.TOO_LARGE


def test_an_empty_text_file_has_no_text():
    assert _reason("notes.txt", b"  \n\n ") is Unreadable.NO_TEXT
