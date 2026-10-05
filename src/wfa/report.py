"""Outputs for a preprocessed Document: a text summary for checking a book without reading
it, the frequency CSV, the removed-text dump, and (until the Streamlit app) a chart."""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

from wfa.document import Document


def frequencies(doc: Document, use_lemmas: bool = False) -> Counter[str]:
    return Counter(doc.lemmas if use_lemmas and doc.lemmas is not None else doc.tokens)


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

    top = frequencies(doc, use_lemmas).most_common(top_n)
    if top:
        lines.append(f"Top {len(top)}" + (" lemmas" if use_lemmas else "") + ":")
        lines.append("  " + ", ".join(f"{w} {n:,}" for w, n in top))

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


def write_csv(doc: Document, out_dir: Path, suffix: str = "", use_lemmas: bool = False) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{output_stem(doc)}{suffix}_word_frequency.csv"
    total = len(doc.lemmas if use_lemmas and doc.lemmas is not None else doc.tokens) or 1
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Word", "Frequency", "Per10k"])
        for word, n in frequencies(doc, use_lemmas).most_common():
            writer.writerow([word, n, round(n * 10_000 / total, 2)])
    return path


def write_removed(doc: Document, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{output_stem(doc)}_removed.txt"
    with path.open("w", encoding="utf-8") as f:
        for cut in doc.removed:
            f.write(f"=== [{cut['rule']}] section: {cut['section']}\n{cut['text'].strip()}\n\n")
    return path


def plot_top_words(doc: Document, n: int = 50, use_lemmas: bool = False) -> None:
    import matplotlib.pyplot as plt  # only needed for the legacy chart

    top = frequencies(doc, use_lemmas).most_common(n)
    if not top:
        return
    words, counts = zip(*top)
    plt.figure(figsize=(10, 8))
    plt.barh(words, counts)
    plt.gca().invert_yaxis()
    plt.xlabel("Frequency")
    plt.ylabel("Lemmas" if use_lemmas else "Words")
    plt.title(f"{doc.metadata.title or Path(doc.path).stem}: top {len(top)}")
    plt.tight_layout()
    plt.show()
