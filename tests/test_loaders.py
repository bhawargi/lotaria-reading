import zipfile

import pytest

from helpers import ENGLISH, GUTENBERG, make_epub
from wfa.loaders import UnsupportedFormatError, decode_text, load

# --- Plain text -----------------------------------------------------------


def test_utf8_bom_and_crlf(tmp_path):
    path = tmp_path / "bom.txt"
    path.write_bytes("\ufeffFirst line\r\nSecond line\rThird".encode("utf-8"))
    doc = load(path)
    assert doc.text == "First line\nSecond line\nThird"
    assert doc.metadata.extra["encoding"] == "utf-8"


def test_non_utf8_encoding_is_detected():
    raw = ("Le café était plein. Une naïveté déconcertante régnait à l'intérieur. " * 20).encode("cp1252")
    text, encoding = decode_text(raw)
    assert "café" in text and "naïveté" in text
    assert encoding != "utf-8"


def test_cyrillic_encoding_is_detected():
    raw = ("Москва — столица России. Это большой и красивый город. " * 20).encode("cp1251")
    text, _ = decode_text(raw)
    assert "столица" in text


def test_plain_text_metadata_falls_back_to_filename(tmp_path):
    path = tmp_path / "my_book.txt"
    path.write_text(ENGLISH * 5, encoding="utf-8")
    doc = load(path)
    assert doc.format == "txt"
    assert doc.metadata.source == "plain"
    assert doc.metadata.title == "my_book"
    assert len(doc.file_hash) == 64


def test_gutenberg_header_metadata(tmp_path):
    path = tmp_path / "pg.txt"
    path.write_text(GUTENBERG.format(body=ENGLISH * 3), encoding="utf-8")
    doc = load(path)
    meta = doc.metadata
    assert meta.source == "gutenberg"
    assert meta.title == "A Test Book Being a Long Subtitle"
    assert meta.author == "Jane Q. Writer"
    assert meta.language == "en"
    assert meta.extra["release_date"].startswith("January 1, 2000")


# --- Format detection -----------------------------------------------------


def test_pdf_is_rejected(tmp_path):
    path = tmp_path / "x.pdf"
    path.write_bytes(b"%PDF-1.7 ...")
    with pytest.raises(UnsupportedFormatError):
        load(path)


def test_non_epub_zip_is_rejected(tmp_path):
    path = tmp_path / "x.docx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", "<xml/>")
    with pytest.raises(UnsupportedFormatError):
        load(path)


def test_binary_is_rejected(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"\x00\x01\x02" * 100)
    with pytest.raises(UnsupportedFormatError):
        load(path)


def test_format_detected_by_content_not_extension(tmp_path):
    path = make_epub(tmp_path)
    renamed = path.rename(tmp_path / "actually_an_epub.txt")
    assert load(renamed).format == "epub"


# --- EPUB -----------------------------------------------------------------


@pytest.fixture
def epub_doc(tmp_path):
    return load(make_epub(tmp_path))


def test_epub_metadata(epub_doc):
    meta = epub_doc.metadata
    assert epub_doc.format == "epub"
    assert meta.source == "epub"
    assert meta.title == "Synthetic Novel"
    assert meta.author == "Ada Author"
    assert meta.language == "en"
    assert meta.extra["languages"] == ["en", "fr"]


def test_epub_follows_spine_and_skips_nav_and_title_page(epub_doc):
    titles = [s.title for s in epub_doc.sections]
    assert titles == ["The Middle", "The Beginning", "Heading Three"]


def test_epub_inline_markup_does_not_split_words(epub_doc):
    beginning = epub_doc.sections[1].text
    assert "Word one." in beginning
    assert "Chapter two text." in epub_doc.sections[0].text


def test_epub_block_elements_become_line_breaks(epub_doc):
    lines = epub_doc.sections[1].text.split("\n")
    assert "One" in lines
    assert "Second paragraph." in lines


def test_epub_image_only_pages_are_reported(epub_doc):
    assert any("image-only" in w for w in epub_doc.warnings)
