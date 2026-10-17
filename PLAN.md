# Project Plan

The thread tying this together: **test Lotaria's claim.** Can a list of word frequencies tell you what a book is about? We compare an LLM's reading of each book's top words alone (the model **never sees the book's text, title or author**) with how the book is published and categorised (Google Books).

**Order:** Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 (README, last).

**Status (2026-10-17):** Phases 0–2 working; Phase 3 lookup working against the live API; Phase 4's foreign words, dispersion plot and characters built; README rewritten. Still to do: the Compare tab (the headline result), deferred tests, linting.

---

## Phase 0: Input preprocessing ✅

**Goal:** any supported input file → one clean, tokenised, cached `Document`. Everything later (counts, the app, the LLM, label comparison) uses the `Document` and never touches raw files again.

**Ground rules**
- All preprocessing is done by Python code running locally. Use existing libraries wherever a good one exists; write our own code only for glue and for gaps the libraries don't cover.
- No external services in Phase 0. Language models (e.g. spaCy's) are downloaded once and run offline.
- Book contents in `books/` are never inspected by hand during development. Real books are checked by running the pipeline locally and reading its summary statistics and the removed-text dump.
- **English literature only.** No language detection or multi-language handling. Words from other languages get highlighted in the final results (a later analysis feature), not handled here.
- **Generic, not tuned to sample books.** Inputs vary and so does their boilerplate. Source-specific knowledge (e.g. Project Gutenberg markers) is configuration, alongside generic heuristics.
- **Implementation first; tests come at the end of Phase 0** (step 0.8), once the pipeline shape settles.

### Common problems the pipeline must handle

| Problem | Typical source |
|---|---|
| Unknown or mixed encodings, BOM, CRLF line endings | Older `.txt` files, Windows tools |
| Mojibake (`â€™` instead of `’`), curly quotes, ligatures (`ﬁ`) | Bad conversions, typeset sources |
| Licence headers and footers counted as content | Project Gutenberg texts |
| Watermarks, running headers, page numbers repeated through the book | Converted or pirated EPUBs, PDF-derived text |
| Words merged by naive punctuation stripping (`word--word` → `wordword`) | Plain-text dash conventions |
| Words broken across lines (`con-\nspiracy`) | Hard-wrapped text |
| Reading order, chapters and metadata lost | EPUB flattened to one string |
| Text only inside images | Poetry and art books (out of scope: no OCR) |

### Library stack

| Job | Library (evaluate first) | Our own code |
|---|---|---|
| Encoding detection | [`charset-normalizer`](https://github.com/jawah/charset_normalizer) | Fallback order: `utf-8-sig` first, then detection |
| EPUB reading: spine order, TOC, metadata | [`ebooklib`](https://github.com/aerkalov/ebooklib) + [`beautifulsoup4`](https://www.crummy.com/software/BeautifulSoup/) / `lxml` | Spine walk → `Section`s; skip nav/cover pages |
| Wrapper/licence stripping (Gutenberg and others) | Rejected: `gutenbergpy` (pulls `pymongo`, Python 2 shims) and `gutenberg-cleaner` (pulls NLTK, Gutenberg only) | **Write:** configurable start/end marker list; Gutenberg is one entry |
| Fixing broken Unicode, mojibake, quotes | [`ftfy`](https://github.com/rspeer/python-ftfy) | — |
| Normalisation: hyphenated line breaks, quotes, whitespace, URLs, bullets | [`textacy.preprocessing`](https://github.com/chartbeat-labs/textacy) (composable `make_pipeline`) | Choose and order the steps |
| Tokenising, stop words, lemmas (later: named entities) | [`spaCy`](https://github.com/explosion/spaCy) + `en_core_web_sm` (offline model); fallback [`NLTK`](https://github.com/nltk/nltk) | Thin tokeniser wrapper so the backend can be swapped |
| Front/back matter, notices, watermarks, running headers, page numbers | No good off-the-shelf option for books | **Write:** generic heuristics + user-supplied patterns |
| `Document` model, options, pipeline, cache | — | **Write** |

**Python version:** resolved by pinning the project to Python 3.12 (spaCy/textacy support); see 0.1.

### Pipeline

```
file ─▶ detect & load ─▶ extract ─▶ strip boilerplate ─▶ normalise ─▶ tokenise ─▶ filter ─▶ Document ─▶ cache
         charset-norm.    ebooklib    ours           ftfy +        spaCy        ours
                          + bs4       ours (watermarks)   textacy
```

### Package layout

```
src/wfa/
  __init__.py
  document.py     # Document / Section / Metadata dataclasses
  loaders.py      # format detection, txt + epub loading, metadata
  cleaning.py     # wrapper markers, front/back matter, notices, watermarks, repeated lines (ours)
  normalize.py    # ftfy + textacy preprocessing pipeline
  tokenize.py     # spaCy wrapper, stop words, token filters
  pipeline.py     # preprocess(path, options) -> Document
  cache.py        # hash-keyed save/load of Documents
  report.py       # summary, CSV, removed-text dump
  cli.py          # `wfa` command
  analysis.py     # Phase 1: frequency table, lookup, book stats
  app.py          # Phase 1: Streamlit app
  themes.py       # Phase 2: LLM themes from (word, count) pairs only
  prompts.py      # Phase 2: LLM instructions, kept out of the UI
  labels.py       # Phase 3: Google Books lookup
  config.py       # .env loading
tests/
  helpers.py      # synthetic material written for tests (never copied from books/)
  test_*.py       # one file per stage
```

### Data model (`document.py`)

```python
@dataclass
class Metadata:
    title: str | None; author: str | None; language: str | None
    source: str            # "gutenberg" | "epub" | "plain"
    extra: dict            # release date, publisher, ...

@dataclass
class Section:
    title: str | None      # chapter heading or EPUB spine/TOC label
    text: str              # cleaned text, original case kept

@dataclass
class Document:
    path: str; file_hash: str; format: str
    metadata: Metadata
    sections: list[Section]   # kept for later dispersion and sentiment-arc plots
    tokens: list[str]         # lowercased, filtered
    lemmas: list[str] | None  # when lemmatisation is on
    stats: dict               # words per stage, removed boilerplate, unique, ...
    warnings: list[str]       # e.g. "3 image-only pages skipped"
    removed: list[dict]       # every cleaning cut: {"rule", "section", "text"}
```

Cleaned text keeps its **original case** (character detection needs capitalisation later); only `tokens` are lowercased.

### Steps

**0.1 Scaffold, environment, library check**
- [x] Move to `pyproject.toml` (`src/` layout); dev dependency `pytest`. `epub2txt` and `matplotlib` stay only until the legacy `main.py` is replaced (0.2 / 0.7).
- [x] Decided: Python **3.12** (`requires-python = ">=3.12,<3.14"`) for spaCy/textacy support.
- [x] Exact versions frozen to `requirements.lock` (refreshed whenever dependencies change).
- [x] Create the `wfa/` package and the `document.py` dataclasses.
- [x] Delete `epub_handler.py` (dead code, and the source of the `ebooklib` import crash) and `requirements.txt`.

**0.2 Loading (`loaders.py`)**
- [x] Detect format by content: EPUB = a zip file whose `mimetype` entry is `application/epub+zip`; otherwise text. PDF, other zips (DOCX) and binary files get a clear error.
- [x] Text: read bytes → `utf-8-sig` → `charset-normalizer` fallback (most coherent among the near-cleanest candidates, since `.best()` alone confuses similar code pages); normalise line endings.
- [x] EPUB with ebooklib: walk the spine, skip nav/cover/non-linear pages and guide types cover/toc/title-page/copyright-page; one `Section` per spine document, titled from the TOC, else the first heading. HTML → text with line breaks only at block elements (so inline markup like drop caps never splits a word). Image-only documents are counted into `warnings`.
- [x] Metadata: EPUB Dublin Core (`title`, `creator`, `language`, extra languages, publisher, date); Gutenberg header fields (with continuation lines); filename fallback. (Language detection was added, then removed: English only.)
- [x] `epub2txt` removed; legacy `main.py` now loads through `wfa.loaders`.
- Note: a `.txt` file is one `Section` for now; splitting plain text into chapters is left for later.

**0.3 Boilerplate removal (`cleaning.py`)**
All rules are generic and configurable through `CleaningOptions`; every cut is recorded in `doc.removed` with its rule.
- [x] **Wrapper markers:** drop text before a start marker and after an end marker. Default list covers Project Gutenberg wordings; callers can add others.
- [x] **Front/back-matter sections:** drop sections whose title is e.g. Contents, Copyright, Also by …, About the Author, Acknowledgements, Index.
- [x] **Edge notices:** scan inward from both ends; drop paragraphs dense in legal/publishing/transcription phrases (copyright, ISBN, licence, URLs, "produced by", …). The forward scan stops at the first chapter heading; both stop after a run of ordinary prose or 10% of the book. Dialogue needs two notice phrases, not one.
- [x] **Page numbers** (lines that are only a number) and **repeated short lines** (running headers, watermarks: seen ≥ 5 times, not sentence-like, not chapter headings).
- [x] **User patterns:** `--remove-pattern REGEX` (repeatable) deletes known noise everywhere.
- [x] Words removed per rule in `stats["cleaning"]`; warning if more than 20% of the text is removed; `main.py --dump-removed` writes every cut to `results/<name>_removed.txt` for review.
- Possible later: plain-text table-of-contents detection; chapter splitting for `.txt` files.

**0.4 Normalisation (`normalize.py`)**
Per section (and section titles); case is preserved. Each step can be switched off in `NormalizeOptions`.
- [x] `ftfy.fix_text`: mojibake, ligatures, width forms, curly quotes → straight.
- [x] Remove Unicode symbol characters (™ © ® ° …) **before** NFKC, which would otherwise turn `™` into `TM`; then NFKC.
- [x] `textacy.preprocessing`: quotation marks (plus guillemets, ours), bullet points, words hyphenated across lines, URLs and emails removed.
- [x] Ours: `--`, `—`, `–` and spaced hyphens → space (so `word--word` splits); `_italic_`/`*bold*` markers stripped; zero-width characters and soft hyphens removed; whitespace collapsed while **keeping paragraph breaks** (textacy's whitespace step would merge them).
- [x] Wired into `main.py` after cleaning.
- Note: `½` becomes `1⁄2` under NFKC; harmless, since numbers are dropped at tokenisation.

**0.5 Tokenisation & filtering (`tokenize.py`)**
- [x] spaCy, English only. Without lemmas: `spacy.blank("en")` (tokenizer only, ~0.5 s per 200k words). With lemmas: `en_core_web_sm` with parser/NER disabled (~11 s per 200k words). Text is fed through `nlp.pipe` in ≤100k-character chunks split at paragraph breaks.
- [x] Pieces spaCy splits out of one written word are re-joined: contractions (`don't`, `it's`, `they'd`) and hyphenated compounds (`well-known`, `mother-in-law`). Stray leading/trailing hyphens are trimmed.
- [x] Possessive `'s` / `'` dropped by default (`lincoln's` → `lincoln`, `cats'` → `cats`), except after pronoun-like words where it's a contraction (`it's`, `that's`).
- [x] `TokenizeOptions`: `lowercase` (on), `stopwords` (off; spaCy's English list, and a contraction counts as a stop word when all its pieces are, e.g. `don't`), `lemmatize` (off), `drop_numbers` (on: any token with a digit), `drop_punct` (on), `split_possessive` (on), `min_length` (1).
- [x] `doc.tokens`, `doc.lemmas` (when on), `stats["tokenize"]` with counts dropped per reason.
- [x] `main.py`: counts come from the tokeniser (`--stopwords`, `--lemmatize`); the old punctuation-stripping `analyze_text` is removed.

**0.6 Pipeline & cache (`pipeline.py`, `cache.py`)**
- [x] `preprocess(path, options) -> Document` (also exported from `wfa`): load → clean → normalise → tokenise, with per-stage timings in `stats["timing_seconds"]` and `stats["from_cache"]`.
- [x] `PreprocessOptions` bundles `CleaningOptions`, `NormalizeOptions`, `TokenizeOptions`.
- [x] Cache key = SHA-256 of file bytes + options + library versions (+ spaCy model version when lemmatising) + a hash of the `wfa` pipeline source files, so editing any rule invalidates old entries automatically (no manual version bump). Stored as gzipped JSON in `.cache/documents/` (gitignored); written atomically; corrupt entries are discarded and recomputed. `clear_cache()` available.
- [x] `main.py` uses `preprocess()`; `--no-cache` forces reprocessing. A cached 216k-word lemmatised run drops from ~12 s to well under a second.

**0.7 Report & CLI (`report.py`, `cli.py`)**
- [x] `report.py`: `summary()` (metadata, encoding, words removed per cleaning rule, token counts and drops, top-N words, timing/cache, warnings). This is how a real book gets checked without reading it. Also `write_csv()` (`Word, Frequency, Per10k`, named from the book title), `write_removed()`, and a temporary matplotlib `plot_top_words()` (removed in Phase 1).
- [x] `cli.py`, installed as the `wfa` command (`main.py` is a shim): several files per run, `-o/--out`, `--stopwords`, `--lemmatize`, `--remove-pattern`, `--top`, `--quiet`, `--no-csv`, `--dump-removed`, `--no-cache` (`--plot` was removed in Phase 1). One bad file is reported without stopping the rest; exit code 1 if any failed.
- [x] CSV names carry the options (`<title>_stop_lemma_word_frequency.csv`), so variants don't overwrite each other.
- [x] `text_analyzer.py` and the stale `results/*.csv` (made by the old code) removed.
- [x] **You:** ran `wfa` on real books; `results/` is now gitignored (local output only).

**0.8 Tests (synthetic fixtures only)**
- [x] `tests/helpers.py`: invented prose, a fake Gutenberg file, an EPUB built with ebooklib (spine order ≠ add order, nav page, title page in the guide, image-only page, drop-cap markup), a `make_doc()` factory.
- [x] One file per stage, 70 tests in ~1 s:
  - `test_loaders.py`: BOM/CRLF, cp1252 and cp1251 detection, Gutenberg header, format detection and rejection, EPUB metadata, spine order, skipped pages, inline markup, image-only warning.
  - `test_cleaning.py`: wrapper markers (single, across sections, custom), front/back-matter titles (and ordinary titles kept), edge notices removed, notice words mid-book kept, dialogue kept, scan stops at a chapter heading, page numbers, watermarks, repeated dialogue/headings kept, user patterns, stats, heavy-removal warning.
  - `test_normalize.py`: mojibake, ligatures, symbols without `TM`, quotes, line-break hyphens, dashes, emphasis, URLs/emails, zero-width characters, bullets, paragraph breaks, options off.
  - `test_tokenize.py`: contractions, compounds, possessives, numbers, punctuation, case, stop words (incl. contractions), minimum length, lemmas, chunking, empty input.
  - `test_pipeline.py`: end-to-end, cache hit, per-options entries, changed file, renamed copy, corrupt entry, cache off, clear cache.
  - `test_cli.py`: several files, CSV contents and names, missing file, `--dump-removed`, `--no-csv`, `--lemmatize` suffix.
- [x] Bugs found and fixed: the spaced-hyphen rule also removed `- ` bullets at line starts; with `drop_numbers=False`, pure numbers were still dropped as punctuation.

### Done when
- [x] `wfa <files>` (or `python main.py <files>`) works on a fresh environment created from `pyproject.toml`.
- [x] `pytest` passes on the synthetic fixtures (70 tests).
- [x] **You:** run `wfa` on your books and check the summaries look sane (boilerplate removed, no obvious noise in the top words).

---

## Phase 1: Analysis core + single-window app (Streamlit)

- [x] `wfa/analysis.py`: pure functions over a `Document`: `frequency_table()` (rank, word, count, per 10,000 words; ties alphabetical), `lookup()` (exact + partial matches), `book_stats()` (words, unique, richness, words used once, mean word length, sections, share removed by cleaning). `report.py` now uses it.
- [x] `app.py` (root shim) → `wfa/app.py`; launch with `streamlit run app.py`.
- [x] **Upload-first, no default book:** the app opens on an upload page (title, short About paragraph, uploader). Uploads are kept by content hash in `.cache/uploads/` (not `books/`), so the same book reuses its cached results. Once a book is loaded, the sidebar shows its name, an **Upload a different book** button, and the processing toggles (stop words on by default, word roots, extra patterns to remove).
- [x] **Main view (Frequencies tab) = Themes on top, frequencies directly below** (themes not a separate tab), so the project's question is visible on one screen:
  - [x] **Frequencies:** stat tiles; interactive Plotly bar chart (single series, validated colour for light and dark, ≤ 24 px bars with rounded ends, hairline grid, hover tooltip with rank/count/per-10k); words-shown slider (10–200); word search; CSV download; full table in an expander.
  - [x] **"Lotaria's electronic reading"** section (themes) above the chart, with a one-line caption nodding to Lotaria in Calvino's *If on a winter's night a traveller*
- [x] **Other tabs:** Reader labels (built in Phase 3), Compare (placeholder until Phase 3 finishes)
- [x] `st.cache_data` per (uploaded file, settings) on top of the Phase 0 disk cache.
- [x] The `wfa` command line stays as the scripted interface; matplotlib and `--plot` removed (the app replaces the chart).
- [ ] Tests for `analysis.py` and an `AppTest` smoke test, once the app settles.

## Phase 2: Themes via an external LLM

The app calls an external LLM (not Claude Code) with **only the top words** of a book: Lotaria's "electronic reading". Every call returns **both** a summary of at most three sentences **and** a list of theme words.

- [x] `wfa/themes.py`:
  - **Pluggable providers** (`Provider` protocol: `available_models()`, `complete_json()`), chosen by `WFA_LLM_PROVIDER` (default `ollama`).
  - **First backend: local Ollama** via the official `ollama` client (`OLLAMA_HOST`, default `localhost:11434`). Nothing leaves the machine; free.
  - **Input:** top 100 content words with counts (spaCy stop words and contractions always excluded, whatever the app's toggle). **The model never sees the book's text, title or author**, by construction: `top_words(doc)` is the only place a `Document` is read; `infer_themes()` / `cached_result()` accept only `(word, count)` pairs, validated (single words, ≤ 40 characters, ≤ 500 pairs).
  - **Instructions hidden:** system prompt, user-message template and response schema live in `wfa/prompts.py`, not in the UI; `prompts.VERSION` invalidates cached answers when they change.
  - **Output:** JSON schema passed to the model (`summary`, `themes`), then validated: summary trimmed to 3 sentences, themes de-duplicated, cleaned, max 10.
  - **Cache:** `.cache/themes/`, keyed by provider + model + the exact word/count pairs + `prompts.VERSION`. "Run again" refreshes the cached answer.
  - Friendly errors: server not running, model not installed, malformed reply.
- [x] App: **Themes section above the frequency chart**. Model picker (installed Ollama models; `WFA_LLM_MODEL` sets a default), **Find themes** / **Run again** button, summary paragraph + theme badges, provenance line, and an expander listing only the words and counts shared with the model.
- [x] **You:** Ollama running locally and tried on real books; default model set in `.env` (`WFA_LLM_MODEL`).
- [ ] More providers when wanted (a hosted API backend is one small class in `PROVIDERS`).
- [ ] Tests for `themes.py` (fake provider, parsing/trimming, cache, refresh) once settled.

## Phase 3: Published labels (Google Books) and comparison

Source: **Google Books API** (`volumes` search). Its `categories` are publisher subject categories (e.g. "Fiction / Science Fiction"), plus description and average rating; not user-made shelves.

- [x] `wfa/labels.py`:
  - `search_terms()` tidies metadata for searching (filename-style titles split into title/author, subtitles dropped).
  - `lookup(title, author)` via `httpx`, English, up to 10 results per query. **Query cascade**, stopping at the first match: `intitle:"T" inauthor:Surname` → `intitle:"T"` → `T Surname` → `T`. Plain-text queries matter: Google's `intitle:`/`inauthor:` operators were observed returning 0 results or HTTP 503 while plain searches worked. 5xx responses are retried twice, then the next query is tried.
  - **Matching:** title on main title (before `:`) / title + subtitle, with all-words containment counting as a full match; author on surname; editions by a different author with the same title are excluded.
  - **Categories pooled across all matching editions** (editions are labelled inconsistently), split into distinct terms, and **ranked by how many editions use each** (`term_counts`), so odd one-off labels (e.g. Flatland filed under "Computers" by one publisher) are visible but clearly outnumbered.
  - Returns `BookLabels` (title, authors, categories, terms, term counts, description without HTML, rating, published date, link, thumbnail, editions matched). Cached in `.cache/labels/` per query (`CACHE_VERSION` invalidates old entries).
  - **Only the title and author are sent to Google.** API key from `GOOGLE_BOOKS_API_KEY`; clear messages for quota exhaustion (with how to get a key), bad key, network failure, Google server trouble, "no results" vs "results, none matched" (listing what was seen).
- [x] App **Reader labels** tab: title/author fields pre-filled from metadata and editable, **Look up on Google Books** button (on demand), cover thumbnail, category badges with edition counts (e.g. *Fiction · 5*), rating, link, publisher's description in an expander.
- [x] Settings from a gitignored `.env` (`wfa/config.py`, python-dotenv; loaded by the app and the CLI; shell exports win). `.env.example` lists `GOOGLE_BOOKS_API_KEY`, `WFA_LLM_PROVIDER`, `WFA_LLM_MODEL`, `OLLAMA_HOST`.
- [x] **You:** API key in `.env`. **Verified live** (Flatland → Fiction · 5, Computers · 1, Mathematics · 1 from 8 editions). Keyless requests share a public quota that is usually exhausted (HTTP 429), so a key is effectively required.
- [ ] **Next:** score overlap between Google Books category terms and the LLM's themes. Decide the method: exact/stemmed word overlap (simple, local) vs. embedding similarity (catches "seafaring" ≈ "Sea stories", needs a local embedding model).
- [ ] **Compare tab:** LLM themes from the top words vs. published categories, side by side. This is the project's headline result.
- [ ] Tests for `labels.py` (stubbed responses: matching, pooling, splitting, errors, cache).

## Phase 4: More from the data

- [x] **Words from other languages** (`wfa/foreign.py`, using the local `wordfreq` word lists; processing stays English-only):
  - Flagged when a word is uncommon in English (Zipf ≤ 4), reasonably common in French, German, Italian, Spanish, Portuguese or Dutch (Zipf ≥ 3), and at least 10× more common there than in English. Borrowings like *ennui*, *sotto voce*, *señor*, *weltanschauung* are caught; naturalised ones (*zeitgeist*, *schadenfreude*) and common English words (*ad*, *house*) are not.
  - Names skipped: words the book mostly writes capitalised (ignoring line and sentence starts) are treated as names.
  - Limitation: `wordfreq` has no Latin list; Latin is only caught when it doubles as Italian.
  - App: "Words from other languages" badges under the frequency chart (word · language · count), and an *Other language* column in the full table.
- [x] **Dispersion plot** (`analysis.dispersion()`, `analysis.section_marks()`): **Where words appear** tab. One row per chosen word (default: top 5, up to 12 from the top 500), a thin tick per occurrence from start (0%) to end (100%), faint lines where chapters/sections begin, hover shows position and section. The tokeniser now records each section's starting token (`stats["tokenize"]["section_starts"]`).
- [x] **Characters** (`wfa/characters.py`, spaCy `en_core_web_sm` entity recognition, local): **Characters** tab, on demand (**Find characters**), cached in `.cache/characters/`.
  - Names tidied (possessive, titles like *Mr*/*Lady* removed, particles like *de*/*van* allowed, ALL-CAPS → Title case); a short form merges into the single fuller name containing it (*Darcy* → *Fitzwilliam Darcy*), but stays separate when ambiguous (*Bennet*).
  - The small model often tags names as organisations/places; those are reclaimed when they start with a title or match a known person.
  - Shows a mentions bar chart (top 15, aliases on hover), a **who appears with whom** heatmap (paragraphs naming both; single-hue sequential scale, light and dark), and the merged-names table. Known limitation: the small model still misses some mentions.

Ideas, not scheduled:

- [ ] **Distinctive words** (TF-IDF across the library): what sets this book apart from the others.
- [ ] **Sentiment arc** across the book (Vonnegut's "shapes of stories").
- [ ] **Zipf's-law plot** and vocabulary richness (type-token ratio) for comparing authors' styles.
- [ ] **Common phrases** (two- and three-word sequences; textacy has helpers).
- [ ] Side-by-side comparison of multiple books.
- [ ] Tests for `foreign.py`, `characters.py` and the dispersion helpers.

## Phase 5: README

- [x] Rewritten `README.MD`:
  - **Reference:** Italo Calvino, *If on a winter's night a traveller* (*Se una notte d'inverno un viaggiatore*, 1979; English translation by William Weaver, 1981), "traveller" spelling as in the app; Lotaria identified as Ludmilla's sister, her method recorded in Silas Flannery's diary.
  - **The idea:** an honest test of Lotaria's claim, noting Calvino's satire.
  - **What it does** (per tab), **what leaves your machine**, setup (Python 3.12, spaCy model, Ollama, Google Books key), `.env` configuration, app and `wfa` usage with all options, architecture diagram and module table, limitations, credits.
- [ ] **You:** add screenshots of the app (none included, since they'd need a real book open).
- [ ] Update the README's Compare row and "The idea" once the Compare tab exists and has results.

## Housekeeping

- [ ] Stop tracking the 18 MB `books.zip`: it's listed in `.gitignore` but still tracked (`git rm --cached books.zip`); optionally purge it from history (rewrites history), or publish it as a GitHub release asset.
- [x] `results/` is gitignored (local output only).
- [x] `.cache` is gitignored.
- [ ] Lint and format to make it prod-ready (e.g. `ruff` for lint + format, configured in `pyproject.toml`; optionally `mypy`).
