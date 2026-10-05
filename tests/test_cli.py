import csv

import pytest

from helpers import GUTENBERG, make_epub, prose
from wfa import cache, cli


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DEFAULT_DIR", tmp_path / "cache")
    import wfa.pipeline
    monkeypatch.setattr(wfa.pipeline.preprocess, "__defaults__", (None, True, tmp_path / "cache"))


@pytest.fixture
def books(tmp_path):
    txt = tmp_path / "book.txt"
    txt.write_text(GUTENBERG.format(body=prose(10)), encoding="utf-8")
    return txt, make_epub(tmp_path)


def test_processes_several_files_and_writes_csvs(books, tmp_path, capsys):
    out = tmp_path / "out"
    assert cli.main([str(p) for p in books] + ["-o", str(out), "--stopwords"]) == 0

    csvs = sorted(p.name for p in out.glob("*.csv"))
    assert csvs == ["A_Test_Book_Being_a_Long_Subtitle_stop_word_frequency.csv", "Synthetic_Novel_stop_word_frequency.csv"]
    with (out / csvs[0]).open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["Word", "Frequency", "Per10k"]
    assert rows[1][0] == "rain" and int(rows[1][1]) == 10

    printed = capsys.readouterr().out
    assert "== A Test Book Being a Long Subtitle by Jane Q. Writer" in printed
    assert "Cleaning:" in printed and "Top" in printed


def test_missing_file_is_reported_and_others_still_run(books, tmp_path, capsys):
    out = tmp_path / "out"
    code = cli.main([str(tmp_path / "missing.txt"), str(books[0]), "-o", str(out)])
    assert code == 1
    assert "Error:" in capsys.readouterr().out
    assert len(list(out.glob("*.csv"))) == 1


def test_dump_removed_and_no_csv(books, tmp_path):
    out = tmp_path / "out"
    cli.main([str(books[0]), "-o", str(out), "--dump-removed", "--no-csv", "--quiet"])
    assert not list(out.glob("*.csv"))
    dump = (out / "A_Test_Book_Being_a_Long_Subtitle_removed.txt").read_text(encoding="utf-8")
    assert "[wrapper]" in dump


def test_lemmatize_suffix(books, tmp_path):
    out = tmp_path / "out"
    cli.main([str(books[0]), "-o", str(out), "--lemmatize", "--quiet"])
    assert [p.name for p in out.glob("*.csv")] == ["A_Test_Book_Being_a_Long_Subtitle_lemma_word_frequency.csv"]
