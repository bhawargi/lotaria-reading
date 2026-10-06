"""Infer a book's themes from its word frequencies alone, using an external LLM.

This is Lotaria's "electronic reading". The model only ever receives (word, count) pairs:
`top_words()` is the single place a Document is read, and everything that talks to a
provider accepts word/count pairs only, checked by `_validate_words()`. So no title,
author or book text can reach a model, by construction.

Every call returns both a short summary (at most three sentences) and a list of theme
words. The instructions themselves live in `wfa.prompts`, away from the UI.

Providers are pluggable; the first backend is a local Ollama server, so nothing leaves
the machine. Results are cached on disk per (words, provider, model, prompt version).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from spacy.lang.en.stop_words import STOP_WORDS

from wfa import analysis, prompts
from wfa.document import Document

CACHE_DIR = Path(".cache") / "themes"
DEFAULT_TOP_WORDS = 100
MAX_WORDS = 500          # hard ceiling on what any call can send
MAX_WORD_LENGTH = 40     # a "word" longer than this isn't a word

WordCounts = list[tuple[str, int]]


class ThemeError(RuntimeError):
    """Provider unreachable, model missing, or an unusable response. Message is user-facing."""


@dataclass
class ThemeResult:
    summary: str
    themes: list[str]
    provider: str
    model: str
    words_sent: int
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


class Provider(Protocol):
    name: str

    def available_models(self) -> list[str]: ...

    def complete_json(self, model: str, system: str, prompt: str, schema: dict) -> str: ...


# --- Providers ------------------------------------------------------------


class OllamaProvider:
    """Local Ollama server (https://ollama.com). Host from OLLAMA_HOST, default localhost:11434."""

    name = "ollama"

    def __init__(self, host: str | None = None, timeout: float = 300):
        import ollama  # imported here so other providers don't need the package

        self._ollama = ollama
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self._client = ollama.Client(host=self.host, timeout=timeout)

    def available_models(self) -> list[str]:
        try:
            return sorted(m.model for m in self._client.list().models)
        except Exception as e:  # connection refused, DNS, timeouts all surface differently
            raise ThemeError(
                f"Can't reach Ollama at {self.host}. Start it with `ollama serve` "
                "(or open the Ollama app), then pull a model, e.g. `ollama pull llama3.2`."
            ) from e

    def complete_json(self, model: str, system: str, prompt: str, schema: dict) -> str:
        try:
            response = self._client.chat(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                format=schema,
                options={"temperature": 0.2},
            )
        except self._ollama.ResponseError as e:
            if e.status_code == 404:
                raise ThemeError(f"Model `{model}` isn't installed. Run `ollama pull {model}`.") from e
            raise ThemeError(f"Ollama returned an error: {e.error}") from e
        except Exception as e:
            raise ThemeError(f"Can't reach Ollama at {self.host}: {e}") from e
        return response.message.content or ""


PROVIDERS: dict[str, type] = {"ollama": OllamaProvider}


def provider_name() -> str:
    return os.environ.get("WFA_LLM_PROVIDER", "ollama").lower()


def get_provider(name: str | None = None) -> Provider:
    name = (name or provider_name()).lower()
    if name not in PROVIDERS:
        raise ThemeError(f"Unknown LLM provider `{name}`. Available: {', '.join(PROVIDERS)}.")
    return PROVIDERS[name]()


# --- The only bridge from a book to the model -----------------------------


def top_words(doc: Document, n: int = DEFAULT_TOP_WORDS) -> WordCounts:
    """Most frequent content words and their counts. Stop words and contractions are always
    excluded here, whatever the app's stop-word toggle says."""
    rows = [
        row for row in analysis.frequency_table(doc)
        if row.word.lower() not in STOP_WORDS and "'" not in row.word
    ]
    return [(row.word, row.count) for row in rows[:min(n, MAX_WORDS)]]


def _validate_words(words: WordCounts) -> WordCounts:
    if not words:
        raise ThemeError("No content words to send; the book is empty after processing.")
    if len(words) > MAX_WORDS:
        raise ValueError(f"At most {MAX_WORDS} words may be sent, got {len(words)}.")
    for item in words:
        if not (isinstance(item, tuple) and len(item) == 2):
            raise ValueError("Only (word, count) pairs may be sent to a model.")
        word, count = item
        if not isinstance(word, str) or not isinstance(count, int):
            raise ValueError("Only (word, count) pairs may be sent to a model.")
        if not word or len(word) > MAX_WORD_LENGTH or any(ch.isspace() for ch in word):
            raise ValueError(f"Not a single word: {word[:60]!r}")
    return words


# --- Main entry points ----------------------------------------------------


def infer_themes(
    words: WordCounts,
    model: str,
    provider: Provider | None = None,
    use_cache: bool = True,
    refresh: bool = False,
    cache_dir: Path = CACHE_DIR,
) -> ThemeResult:
    """Ask the provider for themes from word/count pairs. `refresh` skips a cached answer
    but still saves the new one."""
    words = _validate_words(words)
    provider = provider or get_provider()

    key = _cache_key(provider.name, model, words)
    if use_cache and not refresh and (cached := _load(key, cache_dir)):
        return cached

    raw = provider.complete_json(
        model, prompts.THEMES_SYSTEM, prompts.themes_user_message(words), prompts.THEMES_SCHEMA
    )
    result = parse_response(raw, provider.name, model, len(words))
    if use_cache:
        _save(key, result, cache_dir)
    return result


def cached_result(words: WordCounts, model: str, provider: str | None = None,
                  cache_dir: Path = CACHE_DIR) -> ThemeResult | None:
    """The saved answer for these words and model, without calling the provider."""
    if not words:
        return None
    return _load(_cache_key((provider or provider_name()).lower(), model, _validate_words(words)), cache_dir)


def parse_response(raw: str, provider: str, model: str, words_sent: int) -> ThemeResult:
    try:
        data = json.loads(raw)
        summary, themes = data["summary"], data["themes"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ThemeError("The model's reply wasn't in the expected format. Try again or another model.") from e
    if not isinstance(summary, str) or not isinstance(themes, list):
        raise ThemeError("The model's reply wasn't in the expected format. Try again or another model.")
    return ThemeResult(
        summary=limit_sentences(summary.strip(), prompts.MAX_SENTENCES),
        themes=clean_themes(themes),
        provider=provider,
        model=model,
        words_sent=words_sent,
    )


def limit_sentences(text: str, n: int) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentences[:n]).strip()


def clean_themes(themes: list) -> list[str]:
    seen, cleaned = set(), []
    for theme in themes:
        if not isinstance(theme, str):
            continue
        theme = theme.strip().strip(".,;:").strip()
        if theme and theme.lower() not in seen:
            seen.add(theme.lower())
            cleaned.append(theme)
    return cleaned[:prompts.MAX_THEMES]


# --- Cache ----------------------------------------------------------------


def _cache_key(provider: str, model: str, words: WordCounts) -> str:
    payload = json.dumps(
        {"provider": provider, "model": model, "words": words, "prompt_version": prompts.VERSION},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _load(key: str, cache_dir: Path) -> ThemeResult | None:
    path = cache_dir / f"{key}.json"
    try:
        return ThemeResult(**json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return None
    except (ValueError, TypeError):
        path.unlink(missing_ok=True)
        return None


def _save(key: str, result: ThemeResult, cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_dir / f"{key}.json.tmp"
    tmp.write_text(json.dumps(asdict(result)), encoding="utf-8")
    tmp.replace(cache_dir / f"{key}.json")
