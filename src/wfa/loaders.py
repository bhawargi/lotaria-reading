"""Load a book file into a Document: format detection, decoding, EPUB extraction, metadata.

Loaders only extract. Cleaning, normalisation and tokenisation happen in later stages,
so the Document returned here has sections filled in but no tokens.
"""

from __future__ import annotations

import hashlib
import re
import warnings as _warnings
import zipfile
from pathlib import Path, PurePosixPath

import charset_normalizer
import ebooklib
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import epub

from wfa.document import Document, Metadata, Section

EPUB_MIMETYPE = b"application/epub+zip"

# EPUB guide/landmark types that are navigation or front matter rather than book text.
SKIPPED_GUIDE_TYPES = {"cover", "toc", "title-page", "copyright-page"}

BLOCK_TAGS = [
    "p",
    "div",
    "br",
    "hr",
    "li",
    "dt",
    "dd",
    "tr",
    "blockquote",
    "pre",
    "section",
    "article",
    "header",
    "footer",
    "aside",
    "figcaption",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
]

GUTENBERG_START = re.compile(r"^\*{3}\s*START OF (?:THE|THIS) PROJECT GUTENBERG E-?BOOK", re.IGNORECASE | re.MULTILINE)
GUTENBERG_FIELDS = {
    "title": "title",
    "author": "author",
    "language": "language",
    "release date": "release_date",
}
GUTENBERG_FIELD_LINE = re.compile(r"^(Title|Author|Language|Release date):\s*(.*)$", re.IGNORECASE)


class UnsupportedFormatError(ValueError):
    pass


def load(path: str | Path) -> Document:
    path = Path(path)
    raw = path.read_bytes()
    fmt = detect_format(raw, path)
    doc = _load_epub(path) if fmt == "epub" else _load_text(raw, path)
    doc.file_hash = hashlib.sha256(raw).hexdigest()

    if not doc.metadata.title:
        doc.metadata.title = path.stem
    return doc


def detect_format(raw: bytes, path: Path) -> str:
    if raw.startswith(b"PK") and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            try:
                mimetype = zf.read("mimetype").strip()
            except KeyError:
                mimetype = b""
        if mimetype == EPUB_MIMETYPE:
            return "epub"
        raise UnsupportedFormatError(f"{path.name}: zip archive that is not an EPUB (DOCX, ODT, ...).")
    if raw.startswith(b"%PDF"):
        raise UnsupportedFormatError(f"{path.name}: PDF files are not supported.")
    if b"\x00" in raw[:8192]:
        raise UnsupportedFormatError(f"{path.name}: looks like a binary file, not text.")
    return "txt"


# --- Plain text -----------------------------------------------------------


def decode_text(raw: bytes) -> tuple[str, str]:
    """Return (text, encoding). Tries UTF-8 (BOM-aware) first, then detection."""
    try:
        text, encoding = raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        best = _best_encoding_match(raw)
        text, encoding = str(best), best.encoding
    return text.replace("\r\n", "\n").replace("\r", "\n"), encoding


CHAOS_MARGIN = 0.01


def _best_encoding_match(raw: bytes):
    """charset-normalizer's .best() ranks by "chaos" alone, so near-identical code pages
    (cp1252 vs cp1250 vs mac_latin2) can win by noise. Among candidates that are about as
    clean as the cleanest, prefer the one whose text is most like a real language."""
    matches = list(charset_normalizer.from_bytes(raw))
    if not matches:
        raise UnsupportedFormatError("Could not detect the text encoding.")
    cleanest = min(m.chaos for m in matches)
    close = [m for m in matches if m.chaos <= cleanest + CHAOS_MARGIN]
    return max(close, key=lambda m: m.coherence)


def _load_text(raw: bytes, path: Path) -> Document:
    text, encoding = decode_text(raw)
    metadata = Metadata(source="plain", extra={"encoding": encoding})

    start = GUTENBERG_START.search(text)
    if start:
        metadata.source = "gutenberg"
        _apply_gutenberg_header(text[: start.start()], metadata)

    return Document(
        path=str(path),
        file_hash="",
        format="txt",
        metadata=metadata,
        sections=[Section(title=None, text=text)],
    )


def _apply_gutenberg_header(header: str, metadata: Metadata) -> None:
    """Read 'Title:', 'Author:' etc. from a Gutenberg header. Indented lines continue a field."""
    fields: dict[str, str] = {}
    current = None
    for line in header.split("\n"):
        match = GUTENBERG_FIELD_LINE.match(line)
        if match:
            current = GUTENBERG_FIELDS[match.group(1).lower()]
            fields[current] = match.group(2).strip()
        elif current and line.startswith((" ", "\t")) and line.strip():
            fields[current] += " " + line.strip()
        else:
            current = None

    metadata.title = fields.get("title") or None
    metadata.author = fields.get("author") or None
    metadata.language = _language_code(fields.get("language"))
    if "release_date" in fields:
        metadata.extra["release_date"] = fields["release_date"]


LANGUAGE_NAMES = {
    "english": "en",
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "italian": "it",
    "portuguese": "pt",
    "dutch": "nl",
    "latin": "la",
    "finnish": "fi",
    "swedish": "sv",
}


def _language_code(value: str | None) -> str | None:
    """'English' -> 'en', 'en-US' -> 'en'."""
    if not value:
        return None
    value = value.strip()
    if value.lower() in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[value.lower()]
    return value.split("-")[0].lower() or None


# --- EPUB -----------------------------------------------------------------


def _load_epub(path: Path) -> Document:
    book = epub.read_epub(str(path), options={"ignore_ncx": False})
    doc = Document(path=str(path), file_hash="", format="epub", metadata=_epub_metadata(book))

    toc_titles = _toc_titles(book.toc)
    skipped_hrefs = {
        _strip_fragment(ref.get("href") or "")
        for ref in book.guide
        if (ref.get("type") or "").lower() in SKIPPED_GUIDE_TYPES
    }

    image_only = 0
    for idref, linear in book.spine:
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        if linear == "no" or isinstance(item, (epub.EpubNav, epub.EpubCoverHtml)):
            continue
        if item.get_name() in skipped_hrefs:
            continue

        soup = _parse_html(item.get_content())
        text = html_to_text(soup)
        if not text.strip():
            if soup.find(["img", "image", "svg"]):
                image_only += 1
            continue
        title = toc_titles.get(item.get_name()) or _first_heading(soup)
        doc.sections.append(Section(title=title, text=text))

    if image_only:
        doc.warnings.append(f"{image_only} image-only page(s) skipped; text inside images is not read.")
    if not doc.sections:
        doc.warnings.append("No text found in the EPUB.")
    return doc


def _epub_metadata(book: epub.EpubBook) -> Metadata:
    def first(name: str) -> str | None:
        values = book.get_metadata("DC", name)
        return values[0][0].strip() if values and values[0][0] else None

    languages = [v[0] for v in book.get_metadata("DC", "language") if v[0]]
    creators = [v[0].strip() for v in book.get_metadata("DC", "creator") if v[0]]
    extra = {}
    if len(languages) > 1:
        extra["languages"] = languages
    for name in ("publisher", "date"):
        if value := first(name):
            extra[name] = value

    return Metadata(
        title=first("title"),
        author=", ".join(creators) or None,
        language=_language_code(languages[0]) if languages else None,
        source="epub",
        extra=extra,
    )


def _toc_titles(toc) -> dict[str, str]:
    """Map document file name -> first TOC title pointing at it."""
    titles: dict[str, str] = {}

    def walk(entries):
        for entry in entries:
            if isinstance(entry, tuple):
                section, children = entry
                walk([section])
                walk(children)
            elif isinstance(entry, (epub.Link, epub.Section)) and entry.href and entry.title:
                titles.setdefault(_strip_fragment(entry.href), entry.title.strip())

    walk(toc)
    return titles


def _strip_fragment(href: str) -> str:
    return str(PurePosixPath(href.split("#", 1)[0]))


def _parse_html(content: bytes) -> BeautifulSoup:
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        return BeautifulSoup(content, "lxml")


def html_to_text(soup: BeautifulSoup) -> str:
    """Text with line breaks only at block elements, so inline markup never splits a word."""
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_after("\n")
        if tag.name in ("br", "hr"):
            continue
        tag.insert_before("\n")
    text = soup.get_text()
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _first_heading(soup: BeautifulSoup) -> str | None:
    heading = soup.find(["h1", "h2", "h3"])
    if heading:
        title = heading.get_text(" ", strip=True)
        return title or None
    return None
