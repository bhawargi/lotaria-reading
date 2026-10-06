"""Pure analysis over a preprocessed Document: counts, rankings, lookups, summary statistics.
No I/O and no UI, so the CLI, the app and later phases all share it."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from wfa.document import Document


@dataclass(frozen=True)
class WordRow:
    rank: int
    word: str
    count: int
    per10k: float  # occurrences per 10,000 words, comparable across books of any length


@dataclass(frozen=True)
class BookStats:
    words: int             # tokens after filtering
    unique: int
    richness: float        # unique / words (type-token ratio); falls as books get longer
    hapax: int             # words used exactly once
    mean_word_length: float
    sections: int
    removed_share: float   # share of the raw text the cleaner removed


def words(doc: Document, use_lemmas: bool = False) -> list[str]:
    return doc.lemmas if use_lemmas and doc.lemmas is not None else doc.tokens


def counts(doc: Document, use_lemmas: bool = False) -> Counter[str]:
    return Counter(words(doc, use_lemmas))


def frequency_table(doc: Document, use_lemmas: bool = False, limit: int | None = None) -> list[WordRow]:
    """All words ranked by count (ties broken alphabetically, so the order is stable)."""
    counter = counts(doc, use_lemmas)
    total = sum(counter.values()) or 1
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    if limit is not None:
        ranked = ranked[:limit]
    return [WordRow(i, w, n, round(n * 10_000 / total, 2)) for i, (w, n) in enumerate(ranked, start=1)]


def lookup(table: list[WordRow], query: str, limit: int = 50) -> tuple[WordRow | None, list[WordRow]]:
    """(exact match, other words containing the query), searching case-insensitively."""
    query = query.strip().lower()
    if not query:
        return None, []
    exact = next((row for row in table if row.word.lower() == query), None)
    partial = [row for row in table if query in row.word.lower() and row is not exact]
    return exact, partial[:limit]


def book_stats(doc: Document, use_lemmas: bool = False) -> BookStats:
    counter = counts(doc, use_lemmas)
    total = sum(counter.values())
    cleaning = doc.stats.get("cleaning", {})
    before = cleaning.get("words_before", 0)
    after = cleaning.get("words_after", 0)
    return BookStats(
        words=total,
        unique=len(counter),
        richness=len(counter) / total if total else 0.0,
        hapax=sum(1 for n in counter.values() if n == 1),
        mean_word_length=sum(len(w) * n for w, n in counter.items()) / total if total else 0.0,
        sections=len(doc.sections),
        removed_share=(before - after) / before if before else 0.0,
    )
