"""One entry point for preprocessing: file -> clean, tokenised, cached Document."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from wfa import cache
from wfa.cleaning import CleaningOptions, clean
from wfa.document import Document
from wfa.loaders import load
from wfa.normalize import NormalizeOptions, normalize
from wfa.tokenize import TokenizeOptions, tokenize


@dataclass
class PreprocessOptions:
    cleaning: CleaningOptions = field(default_factory=CleaningOptions)
    normalize: NormalizeOptions = field(default_factory=NormalizeOptions)
    tokenize: TokenizeOptions = field(default_factory=TokenizeOptions)


def preprocess(
    path: str | Path,
    options: PreprocessOptions | None = None,
    use_cache: bool = True,
    cache_dir: Path = cache.DEFAULT_DIR,
) -> Document:
    """Load, clean, normalise and tokenise a book. Results are cached on disk; the
    returned Document's `stats["from_cache"]` says whether this call reused one."""
    options = options or PreprocessOptions()
    key = cache.cache_key(cache.file_hash(path), options)

    if use_cache and (doc := cache.load_cached(key, cache_dir)):
        doc.path = str(path)  # same content may have been cached under another name
        doc.stats["from_cache"] = True
        return doc

    timings = {}
    clock = time.perf_counter()

    def lap(name: str) -> None:
        nonlocal clock
        now = time.perf_counter()
        timings[name] = round(now - clock, 3)
        clock = now

    doc = load(path)
    lap("load")
    clean(doc, options.cleaning)
    lap("clean")
    normalize(doc, options.normalize)
    lap("normalize")
    tokenize(doc, options.tokenize)
    lap("tokenize")

    doc.stats["timing_seconds"] = timings
    doc.stats["from_cache"] = False
    if use_cache:
        cache.save_cached(key, doc, cache_dir)
    return doc
