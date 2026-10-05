"""Disk cache for preprocessed Documents.

The key covers everything that can change the output: the file's bytes, the options,
the versions of the libraries doing the work, and the source code of the wfa pipeline
modules themselves, so editing a rule invalidates old entries without a manual version bump.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from dataclasses import asdict
from functools import lru_cache
from importlib import metadata
from pathlib import Path

from wfa.document import Document

DEFAULT_DIR = Path(".cache") / "documents"
LIBRARIES = ["charset-normalizer", "ebooklib", "beautifulsoup4", "lxml", "ftfy", "textacy", "spacy"]
MODEL_PACKAGE = "en_core_web_sm"
PIPELINE_MODULES = ["document", "loaders", "cleaning", "normalize", "tokenize", "pipeline"]


def file_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def cache_key(content_hash: str, options) -> str:
    payload = {
        "file": content_hash,
        "options": asdict(options),
        "libraries": _library_versions(include_model=options.tokenize.lemmatize),
        "code": _code_hash(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def load_cached(key: str, cache_dir: Path = DEFAULT_DIR) -> Document | None:
    path = cache_dir / f"{key}.json.gz"
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return Document.from_dict(json.load(f))
    except (OSError, ValueError, TypeError, KeyError):
        path.unlink(missing_ok=True)  # corrupt or from an incompatible version: recompute
        return None


def save_cached(key: str, doc: Document, cache_dir: Path = DEFAULT_DIR) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_dir / f"{key}.json.gz.tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f)
    tmp.replace(cache_dir / f"{key}.json.gz")


def clear_cache(cache_dir: Path = DEFAULT_DIR) -> None:
    shutil.rmtree(cache_dir, ignore_errors=True)


@lru_cache(maxsize=2)
def _library_versions(include_model: bool) -> dict[str, str | None]:
    names = LIBRARIES + ([MODEL_PACKAGE] if include_model else [])
    versions = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


@lru_cache(maxsize=1)
def _code_hash() -> str:
    digest = hashlib.sha256()
    package_dir = Path(__file__).parent
    for module in PIPELINE_MODULES:
        digest.update((package_dir / f"{module}.py").read_bytes())
    return digest.hexdigest()
