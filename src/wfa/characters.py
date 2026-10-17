"""Characters: people named in the book (spaCy entity recognition, run locally) and which of
them appear together.

Runs on the cleaned text with its original capitalisation. The small spaCy model often tags
character names as organisations or places ("Bingley" -> ORG), so such entities are reclaimed
when they start with a personal title ("Mrs Bennet") or match a name already found as a person.
Names are tidied (possessive 's and
titles like "Mr" removed) and a short form ("Darcy") is merged into the single fuller name that
contains it ("Fitzwilliam Darcy"); when a short form fits several full names ("Bennet" for
Elizabeth and Jane Bennet), it stays on its own. Two characters "appear together" when both are
named in the same paragraph. Results are cached on disk per text, model and code version.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from functools import lru_cache
from importlib import metadata
from pathlib import Path

import spacy

from wfa.document import Document

MODEL = "en_core_web_sm"
CACHE_DIR = Path(".cache") / "characters"
CHUNK_CHARS = 100_000
TOP_N = 15
MIN_MENTIONS = 2

TITLES = {
    "mr",
    "mrs",
    "ms",
    "miss",
    "mister",
    "madam",
    "madame",
    "dr",
    "doctor",
    "sir",
    "lady",
    "lord",
    "dame",
    "captain",
    "capt",
    "colonel",
    "col",
    "general",
    "major",
    "lieutenant",
    "professor",
    "prof",
    "rev",
    "reverend",
    "father",
    "mother",
    "brother",
    "sister",
    "uncle",
    "aunt",
    "king",
    "queen",
    "prince",
    "princess",
    "duke",
    "duchess",
    "count",
    "countess",
    "baron",
    "saint",
    "st",
}

PARTICLES = {"de", "da", "di", "du", "del", "della", "van", "von", "der", "den", "la", "le", "of", "y"}
RECLAIMABLE_LABELS = {"ORG", "GPE", "NORP", "FAC", "LOC", "PRODUCT", "WORK_OF_ART"}


@dataclass
class Character:
    name: str
    mentions: int
    aliases: list[str]  # other forms merged into this character


@dataclass
class CharacterResult:
    characters: list[Character]  # most mentioned first, at most TOP_N
    together: list[list[int]]  # together[i][j]: paragraphs naming both i and j (i != j)
    paragraphs: int


def find_characters(doc: Document, use_cache: bool = True, cache_dir: Path = CACHE_DIR) -> CharacterResult:
    key = _cache_key(doc)
    if use_cache and (cached := _load(key, cache_dir)):
        return cached

    paragraphs = [p for section in doc.sections for p in section.text.split("\n\n") if p.strip()]
    mentions: Counter[str] = Counter()
    per_paragraph: list[set[str]] = [set() for _ in paragraphs]
    maybe: list[tuple[int, str, bool]] = []  # (paragraph, name, starts with a title) from non-PERSON labels
    nlp = _pipeline()
    for spacy_doc, index in nlp.pipe(_pieces(paragraphs), batch_size=64, as_tuples=True):
        for ent in spacy_doc.ents:
            name = clean_name(ent.text)
            if not name:
                continue
            if ent.label_ == "PERSON":
                mentions[name] += 1
                per_paragraph[index].add(name)
            elif ent.label_ in RECLAIMABLE_LABELS:
                maybe.append((index, name, _has_title(ent.text)))

    person_words = {w for name in mentions for w in name.split()}
    for index, name, titled in maybe:
        if titled or name in mentions or all(w in person_words for w in name.split()):
            mentions[name] += 1
            per_paragraph[index].add(name)

    canonical = merge_aliases(mentions)
    totals: Counter[str] = Counter()
    aliases: dict[str, set[str]] = defaultdict(set)
    for name, n in mentions.items():
        totals[canonical[name]] += n
        if name != canonical[name]:
            aliases[canonical[name]].add(name)

    top = [name for name, n in totals.most_common(TOP_N) if n >= MIN_MENTIONS]
    position = {name: i for i, name in enumerate(top)}
    together = [[0] * len(top) for _ in top]
    for names in per_paragraph:
        present = sorted({position[canonical[n]] for n in names if canonical[n] in position})
        for a_i, a in enumerate(present):
            for b in present[a_i + 1 :]:
                together[a][b] += 1
                together[b][a] += 1

    result = CharacterResult(
        characters=[Character(name, totals[name], sorted(aliases[name])) for name in top],
        together=together,
        paragraphs=len(paragraphs),
    )
    if use_cache:
        _save(key, result, cache_dir)
    return result


def cached_result(doc: Document, cache_dir: Path = CACHE_DIR) -> CharacterResult | None:
    """The saved result for this text, without running the model."""
    return _load(_cache_key(doc), cache_dir)


def clean_name(text: str) -> str | None:
    """'Mr. Darcy's' -> 'Darcy'. None for things that don't look like a name."""
    text = re.sub(r"['’]s?$", "", text.strip())
    words = [w for w in re.split(r"\s+", text) if w]
    while words and words[0].lower().rstrip(".") in TITLES:
        words = words[1:]
    words = [w.strip(".,;:!?\"'()[]") for w in words]
    words = [w.capitalize() if w.isupper() and len(w) > 1 else w for w in words if w]  # ELIZABETH -> Elizabeth
    if not words or len(words) > 5:
        return None
    for i, w in enumerate(words):
        if 0 < i < len(words) - 1 and w.lower() in PARTICLES:
            continue  # "Catherine de Bourgh", "Ludwig van Beethoven"
        if not re.match(r"^[A-Z][\w'-]*$", w):
            return None  # every other part capitalised, letters only
    return " ".join(words)


def _has_title(text: str) -> bool:
    first = text.strip().split()[0].lower().rstrip(".") if text.strip() else ""
    return first in TITLES


def merge_aliases(mentions: Counter[str]) -> dict[str, str]:
    """Map each name to its character: a one-word name joins the single multi-word name that
    contains it; otherwise it stands alone."""
    multi = [name for name in mentions if " " in name]
    canonical = {}
    for name in mentions:
        if " " in name:
            canonical[name] = name
            continue
        owners = [m for m in multi if name in m.split()]
        canonical[name] = owners[0] if len(owners) == 1 else name
    return canonical


@lru_cache(maxsize=1)
def _pipeline():
    return spacy.load(MODEL, disable=["tagger", "parser", "attribute_ruler", "lemmatizer"])


def _pieces(paragraphs: list[str]):
    for index, paragraph in enumerate(paragraphs):
        while len(paragraph) > CHUNK_CHARS:
            cut = paragraph.rfind(" ", 0, CHUNK_CHARS)
            cut = cut if cut > 0 else CHUNK_CHARS
            yield paragraph[:cut], index
            paragraph = paragraph[cut:]
        yield paragraph, index


# --- Cache ----------------------------------------------------------------


def _cache_key(doc: Document) -> str:
    digest = hashlib.sha256(doc.text.encode("utf-8"))
    digest.update(Path(__file__).read_bytes())
    with contextlib.suppress(metadata.PackageNotFoundError):
        digest.update(metadata.version(MODEL).encode())
    return digest.hexdigest()


def _load(key: str, cache_dir: Path) -> CharacterResult | None:
    path = cache_dir / f"{key}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["characters"] = [Character(**c) for c in data["characters"]]
        return CharacterResult(**data)
    except FileNotFoundError:
        return None
    except (ValueError, TypeError, KeyError):
        path.unlink(missing_ok=True)
        return None


def _save(key: str, result: CharacterResult, cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_dir / f"{key}.json.tmp"
    tmp.write_text(json.dumps(asdict(result)), encoding="utf-8")
    tmp.replace(cache_dir / f"{key}.json")
