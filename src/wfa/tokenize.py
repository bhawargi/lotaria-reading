"""Split normalised text into word tokens with spaCy (English only).

spaCy splits contractions ("do" + "n't") and hyphenated words ("well" "-" "known");
we join those pieces back when they were written as one word, so frequencies count
words as a reader sees them. Possessive "'s" is dropped by default ("Lincoln's" ->
"lincoln"), while contractions like "it's" are kept whole.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import spacy
from spacy.language import Language
from spacy.tokens import Token

from wfa.document import Document

MODEL = "en_core_web_sm"
CHUNK_CHARS = 100_000  # stay well under spaCy's max_length; chunks split at paragraph breaks

CONTRACTION_SUFFIXES = {"n't", "'s", "'re", "'ve", "'ll", "'d", "'m", "'"}
# Words where a following "'s" means "is/has/us", not possession.
S_CONTRACTION_BASES = {
    "it", "he", "she", "that", "there", "here", "what", "who", "where", "when", "how",
    "let", "this", "everyone", "everybody", "nobody", "somebody", "someone", "one",
}
HAS_DIGIT = re.compile(r"\d")
HAS_LETTER = re.compile(r"[^\W\d_]")


@dataclass
class TokenizeOptions:
    lowercase: bool = True
    stopwords: bool = False         # remove English stop words
    lemmatize: bool = False         # also produce lemmas (loads the full spaCy model)
    drop_numbers: bool = True       # tokens containing digits
    drop_punct: bool = True         # tokens with no letters
    split_possessive: bool = True   # "lincoln's" -> "lincoln"
    min_length: int = 1


def tokenize(doc: Document, options: TokenizeOptions | None = None) -> Document:
    options = options or TokenizeOptions()
    nlp = _pipeline(options.lemmatize)
    stop_words = nlp.Defaults.stop_words

    tokens: list[str] = []
    lemmas: list[str] = []
    dropped = {"stopwords": 0, "numbers": 0, "punct": 0, "short": 0}

    section_starts = [0] * len(doc.sections)  # token index where each section begins
    seen_sections: set[int] = set()
    for spacy_doc, section_idx in nlp.pipe(_chunks(doc), batch_size=8, as_tuples=True):
        if section_idx not in seen_sections:
            seen_sections.add(section_idx)
            section_starts[section_idx] = len(tokens)
        for word, lemma, pieces in _words(spacy_doc, options):
            reason = _drop_reason(word, pieces, stop_words, options)
            if reason:
                dropped[reason] += 1
                continue
            tokens.append(word.lower() if options.lowercase else word)
            lemmas.append(lemma.lower() if options.lowercase else lemma)

    doc.tokens = tokens
    doc.lemmas = lemmas if options.lemmatize else None
    doc.stats["tokenize"] = {
        "tokens": len(tokens),
        "unique": len(set(tokens)),
        "unique_lemmas": len(set(lemmas)) if options.lemmatize else None,
        "dropped": dropped,
        "section_starts": _fill_gaps(section_starts, seen_sections),
    }
    return doc


def _fill_gaps(starts: list[int], seen: set[int]) -> list[int]:
    """Sections that produced no chunk start where the next one does (or at the end)."""
    filled = list(starts)
    for i in reversed(range(len(filled))):
        if i not in seen:
            filled[i] = filled[i + 1] if i + 1 < len(filled) else (max(starts) if starts else 0)
    return filled


@lru_cache(maxsize=2)
def _pipeline(lemmatize: bool) -> Language:
    if not lemmatize:
        return spacy.blank("en")  # tokenizer + lexical attributes only: fast
    # The lemmatizer needs part-of-speech tags; parser and NER are not needed.
    return spacy.load(MODEL, disable=["parser", "ner"])


def _chunks(doc: Document):
    """Yield (text, section index) pieces under CHUNK_CHARS, never splitting a paragraph
    unless it alone is too long."""
    for index, section in enumerate(doc.sections):
        buffer: list[str] = []
        size = 0
        for paragraph in section.text.split("\n\n"):
            if size + len(paragraph) > CHUNK_CHARS and buffer:
                yield "\n\n".join(buffer), index
                buffer, size = [], 0
            while len(paragraph) > CHUNK_CHARS:
                cut = paragraph.rfind(" ", 0, CHUNK_CHARS)
                cut = cut if cut > 0 else CHUNK_CHARS
                yield paragraph[:cut], index
                paragraph = paragraph[cut:]
            buffer.append(paragraph)
            size += len(paragraph) + 2
        if buffer:
            yield "\n\n".join(buffer), index


def _words(spacy_doc, options: TokenizeOptions):
    """Yield (word, lemma) pairs, re-joining pieces spaCy split out of one written word."""
    group: list[Token] = []
    for token in spacy_doc:
        if token.is_space:
            if group:
                yield _join(group, options)
            group = []
            continue
        if group and _attaches(group[-1], token):
            group.append(token)
        else:
            if group:
                yield _join(group, options)
            group = [token]
    if group:
        yield _join(group, options)


def _attaches(prev: Token, token: Token) -> bool:
    if prev.whitespace_:
        return False
    text = token.text.lower()
    if text in CONTRACTION_SUFFIXES and HAS_LETTER.search(prev.text):
        return True
    # well-known, mother-in-law: a hyphen between two letter-bearing pieces.
    if token.text == "-" and HAS_LETTER.search(prev.text):
        return True
    return prev.text == "-" and HAS_LETTER.search(token.text) is not None


def _join(group: list[Token], options: TokenizeOptions) -> tuple[str, str, list[str]]:
    """Return (word, lemma, piece texts) for a group of spaCy tokens forming one written word."""
    while len(group) > 1 and group[-1].text == "-":
        group = group[:-1]

    if len(group) >= 2 and group[-1].text.lower() in ("'s", "'") and options.split_possessive:
        if len(group) > 2 or group[0].text.lower() not in S_CONTRACTION_BASES:
            group = group[:-1]

    pieces = [t.text for t in group]
    if len(group) == 1:
        token = group[0]
        lemma = token.lemma_ if options.lemmatize and token.lemma_ else token.text
        return token.text.strip("-"), lemma.strip("-"), pieces

    word = "".join(pieces).strip("-")
    return word, word, pieces  # contractions and compounds are their own lemma


def _drop_reason(word: str, pieces: list[str], stop_words: set[str], options: TokenizeOptions) -> str | None:
    if HAS_DIGIT.search(word):
        if options.drop_numbers:
            return "numbers"
    elif options.drop_punct and not HAS_LETTER.search(word):
        return "punct"
    if options.stopwords and (
        word.lower() in stop_words or all(p.lower() in stop_words for p in pieces if p != "-")
    ):
        return "stopwords"  # "don't" = "do" + "n't", both stop words
    if len(word) < options.min_length:
        return "short"
    return None
