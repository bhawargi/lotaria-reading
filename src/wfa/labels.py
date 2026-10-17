"""Published labels for a book from the Google Books API: categories, description, rating.

Only the title and author (as typed or confirmed by the user) are sent to Google; nothing
from the book's text. Results are cached on disk per query. An API key is read from the
GOOGLE_BOOKS_API_KEY environment variable; without one, requests use Google's shared
anonymous quota, which is often exhausted.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

API_URL = "https://www.googleapis.com/books/v1/volumes"
CACHE_DIR = Path(".cache") / "labels"
MAX_RESULTS = 10
MIN_TITLE_SIMILARITY = 0.6
MIN_AUTHOR_SIMILARITY = 0.5
RETRIES = 2  # extra attempts on a 5xx before moving on to the next query
RETRY_DELAY = 0.5  # seconds, growing per attempt
CACHE_VERSION = 2


class LabelError(RuntimeError):
    """Network failure, quota/key problem, or no match. Message is user-facing."""


class _Unavailable(LabelError):
    """Google answered with a server error even after retries; the next query may still work."""


@dataclass
class BookLabels:
    title: str
    authors: list[str]
    categories: list[str]  # e.g. ["Fiction / Science Fiction / General"], most editions first
    category_terms: list[str]  # the same, split into distinct terms: ["Fiction", "Science Fiction", ...]
    term_counts: dict[str, int]  # how many matching editions use each term
    description: str | None
    average_rating: float | None
    ratings_count: int | None
    published: str | None
    link: str | None
    thumbnail: str | None
    volumes_matched: int  # categories are pooled from this many matching editions
    source: str = "Google Books"
    fetched: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))


def search_terms(title: str | None, author: str | None) -> tuple[str, str]:
    """Tidy title/author for searching: filename-ish titles ('Flatland_-_Edwin_A_Abbott')
    become 'Flatland' and 'Edwin A Abbott' when no author is known."""
    title = re.sub(r"[_]+", " ", title or "").strip()
    author = (author or "").strip()
    if not author and " - " in title:
        title, author = (part.strip() for part in title.split(" - ", 1))
    title = re.sub(r"\s*[,:;(\[].*$", "", title).strip() or title  # drop subtitles for matching
    return title, author


def lookup(
    title: str, author: str = "", use_cache: bool = True, cache_dir: Path = CACHE_DIR, api_key: str | None = None
) -> BookLabels:
    title, author = title.strip(), author.strip()
    if not title:
        raise LabelError("Enter a title to look up.")

    key = _cache_key(title, author)
    if use_cache and (cached := _load(key, cache_dir)):
        return cached

    api_key = api_key or os.environ.get("GOOGLE_BOOKS_API_KEY")
    seen: list[str] = []
    unavailable = 0
    for query in _queries(title, author):  # strictest first; stop at the first that yields a match
        try:
            items = _request(query, api_key)
        except _Unavailable:
            unavailable += 1
            continue
        seen += [i.get("volumeInfo", {}).get("title", "?") for i in items]
        try:
            labels = _best_match(items, title, author)
            break
        except LabelError:
            continue
    else:
        who = f"“{title}”" + (f" by {author}" if author else "")
        if not seen and unavailable:
            raise LabelError("Google Books is having trouble right now (server errors). Try again in a minute.")
        if not seen:
            raise LabelError(f"Google Books returned no results for {who}.")
        sample = "; ".join(dict.fromkeys(seen))[:300]
        raise LabelError(f"Google Books returned results for {who}, but none matched the title. Saw: {sample}")
    if use_cache:
        _save(key, labels, cache_dir)
    return labels


def cached_lookup(title: str, author: str = "", cache_dir: Path = CACHE_DIR) -> BookLabels | None:
    return _load(_cache_key(title.strip(), author.strip()), cache_dir) if title.strip() else None


# --- API ------------------------------------------------------------------


def _queries(title: str, author: str) -> list[str]:
    """Search queries from strictest to loosest. Authors are matched by surname only, since
    catalogues spell full names inconsistently ("Edwin A. Abbott", "Edwin Abbott Abbott").
    Plain-text queries come last: Google's intitle:/inauthor: operators sometimes return
    nothing (or server errors) while plain searches work; _best_match filters the noise."""
    surname = re.sub(r"[^\w\s-]", "", author).split()[-1] if author.strip() else ""
    queries = []
    if surname:
        queries.append(f'intitle:"{title}" inauthor:{surname}')
    queries.append(f'intitle:"{title}"')
    queries.append(f"{title} {surname}".strip())
    queries.append(title)
    return list(dict.fromkeys(queries))


def _request(query: str, api_key: str | None) -> list[dict]:
    params = {"q": query, "maxResults": MAX_RESULTS, "printType": "books", "langRestrict": "en"}
    if api_key:
        params["key"] = api_key
    for attempt in range(RETRIES + 1):
        try:
            response = httpx.get(API_URL, params=params, timeout=15)
        except httpx.HTTPError as e:
            raise LabelError(f"Couldn't reach Google Books: {e}") from e
        if response.status_code < 500:
            break
        if attempt < RETRIES:
            time.sleep(RETRY_DELAY * (attempt + 1))
    else:
        raise _Unavailable(f"Google Books returned HTTP {response.status_code}.")

    if response.status_code == 429:
        raise LabelError(
            "Google Books refused the request (daily quota used up). "
            + (
                "Your API key's quota is exhausted; try again tomorrow."
                if api_key
                else "Requests without an API key share a public quota. Create a free key (Google Cloud "
                "Console → enable the Books API → Credentials → API key) and set GOOGLE_BOOKS_API_KEY."
            )
        )
    if response.status_code in (400, 403):
        raise LabelError(
            "Google Books rejected the request; check that GOOGLE_BOOKS_API_KEY is valid "
            "and the Books API is enabled for it."
        )
    if response.status_code != 200:
        raise LabelError(f"Google Books returned HTTP {response.status_code}.")
    return response.json().get("items", [])


def _best_match(items: list[dict], title: str, author: str) -> BookLabels:
    """Pick the closest edition by title (and author), then pool categories from every
    edition that matches as well, since editions are labelled inconsistently."""
    scored = []
    for item in items:
        info = item.get("volumeInfo", {})
        score = _title_score(title, info.get("title", ""), info.get("subtitle", ""))
        if author:
            author_score = _author_score(author, info.get("authors", []))
            if info.get("authors") and author_score < MIN_AUTHOR_SIMILARITY:
                continue  # same title, different author: another book
            score = 0.7 * score + 0.3 * author_score
        scored.append((score, info))
    matches = [(s, info) for s, info in sorted(scored, key=lambda x: -x[0]) if s >= MIN_TITLE_SIMILARITY]
    if not matches:
        raise LabelError(f"No Google Books match for “{title}”" + (f" by {author}" if author else "") + ".")

    best = matches[0][1]
    category_counts: Counter[str] = Counter()
    term_counts: Counter[str] = Counter()
    rated = None
    for _, info in matches:
        editions_categories = info.get("categories", [])
        category_counts.update(set(editions_categories))
        term_counts.update(set(_split_categories(editions_categories)))
        if rated is None and info.get("ratingsCount"):
            rated = info
    categories = [c for c, _ in category_counts.most_common()]  # ties keep first-seen order
    terms = [t for t, _ in term_counts.most_common()]

    links = best.get("imageLinks", {})
    return BookLabels(
        title=best.get("title", title),
        authors=best.get("authors", []),
        categories=categories,
        category_terms=terms,
        term_counts=dict(term_counts),
        description=_strip_html(best.get("description")),
        average_rating=(rated or best).get("averageRating"),
        ratings_count=(rated or best).get("ratingsCount"),
        published=best.get("publishedDate"),
        link=best.get("infoLink") or best.get("canonicalVolumeLink"),
        thumbnail=(links.get("thumbnail") or links.get("smallThumbnail") or "").replace("http://", "https://") or None,
        volumes_matched=len(matches),
    )


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _title_score(wanted: str, title: str, subtitle: str = "") -> float:
    """Best of: whole title, main title (before ':'), title + subtitle. A main title that
    contains every wanted word (and little else) counts as a full match."""
    main = re.split(r"\s*[:;(\[]", title, maxsplit=1)[0]
    score = max(_similarity(wanted, t) for t in (title, main, f"{title} {subtitle}".strip()))
    wanted_words, main_words = set(_norm(wanted).split()), _norm(main).split()
    if wanted_words and wanted_words <= set(main_words) and len(main_words) <= len(wanted_words) + 2:
        score = 1.0
    return score


def _author_score(wanted: str, authors: list[str]) -> float:
    """Surname match counts fully; otherwise fuzzy similarity to the closest listed author."""
    surname = _norm(wanted).split()[-1] if _norm(wanted) else ""
    best = 0.0
    for author in authors:
        if surname and surname in _norm(author).split():
            return 1.0
        best = max(best, _similarity(wanted, author))
    return best


def _split_categories(categories: list[str]) -> list[str]:
    terms: list[str] = []
    for category in categories:
        for part in category.split("/"):
            part = part.strip()
            if part and part.lower() != "general" and part.lower() not in (t.lower() for t in terms):
                terms.append(part)
    return terms


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+([.,;:!?])", r"\1", text).strip()


# --- Cache ----------------------------------------------------------------


def _cache_key(title: str, author: str) -> str:
    payload = json.dumps({"title": title.lower(), "author": author.lower(), "v": CACHE_VERSION}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _load(key: str, cache_dir: Path) -> BookLabels | None:
    path = cache_dir / f"{key}.json"
    try:
        return BookLabels(**json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return None
    except (ValueError, TypeError):
        path.unlink(missing_ok=True)
        return None


def _save(key: str, labels: BookLabels, cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_dir / f"{key}.json.tmp"
    tmp.write_text(json.dumps(asdict(labels)), encoding="utf-8")
    tmp.replace(cache_dir / f"{key}.json")
