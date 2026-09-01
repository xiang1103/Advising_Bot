# `backend/` — FastAPI service

Serves the chat API, runs the RAG + LangGraph pipeline, and owns all database
access. Read the root `CLAUDE.md` first for the system-level picture (in
particular the *two independent persistence systems* section) — this file covers
backend internals only.

---

## ⚠️ Maintaining this file

**Update this file in the same commit as any backend change that invalidates
it.** Specifically: new/changed/removed routes, changes to the exception
contract between layers, changes to graph nodes or state, new db operations,
changed ordering guarantees, or anything you had to debug that wasn't obvious
from the code. If you fix something listed under "Known bugs", delete the entry.

---

## Layout

```
backend/
├── app.py                      composition root: lifespan, middleware, error handlers, router wiring
├── config.py                   constants only (index/namespace names, model ids, TIMEZONE)
├── schema.py                   Pydantic request/response models — mirrors frontend/lib/types.ts
├── utils.py                    setup_logging()
├── routers/
│   ├── chat.py                 POST /chat  — retrieval, streaming, background persistence
│   └── threads.py              GET /threads, GET /threads/{id}/messages
├── agent_graph/
│   └── langgraph.py            AdvisingState, chatbot/summarize nodes, graph builder, token stream
├── clients/
│   ├── pinecone_driver.py      index handle, search, top-k text extraction
│   └── llm/factory.py          provider selection: gemini | ollama
├── db/
│   ├── supabase_operations.py  every table read/write
│   └── error_handler.py        driver failures → semantic DatabaseError subclasses
└── tests/                      integration tests against a LOCAL Supabase stack
```

---

## Layering rules (violating these is how bugs get in)

```
routers  ──►  db/supabase_operations  ──►  db/error_handler
   │                                            │
   │                                            └─ raises DatabaseError subclasses
   └──►  agent_graph, clients
                                    app.py exception handlers ──► HTTP status
```

1. **`db/` never decides HTTP status codes.** It raises `DatabaseError`,
   `DatabaseUnavailable`, or `DatabaseRequestError`, which describe *what kind*
   of failure happened. This keeps the module usable from scripts and tests with
   no web layer.
2. **`app.py` is the single place those become HTTP.** Handlers are registered
   for all three classes explicitly, because FastAPI dispatches on the exact
   class rather than walking the MRO — registering only the base would leave the
   subclasses unhandled.
3. **Routers must not catch `DatabaseError`.** `threads.py::get_thread_messages`
   deliberately lets it propagate: swallowing it would flatten a transient 503
   into an indistinguishable 500 and the frontend would stop retrying.
   `threads.py::get_all_threads` still wraps everything in a blanket 500 — that
   is older code and inconsistent with the rule; prefer the newer style.
4. `config.py` holds constants only. No I/O, no clients, no env reads.

### Exception classification (`db/error_handler.py`)

`db_operation("name")` is a context manager wrapping every Supabase call. It
catches `postgrest.APIError` and `httpx.HTTPError` and re-raises with the
original preserved as `__cause__`.

| Signal | Becomes | Meaning |
|---|---|---|
| any `httpx.HTTPError` (no response ever arrived) | `DatabaseUnavailable` | 503 — retry is meaningful |
| SQLSTATE `57014`, `53300`, `53400`, `40001`, `40P01`, or `08*` | `DatabaseUnavailable` | 503 |
| SQLSTATE `22*`, `23*`, or `PGRST103` | `DatabaseRequestError` | 400 — identical retry fails identically |
| integer `code` in `{408,429,500,502,503,504}` | `DatabaseUnavailable` | postgrest falls back to raw HTTP status when the error body wasn't JSON |
| anything else, or no code at all | `DatabaseError` | 500 — treated as *our* bug/misconfiguration |

The default is deliberately `DatabaseError`: an unrecognised code is a bug until
proven otherwise. When adding a code to `_TRANSIENT_CODES` etc., say why.
Driver messages are never leaked to the client — handlers log the exception and
return a fixed generic `detail`.

---

## `POST /chat` — the request lifecycle

Read `routers/chat.py` alongside this. The ordering here is load-bearing.

1. `asked_at = datetime.now(TIMEZONE)` is captured **before** anything slow, so
   the stored question timestamp reflects arrival, not completion.
2. **All fallible work happens before the `StreamingResponse` is returned.**
   Pinecone retrieval (`get_pc_index` → `pc_search` → `retrieve_topk_text`) runs
   up front and raises `HTTPException(500)`. This is not stylistic: **once a
   streaming response has begun, the status code is already on the wire and
   cannot be changed.** Any new fallible step must go above the `return`, or its
   failure will surface to the user as a `200 OK` containing an error string.
3. `create_thread_table_entry(thread_id, title)` runs **before** anything can
   write to `conversations`, because `conversations.thread_id` is a foreign key.
   Reversing these two calls silently loses every message.
   `tests/test_conversation_persistence.py::test_save_conversation_rejects_unknown_thread`
   exists to pin exactly this ordering.
4. A `collected_convo: list[str]` sink is created and passed **by reference** to
   both the generator and the background task. `token_generator` appends each
   chunk to it as it yields; `persist_conversation` reads it after the stream
   completes.
   **Never rebind the sink** (`sink = [...]`, `sink = sink + [...]`) — the
   background task holds a reference to the *original* list object and would
   read an empty one. Only `.append()`.
5. `BackgroundTasks` is attached to the `StreamingResponse`, so persistence runs
   **after** the last byte is sent. A client that disconnects mid-stream still
   gets its partial response saved — `token_generator` deliberately does not
   clear the sink on error, because a partial answer is better than none.
6. `persist_conversation` early-returns on an empty sink. This matters:
   `save_conversation` raises `ValueError` on an empty `bot_response`, and that
   `ValueError` would escape inside a background task where no exception handler
   can turn it into a response. Everything inside `persist_conversation` is also
   wrapped in a `try/except` that logs — a persistence failure must never break
   an already-delivered stream.

### Error surfaces on this route

- Retrieval failure → real HTTP 500 (before streaming).
- `create_thread_table_entry` failure → propagates to `app.py`'s DB handlers →
  503/400/500 (still before streaming).
- Generation failure mid-stream → the generator yields
  `"\n\n[Advising Bot failed to finish generating this response.]"` inside a
  200 response. The frontend appends its own interruption marker on a hard
  network failure.
- Anything unexpected anywhere → the `catch_unexpected_exceptions` HTTP
  middleware in `app.py` logs it and returns a generic JSON 500. Note that CORS
  is applied as a separate middleware; errors raised by CORS do not reach it.

---

## `agent_graph/langgraph.py`

State is `AdvisingState(MessagesState)` with two extra keys:
`summary: str` and `context_results: list[str]`.

```
START ──► chatbot ──┬──► summarize_node ──► END      (len(messages) > max_messages)
                    └──► END                          (otherwise)
```

- **`chatbot_node`** rebuilds the system message on every call:
  `SYSTEM_ROLE` + the running `summary` (if any) + the RAG hits wrapped in
  `<context>…</context>`. The retrieved context is injected into the *system*
  message, never as a user turn — the jailbreak-resistance rules in
  `SYSTEM_ROLE` depend on that separation. Edit `SYSTEM_ROLE` with care; the
  README documents specific prompt-injection behaviours it is expected to hold.
- **`summarize_node`** summarises `messages[:-2]` — i.e. everything except the
  latest user question and its answer — then emits a `RemoveMessage` for each
  summarised message. **This is destructive and irreversible in the
  checkpoint.** The previous summary is folded into the prompt so it compounds
  rather than being lost. If `messages_to_summarize` is empty it returns `{}`,
  which is the correct no-op (returning `{"messages": []}` would be too, but an
  empty dict is cheaper and clearer).
- **`should_summarize`** returns either `"summarize_node"` or `END`. It is
  registered via `add_conditional_edges` with **no path map**, so the return
  value *is* the destination node name. Renaming the node without updating the
  returned string silently breaks the edge at graph-compile time.
- `max_messages` defaults to 8 and is bound with `functools.partial` at build
  time. `app.py` passes `max_messages=8` explicitly. Note the check is on total
  message count (user + assistant), so 8 ≈ 4 exchanges.
- **`generate_response_stream`** uses `stream_mode="messages"` and filters on
  `metadata["langgraph_node"] == "chatbot"`, so summarisation tokens never leak
  into the user's reply. It handles both content shapes LangChain emits: a plain
  `str`, and a list of content blocks where the text is at `content[0]["text"]`
  (Gemini). A new provider with a third shape needs a branch here or it will
  stream nothing.
- `context_results` is part of the graph state and is therefore **checkpointed**.
  It is overwritten on every invocation with the current turn's hits.

The graph is built and compiled **once**, in `app.py`'s lifespan, and stored on
`app.state.advising_app`. The `PostgresSaver` connection is held open for the
whole application lifespan by the `with` block — do not move the compile step
outside it or the checkpointer's connection closes immediately.

---

## `db/supabase_operations.py`

The Supabase client is created at **module import time** from `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY`. Importing this module with the wrong environment
either raises or — worse — silently binds to whatever project the developer's
`.env` names. This constraint drives the whole design of `tests/conftest.py`.

| Function | Order | Notes |
|---|---|---|
| `create_thread_table_entry(id, title)` | — | `upsert(on_conflict="id", ignore_duplicates=True)`. Idempotent by design: called on **every** message. |
| `save_conversation(...)` | user row then bot row, one insert | Both rows in a single `insert([...])` call so the pair is atomic. |
| `list_all_threads(limit=50)` | `updated_at desc` | Sidebar. |
| `retrieve_thread_conversation(thread_id)` | **oldest first** | Feeds `GET /threads/{id}/messages`; matches render order. |
| `get_history(thread_id, page_num, page_size)` | **newest first** | Pagination. Not currently called by any route. |

Edge cases that will bite:

- **`ignore_duplicates=True` means a thread title is never updated after
  creation.** The frontend cooperates by sending `""` for non-first messages,
  and `create_thread_table_entry` omits the `title` key entirely when it's
  falsy so the DB default applies. A rename feature needs a separate `update`,
  not a change to this upsert. Pinned by
  `test_create_thread_table_entry_is_idempotent`.
- **`retrieve_thread_conversation` and `get_history` sort in opposite
  directions.** Do not swap one for the other. Both add a secondary `.order("id")`
  because `created_at` is only `clock_timestamp()` precision and the user/bot
  rows of one turn can tie; `id` (a monotonic identity column) is the tiebreak
  that keeps a turn from rendering bot-before-user.
- **`get_history`'s secondary `.order("id")` is ascending even though
  `created_at` is descending.** On a tie that reverses the pair within a turn.
  It has not mattered because `created_at` differs between question and answer,
  but a future caller relying on strict newest-first ordering should fix this to
  `.order("id", desc=True)`.
- **`list_all_threads` orders by `updated_at`, which nothing ever writes.**
  There is no touch trigger on the column (the migration only sets a default),
  and no code path updates it. In practice the sidebar is ordered by *creation*
  time. `test_list_all_threads_is_newest_first_and_respects_limit` sets
  `updated_at` by hand precisely because the app never does. If you want the
  sidebar to reflect recent activity, add a trigger or an explicit update in
  `save_conversation` — and update this note.
- `save_conversation` normalises both timestamps with
  `.astimezone(timezone.utc).isoformat()` for JSON serialisability. Passing a
  naive datetime will be interpreted as local time; `config.TIMEZONE` is UTC and
  callers should use it.
- `get_history` validates `page_num >= 1` locally because a `page_num` of 0
  produces a negative OFFSET, which Postgres rejects with a 400 only after a
  full round trip.
- `create_thread_table_entry` raises `DatabaseRequestError` for a falsy id;
  `save_conversation` raises a plain `ValueError` for empty inputs. That
  inconsistency is real — `ValueError` is not caught by `app.py`'s handlers and
  would become a generic 500 from the middleware. Only safe today because its
  sole caller (`persist_conversation`) pre-checks and catches everything.

---

## `clients/`

- **`pinecone_driver.py`** — module-level `Pinecone(api_key=...)` built at import
  from `PINECONE_KEY`. `get_pc_index` raises `ValueError` if the index is
  missing (it never creates one); `create_pc_index` exists only for the
  ingestion scripts. `retrieve_topk_text` clamps `top_k` to the number of hits
  and strips soft hyphens (`\xad`) that the scraped bulletin text is full of —
  dropping that `.replace` puts invisible characters into the prompt.
  It reads `hit["fields"]["chunk_text"]` by literal key; `config.DEFAULT_TEXT_FIELD`
  holds the same string but is not used here. Change both together.
- **`clients/llm/factory.py`** — `create_model(provider=None, model_name=None)`.
  Provider defaults to `LLM_PROVIDER` env, then `"gemini"`. `langchain_ollama`
  is imported lazily inside the branch so Gemini users need not install it.
  Model ids live in `config.py` (`GEMINI_MODEL`, `OLLAMA_MODEL`).

---

## `tests/`

Integration tests only (`pytestmark = pytest.mark.integration`). They exercise
the real persistence seam — real Postgres, real schema, real foreign key, real
PostgREST — because that is exactly what mocking cannot verify.

```bash
supabase start && supabase db reset
pytest backend/tests/                    # from the repo root
```

`conftest.py` earns its complexity:

- It shells out to `supabase status -o env` at **conftest import time**, before
  any test module is imported, because `backend.db.supabase_operations` builds
  its client at import time. The `ops` fixture then imports that module lazily
  via `importlib`.
- It accepts either CLI key spelling (`SERVICE_ROLE_KEY`/`SECRET_KEY`,
  `ANON_KEY`/`PUBLISHABLE_KEY`) so a CLI upgrade doesn't break the suite.
- `_assert_local` hard-stops the run if either URL is not localhost. The
  `clean_tables` fixture issues `truncate ... restart identity cascade` on every
  test; pointing that at a real project is unrecoverable. **Never weaken this
  guard.**
- Truncation happens *before* each test, not after, so a failed test leaves its
  rows behind for inspection.
- The whole suite **skips** (not fails) when the stack is down.
- Teardown talks to Postgres directly via `psycopg`, bypassing PostgREST, so it
  stays independent of the layer under test. `psycopg` comes from
  `requirements-dev.txt`.

When you add a db operation, add an integration test for the property that the
routers actually depend on — ordering, idempotency, FK behaviour — not for the
Supabase client itself.

---

## Known bugs (delete the entry when fixed)

1. **`app.py:13` imports a module that does not exist.**
   `from backend.clients.llm.gemini import create_model`. `clients/llm/gemini.py`
   was deleted in commit `44be6f7`; the replacement is
   `backend/clients/llm/factory.py` (which `agent_graph/langgraph.py` already
   imports correctly). The server cannot start until this is fixed. A stale
   `__pycache__/gemini.cpython-312.pyc` is present but Python will not import
   from it without the source file.
2. **`app.py` imports `GEMINI_MODEL` from `config` but never uses it** — the
   factory reads it. Harmless, but remove it when touching that import block.
3. **`routers/chat.py` binds the exception in
   `except Exception as exc:` and never uses it** — the retrieval failure is
   raised as a bare `HTTPException` with no `logger.exception`, so the original
   Pinecone error is lost. Log it before re-raising.
4. **`ChatRequest` has no `model` field** while the frontend sends one, so the
   UI's provider dropdown is silently ignored. See the root `CLAUDE.md` for what
   honouring it would actually require.
5. **`routers/threads.py::get_all_threads` catches `Exception` and returns a
   flat 500**, defeating the semantic error layer for that one route. Bring it
   in line with `get_thread_messages`, which lets DB exceptions propagate.
