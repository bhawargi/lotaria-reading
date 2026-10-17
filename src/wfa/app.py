"""Streamlit app: one window. It opens on an upload page; once a book is uploaded, the main
view puts Lotaria's electronic reading (themes) directly above the book's word frequencies,
which is the project's question in one screen: do the frequencies tell you what the book is
about? Further analyses live in their own tabs.

Run with `streamlit run app.py` from the repository root. Uploaded books are kept by content
hash under `.cache/uploads/`, so re-uploading the same book reuses its cached results.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from wfa import analysis, labels, report, themes
from wfa.cleaning import CleaningOptions
from wfa.document import Document
from wfa.loaders import UnsupportedFormatError
from wfa.pipeline import PreprocessOptions, preprocess
from wfa.tokenize import TokenizeOptions

UPLOAD_DIR = Path(".cache") / "uploads"
SUPPORTED = (".txt", ".epub")

ABOUT = (
    "Upload an English book (.txt or .epub) to see which words it leans on most. "
    "Licences, front matter and page clutter are stripped first. Then a local LLM, shown only "
    "the most frequent words, guesses what the book is about. Everything runs on your machine."
)

# Chart tokens (single series; validated against Streamlit's light and dark backgrounds).
CHART = {
    "light": {"bar": "#2a78d6", "text": "#52514e", "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7"},
    "dark": {"bar": "#3987e5", "text": "#c3c2b7", "muted": "#898781", "grid": "#2c2c2a", "axis": "#383835"},
}
BAR_ROW_PX = 26   # height per word; with the gap below, bars stay under 24px thick
BAR_GAP = 0.3


def run() -> None:
    st.set_page_config(page_title="Word Frequency Analysis", layout="wide")

    book = st.session_state.get("book")
    if book is None:
        upload_page()
        return

    path = Path(book["path"])
    settings = sidebar(book["name"])
    try:
        doc = load_document(str(path), **settings)
    except (OSError, UnsupportedFormatError) as e:
        st.error(f"Could not read {book['name']}: {e}")
        return

    header(doc)
    frequencies_tab, labels_tab, compare_tab = st.tabs(["Frequencies", "Reader labels", "Compare"])
    with frequencies_tab:
        themes_view(doc)
        st.divider()
        frequencies_view(doc, settings["lemmatize"])
    with labels_tab:
        labels_view(doc)
    with compare_tab:
        st.info("Side-by-side comparison of word lists, themes and labels arrives in Phases 3–4.")


# --- Upload page and sidebar ----------------------------------------------


def upload_page() -> None:
    st.title("Word Frequency Analysis")
    st.subheader("About")
    st.markdown(ABOUT)
    uploaded = st.file_uploader(
        "Upload a book", type=[ext.lstrip(".") for ext in SUPPORTED],
        key=f"uploader_{st.session_state.get('uploads', 0)}",
    )
    if uploaded is not None:
        path = save_upload(uploaded.name, uploaded.getvalue())
        st.session_state["book"] = {"name": uploaded.name, "path": str(path)}
        st.rerun()


def sidebar(book_name: str) -> dict:
    with st.sidebar:
        st.header("Book")
        st.markdown(f"**{book_name}**")
        if st.button("Upload a different book", width="stretch"):
            del st.session_state["book"]
            st.session_state["uploads"] = st.session_state.get("uploads", 0) + 1  # fresh, empty uploader
            st.rerun()

        st.header("Processing")
        stopwords = st.toggle("Remove stop words", value=True,
                              help="Drop common words like 'the', 'and', 'she' (spaCy's English list).")
        lemmatize = st.toggle("Count word roots", value=False,
                              help="Count 'running' and 'ran' as 'run'. Slower the first time per book.")
        patterns = st.text_area(
            "Extra text to remove", value="", height=80,
            help="One regular expression per line, e.g. a watermark. Removed everywhere in the book.",
        )

    return {
        "stopwords": stopwords,
        "lemmatize": lemmatize,
        "patterns": tuple(p.strip() for p in patterns.splitlines() if p.strip()),
    }


def save_upload(name: str, data: bytes, upload_dir: Path = UPLOAD_DIR) -> Path:
    """Keep the upload under its content hash (same book, same folder), with its original name."""
    folder = upload_dir / hashlib.sha256(data).hexdigest()[:16]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / Path(name).name
    if not path.exists():
        path.write_bytes(data)
    return path


# --- Data -----------------------------------------------------------------


@st.cache_data(show_spinner="Reading the book…", max_entries=32)
def load_document(path: str, stopwords: bool, lemmatize: bool, patterns: tuple[str, ...]) -> Document:
    """Memoised per (upload, settings); uploads are content-addressed, and the disk cache sits underneath."""
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
    st.subheader("Lotaria's electronic reading")
    st.caption(
        "Inspired by Lotaria, the mad machine-reader of Calvino's *If on a winter's night a traveller*. "
        "An LLM sees only the top words below, and guesses the rest."
    )

    try:
        provider = llm_provider()
        models = provider.available_models()
    except themes.ThemeError as e:
        st.warning(str(e))
        return
    if not models:
        st.info(f"No models installed in {provider.name}. Pull one, e.g. `ollama pull llama3.2`, then reload.")
        return

    preferred = st.session_state.get("theme_model") or os.environ.get("WFA_LLM_MODEL")
    controls = st.columns([3, 1.4, 3])
    model = controls[0].selectbox(
        "Model", models, index=models.index(preferred) if preferred in models else 0,
        help=f"Models available in your local {provider.name} installation.",
    )
    st.session_state["theme_model"] = model

    words = themes.top_words(doc)  # the only thing a model ever receives
    result = themes.cached_result(words, model, provider.name)
    controls[1].markdown("&nbsp;")  # align the button with the select box
    if controls[1].button("Find themes" if result is None else "Run again", width="stretch"):
        with st.spinner(f"Asking {model}…"):
            try:
                result = themes.infer_themes(words, model, provider, refresh=result is not None)
            except themes.ThemeError as e:
                st.error(str(e))
                return

    if result is None:
        return
    st.markdown(result.summary)
    if result.themes:
        st.markdown(" ".join(f":gray-badge[{t.replace(']', ')')}]" for t in result.themes))
    st.caption(f"{result.model} via {result.provider}, from the top {result.words_sent} words · {result.created[:10]}")
    with st.expander(f"The {len(words)} words shared with the model"):
        st.dataframe(
            pd.DataFrame(words, columns=["Word", "Count"]), hide_index=True, width="stretch",
            column_config={"Count": st.column_config.NumberColumn(format="%d")},
        )


@st.cache_resource
def llm_provider() -> themes.Provider:
    return themes.get_provider()


def labels_view(doc: Document) -> None:
    st.subheader("Published labels")
    st.caption("How the book is categorised on Google Books. Only the title and author below are sent to Google.")

    title, author = labels.search_terms(doc.metadata.title, doc.metadata.author)
    cols = st.columns([3, 3, 1.6])
    title = cols[0].text_input("Title", value=title, key=f"label_title_{doc.file_hash}")
    author = cols[1].text_input("Author", value=author, key=f"label_author_{doc.file_hash}")

    result = labels.cached_lookup(title, author)
    cols[2].markdown("&nbsp;")  # align the button with the inputs
    if cols[2].button("Look up on Google Books" if result is None else "Look up again", width="stretch"):
        with st.spinner("Searching Google Books…"):
            try:
                result = labels.lookup(title, author, use_cache=result is None)
            except labels.LabelError as e:
                st.error(str(e))
                return
    if result is None:
        return

    left, right = st.columns([1, 5])
    if result.thumbnail:
        left.image(result.thumbnail, width=96)
    with right:
        byline = ", ".join(result.authors) or "unknown author"
        st.markdown(f"**{result.title}** · {byline}" + (f" · {result.published[:4]}" if result.published else ""))
        if result.category_terms:
            st.markdown(" ".join(f":gray-badge[{t.replace(']', ')')}]" for t in result.category_terms))
        else:
            st.caption("No categories listed for this book.")
        if result.average_rating:
            st.caption(f"Rated {result.average_rating:g}/5 by {result.ratings_count or 0:,} Google Books users")
        details = f"Categories pooled from {result.volumes_matched} matching edition(s)"
        st.caption(details + (f" · [View on Google Books]({result.link})" if result.link else ""))
    if result.description:
        with st.expander("Publisher's description"):
            st.markdown(result.description)


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
