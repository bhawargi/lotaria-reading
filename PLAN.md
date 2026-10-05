# Project Plan

The thread tying this together: **test Lotaria's claim.** Can a list of word frequencies tell you what a book is about? We compare three readings of each book: a frequency-only LLM reading ("Lotaria mode"), a full-text LLM reading, and the labels real readers give it.

**Order:** Phase 0 → Phase 1 (alongside) → Phase 2 → Phase 3 → Phase 4 → Phase 5. The app (Phase 2) can start as a single Frequencies tab right after Phase 0 and gain tabs as later phases land.

---

## Phase 0: Groundwork

Separate the core logic from the UI so the app and the LLM step have something solid to build on.

- [ ] Reorganise into a small package `wfa/`:
  - [ ] `ingest.py`: read `.txt` and `.epub` → `Book(title, author, text)`. Get title/author from EPUB metadata or from the Gutenberg header lines (`Title:`, `Author:`); Phase 4 needs them to look books up.
  - [ ] `analysis.py`: pure functions only (no plotting, no printing).
  - [ ] `store.py`: save results per book (JSON to start, SQLite later if needed), keyed by a hash of the file. Reopening a book is instant, and an LLM call is never billed twice.
- [ ] Fix existing bugs:
  - [ ] `main.py` imports `epub_handler`, which needs `ebooklib` (not in `requirements.txt`), so a fresh install crashes. Delete the dead `epub_handler.py`.
  - [ ] `export_to_csv` ignores its `filename` argument and reads `sys.argv[1]` instead.
  - [ ] `books/tmp.txt` is never cleaned up, and writing it fails if `books/` doesn't exist. Work in memory instead.
  - [ ] `zip(*top_words)` crashes on empty input.
  - [ ] Remove the leftover `print("was here")`.
- [ ] Better word splitting: keep contractions ("don't") and hyphenated words, and strip Unicode punctuation (curly quotes, em-dashes).
- [ ] Optional stop-word filtering (articles, pronouns, particles).
- [ ] Basic tests for `ingest` and `analysis`.
- [ ] Pin dependency versions in `requirements.txt`.

## Phase 1: README

- [ ] Correct reference: Italo Calvino, *If on a winter's night a traveler* (*Se una notte d'inverno un viaggiatore*, 1979; English translation by William Weaver, 1981). Choose "traveler" or "traveller" to match the edition cited.
- [ ] Identify the character: Lotaria is the sister of Ludmilla (the Other Reader). The quote comes from Silas Flannery's diary, Chapter 8 (check against your copy).
- [ ] Motivation section: Calvino writes Lotaria's "electronic reading" partly as satire, set against Ludmilla's reading for pleasure. Frame the project as an honest test of Lotaria's claim; the LLM step is close to the machine reading she imagined.
- [ ] Update the usage instructions for the Streamlit app, and add screenshots.
- [ ] Short roadmap linking to this plan.

## Phase 2: Single-window app (Streamlit)

- [ ] `app.py` with Streamlit; launch with `streamlit run app.py`.
- [ ] Layout: a **sidebar** with the book library and upload (txt/epub), plus **tabs** for each view:
  - [ ] **Frequencies**: interactive Plotly bar chart, top-N slider, stop-word toggle, search for a word, CSV download.
  - [ ] **Themes** (Phase 3)
  - [ ] **Reader labels** (Phase 4)
  - [ ] **Compare** (Phase 4/5)
- [ ] Use `st.cache_data` together with `store.py` so analyses aren't recomputed.
- [ ] Keep the command line as a thin wrapper over `wfa/` for scripted runs.

## Phase 3: Themes via LLM

A single structured API call per mode; no agent loop needed.

- [ ] `wfa/themes.py` using the Anthropic Python SDK (`claude-opus-5-5`), with structured JSON output: themes, a one-paragraph summary, genre guesses, key characters.
- [ ] Two modes:

  | Mode | Input | Rough cost (at $4 per million input tokens) | Purpose |
  |---|---|---|---|
  | **Lotaria mode** | Top ~300 words (stop words removed) + basic statistics | about $0.01 | Tests the quote directly |
  | **Full read** | Whole text (fits in the 1M context; the largest sample, *The Great Conspiracy*, is roughly 400k tokens) | about $1.60 for the largest book | Reference reading |

- [ ] Save results per book hash; show the cost estimate (token count) before running a full read.
- [ ] API key from the environment (`ANTHROPIC_API_KEY`), never committed.

## Phase 4: Reader labels and comparison

Goodreads closed its public API to new developers in 2020, and scraping breaks its terms of service. Use these instead:

- [ ] **UCSD Goodreads Book Graph:** research dataset with each book's "popular shelves" (real Goodreads user labels, as of around 2017).
- [ ] **Open Library subjects API** and **Google Books categories:** free, live, legal.
- [ ] **Gutendex** (Project Gutenberg's API): subjects and bookshelves; several sample books are Gutenberg texts.
- [ ] `wfa/labels.py`: look books up by title/author, normalise the labels.
- [ ] Score overlap between reader labels and each LLM mode (embedding similarity or a second LLM call as judge).
- [ ] **Compare tab:** Lotaria mode vs. full read vs. reader labels, side by side. This is the project's headline result.

## Phase 5: More from the data (ideas)

- [ ] **Distinctive words** (TF-IDF across the library): what sets this book apart from the others.
- [ ] **Dispersion plot:** where in the narrative a word appears.
- [ ] **Character detection** (spaCy named-entity recognition) and a network of characters appearing near each other.
- [ ] **Sentiment arc** across the book (Vonnegut's "shapes of stories").
- [ ] **Zipf's-law plot** and vocabulary richness (type-token ratio) for comparing authors' styles.
- [ ] **Common phrases** (two- and three-word sequences).
- [ ] Side-by-side comparison of multiple books.

## Housekeeping

- [ ] Move the 18 MB `books.zip` out of git (Git LFS or a GitHub release asset).
- [ ] Decide whether `results/` stays in git (sample outputs) or gets ignored.
