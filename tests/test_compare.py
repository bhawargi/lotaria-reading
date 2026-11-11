"""The Compare tab: each side shows its result, or a pointer to the tab that produces it."""

from streamlit.testing.v1 import AppTest

from wfa.labels import BookLabels
from wfa.themes import ThemeResult

READING = ThemeResult(
    summary="A voyage goes wrong.", themes=["ships", "memory"], provider="ollama", model="m", words_sent=100
)
PUBLISHED = BookLabels(
    title="A Book",
    authors=["An Author"],
    categories=["Fiction"],
    category_terms=["Fiction"],
    term_counts={"Fiction": 3},
    description="Sailors meet a mystery.",
    average_rating=None,
    ratings_count=None,
    published="2022",
    link=None,
    thumbnail=None,
    volumes_matched=3,
)


def _script(reading, published):
    from wfa.app import compare_view

    compare_view(reading, published)


def _render(reading, published):
    at = AppTest.from_function(_script, kwargs={"reading": reading, "published": published}).run()
    assert not at.exception
    return at


def _text(elements):
    return " ".join(e.value for e in elements)


def test_both_results_side_by_side():
    at = _render(READING, PUBLISHED)
    left, right = at.columns
    assert "A voyage goes wrong." in _text(left.markdown)
    assert ":gray-badge[ships] :gray-badge[memory]" in _text(left.markdown)
    assert ":gray-badge[Fiction · 3]" in _text(right.markdown)
    assert "Sailors meet a mystery." in _text(right.markdown)
    assert not at.info


def test_missing_reading_points_to_frequencies_tab():
    at = _render(None, PUBLISHED)
    left, right = at.columns
    assert "Find themes" in _text(left.info)
    assert "Sailors meet a mystery." in _text(right.markdown)


def test_missing_labels_point_to_labels_tab():
    at = _render(READING, None)
    left, right = at.columns
    assert "A voyage goes wrong." in _text(left.markdown)
    assert "Look up on Google Books" in _text(right.info)


def test_published_without_categories_or_description():
    bare = BookLabels(**{**PUBLISHED.__dict__, "category_terms": [], "term_counts": {}, "description": None})
    at = _render(READING, bare)
    right = at.columns[1]
    assert "No categories" in _text(right.caption)
    assert "No publisher's description" in _text(right.caption)
