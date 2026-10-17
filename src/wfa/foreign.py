"""Flag words from other languages in an English book (ennui, sotto voce, schadenfreude…).

Processing stays English-only; this only marks words in the results. A word is flagged when,
per the `wordfreq` word lists, it is uncommon in English but clearly more common in one of a
few other languages. Words the book mostly writes capitalised are treated as names and skipped.
`wordfreq` has no Latin list, so Latin phrases are only caught when they double as Italian.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from wordfreq import zipf_frequency

from wfa import analysis
from wfa.document import Document

LANGUAGES = {"fr": "French", "de": "German", "it": "Italian", "es": "Spanish", "pt": "Portuguese", "nl": "Dutch"}

# Zipf scale: 3 ≈ once per million words, 6 ≈ once per thousand.
MAX_ENGLISH_ZIPF = 4.0   # common English words are never flagged ("ad", "house")
MIN_OTHER_ZIPF = 3.0     # the word must be reasonably common in the other language
MIN_MARGIN = 1.0         # ...and at least 10x more common there than in English
MIN_LENGTH = 3
MAX_CAPITALISED_SHARE = 0.5
CANDIDATE_LIMIT = 5000   # only the most frequent words are checked, for speed

WORD = re.compile(r"[^\W\d_]+(?:['-][^\W\d_]+)*")
SENTENCE_START_CHARS = set(".!?:;\"'")


@dataclass(frozen=True)
class ForeignWord:
    word: str
    count: int
    language: str        # e.g. "French"
    english_zipf: float
    other_zipf: float


def foreign_words(doc: Document) -> list[ForeignWord]:
    capitalised = _capitalised_share(doc)
    found = []
    for row in analysis.frequency_table(doc, limit=CANDIDATE_LIMIT):
        word = row.word.lower()
        if len(word) < MIN_LENGTH or not word.isalpha():
            continue
        if capitalised.get(word, 0.0) > MAX_CAPITALISED_SHARE:
            continue  # mostly written with a capital: a name
        english = zipf_frequency(word, "en")
        if english > MAX_ENGLISH_ZIPF:
            continue
        code, other = max(((c, zipf_frequency(word, c)) for c in LANGUAGES), key=lambda x: x[1])
        if other >= MIN_OTHER_ZIPF and other - english >= MIN_MARGIN:
            found.append(ForeignWord(row.word, row.count, LANGUAGES[code], round(english, 2), round(other, 2)))
    return found


def _capitalised_share(doc: Document) -> dict[str, float]:
    """For each word, the share of its occurrences that start with a capital letter, ignoring
    positions where any word is capitalised anyway (line starts, after . ! ? or an opening quote)."""
    total: Counter[str] = Counter()
    upper: Counter[str] = Counter()
    for section in doc.sections:
        for line in section.text.split("\n"):
            for match in WORD.finditer(line):
                j = match.start() - 1
                while j >= 0 and line[j].isspace():
                    j -= 1
                if j < 0 or line[j] in SENTENCE_START_CHARS:
                    continue
                word = match.group()
                key = word.lower()
                total[key] += 1
                if word[0].isupper():
                    upper[key] += 1
    return {w: upper[w] / n for w, n in total.items()}
