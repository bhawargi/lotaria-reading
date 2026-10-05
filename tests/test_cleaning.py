from helpers import PROSE, make_doc, prose
from wfa.cleaning import CleaningOptions, clean

START = "*** START OF THE PROJECT GUTENBERG EBOOK SOMETHING ***"
END = "*** END OF THE PROJECT GUTENBERG EBOOK SOMETHING ***"


def rules(doc):
    return {cut["rule"] for cut in doc.removed}


# --- Wrapper markers ------------------------------------------------------


def test_wrapper_markers_keep_only_the_inside():
    doc = clean(make_doc(f"Distributor header\n\n{START}\n\n{prose(5)}\n\n{END}\n\nLicence terms."))
    assert "Distributor" not in doc.text and "Licence" not in doc.text
    assert START not in doc.text and END not in doc.text
    assert doc.text.count("rain had not stopped") == 5


def test_wrapper_markers_across_sections():
    doc = clean(make_doc("Cover blurb.", f"Intro\n{START}\n{PROSE}", prose(3), f"{PROSE}\n{END}\nFooter", "Licence."))
    assert len(doc.sections) == 3
    assert "Cover" not in doc.text and "Intro" not in doc.text
    assert "Footer" not in doc.text and "Licence" not in doc.text


def test_custom_wrapper_markers():
    options = CleaningOptions(markers=[(r"^=== BEGIN BOOK ===$", r"^=== END BOOK ===$")])
    doc = clean(make_doc(f"Shop notice\n=== BEGIN BOOK ===\n{prose(4)}\n=== END BOOK ===\nMore shop."), options)
    assert "Shop" not in doc.text
    assert doc.text.count("rain had not stopped") == 4


def test_no_markers_leaves_text_alone():
    doc = clean(make_doc(prose(6)))
    assert doc.text == prose(6)
    assert doc.removed == []


# --- Front/back-matter sections -------------------------------------------


def test_front_and_back_matter_sections_are_dropped_by_title():
    doc = clean(make_doc(
        ("Contents", "Chapter One\nChapter Two"),
        ("Copyright", "Some legal words"),
        ("Chapter One", prose(3)),
        ("Chapter Two", prose(3)),
        ("Also by Ada Author", "Another Novel\nA Third Novel"),
        ("About the Author", "Ada lives by the sea."),
    ))
    assert [s.title for s in doc.sections] == ["Chapter One", "Chapter Two"]
    assert "front_back_section" in rules(doc)


def test_ordinary_titles_containing_skip_words_are_kept():
    doc = clean(make_doc(("The Index Finger", prose(3)), ("Credits Due to Fortune", prose(3))))
    assert len(doc.sections) == 2


# --- Edge notices ---------------------------------------------------------


def test_front_and_back_notices_are_removed():
    front = "Copyright 2001 by A. Writer. All rights reserved.\nISBN 978-0-00-000000-0"
    back = "Published by Example Press. Printed in the United Kingdom. www.example.com"
    doc = clean(make_doc(f"{front}\n\nFor my mother\n\n{prose(10)}\n\n{back}"))
    assert "Copyright" not in doc.text and "ISBN" not in doc.text and "Published by" not in doc.text
    assert "For my mother" in doc.text
    assert "notice" in rules(doc)


def test_notice_words_in_the_middle_of_the_book_are_kept():
    middle = "He argued about the copyright and the licence of the publishing house all night."
    doc = clean(make_doc(f"{prose(10)}\n\n{middle}\n\n{prose(10)}"))
    assert middle in doc.text


def test_short_dialogue_with_one_cue_is_kept():
    dialogue = '"You have my permission," she said.'
    doc = clean(make_doc(f"Copyright 2001. All rights reserved.\n\n{dialogue}\n\n{prose(10)}"))
    assert dialogue in doc.text
    assert "All rights reserved" not in doc.text


def test_front_scan_stops_at_the_first_chapter_heading():
    after_heading = "The edition of the newspaper lay on the table."
    doc = clean(make_doc(f"CHAPTER I\n\n{after_heading}\n\n{prose(10)}"))
    assert after_heading in doc.text


# --- Page numbers and repeated lines --------------------------------------


def test_page_numbers_and_repeated_watermarks_are_removed():
    body = "\n\n".join(f"{PROSE}\n\nScanSite.com\n\n{n}" for n in range(1, 12))
    doc = clean(make_doc(body))
    assert "ScanSite" not in doc.text
    assert not any(line.strip().isdigit() for line in doc.text.split("\n"))
    assert {"page_number", "repeated_line"} <= rules(doc)


def test_repeated_dialogue_and_headings_are_kept():
    body = "\n\n".join(f'CHAPTER {n}\n\n"No."\n\n{PROSE}' for n in range(1, 12))
    doc = clean(make_doc(body))
    assert doc.text.count('"No."') == 11
    assert doc.text.count("CHAPTER") == 11


def test_lines_repeated_fewer_times_than_the_threshold_are_kept():
    body = "\n\n".join(f"{PROSE}\n\nA Running Header" for _ in range(3))
    assert clean(make_doc(body)).text.count("A Running Header") == 3


# --- User patterns, stats, warnings ---------------------------------------


def test_extra_patterns_are_removed_everywhere():
    doc = clean(make_doc(f"{PROSE} [scan by xyz] {PROSE}"), CleaningOptions(extra_patterns=[r"\[scan by \w+\]"]))
    assert "scan by" not in doc.text
    assert "extra_pattern" in rules(doc)


def test_stats_count_removed_words_per_rule():
    doc = clean(make_doc(f"Header words here\n\n{START}\n\n{prose(5)}\n\n{END}"))
    stats = doc.stats["cleaning"]
    assert stats["words_before"] - stats["words_after"] == sum(stats["removed_by_rule"].values())
    assert stats["removed_by_rule"]["wrapper"] > 0


def test_heavy_removal_raises_a_warning():
    doc = clean(make_doc(f"{prose(5)}\n\n{START}\n\n{PROSE}\n\n{END}"))
    assert any("removed" in w for w in doc.warnings)
