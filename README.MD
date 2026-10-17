# Word Frequency Analysis

Inspired by the dialogue (*for shits and giggles!*)

> "What is the reading of a text, in fact, except the recording of certain thematic recurrences, certain insistences of form and meaning? An electronic reading supplies me with a list of frequencies, which I have only to glance at to form an idea of the problems the book suggests to my critical study."
>
> — Lotaria, in Italo Calvino's *If on a winter's night a traveller* (*Se una notte d'inverno un viaggiatore*, 1979; English translation by William Weaver, 1981)

## The idea

In Calvino's novel, Lotaria (the sister of Ludmilla, the Other Reader) doesn't read books so much as process them: a machine turns each one into a list of word frequencies, and a glance at the list tells her what the book is about. The novelist Silas Flannery describes her method in his diary, and Calvino treats it partly as satire, set against Ludmilla's reading for pleasure.

This project takes Lotaria at her word and tests her claim:

1. Strip a book down to its word frequencies.
2. Show **only the most frequent words and their counts** to a language model, never the text, title or author, and ask what the book is about.
3. Compare that "electronic reading" with how the book is actually published and categorised.

Everything runs on your machine except an optional, on-demand lookup of the book's title and author on Google Books.

## What it does

Upload an English book (`.txt` or `.epub`) and the app shows:

| Tab | What you get |
|---|---|
| **Frequencies** | *Lotaria's electronic reading*: a local LLM's summary (at most three sentences) and theme words, inferred from the top 100 words alone. Below it: word counts, an interactive chart of the most frequent words, word search, a CSV download, the full table, and **words borrowed from other languages** (*ennui · French*, *sotto voce · Italian*). |
| **Where words appear** | A dispersion plot: one row per word, a tick for every use from the first page to the last, with chapter boundaries marked. |
| **Characters** | People named in the book (spaCy entity recognition), how often each is mentioned, and a heatmap of who appears with whom. |
| **Published labels** | The book's Google Books categories (ranked by how many editions use each), rating and publisher's description. |
| **Compare** | Coming next: the LLM's themes side by side with the published categories. |

Before any counting, the text is cleaned: licence headers and footers (e.g. Project Gutenberg), front and back matter, copyright notices, watermarks, running headers and page numbers are removed; broken encodings, curly quotes, ligatures and words split across lines are repaired. Contractions (*don't*) and compounds (*well-known*) stay whole; stop words and word roots (*running* → *run*) are optional.

### What leaves your machine

- **The LLM** runs locally through [Ollama](https://ollama.com). By construction it only ever receives `(word, count)` pairs: no text, title or author.
- **Google Books** receives the title and author, and only when you press *Look up on Google Books*.
- Nothing else. Uploaded books and all results are cached locally under `.cache/`.

## Setup

Requires **Python 3.12**, the version it's tested on (`pyproject.toml` allows 3.12–3.13).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m spacy download en_core_web_sm
```

`requirements.lock` pins the exact versions the project was last tested with (`pip install -r requirements.lock` reproduces them).

**For Lotaria's electronic reading** (themes), install [Ollama](https://ollama.com), start it, and pull a model:

```bash
ollama serve            # or open the Ollama app
ollama pull qwen3.5:4b  # the model used during development; any chat model works
```

**For Published labels**, create a free Google Books API key (Google Cloud Console → enable the *Books API* → Credentials → *Create API key*). Requests without a key share a public quota that is usually exhausted.

### Configuration

Copy `.env.example` to `.env` (gitignored) and fill in what you need. Values exported in your shell take precedence.

| Variable | Purpose | Default |
|---|---|---|
| `GOOGLE_BOOKS_API_KEY` | Google Books lookups | none |
| `WFA_LLM_PROVIDER` | LLM backend | `ollama` |
| `WFA_LLM_MODEL` | Model preselected in the app | first installed model |
| `OLLAMA_HOST` | Ollama server address | `http://localhost:11434` |

## Usage

### The app

```bash
streamlit run app.py
```

Upload a book; switch books from the sidebar, where you can also toggle stop words and word roots, or add regular expressions for extra text to remove (e.g. a watermark).

### The command line

`wfa` (or `python main.py`) processes one or more books and writes a frequency CSV per book to `results/`:

```bash
wfa mybook.epub --stopwords
wfa books/*.txt books/*.epub --stopwords --lemmatize --dump-removed
```

Each run prints a summary: metadata, how many words each cleaning rule removed, token counts, the top words and any warnings. That's a quick way to check a book was cleaned well without reading it.

| Option | Effect |
|---|---|
| `-o, --out DIR` | Output folder (default `results/`) |
| `--stopwords` | Remove English stop words |
| `--lemmatize` | Count word roots (slower; loads the spaCy model) |
| `--remove-pattern REGEX` | Delete extra text everywhere, e.g. a watermark (repeatable) |
| `--top N` | Words shown in the summary (default 20) |
| `--dump-removed` | Write everything the cleaner removed to `<out>/<title>_removed.txt` |
| `--quiet`, `--no-csv` | Skip the summary or the CSV |
| `--no-cache` | Reprocess even if a cached result exists |

CSV columns: `Rank, Word, Frequency, Per10k` (uses per 10,000 words, comparable across books of different lengths).

## How it works

```
file ─▶ load ─▶ clean ─▶ normalise ─▶ tokenise ─▶ Document (cached)
          │                                          │
          │                     ┌────────────────────┼─────────────────────┐
          ▼                     ▼                    ▼                     ▼
   title, author ─▶ Google   top words ─▶ LLM    frequencies,       characters
                    Books    (word, count only)  dispersion,        (spaCy NER)
                                                 foreign words
```

| Module (`src/wfa/`) | Role |
|---|---|
| `loaders.py` | Format detection, encoding detection, EPUB reading in spine order, metadata |
| `cleaning.py` | Licence wrappers, front/back matter, notices, watermarks, page numbers, repeated lines |
| `normalize.py` | Broken Unicode, quotes, dashes, hyphenation, whitespace |
| `tokenize.py` | spaCy tokenising, contractions and compounds, stop words, lemmas |
| `pipeline.py`, `cache.py` | `preprocess(path) -> Document`, cached by file content, options, library versions and code |
| `analysis.py` | Frequency table, word lookup, book statistics, dispersion |
| `foreign.py` | Words borrowed from other languages |
| `characters.py` | Named characters and co-occurrence |
| `themes.py`, `prompts.py` | LLM themes from word/count pairs; the prompts are kept out of the UI |
| `labels.py` | Google Books lookup |
| `app.py`, `cli.py`, `report.py`, `config.py` | Streamlit app, `wfa` command, summaries and CSVs, `.env` loading |

## Development

```bash
pytest                       # tests (synthetic fixtures only; no real books needed)
ruff check .                 # lint
ruff format .                # format
```

Lint and format settings live in `pyproject.toml`.

## Limitations

- **English only.** Words from other languages are flagged, not translated or analysed. Latin isn't covered by the word lists used.
- **`.txt` and `.epub` only.** No PDF or Word files, and no text recognition in images.
- **Characters** come from spaCy's small English model, which misses some mentions and occasionally labels a non-person.
- **Google Books categories** are assigned by publishers (e.g. "Fiction / Classics"), not tags made by readers, and differ between editions.
- **Themes** are only as good as the local model you run.

## Credits

Built on [spaCy](https://spacy.io), [textacy](https://github.com/chartbeat-labs/textacy), [ftfy](https://github.com/rspeer/python-ftfy), [charset-normalizer](https://github.com/jawah/charset_normalizer), [EbookLib](https://github.com/aerkalov/ebooklib), [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/), [wordfreq](https://github.com/rspeer/wordfreq), [Streamlit](https://streamlit.io), [Plotly](https://plotly.com/python/), [Ollama](https://ollama.com), [HTTPX](https://www.python-httpx.org) and the [Google Books API](https://developers.google.com/books).
