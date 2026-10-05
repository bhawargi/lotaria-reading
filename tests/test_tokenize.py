import pytest

from helpers import make_doc
from wfa import tokenize as tokenize_module
from wfa.tokenize import TokenizeOptions, tokenize

SAMPLE = (
    "\"Don't go,\" she said. It's Lincoln's well-known house, isn't it? "
    "They'd seen 12 men... I'm tired.\n\nA mother-in-law's view. The cats' toys. pre-"
)


def tokens(text, **options):
    return tokenize(make_doc(text), TokenizeOptions(**options)).tokens


def test_contractions_and_compounds_stay_whole():
    result = tokens(SAMPLE)
    for word in ["don't", "it's", "isn't", "they'd", "i'm", "well-known", "mother-in-law"]:
        assert word in result
    assert "n't" not in result and "-" not in result


def test_possessives_are_dropped_but_s_contractions_kept():
    result = tokens(SAMPLE)
    assert "lincoln" in result and "lincoln's" not in result
    assert "cats" in result
    assert "it's" in result
    assert "lincoln's" in tokens(SAMPLE, split_possessive=False)


def test_numbers_punctuation_and_stray_hyphens():
    result = tokens(SAMPLE)
    assert "12" not in result
    assert not any(t in result for t in ['"', ",", ".", "...", "?"])
    assert "pre" in result
    assert "12" in tokens(SAMPLE, drop_numbers=False)


def test_lowercase_option():
    assert "Lincoln" in tokens(SAMPLE, lowercase=False)
    assert "Lincoln" not in tokens(SAMPLE)


def test_stopwords_including_contractions():
    result = tokens(SAMPLE, stopwords=True)
    assert not {"she", "it", "don't", "it's", "isn't", "i'm"} & set(result)
    assert {"lincoln", "well-known", "house", "mother-in-law"} <= set(result)


def test_min_length():
    assert all(len(t) >= 4 for t in tokens(SAMPLE, min_length=4))


def test_dropped_counts_are_reported():
    doc = tokenize(make_doc(SAMPLE), TokenizeOptions(stopwords=True))
    dropped = doc.stats["tokenize"]["dropped"]
    assert dropped["stopwords"] > 0 and dropped["numbers"] == 1 and dropped["punct"] > 0
    assert doc.stats["tokenize"]["tokens"] == len(doc.tokens)


def test_lemmas():
    doc = tokenize(make_doc("The children were running and the men said nothing."), TokenizeOptions(lemmatize=True))
    assert doc.lemmas is not None and len(doc.lemmas) == len(doc.tokens)
    assert {"child", "run", "man", "say"} <= set(doc.lemmas)
    assert tokenize(make_doc("The children ran."), TokenizeOptions()).lemmas is None


def test_long_text_is_chunked_without_changing_tokens(monkeypatch):
    text = "\n\n".join(["The quick brown fox jumps over the lazy dog."] * 50)
    expected = tokens(text)
    monkeypatch.setattr(tokenize_module, "CHUNK_CHARS", 120)
    assert tokens(text) == expected


@pytest.mark.parametrize("text", ["", "   \n\n  ", "... --- !!!"])
def test_empty_or_wordless_text(text):
    assert tokens(text) == []
