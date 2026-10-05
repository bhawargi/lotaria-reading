"""Command line: preprocess one or more books, print a summary, write frequency CSVs."""

from __future__ import annotations

import argparse
from pathlib import Path

from wfa import report
from wfa.cleaning import CleaningOptions
from wfa.loaders import UnsupportedFormatError
from wfa.pipeline import PreprocessOptions, preprocess
from wfa.tokenize import TokenizeOptions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wfa", description="Word frequency analysis of books (.txt, .epub).")
    parser.add_argument("files", nargs="+", type=Path, help="one or more .txt / .epub files")
    parser.add_argument("-o", "--out", type=Path, default=Path("results"), help="output folder (default: results)")
    parser.add_argument("--stopwords", action="store_true", help="remove English stop words")
    parser.add_argument("--lemmatize", action="store_true",
                        help="count word roots (running -> run); slower, loads the spaCy model")
    parser.add_argument("--remove-pattern", action="append", default=[], metavar="REGEX",
                        help="extra text to delete everywhere, e.g. a watermark (repeatable)")
    parser.add_argument("--top", type=int, default=20, help="words shown in the summary (default: 20)")
    parser.add_argument("--quiet", action="store_true", help="don't print the summary")
    parser.add_argument("--no-csv", action="store_true", help="don't write the frequency CSV")
    parser.add_argument("--dump-removed", action="store_true",
                        help="write everything the cleaner removed to <out>/<title>_removed.txt")
    parser.add_argument("--plot", action="store_true", help="show a chart of the top 50 words")
    parser.add_argument("--no-cache", action="store_true", help="reprocess even if a cached result exists")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    options = PreprocessOptions(
        cleaning=CleaningOptions(extra_patterns=args.remove_pattern),
        tokenize=TokenizeOptions(stopwords=args.stopwords, lemmatize=args.lemmatize),
    )
    suffix = ("_stop" if args.stopwords else "") + ("_lemma" if args.lemmatize else "")

    failures = 0
    for path in args.files:
        try:
            doc = preprocess(path, options, use_cache=not args.no_cache)
        except (OSError, UnsupportedFormatError) as e:
            print(f"Error: {path}: {e}")
            failures += 1
            continue

        if not args.quiet:
            print(report.summary(doc, top_n=args.top, use_lemmas=args.lemmatize))
        if not args.no_csv:
            print(f"CSV: {report.write_csv(doc, args.out, suffix, use_lemmas=args.lemmatize)}")
        if args.dump_removed:
            print(f"Removed text: {report.write_removed(doc, args.out)}")
        if args.plot:
            report.plot_top_words(doc, use_lemmas=args.lemmatize)
        print()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
