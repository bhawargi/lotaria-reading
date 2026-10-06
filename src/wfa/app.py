"""Streamlit app: one window, a book library in the sidebar. The main view puts a book's themes
directly above its word frequencies, which is the project's question in one screen: do the
frequencies tell you what the book is about? Further analyses live in their own tabs.

Run with `streamlit run app.py` from the repository root. The library folder is `books/`
(override with the WFA_LIBRARY environment variable).
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from wfa import analysis, report
from wfa.cleaning import CleaningOptions
from wfa.document import Document
from wfa.loaders import UnsupportedFormatError
from wfa.pipeline import PreprocessOptions, preprocess
from wfa.tokenize import TokenizeOptions

LIBRARY = Path(os.environ.get("WFA_LIBRARY", "books"))
SUPPORTED = (".txt", ".epub")

# Chart tokens (single series; validated against Streamlit's light and dark backgrounds).
CHART = {
    "light": {"bar": "#2a78d6", "text": "#52514e", "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7"},
    "dark": {"bar": "#3987e5", "text": "#c3c2b7", "muted": "#898781", "grid": "#2c2c2a", "axis": "#383835"},
}
BAR_ROW_PX = 26   # height per word; with the gap below, bars stay under 24px thick
BAR_GAP = 0.3


def run() -> None:
    st.set_page_config(page_title="Word Frequency Analysis", layout="wide")
    path, settings = sidebar()

    if path is None:
        st.title("Word Frequency Analysis")
        st.info("Choose a book from the library in the sidebar, or upload a .txt or .epub file.")
        return

    try:
        doc = load_document(str(path), path.stat().st_mtime, **settings)
    except (OSError, UnsupportedFormatError) as e:
        st.error(f"Could not read {path.name}: {e}")
        return

    header(doc)
    frequencies_tab, labels_tab, compare_tab = st.tabs(["Frequencies", "Reader labels", "Compare"])
    with frequencies_tab:
        themes_view(doc)
        st.divider()
        frequencies_view(doc, settings["lemmatize"])
    with labels_tab:
        st.info("Reader labels (Open Library, Gutendex, Goodreads dataset) arrive in Phase 3.")
    with compare_tab:
        st.info("Side-by-side comparison of word lists, themes and labels arrives in Phases 3–4.")


# --- Sidebar --------------------------------------------------------------


def sidebar() -> tuple[Path | None, dict]:
    with st.sidebar:
        st.header("Library")
        uploaded = st.file_uploader("Add a book", type=[ext.lstrip(".") for ext in SUPPORTED])
        if uploaded is not None:
            saved = save_upload(LIBRARY, uploaded.name, uploaded.getvalue())
            st.session_state["selected_book"] = saved.name

        books = list_books(LIBRARY)
        if not books:
            st.caption("No books yet. Upload a .txt or .epub file above.")
            path = None
        else:
            names = [b.name for b in books]
            current = st.session_state.get("selected_book")
            index = names.index(current) if current in names else 0
            choice = st.selectbox("Book", names, index=index)
            st.session_state["selected_book"] = choice
            path = LIBRARY / choice

        st.header("Processing")
        stopwords = st.toggle("Remove stop words", value=True,
                              help="Drop common words like 'the', 'and', 'she' (spaCy's English list).")
        lemmatize = st.toggle("Count word roots", value=False,
                              help="Count 'running' and 'ran' as 'run'. Slower the first time per book.")
        patterns = st.text_area(
            "Extra text to remove", value="", height=80,
            help="One regular expression per line, e.g. a watermark. Removed everywhere in the book.",
        )

    settings = {
        "stopwords": stopwords,
        "lemmatize": lemmatize,
        "patterns": tuple(p.strip() for p in patterns.splitlines() if p.strip()),
    }
    return path, settings


def list_books(library: Path) -> list[Path]:
    if not library.is_dir():
        return []
    return sorted((p for p in library.iterdir() if p.suffix.lower() in SUPPORTED and p.is_file()),
                  key=lambda p: p.name.lower())


def save_upload(library: Path, name: str, data: bytes) -> Path:
    """Save into the library; an existing file with the same name but different content gets a suffix."""
    library.mkdir(parents=True, exist_ok=True)
    target = library / Path(name).name
    stem, suffix = target.stem, target.suffix
    n = 1
    while target.exists() and target.read_bytes() != data:
        n += 1
        target = library / f"{stem} ({n}){suffix}"
    if not target.exists():
        target.write_bytes(data)
    return target


# --- Data -----------------------------------------------------------------


@st.cache_data(show_spinner="Reading the book…", max_entries=32)
def load_document(path: str, mtime: float, stopwords: bool, lemmatize: bool, patterns: tuple[str, ...]) -> Document:
    """Memoised per (file, modification time, settings); the disk cache sits underneath."""
    options = PreprocessOptions(
        cleaning=CleaningOptions(extra_patterns=list(patterns)),
        tokenize=TokenizeOptions(stopwords=stopwords, lemmatize=lemmatize),
    )
    return preprocess(path, options)


# --- Views ----------------------------------------------------------------


def header(doc: Document) -> None:
    m = doc.metadata
    st.title(m.title or Path(doc.path).stem)
    if m.author:
        st.caption(f"by {m.author}")
    for warning in doc.warnings:
        st.warning(warning)


def frequencies_view(doc: Document, use_lemmas: bool) -> None:
    stats = analysis.book_stats(doc, use_lemmas)
    unit = "word roots" if use_lemmas else "words"

    cols = st.columns(4)
    cols[0].metric(f"Total {unit}", f"{stats.words:,}")
    cols[1].metric(f"Unique {unit}", f"{stats.unique:,}")
    cols[2].metric("Used once", f"{stats.hapax:,}", help="Words that appear exactly once (hapax legomena).")
    cols[3].metric("Removed as boilerplate", f"{stats.removed_share:.1%}",
                   help="Share of the raw text the cleaner removed (licences, front matter, page numbers…).")

    table = analysis.frequency_table(doc, use_lemmas)
    if not table:
        st.info("No words left after processing.")
        return

    controls = st.columns([2, 3, 1.4])
    if len(table) > 10:
        top_n = controls[0].slider("Words shown", min_value=10, max_value=min(200, len(table)),
                                   value=min(30, len(table)), step=5)
    else:
        top_n = len(table)
    query = controls[1].text_input("Find a word", placeholder="e.g. river")
    controls[2].download_button(
        "Download CSV", data=report.csv_text(doc, use_lemmas),
        file_name=f"{report.output_stem(doc)}{'_lemma' if use_lemmas else ''}_word_frequency.csv",
        mime="text/csv", width="stretch",
    )

    if query:
        search_results(table, query)

    st.plotly_chart(bar_chart(table[:top_n], unit), width="stretch", config={"displayModeBar": False})

    with st.expander(f"All {len(table):,} {unit} as a table"):
        st.dataframe(
            pd.DataFrame([asdict(row) for row in table]),
            hide_index=True, width="stretch",
            column_config={
                "rank": st.column_config.NumberColumn("Rank", width="small"),
                "word": st.column_config.TextColumn("Word"),
                "count": st.column_config.NumberColumn("Count", format="%d"),
                "per10k": st.column_config.NumberColumn("Per 10,000", format="%.2f",
                                                        help="Occurrences per 10,000 words"),
            },
        )


def themes_view(doc: Document) -> None:
    st.subheader("Themes")
    st.caption(
        "What is this book about? Two readings will sit here side by side: one from the word "
        "frequencies below alone (Lotaria's \"electronic reading\"), and one from the full text."
    )
    lotaria, full = st.columns(2)
    with lotaria:
        st.markdown("**From the frequencies only**")
        st.info("Arrives in Phase 2.")
    with full:
        st.markdown("**From the full text**")
        st.info("Arrives in Phase 2.")


def search_results(table: list[analysis.WordRow], query: str) -> None:
    exact, partial = analysis.lookup(table, query)
    if exact:
        st.success(f"**{exact.word}** is #{exact.rank:,}: used {exact.count:,} times ({exact.per10k} per 10,000 words).")
    else:
        st.info(f"“{query.strip()}” doesn't appear after processing (it may be a stop word, or filtered out).")
    if partial:
        st.caption("Other words containing it: " + ", ".join(f"{r.word} ({r.count:,})" for r in partial[:20]))


def bar_chart(rows: list[analysis.WordRow], unit: str) -> go.Figure:
    tokens = CHART["dark" if _theme() == "dark" else "light"]
    fig = go.Figure(go.Bar(
        x=[r.count for r in rows],
        y=[r.word for r in rows],
        orientation="h",
        marker=dict(color=tokens["bar"], cornerradius=4),
        customdata=[[r.rank, r.per10k] for r in rows],
        hovertemplate="<b>%{y}</b><br>#%{customdata[0]}: %{x:,} times<br>%{customdata[1]} per 10,000<extra></extra>",
    ))
    fig.update_layout(
        height=max(240, len(rows) * BAR_ROW_PX + 60),
        bargap=BAR_GAP,
        margin=dict(l=8, r=16, t=8, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=tokens["text"], size=13),
        hoverlabel=dict(font_size=13),
        xaxis=dict(title=dict(text="Times used", font=dict(color=tokens["muted"])),
                   gridcolor=tokens["grid"], gridwidth=1, zeroline=False, rangemode="tozero",
                   tickfont=dict(color=tokens["muted"]), tickformat=",d"),
        yaxis=dict(autorange="reversed", automargin=True, ticksuffix="  ", showgrid=False,
                   showline=True, linecolor=tokens["axis"], linewidth=1,  # the baseline bars grow from
                   tickfont=dict(color=tokens["text"])),
    )
    return fig


def _theme() -> str:
    try:
        return st.context.theme.type or "light"
    except AttributeError:
        return "light"
