# `backend/` — FastAPI service

Serves the chat API, runs the RAG + LangGraph pipeline, and owns all database
access. Read the root `CLAUDE.md` first for the system-level picture — in
particular the *two independent persistence systems* section.

**This file covers what spans the whole backend.** Per-directory detail lives in
the nested files below, which are authoritative for their own area; keep facts
in exactly one of them.

| Directory | File | Owns |
|---|---|---|
| `routers/` | [`routers/CLAUDE.md`](routers/CLAUDE.md) | endpoints, the `/chat` lifecycle, the streaming contract |
| `agent_graph/` | [`agent_graph/CLAUDE.md`](agent_graph/CLAUDE.md) | graph state, nodes, prompt, summarisation, checkpointing |
| `db/` | [`db/CLAUDE.md`](db/CLAUDE.md) | operations, exception classification, schema, migrations |
| `clients/` | [`clients/CLAUDE.md`](clients/CLAUDE.md) | Pinecone adapter |
| `clients/llm/` | [`clients/llm/CLAUDE.md`](clients/llm/CLAUDE.md) | provider factory |
| `tests/` | [`tests/CLAUDE.md`](tests/CLAUDE.md) | the integration suite and its safety guards |

---

## ⚠️ Maintaining these files

**Update the affected `CLAUDE.md` in the same commit as the code.** These files
are the only durable memory future sessions have; a stale one is worse than a
missing one because it is trusted.

Put each fact in the **nearest** file that owns it. Something spanning two
directories (a layering rule, an ordering constraint between layers) belongs
here; something spanning backend and frontend belongs in the root file. When you
fix an item under any "Known issues"/"Known bugs" list, **delete the entry** —
do not leave it marked resolved.

---

## Top-level modules

```
backend/
├── app.py        composition root: lifespan, middleware, error handlers, router wiring
├── config.py     constants only — index/namespace names, model ids, TIMEZONE
├── schema.py     Pydantic models — mirrors frontend/lib/types.ts
└── utils.py      setup_logging()
```

- **`app.py` is the only place that wires things together.** It resolves
  `LANGGRAPH_CHECKPOINT_URL` (raising `RuntimeError` if unset), builds the model,
  opens the `PostgresSaver`, compiles the graph onto `app.state.advising_app`,
  registers middleware and exception handlers, includes the routers, and exposes
  `GET /health`.
- **`config.py` holds constants only.** No I/O, no clients, no env reads.
- **`schema.py` is a shared contract.** `ChatRequest`, `ThreadSummary`,
  `ConversationBlock`. Change it and `frontend/lib/types.ts` together. The
  `Literal["user","advising_bot"]` on `ConversationBlock.role` must also match
  the SQL `CHECK` constraint.
- **`utils.setup_logging(verbose=False)`** configures the root logger with
  `force=True` and silences `httpx`/`httpcore`. Note the docstring says
  DEBUG/WARNING but the code uses INFO/ERROR — and **nothing currently calls
  it**, so the service runs on Python's default logging config.

---

## Layering rules

Violating these is how bugs get in.

```
routers  ──►  db/supabase_operations  ──►  db/error_handler
   │                                            │
   │                                            └─ raises DatabaseError subclasses
   └──►  agent_graph, clients
                                    app.py exception handlers ──► HTTP status
```

1. **`db/` never decides HTTP status codes.** It raises `DatabaseError`,
   `DatabaseUnavailable`, or `DatabaseRequestError`, which describe *what kind*
   of failure happened. That keeps the module usable from scripts and tests with
   no web layer. The classification table lives in `db/CLAUDE.md`.
2. **`app.py` is the single place those become HTTP** (503 / 400 / 500).
   Handlers are registered for all three classes **explicitly**, because FastAPI
   dispatches on the exact class rather than walking the MRO — registering only
   the base would leave the subclasses unhandled. Driver messages are logged,
   never returned to the client.
3. **Routers must not catch `DatabaseError`.** Swallowing it flattens a
   retryable 503 into an indistinguishable 500 and the frontend stops retrying.
   `threads.py::get_thread_messages` is the model to follow;
   `get_all_threads` is older code that does not.
4. **`clients/` and `agent_graph/` know nothing about HTTP or the database.**
   They take plain arguments and return plain data.
5. **Everything imports absolutely** (`from backend.config import ...`), so the
   repo root must be the import root. Run uvicorn from the repo root;
   `pytest.ini` sets `pythonpath = .` to match.

### Error-handling layers, outermost first

| Layer | Catches | Result |
|---|---|---|
| `catch_unexpected_exceptions` HTTP middleware | anything that escapes a route | generic JSON 500, logged |
| `@app.exception_handler(DatabaseUnavailable)` | transient DB failure | 503 "please try again" |
| `@app.exception_handler(DatabaseRequestError)` | rejected request | 400 |
| `@app.exception_handler(DatabaseError)` | our bug / misconfiguration | 500 "Internal error." |

CORS is a separate middleware; errors it raises do not reach
`catch_unexpected_exceptions`. Origins are restricted by
`allow_origin_regex` to `localhost`/`127.0.0.1` on any port, with
`allow_origins` intentionally empty.

---

## Cross-cutting facts worth knowing before you edit anything

- **Several modules read `os.getenv` at import time, not call time** —
  `db/supabase_operations.py` (the Supabase client itself),
  `clients/pinecone_driver.py`, `clients/llm/factory.py` (`GEMINI_KEY`). Setting
  an env var after importing the module has no effect. This is why
  `tests/conftest.py` is built the way it is.
- **Startup is expensive and happens once.** The model is created and the graph
  compiled in the lifespan, inside the `with PostgresSaver...` block that must
  stay open for the process lifetime. There is no per-request model selection
  seam.
- **Once a streaming response starts, the status code is fixed.** Every fallible
  step on `/chat` must run before the `StreamingResponse` is returned. See
  `routers/CLAUDE.md`.
- **The thread UUID is minted in the browser** and is the same value in
  `threads.id`, `conversations.thread_id`, and the LangGraph checkpoint's
  `configurable.thread_id`. Never derive, prefix, or transform it.
- **FK ordering:** `create_thread_table_entry` before `save_conversation`,
  always.

---

## Known bugs (delete the entry when fixed)

Cross-cutting index; area-specific issues are listed in the nested files.

1. **`app.py:13` imports a module that does not exist.**
   `from backend.clients.llm.gemini import create_model` — `clients/llm/gemini.py`
   was deleted in commit `44be6f7`; the replacement is
   `backend/clients/llm/factory.py` (which `agent_graph/langgraph.py` already
   imports correctly). **The server cannot start until this is fixed.** A stale
   `__pycache__/gemini.cpython-312.pyc` is on disk but Python will not import
   from it without the source.
2. **`ChatRequest` has no `model` field** while the frontend sends one, so the
   UI's provider dropdown is silently ignored. Honouring it requires a
   per-request model seam that does not exist yet — see
   `clients/llm/CLAUDE.md`.
3. **`utils.setup_logging()` is never called**, so none of the logging config —
   the format string, the `httpx` silencing — is in effect. `app.py` should call
   it during startup.
4. **`app.py` imports `GEMINI_MODEL` from `config` but never uses it.** Harmless,
   but remove it when fixing (1), since it reinforces the wrong idea that
   `app.py` picks the model.
5. **`routers/threads.py::get_all_threads` flattens the semantic error layer** —
   see rule 3 above.
