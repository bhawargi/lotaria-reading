import pytest

from helpers import make_doc
from wfa.normalize import NormalizeOptions, normalize, normalize_text


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Itâ€™s â€œbrokenâ€\x9d text", 'It\'s "broken" text'),  # UTF-8 decoded as cp1252
        ("The ﬁrst ﬂower", "The first flower"),
        ("Trademark™ © 2001 ®", "Trademark 2001"),  # no "TM" left behind by NFKC
        ("„Low“ «angled» ‹single› ‘curly’", "\"Low\" \"angled\" 'single' 'curly'"),
        ("a well-known con-\nspiracy", "a well-known conspiracy"),
        ("sections--that, a—b, c – d, e - f", "sections that, a b, c d, e f"),
        ("He was _very_ *tired*, said snake_case", "He was very tired, said snake_case"),
        ("Visit https://example.com or mail a@b.org now", "Visit or mail now"),
        ("zero\u200bwidth and soft\u00adhyphen", "zerowidth and softhyphen"),
        ("• first\n• second", "- first\n- second"),
    ],
)
def test_normalize_text(raw, expected):
    assert normalize_text(raw) == expected


def test_paragraph_breaks_survive_whitespace_collapse():
    assert normalize_text("One  line.\n\n\n\n   Two lines.  \nThree.") == "One line.\n\nTwo lines.\nThree."


def test_case_is_preserved():
    assert normalize_text("London Bridge") == "London Bridge"


def test_steps_can_be_switched_off():
    options = NormalizeOptions(split_dashes=False, strip_emphasis=False, remove_urls_emails=False)
    assert normalize_text("a--b _c_ https://x.org", options) == "a--b _c_ https://x.org"


def test_normalize_updates_sections_titles_and_stats():
    doc = normalize(make_doc(("Chapter—One", "Text  with   spaces")))
    assert doc.sections[0].title == "Chapter One"
    assert doc.sections[0].text == "Text with spaces"
    assert doc.stats["normalize"]["chars_after"] < doc.stats["normalize"]["chars_before"]
