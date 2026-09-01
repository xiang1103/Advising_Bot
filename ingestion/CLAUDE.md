# `ingestion/` — offline corpus pipeline

Builds the knowledge base the bot retrieves from. **Nothing here runs at request
time.** These are one-off scripts a developer executes by hand; the FastAPI
service never imports them.

```
catalog.stonybrook.edu  ──scraper.py──►  raw CSV  ──clean_and_finalize_data──►  final CSV
                                                                                    │
                                                              pc_upsert.py ─────────┘
                                                                    ▼
                                                     Pinecone index "stonybrook"
                                                     namespace "SBUBulletin"
```

The retrieval side of this contract lives in `backend/clients/CLAUDE.md`.
**The two must agree on the field name `chunk_text` and on the embedding
model** — a mismatch in either produces silent nonsense, not an error.

---

## ⚠️ Maintaining this file

**Update this file in the same commit as any change here.** Especially: a change
to the scraped source or its HTML assumptions, a change to the cleaning rules or
the chunking strategy, a change to the CSV columns, batch sizes, or the target
index/namespace. If you fix an item under "Known issues", delete the entry.

A change to the CSV column names or the embedding model is a **breaking change
to retrieval** — say so in the commit message and update
`backend/clients/CLAUDE.md` and `backend/config.py` in the same commit.

---

## The data contract

Both CSVs and every Pinecone record use exactly two fields:

| Column | Meaning |
|---|---|
| `_id` | `vec_<n>`, consecutive from 1, reassigned during cleaning |
| `chunk_text` | header + joined paragraphs, one retrievable passage |

`chunk_text` is **the** name the whole system agrees on: it is the CSV column,
the Pinecone record field, `config.DEFAULT_TEXT_FIELD`, the `field_map` target
in `create_pc_index`, and the literal key `retrieve_topk_text` reads. Renaming
it means changing all five and re-embedding the corpus.

Current corpus: `data/stonybrook_pinecone_data.csv`, 10,363 records.
(`data/Pinecone - Sheet1.csv` is a 10-record sample.) `data/` is gitignored.

---

## `scraper.py`

`CatalogScraper(start_url, output_filename, max_pages)` — BFS crawl of
`catalog.stonybrook.edu`, then a cleaning pass. Run directly:

```bash
python ingestion/scraper.py     # start_url and filenames are hardcoded in __main__
```

### Crawling

- BFS over a `deque`, bounded by `max_pages` (the `__main__` block passes
  100,000, i.e. effectively unbounded — it is meant to be stopped with Ctrl-C).
- **Stays on the start domain** (`urlparse(...).netloc == self.domain`), skips
  `mailto:`/`javascript:`/`#`/`tel:` and `.pdf`/`.jpg`/`.png`, and strips
  fragments so `#section` links do not re-crawl a page.
- `time.sleep(1)` between pages. **This is the politeness budget for a
  university server — do not remove it or parallelise the crawl.** At one second
  per page a full run takes hours by design.
- A failed fetch is logged and skipped, so one bad page never aborts a run.

### Extraction and chunking

- Strips `nav`, `header`, `footer`, `aside`, then works inside
  `main` → `div#content` → `body`, in that order of preference.
- **A chunk is one `h2` section**: the running header plus every `<p>` under it,
  joined with spaces, emitted as `"{header}: {paragraphs}"` (no extra colon when
  the header already ends in one). `h1` (or `<title>`) seeds the first header.
- `ignore_headers` drops site chrome that survived the tag strip — *Audiences,
  About, Admissions, Academics, Things to Do, Resources, Logins, Info For*.
  Sections under those are marked `"Ignored Content"` and skipped entirely. Note
  these are **navigation labels**, and *Academics*/*Admissions* are plausible
  real bulletin headings too — this is a blunt filter and may be dropping
  genuine content.
- `seen_chunks` dedupes on exact text, which matters because catalog boilerplate
  repeats across hundreds of pages.
- Rows are appended to the CSV **as they are found**, so a Ctrl-C mid-run leaves
  a usable partial file. The header row is written in `__init__`, which means
  **constructing the scraper truncates `output_filename`.**

### `clean_and_finalize_data(raw_csv, final_csv)`

Four transforms, in order, then a filter:

1. **Strip soft hyphens** (`\xad`) — the catalog is full of them and they make
   `Edu­ca­tion` compare unequal to `Education`. Retrieval strips them *again* at
   query time in `retrieve_topk_text`, deliberately belt-and-braces.
2. **Insert a space after `.,!?` when glued to a letter** (`website.The` →
   `website. The`).
3. **Insert a space at lower→upper boundaries** (`EquityAdministration` →
   `Equity Administration`).
4. Collapse whitespace.
5. **Drop chunks under 15 words**, then reassign `_id` consecutively.

Rule 3 is aggressive and **corrupts legitimate camel-cased and acronym-adjacent
text** — `MSCHE` survives, but a course code or name that relies on internal
capitals will be split. It is a deliberate trade for the far more common
scraper artefact. If retrieval starts returning oddly spaced course titles, this
is the line to look at.

---

## `pc_upsert.py`

```python
from ingestion.pc_upsert import upsert_to_pinecone
upsert_to_pinecone("data/stonybrook_pinecone_data.csv", "stonybrook", "SBUBulletin")
```

There is **no `__main__` block** — call it from a REPL or a small script, from
the repo root (it imports `backend.clients.pinecone_driver`, so the repo root
must be the import root, exactly as for the server).

| Function | Notes |
|---|---|
| `get_pc_records(path)` | reads the CSV and coerces `_id` to `str`. **Currently unused** — `upsert_to_pinecone` re-reads the file itself and skips the coercion |
| `upsert_to_pinecone(csv_file, index_name, namespace)` | create-or-get the index, then insert; prints and re-raises on failure |
| `insert_pc_data(pc_index, records, namespace, batch_size=24, max_retries=5)` | batched upsert with backoff |

Behaviour worth knowing:

- **It calls `create_pc_index`, not `get_pc_index`** — so running it against a
  new index name silently *creates* one rather than failing. Check the name.
  Index creation pins `llama-text-embed-v2` on `aws`/`us-east-1` and maps the
  text field to `config.DEFAULT_TEXT_FIELD`.
- **Upsert, not insert.** Re-running with the same `_id`s overwrites in place;
  it does not duplicate. But because cleaning **reassigns `_id` consecutively**,
  a re-scrape that changes the row count shifts every id — old records are then
  orphaned rather than replaced, and the namespace accumulates stale text.
  **Clear the namespace before a full re-ingest**, or move to stable content-
  derived ids.
- `batch_size` is asserted `<= 96` (Pinecone's cap); the default 24 is
  conservative.
- Retries only on rate limiting — the check is a **substring match** on
  `RESOURCE_EXHAUSTED`, `Too Many Requests`, or `(429)` in the exception text,
  with 5s exponential backoff capped at 60s. Any other error fails the batch
  immediately as a `RuntimeError` naming the batch start index.
- **Failure is not atomic.** A batch failing at record 5,000 leaves the first
  5,000 upserted. Re-running is safe (upsert semantics) provided the ids have
  not shifted.
- **Embedding happens server-side at Pinecone**, via `upsert_records` against an
  index created for a model. Records carry raw text, not vectors. Changing the
  embedding model therefore means recreating the index and re-ingesting
  everything — queries embedded with a different model return noise, not an
  error.

---

## Re-ingesting from scratch

1. `python ingestion/scraper.py` — hours; Ctrl-C is safe.
2. Eyeball the final CSV. Row count and a sample of `chunk_text` catch most
   scraper breakage; a silent drop to a few hundred rows means the catalog's
   HTML changed.
3. **Clear the target Pinecone namespace** if the row count moved (see the id
   drift note above).
4. `upsert_to_pinecone(final_csv, INDEX_NAME, NAMESPACE)`.
5. Ask the bot two or three questions whose answers you know. Retrieval failure
   is silent — a wrong-but-fluent answer is the failure mode, not an exception.
6. Update this file if the shape of the data changed.

---

## Known issues (delete when fixed)

1. **`print` everywhere instead of `logging`.** Both modules create a
   `logger`/import `logging` and then never use it, so output bypasses the
   configured handlers. `scraper.py` does not even create one.
2. **`get_pc_records` is dead code**, and it is the only place `_id` is coerced
   to `str` — `upsert_to_pinecone` re-reads the CSV with a plain
   `pd.read_csv(...).to_dict()`, so ids reach Pinecone with whatever dtype
   pandas inferred. Today they are `vec_<n>` strings so it does not bite; a
   purely numeric id column would.
3. **No `__main__` in `pc_upsert.py`** and hardcoded paths in `scraper.py`'s —
   neither script takes arguments, so every run is an edit-then-run.
4. **`clean_and_finalize_data` prints a "Short/useless rows removed" count but
   never reports the gibberish filtering it claims** — the only filter is the
   15-word minimum.
5. **The crawl has no resume.** Ctrl-C keeps the rows already written, but a
   restart re-crawls from the start URL and truncates the output file on
   construction.
6. **No verification step after upsert** — nothing checks that Pinecone's record
   count matches the CSV's.
