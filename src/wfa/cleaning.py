"""Remove text that isn't part of the book: distributor wrappers, front/back matter,
legal and publishing notices, watermarks, running headers and page numbers.

Every rule is source-agnostic and conservative:
- Content-based rules (notices, front/back matter) only act near the start or end of
  the book, where that material lives, so the narrative itself is never scanned for them.
- Every cut is recorded in `doc.removed` with the rule that made it, and counted in
  `doc.stats["cleaning"]`, so over-stripping is visible without reading the book.
- Source-specific knowledge (e.g. Project Gutenberg's markers) is plain configuration in
  `CleaningOptions`, and callers can add their own markers and patterns.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from wfa.document import Document, Section

# (start, end) wrapper markers. Text before the start marker and after the end marker is dropped.
DEFAULT_MARKERS: list[tuple[str, str]] = [
    # Project Gutenberg (current and older wordings).
    (
        r"^\W*\*{3}\s*START OF (?:THE|THIS) PROJECT GUTENBERG.*$",
        r"^\W*\*{3}\s*END OF (?:THE|THIS) PROJECT GUTENBERG.*$",
    ),
    (r"^\W*\*END\*THE SMALL PRINT!.*$", r"^\W*End of (?:the )?Project Gutenberg.*$"),
]

# Section titles that mark non-book material (matched against the whole, trimmed title).
DEFAULT_SKIP_TITLES = [
    r"(?:table of )?contents", r"copyright(?: page)?", r"title page", r"half[- ]title",
    r"also by .*", r"other (?:books|titles|works) by .*", r"(?:books|titles) by .*",
    r"praise for .*", r"about the (?:author|authors|publisher|translator)s?",
    r"acknowledge?ments?", r"colophon", r"imprint", r"credits",
    r"newsletter.*", r"sign up.*", r"connect with .*", r"reading group guide.*",
    r"index", r"copyright notice", r"legal notice", r"license", r"licence",
]

# Phrases typical of legal, publishing, distribution and transcription notices.
DEFAULT_NOTICE_CUES = [
    r"copyright", r"©", r"\(c\)\s*\d{4}", r"all rights reserved", r"\bisbn\b", r"\bissn\b",
    r"licen[cs]e[ds]?", r"trademark", r"™", r"®", r"permission", r"reproduced",
    r"published by", r"publisher", r"publishing", r"printed in", r"first (?:published|edition|printing)",
    r"library of congress", r"catalogu?ing", r"british library", r"\bedition\b",
    r"https?://", r"www\.", r"\b[\w-]+\.(?:com|org|net|co\.uk)\b", r"e-?books?\b",
    r"distribut(?:ed|ion|e)", r"terms of (?:use|service)", r"disclaimer", r"warrant(?:y|ies)",
    r"fictitious", r"resemblance to actual", r"cover (?:design|art|image|illustration)",
    r"typeset", r"produced by", r"transcri(?:bed|ber|ption)", r"proofread", r"digiti[sz]ed",
    r"scanned", r"prepared by", r"electronic (?:version|edition)", r"\bdonat(?:e|ion)",
    r"sold subject to", r"without the prior", r"\bpiracy\b", r"\bunauthori[sz]ed\b",
]

PAGE_NUMBER = re.compile(r"^\s*(?:page\s*)?\d{1,4}\s*$", re.IGNORECASE)
HEADING = re.compile(
    r"^\s*(?:chapter|part|book|section|volume|act|scene|canto|letter)\b|^\s*[IVXLCDM]+\.?\s*$",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"""[.!?;:,"'”’)\]]\s*$""")
WORD = re.compile(r"\w+")
QUOTE = re.compile(r"[\"“”‘’«»]|(?:^|\s)'")


@dataclass
class CleaningOptions:
    markers: list[tuple[str, str]] = field(default_factory=lambda: list(DEFAULT_MARKERS))
    skip_titles: list[str] = field(default_factory=lambda: list(DEFAULT_SKIP_TITLES))
    notice_cues: list[str] = field(default_factory=lambda: list(DEFAULT_NOTICE_CUES))
    # Extra regexes for known noise (e.g. a watermark); every match is deleted wherever it occurs.
    extra_patterns: list[str] = field(default_factory=list)

    edge_fraction: float = 0.1     # never scan further than this share of the book from either end
    prose_run_stop: int = 3        # stop scanning after this many consecutive prose paragraphs
    prose_min_words: int = 25      # a non-notice paragraph at least this long counts as prose
    notice_min_cues: int = 2       # cue matches that make a paragraph a notice...
    notice_short_words: int = 40   # ...or a single cue in a paragraph shorter than this
    repeat_min: int = 5            # a short line seen this often is a running header/watermark
    repeat_max_chars: int = 80
    warn_removed_fraction: float = 0.2


def clean(doc: Document, options: CleaningOptions | None = None) -> Document:
    options = options or CleaningOptions()
    words_before = _count_words(doc.text)
    removed: Counter[str] = Counter()

    def record(rule: str, section: Section | None, text: str) -> None:
        if not text.strip():
            return
        removed[rule] += _count_words(text)
        doc.removed.append({"rule": rule, "section": section.title if section else None, "text": text})

    _strip_markers(doc, options, record)
    _drop_skip_sections(doc, options, record)
    _drop_extra_patterns(doc, options, record)
    _drop_page_numbers_and_repeated_lines(doc, options, record)
    _drop_edge_notices(doc, options, record)
    doc.sections = [s for s in doc.sections if s.text.strip()]

    words_after = _count_words(doc.text)
    doc.stats["cleaning"] = {
        "words_before": words_before,
        "words_after": words_after,
        "removed_by_rule": dict(removed),
    }
    if words_before and (words_before - words_after) / words_before > options.warn_removed_fraction:
        share = (words_before - words_after) / words_before
        doc.warnings.append(f"Cleaning removed {share:.0%} of the text; check the removed-text dump.")
    return doc


# --- Rules ----------------------------------------------------------------


def _strip_markers(doc, options, record):
    for start_pattern, end_pattern in options.markers:
        start_re = re.compile(start_pattern, re.IGNORECASE | re.MULTILINE)
        end_re = re.compile(end_pattern, re.IGNORECASE | re.MULTILINE)

        start_idx = next((i for i, s in enumerate(doc.sections) if start_re.search(s.text)), None)
        end_idx = next((i for i in reversed(range(len(doc.sections))) if end_re.search(doc.sections[i].text)), None)
        if start_idx is None and end_idx is None:
            continue

        if start_idx is not None:
            for section in doc.sections[:start_idx]:
                record("wrapper", section, section.text)
                section.text = ""
            section = doc.sections[start_idx]
            match = start_re.search(section.text)
            record("wrapper", section, section.text[: match.end()])
            section.text = section.text[match.end():]

        if end_idx is not None:
            section = doc.sections[end_idx]
            match = end_re.search(section.text)
            if match:
                record("wrapper", section, section.text[match.start():])
                section.text = section.text[: match.start()]
            for section in doc.sections[end_idx + 1:]:
                record("wrapper", section, section.text)
                section.text = ""
        break  # one wrapper per book


def _drop_skip_sections(doc, options, record):
    pattern = re.compile(r"^\s*(?:" + "|".join(options.skip_titles) + r")\s*$", re.IGNORECASE)
    for section in doc.sections:
        if section.title and pattern.match(section.title):
            record("front_back_section", section, section.text)
            section.text = ""


def _drop_extra_patterns(doc, options, record):
    for raw in options.extra_patterns:
        pattern = re.compile(raw, re.IGNORECASE)
        for section in doc.sections:
            for match in pattern.finditer(section.text):
                record("extra_pattern", section, match.group())
            section.text = pattern.sub("", section.text)


def _drop_page_numbers_and_repeated_lines(doc, options, record):
    counts = Counter(
        key for section in doc.sections for line in section.text.split("\n")
        if (key := _repeat_key(line, options))
    )
    repeated = {key for key, n in counts.items() if n >= options.repeat_min}

    for section in doc.sections:
        kept = []
        for line in section.text.split("\n"):
            if PAGE_NUMBER.match(line):
                record("page_number", section, line)
            elif _repeat_key(line, options) in repeated:
                record("repeated_line", section, line)
            else:
                kept.append(line)
        section.text = "\n".join(kept)


def _repeat_key(line: str, options) -> str | None:
    """Normalised form of a line that could be a running header or watermark, else None.
    Sentence-like lines, dialogue and chapter headings never qualify."""
    stripped = line.strip()
    if not stripped or len(stripped) > options.repeat_max_chars:
        return None
    if SENTENCE_END.search(stripped):
        return None  # ends like a sentence or a line of dialogue
    if HEADING.match(stripped) or not WORD.search(stripped):
        return None
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", stripped.lower()))


def _drop_edge_notices(doc, options, record):
    """Scan inward from each end of the book, removing notice paragraphs, and stop at the
    first run of ordinary prose (or at `edge_fraction` of the book). Front and back matter
    is a contiguous block, so nothing past the first real prose is ever touched."""
    cue_re = re.compile("|".join(options.notice_cues), re.IGNORECASE)
    paragraphs = [
        [i, part] for i, section in enumerate(doc.sections)
        for part in re.split(r"(\n\s*\n)", section.text)
    ]
    total = _count_words(doc.text)
    if not total:
        return

    def scan(indices, stop_at_heading):
        seen_words, prose_run = 0, 0
        for idx in indices:
            section_idx, paragraph = paragraphs[idx]
            n_words = _count_words(paragraph)
            if not n_words:
                continue
            if seen_words > total * options.edge_fraction or prose_run >= options.prose_run_stop:
                return
            if stop_at_heading and HEADING.match(paragraph.strip()):
                return  # the book proper has started
            seen_words += n_words
            if _is_notice(paragraph, n_words, cue_re, options):
                record("notice", doc.sections[section_idx], paragraph)
                paragraphs[idx][1] = ""
                prose_run = 0
            elif n_words >= options.prose_min_words:
                prose_run += 1

    scan(range(len(paragraphs)), stop_at_heading=True)
    scan(reversed(range(len(paragraphs))), stop_at_heading=False)

    for section in doc.sections:
        section.text = ""
    for section_idx, paragraph in paragraphs:
        doc.sections[section_idx].text += paragraph


def _is_notice(paragraph: str, n_words: int, cue_re, options) -> bool:
    cues = len(cue_re.findall(paragraph))
    if cues >= options.notice_min_cues:
        return True
    # A single cue only counts in a short paragraph that isn't dialogue.
    return cues == 1 and n_words < options.notice_short_words and not QUOTE.search(paragraph)


def _count_words(text: str) -> int:
    return len(WORD.findall(text))
