"""Outputs for a preprocessed Document: a text summary for checking a book without reading
it, the frequency CSV, and the removed-text dump."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from wfa import analysis
from wfa.document import Document


def summary(doc: Document, top_n: int = 20, use_lemmas: bool = False) -> str:
    m, st = doc.metadata, doc.stats
    lines = [
        f"== {m.title or '(untitled)'}" + (f" by {m.author}" if m.author else ""),
        f"File: {doc.path} ({doc.format}, source: {m.source}"
        + (f", encoding: {m.extra['encoding']}" if "encoding" in m.extra else "")
        + f", {len(doc.sections)} section(s))",
    ]

    c = st["cleaning"]
    removed = c["words_before"] - c["words_after"]
    share = removed / c["words_before"] if c["words_before"] else 0
    lines.append(f"Cleaning: {c['words_before']:,} -> {c['words_after']:,} words ({removed:,} removed, {share:.1%})")
    for rule, n in sorted(c["removed_by_rule"].items(), key=lambda kv: -kv[1]):
        lines.append(f"  {rule:<20} {n:>8,}")

    t = st["tokenize"]
    line = f"Tokens: {t['tokens']:,} ({t['unique']:,} unique"
    if t.get("unique_lemmas") is not None:
        line += f", {t['unique_lemmas']:,} unique lemmas"
    dropped = ", ".join(f"{k} {v:,}" for k, v in t["dropped"].items() if v)
    lines.append(line + ")" + (f"; dropped: {dropped}" if dropped else ""))

    top = analysis.frequency_table(doc, use_lemmas, limit=top_n)
    if top:
        lines.append(f"Top {len(top)}" + (" lemmas" if use_lemmas else "") + ":")
        lines.append("  " + ", ".join(f"{row.word} {row.count:,}" for row in top))

    if st.get("from_cache"):
        lines.append("Time: cached result")
    elif "timing_seconds" in st:
        lines.append("Time: " + ", ".join(f"{k} {v:.2f}s" for k, v in st["timing_seconds"].items()))
    lines += [f"Warning: {w}" for w in doc.warnings]
    return "\n".join(lines)


def output_stem(doc: Document) -> str:
    """File-safe name from the book title, falling back to the input file name."""
    name = doc.metadata.title or Path(doc.path).stem
    slug = re.sub(r"[^\w-]+", "_", name).strip("_")[:80]
    return slug or Path(doc.path).stem


def csv_text(doc: Document, use_lemmas: bool = False) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Rank", "Word", "Frequency", "Per10k"])
    for row in analysis.frequency_table(doc, use_lemmas):
        writer.writerow([row.rank, row.word, row.count, row.per10k])
    return buffer.getvalue()


def write_csv(doc: Document, out_dir: Path, suffix: str = "", use_lemmas: bool = False) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{output_stem(doc)}{suffix}_word_frequency.csv"
    path.write_text(csv_text(doc, use_lemmas), encoding="utf-8")
    return path


def write_removed(doc: Document, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{output_stem(doc)}_removed.txt"
    with path.open("w", encoding="utf-8") as f:
        for cut in doc.removed:
            f.write(f"=== [{cut['rule']}] section: {cut['section']}\n{cut['text'].strip()}\n\n")
    return path
