"""Normalise cleaned text so the same word is always written the same way.

Library steps: ftfy (broken encodings, mojibake, ligatures, curly quotes, width forms,
NFKC) and textacy.preprocessing (quotation marks, bullets, words hyphenated across lines,
URLs and emails). Our own steps cover what those don't: dashes that would glue words
together, plain-text emphasis markers, symbols, and whitespace that keeps paragraph breaks.
Case is preserved; lowercasing happens at tokenisation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import ftfy
from textacy.preprocessing import normalize as tnorm
from textacy.preprocessing import replace as treplace

from wfa.document import Document

# Em/en/figure dashes, horizontal bar, two-em/three-em dashes, and "--" used as a dash.
DASH = re.compile("\\s*(?:-{2,}|[\u2012-\u2015\u2e3a\u2e3b\ufe58\ufe63\uff0d])\\s*")
SPACED_HYPHEN = re.compile(r"(?<=[^\S\n])-(?=[^\S\n])")  # within a line only, so "- " bullets survive
# _italic_ and *bold* conventions in plain-text books.
EMPHASIS = re.compile(r"(?<!\w)[_*]+(?=\w)|(?<=\w)[_*]+(?!\w)")
ZERO_WIDTH = re.compile("[\u200b-\u200d\u2060\ufeff\u00ad]")  # includes soft hyphen
GUILLEMETS = str.maketrans({"«": '"', "»": '"', "‹": "'", "›": "'"})
SPACES = re.compile(r"[^\S\n]+")
BLANK_LINES = re.compile(r"\n\s*\n\s*")


@dataclass
class NormalizeOptions:
    fix_unicode: bool = True        # ftfy: mojibake, ligatures, width forms, NFKC
    quotes: bool = True             # curly/angled/low quotes -> ' and "
    rejoin_hyphenated: bool = True  # "con-\nspiracy" -> "conspiracy"
    split_dashes: bool = True       # "word--word", "word—word" -> "word word"
    strip_emphasis: bool = True     # "_word_", "*word*" -> "word"
    remove_urls_emails: bool = True
    remove_symbols: bool = True     # ™ © ® ° and other Unicode "symbol" characters
    bullets: bool = True


def normalize(doc: Document, options: NormalizeOptions | None = None) -> Document:
    options = options or NormalizeOptions()
    chars_before = sum(len(s.text) for s in doc.sections)
    for section in doc.sections:
        section.text = normalize_text(section.text, options)
        if section.title:
            section.title = normalize_text(section.title, options)
    doc.stats["normalize"] = {
        "chars_before": chars_before,
        "chars_after": sum(len(s.text) for s in doc.sections),
    }
    return doc


def normalize_text(text: str, options: NormalizeOptions | None = None) -> str:
    options = options or NormalizeOptions()
    if options.fix_unicode:
        # Unicode normalisation (NFKC) waits until symbols are gone, or "™" becomes "TM".
        text = ftfy.fix_text(text, uncurl_quotes=options.quotes, normalization=None)
    if options.remove_symbols:
        text = "".join(" " if unicodedata.category(ch) == "So" else ch for ch in text)
    if options.fix_unicode:
        text = unicodedata.normalize("NFKC", text)
    if options.quotes:
        text = tnorm.quotation_marks(text).translate(GUILLEMETS)
    if options.bullets:
        text = tnorm.bullet_points(text)
    if options.rejoin_hyphenated:
        text = tnorm.hyphenated_words(text)
    if options.remove_urls_emails:
        text = treplace.urls(text, repl=" ")
        text = treplace.emails(text, repl=" ")
    if options.split_dashes:
        text = DASH.sub(" ", text)
        text = SPACED_HYPHEN.sub(" ", text)
    if options.strip_emphasis:
        text = EMPHASIS.sub("", text)
    return _whitespace(text)


def _whitespace(text: str) -> str:
    """Collapse spaces within lines and runs of blank lines, keeping paragraph breaks."""
    text = ZERO_WIDTH.sub("", text)
    text = SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return BLANK_LINES.sub("\n\n", text).strip()
