import pytest

from helpers import GUTENBERG, prose
from wfa import cache
from wfa.pipeline import PreprocessOptions, preprocess
from wfa.tokenize import TokenizeOptions


@pytest.fixture
def book(tmp_path):
    path = tmp_path / "book.txt"
    path.write_text(GUTENBERG.format(body=prose(10)), encoding="utf-8")
    return path


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "cache"


def test_end_to_end(book, cache_dir):
    doc = preprocess(book, cache_dir=cache_dir)
    assert doc.metadata.title == "A Test Book Being a Long Subtitle"
    assert "gutenberg" not in doc.tokens and "license" not in doc.tokens
    assert doc.tokens.count("rain") == 10
    assert set(doc.stats["timing_seconds"]) == {"load", "clean", "normalize", "tokenize"}
    assert doc.stats["from_cache"] is False


def test_second_run_comes_from_cache(book, cache_dir):
    first = preprocess(book, cache_dir=cache_dir)
    second = preprocess(book, cache_dir=cache_dir)
    assert second.stats["from_cache"] is True
    assert second.tokens == first.tokens and second.metadata == first.metadata


def test_different_options_are_cached_separately(book, cache_dir):
    preprocess(book, cache_dir=cache_dir)
    other = preprocess(book, PreprocessOptions(tokenize=TokenizeOptions(stopwords=True)), cache_dir=cache_dir)
    assert other.stats["from_cache"] is False
    assert len(list(cache_dir.glob("*.json.gz"))) == 2


def test_changed_file_is_reprocessed(book, cache_dir):
    preprocess(book, cache_dir=cache_dir)
    book.write_text(GUTENBERG.format(body=prose(3)), encoding="utf-8")
    doc = preprocess(book, cache_dir=cache_dir)
    assert doc.stats["from_cache"] is False
    assert doc.tokens.count("rain") == 3


def test_renamed_copy_hits_cache_with_its_own_path(book, cache_dir, tmp_path):
    preprocess(book, cache_dir=cache_dir)
    copy = tmp_path / "renamed.txt"
    copy.write_bytes(book.read_bytes())
    doc = preprocess(copy, cache_dir=cache_dir)
    assert doc.stats["from_cache"] is True
    assert doc.path == str(copy)


def test_corrupt_cache_entry_is_recomputed(book, cache_dir):
    preprocess(book, cache_dir=cache_dir)
    (entry,) = cache_dir.glob("*.json.gz")
    entry.write_bytes(b"not gzip")
    doc = preprocess(book, cache_dir=cache_dir)
    assert doc.stats["from_cache"] is False
    assert preprocess(book, cache_dir=cache_dir).stats["from_cache"] is True


def test_use_cache_false_neither_reads_nor_writes(book, cache_dir):
    preprocess(book, use_cache=False, cache_dir=cache_dir)
    assert not cache_dir.exists()


def test_clear_cache(book, cache_dir):
    preprocess(book, cache_dir=cache_dir)
    cache.clear_cache(cache_dir)
    assert not cache_dir.exists()
