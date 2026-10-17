"""Synthetic test material. Everything here is invented; nothing is taken from real books."""

from __future__ import annotations

from ebooklib import epub

from wfa.document import Document, Metadata, Section

ENGLISH = (
    "It was a bright cold day in April, and the clocks were striking thirteen. "
    "The reader opened the book and began to read the first chapter slowly. "
)

# ~30 words, no notice-like phrases: counts as ordinary prose for the cleaner.
PROSE = (
    "The rain had not stopped for three days, and the river was rising past the old stone "
    "bridge where the children used to play every summer evening before supper was called."
)

GUTENBERG = """\
The Project Gutenberg eBook of A Test Book

This ebook is for the use of anyone anywhere in the United States.

Title: A Test Book
       Being a Long Subtitle

Author: Jane Q. Writer

Release date: January 1, 2000 [eBook #99999]

Language: English

*** START OF THE PROJECT GUTENBERG EBOOK A TEST BOOK ***

CHAPTER I.

{body}

*** END OF THE PROJECT GUTENBERG EBOOK A TEST BOOK ***

Project Gutenberg license text.
"""


def prose(paragraphs: int) -> str:
    return "\n\n".join([PROSE] * paragraphs)


def make_doc(*sections: str | tuple[str | None, str]) -> Document:
    """Document from section texts, or (title, text) pairs."""
    built = [Section(*s) if isinstance(s, tuple) else Section(None, s) for s in sections]
    return Document(path="synthetic.txt", file_hash="0" * 64, format="txt", metadata=Metadata(), sections=built)


def make_epub(directory, name: str = "novel.epub"):
    book = epub.EpubBook()
    book.set_identifier("test-id")
    book.set_title("Synthetic Novel")
    book.set_language("en")
    book.add_author("Ada Author")
    book.add_metadata("DC", "language", "fr")

    def chapter(file_name, title, body):
        c = epub.EpubHtml(title=title, file_name=file_name, lang="en")
        c.content = f"<html><body>{body}</body></html>"
        book.add_item(c)
        return c

    title_page = chapter("title.xhtml", "Title", "<h1>Synthetic Novel</h1>")
    ch1 = chapter(
        "ch1.xhtml",
        "The Beginning",
        f"<h2>One</h2><p><span class='dropcap'>W</span>ord one. {ENGLISH}</p><p>Second paragraph.</p>",
    )
    ch2 = chapter("ch2.xhtml", "The Middle", f"<h2>Two</h2><p>Chapter <i>two</i> text. {ENGLISH}</p>")
    images = chapter("img.xhtml", "Plate", "<p><img src='plate.png' alt=''/></p>")
    untitled = chapter("ch3.xhtml", "", f"<h3>Heading Three</h3><p>Third. {ENGLISH}</p>")

    book.toc = [epub.Link("ch1.xhtml", "The Beginning", "ch1"), epub.Link("ch2.xhtml#start", "The Middle", "ch2")]
    book.guide = [{"href": "title.xhtml", "title": "Title Page", "type": "title-page"}]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    # Spine order deliberately differs from the order items were added.
    book.spine = ["nav", title_page, ch2, ch1, images, untitled]

    path = directory / name
    epub.write_epub(str(path), book)
    return path
