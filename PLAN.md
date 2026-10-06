# Project Plan

The thread tying this together: **test Lotaria's claim.** Can a list of word frequencies tell you what a book is about? We compare an LLM's reading of each book's top words alone (the model **never sees the book's text, title or author**) with the labels real readers give it.

**Order:** Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 (README, last).

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

**Python version risk:** the current virtual environment is Python 3.14. spaCy (and therefore textacy) may not have wheels for 3.14 yet. Step 0.1 checks this first. If they're missing, pin the project to Python 3.12/3.13 (simple with `uv`) rather than dropping spaCy.

### Pipeline

```
file ─▶ detect & load ─▶ extract ─▶ strip boilerplate ─▶ normalise ─▶ tokenise ─▶ filter ─▶ Document ─▶ cache
         charset-norm.    ebooklib    ours           ftfy +        spaCy        ours
                          + bs4       ours (watermarks)   textacy
```

### Package layout

```
wfa/
  __init__.py
  document.py     # Document / Section / Metadata dataclasses
  loaders.py      # format detection, txt + epub loading, metadata
  cleaning.py     # Gutenberg stripping (library), watermark + repeated-line filter (ours)
  normalize.py    # ftfy + textacy preprocessing pipeline
  tokenize.py     # spaCy/NLTK wrapper, stop words, token filters
  pipeline.py     # preprocess(path, options) -> Document
  cache.py        # hash-keyed save/load of Documents
  report.py       # summary statistics for checking real books without reading them
tests/
  fixtures/       # tiny synthetic files written for tests (never copied from books/)
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
    warnings: list[str]       # e.g. "3 image-only pages skipped", "language not supported"
```

Cleaned text keeps its **original case** (character detection needs capitalisation later); only `tokens` are lowercased.

### Steps

**0.1 Scaffold, environment, library check**
- [x] Move to `pyproject.toml` (`src/` layout); dev dependency `pytest`. `epub2txt` and `matplotlib` stay only until the legacy `main.py` is replaced (0.2 / 0.7).
- [x] Decided: Python **3.12** (`requires-python = ">=3.12,<3.14"`) for spaCy/textacy support.
- [ ] Freeze exact versions to `requirements.lock` once the new environment installs cleanly.
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
- [x] `report.py`: `summary()` (metadata, encoding, words removed per cleaning rule, token counts and drops, top-N words, timing/cache, warnings). This is how a real book gets checked without reading it. Also `write_csv()` (`Word, Frequency, Per10k`, named from the book title), `write_removed()`, and the temporary matplotlib `plot_top_words()`.
- [x] `cli.py`, installed as the `wfa` command (`main.py` is a shim): several files per run, `-o/--out`, `--stopwords`, `--lemmatize`, `--remove-pattern`, `--top`, `--quiet`, `--no-csv`, `--dump-removed`, `--plot` (now opt-in), `--no-cache`. One bad file is reported without stopping the rest; exit code 1 if any failed.
- [x] CSV names carry the options (`<title>_stop_lemma_word_frequency.csv`), so variants don't overwrite each other.
- [x] `text_analyzer.py` and the stale `results/*.csv` (made by the old code) removed.
- [ ] **You:** run on `books/` and regenerate `results/`, e.g. `wfa books/*.txt books/*.epub --stopwords --dump-removed`, then skim the summaries and `*_removed.txt` files.

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
- [x] **Other tabs:** Reader labels (placeholder until Phase 3), Compare (placeholder until Phases 3/4)
- [x] `st.cache_data` per (file, modification time, settings) on top of the Phase 0 disk cache.
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
  - **Cache:** `.cache/themes/`, keyed by provider + model + exact prompt + schema + `PROMPT_VERSION`. "Run again" refreshes the cached answer.
  - Friendly errors: server not running, model not installed, malformed reply.
- [x] App: **Themes section above the frequency chart**. Model picker (installed Ollama models; `WFA_LLM_MODEL` sets a default), **Find themes** / **Run again** button, summary paragraph + theme badges, provenance line, and an expander listing only the words and counts shared with the model.
- [ ] **You:** start Ollama (`ollama serve` or the app) and pull a model, e.g. `ollama pull llama3.2`, then try it on a few books.
- [ ] More providers when wanted (a hosted API backend is one small class in `PROVIDERS`).
- [ ] Tests for `themes.py` (fake provider, parsing/trimming, cache, refresh) once settled.

## Phase 3: Reader labels and comparison

Goodreads closed its public API to new developers in 2020, and scraping breaks its terms of service. Use these instead:

- [ ] **UCSD Goodreads Book Graph:** research dataset with each book's "popular shelves" (real Goodreads user labels, as of around 2017).
- [ ] **Open Library subjects API** and **Google Books categories:** free, live, legal.
- [ ] **Gutendex** (Project Gutenberg's API): subjects and bookshelves for Gutenberg texts.
- [ ] `wfa/labels.py`: look books up by `metadata.title` / `metadata.author` (from Phase 0), normalise the labels.
- [ ] Score overlap between reader labels and the LLM's themes (e.g. embedding similarity).
- [ ] **Compare tab:** LLM themes from the top words vs. reader labels, side by side. This is the project's headline result.

## Phase 4: More from the data (ideas)

- [ ] **Distinctive words** (TF-IDF across the library): what sets this book apart from the others.
- [ ] **Dispersion plot:** where in the narrative a word appears (uses `Document.sections`).
- [ ] **Character detection** (spaCy named-entity recognition on the original-case text) and a network of characters appearing near each other.
- [ ] **Sentiment arc** across the book (Vonnegut's "shapes of stories").
- [ ] **Zipf's-law plot** and vocabulary richness (type-token ratio) for comparing authors' styles.
- [ ] **Common phrases** (two- and three-word sequences; textacy has helpers).
- [ ] Side-by-side comparison of multiple books.

## Phase 5: README

- [ ] Correct reference: Italo Calvino, *If on a winter's night a traveler* (*Se una notte d'inverno un viaggiatore*, 1979; English translation by William Weaver, 1981). Choose "traveler" or "traveller" to match the edition cited.
- [ ] Identify the character: Lotaria is the sister of Ludmilla (the Other Reader). The quote comes from Silas Flannery's diary, Chapter 8 (check against your copy).
- [ ] Motivation section: Calvino writes Lotaria's "electronic reading" partly as satire, set against Ludmilla's reading for pleasure. Frame the project as an honest test of Lotaria's claim and report what the Compare tab found.
- [ ] Usage instructions for the Streamlit app, screenshots, architecture overview, credits for the libraries used.

## Housekeeping

- [ ] Move the 18 MB `books.zip` out of git (Git LFS or a GitHub release asset).
- [ ] Decide whether `results/` stays in git (sample outputs) or gets ignored.
- [ ] Add `.cache/` to `.gitignore`.
- [ ] Lint with pylint, black, and some others to make it prod ready
