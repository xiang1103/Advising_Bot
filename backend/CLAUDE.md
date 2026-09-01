# `backend/` — FastAPI service

Serves the chat API, runs the RAG + LangGraph pipeline, and owns all database
access. Read the root `CLAUDE.md` first for the system-level picture — in
particular the *two independent persistence systems* section.

**This file covers what spans the whole backend:** the composition root, the
layering rules, and the invariants that hold across layers. Anything specific to
one area lives in that area's file, which is authoritative for it.

| Directory | File | Owns |
|---|---|---|
| `routers/` | [`routers/CLAUDE.md`](routers/CLAUDE.md) | endpoints, the `/chat` lifecycle, the streaming contract |
| `agent_graph/` | [`agent_graph/CLAUDE.md`](agent_graph/CLAUDE.md) | graph state, nodes, prompt, summarisation, checkpointing |
| `db/` | [`db/CLAUDE.md`](db/CLAUDE.md) | operations, exception classification, table invariants |
| `clients/` | [`clients/CLAUDE.md`](clients/CLAUDE.md) | Pinecone adapter |
| `clients/llm/` | [`clients/llm/CLAUDE.md`](clients/llm/CLAUDE.md) | provider factory |
| `tests/` | [`tests/CLAUDE.md`](tests/CLAUDE.md) | the integration suite and its safety guards |

Keep each fact in exactly one file. See the scope rule in the root `CLAUDE.md`.

---

## Top-level modules

These four have no subdirectory of their own, so this file owns them.

```
backend/
├── app.py        composition root: lifespan, middleware, error handlers, router wiring
├── config.py     constants only — index/namespace names, model ids, TIMEZONE
├── schema.py     Pydantic models — mirrors frontend/lib/types.ts
└── utils.py      setup_logging()
```

- **`app.py` is the only place that wires things together**, and the only place
  that knows about every other layer. It resolves `LANGGRAPH_CHECKPOINT_URL`
  (raising `RuntimeError` if unset), builds the model, opens the
  `PostgresSaver`, compiles the graph onto `app.state.advising_app`, registers
  middleware and exception handlers, includes the routers, and exposes
  `GET /health`. Nothing else should reach across layers like this.
- **`config.py` holds constants only.** No I/O, no clients, no env reads.
- **`schema.py` is a shared contract**, not just backend types — see the root
  `CLAUDE.md` for the frontend and SQL counterparts it must agree with.
- **`utils.setup_logging(verbose=False)`** configures the root logger and
  silences `httpx`/`httpcore`. **Nothing calls it**, so the service currently
  runs on Python's default logging config; its docstring also disagrees with its
  code (DEBUG/WARNING vs. INFO/ERROR).

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

1. **`db/` never decides HTTP status codes.** It raises exceptions that describe
   *what kind* of failure happened — transient, bad request, or our bug — not
   what status to send. That keeps the module usable from scripts and tests with
   no web layer.
2. **`app.py` is the single place those become HTTP.** One handler per exception
   class, registered explicitly.
3. **Routers must not catch `DatabaseError`.** Swallowing it flattens a
   retryable failure into an indistinguishable 500 and the frontend stops
   retrying.
4. **`clients/` and `agent_graph/` know nothing about HTTP or the database.**
   They take plain arguments and return plain data.
5. **Everything imports absolutely** (`from backend.config import ...`), so the
   repo root must be the import root — for uvicorn and for pytest alike.

### The error boundary

Failures are classified once, in `db/`, and translated once, in `app.py`:

| Layer | Catches | Result |
|---|---|---|
| `catch_unexpected_exceptions` HTTP middleware | anything that escapes a route | generic JSON 500, logged |
| `@app.exception_handler(DatabaseUnavailable)` | transient DB failure | 503 |
| `@app.exception_handler(DatabaseRequestError)` | rejected request | 400 |
| `@app.exception_handler(DatabaseError)` | our bug / misconfiguration | 500 |

Two things about this that are easy to get wrong: handlers must be registered
for **all three classes explicitly**, because FastAPI dispatches on the exact
class rather than walking the MRO; and driver messages are logged, never
returned to the client. The signal-to-exception mapping is in
`db/CLAUDE.md`.

CORS is a separate middleware, so errors it raises never reach the
`catch_unexpected_exceptions` boundary.

---

## Invariants that hold across layers

Each is enforced or explained in the file that owns it; they are listed here
because breaking one from a different layer is the realistic failure mode.

- **Startup happens once and is expensive.** The model is created and the graph
  compiled during the lifespan, inside a `PostgresSaver` context that must stay
  open for the process lifetime. There is no per-request model-selection seam.
- **Once a streaming response starts, the status code is fixed.** Every fallible
  step on `/chat` must run before the response is returned.
- **The thread UUID is minted in the browser** and is the same value in
  `threads.id`, `conversations.thread_id`, and the LangGraph checkpoint config.
  Never derive, prefix, or transform it.
- **Thread row before message rows.** `conversations.thread_id` is a foreign
  key, so `create_thread_table_entry` must precede `save_conversation`.
- **Several modules read `os.getenv` at import time**, not call time — the
  Supabase client is built during import. This is why the test suite sets the
  environment before importing anything and imports lazily through a fixture.

---

## Known issues

Area-specific issues are listed at the bottom of each nested file. These belong
to the modules this file owns:

1. **`app.py:13` imports a module that does not exist.**
   `from backend.clients.llm.gemini import create_model` — that module was
   deleted when the provider factory was introduced. **The server cannot start
   until this is fixed.** Background in `clients/llm/CLAUDE.md`.
2. **`utils.setup_logging()` is never called**, so none of the logging
   configuration is in effect. `app.py` should call it during startup.
3. **`app.py` imports `GEMINI_MODEL` but never uses it.** Harmless, but remove
   it when fixing (1) — it reinforces the wrong idea that `app.py` picks the
   model.
