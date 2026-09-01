# `backend/clients/` — external service adapters

Thin wrappers around the third-party services the backend depends on.

- `pinecone_driver.py` — the vector store (RAG retrieval).
- `llm/` — LLM provider selection. See `backend/clients/llm/CLAUDE.md`.

**Rules for this directory:** adapters know nothing about HTTP, nothing about
FastAPI, and nothing about the database. They take plain arguments and return
plain data. Anything that needs a status code, a request, or a `DatabaseError`
belongs elsewhere.

---

## ⚠️ Maintaining this file

**Update this file in the same commit as any change here.** Especially: a new
client, a change to a function's return shape, a change to which exceptions
escape, a change to the embedding model or index configuration, or a new
environment variable. If you fix an item under "Known issues", delete the entry.

---

## `pinecone_driver.py`

The Pinecone handle is built at **module import time**:

```python
load_dotenv()
pc = Pinecone(api_key=os.getenv("PINECONE_KEY"))
```

`PINECONE_KEY` must be set before this module is imported; setting it afterwards
has no effect. Index and namespace names are **not** here — they live in
`config.py` (`INDEX_NAME = "stonybrook"`, `NAMESPACE = "SBUBulletin"`) and are
passed in by the caller.

| Function | Returns | Raises |
|---|---|---|
| `get_pc_index(index_name)` | an index handle | `ValueError` if the index does not exist |
| `pc_search(index, namespace, query, top_k=5)` | raw Pinecone search response | `ValueError` on a null argument; `RuntimeError` wrapping any search failure |
| `retrieve_topk_text(results, top_k=3)` | `list[str]` of chunk texts | `ValueError` if `results` is falsy |
| `create_pc_index(index_name, model=...)` | an index handle | — (creates if absent) |

### Things that will bite

- **`get_pc_index` never creates an index.** It raises if the name is missing.
  Creation is `create_pc_index`, which exists for the ingestion scripts only and
  must not be called from a request path — index creation is slow and
  provisioning is a deploy-time concern.
- **`retrieve_topk_text` strips soft hyphens**:
  `hit["fields"]["chunk_text"].replace('\xad', '')`. The scraped bulletin is full
  of them. Dropping that `.replace` puts invisible characters into the prompt,
  which corrupts course codes and degrades retrieval-grounded answers in a way
  that is very hard to see when reading logs.
- **It clamps `top_k` to the number of hits** before slicing, so asking for more
  than Pinecone returned is safe.
- **It reaches into the response by literal keys**: `results['result']['hits']`
  and `hit["fields"]["chunk_text"]`. A Pinecone SDK response-shape change
  surfaces as a `KeyError`, not a graceful degradation. `chunk_text` is also
  spelled out as `config.DEFAULT_TEXT_FIELD`, which is used by `create_pc_index`'s
  `field_map` but **not** here — the two must be changed together.
- **`pc_search` wraps every failure in `RuntimeError`** with the original as
  `__cause__`. In `routers/chat.py` this is caught and converted to an
  `HTTPException(500)` *before* streaming begins, which is the only point at
  which a real status code can still be sent.
- **The embedding model is pinned in `create_pc_index`**
  (`llama-text-embed-v2`, `aws` / `us-east-1`). Changing it means re-embedding
  the whole corpus; queries embedded with a different model return noise rather
  than an error.

---

## Adding a client

1. New module in this directory (or a subpackage if it grows past one file).
2. Read credentials from the environment; put names, ids, and tunables in
   `config.py`, not here.
3. Raise plain exceptions. Do not import `fastapi`. Let the caller decide the
   status code, and make sure any fallible call is reachable *before* a
   streaming response starts.
4. Update this file and the env table in the root `CLAUDE.md`.

---

## Known issues (delete when fixed)

1. **`assert top_k >= 0` in `pc_search` permits `top_k=0`** despite the message
   saying "must be above 0", and `assert` is stripped entirely under `python -O`.
   Prefer an explicit `if ... raise ValueError`.
2. **`create_pc_index` uses `print`, not `logging`** — output bypasses the
   configured handlers set up by `utils.setup_logging()`.
3. **`load_dotenv()` at module import** gives importing this module a side
   effect on the process environment; that belongs at the entry point.
4. **No retry or timeout on `pc_search`.** A slow Pinecone response blocks the
   request thread before streaming starts, with no upper bound.
