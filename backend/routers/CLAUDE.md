# `backend/routers/` — HTTP endpoints

Every HTTP route the service exposes lives here (plus `/health`, defined inline
in `app.py`). Routers are the **only** layer that knows about HTTP. Read
`backend/CLAUDE.md` for the layering rules this directory is bound by.

---

## ⚠️ Maintaining this file

**Update this file in the same commit as any change to a route.** That includes:
a new/removed/renamed endpoint, a change to a request or response shape, a
change to which exceptions a route allows to propagate, a change to the ordering
of calls inside `chat()`, or anything about the streaming contract. If you fix
an item under "Known issues", delete the entry.

---

## Routes

| Method | Path | Handler | Response |
|---|---|---|---|
| POST | `/chat` | `chat.py::chat` | `StreamingResponse`, `text/plain; charset=utf-8` |
| GET | `/threads` | `threads.py::get_all_threads` | `list[ThreadSummary]` |
| GET | `/threads/{thread_id}/messages` | `threads.py::get_thread_messages` | `list[ConversationBlock]` |

Both routers are registered in `app.py` via `app.include_router(...)`. Each
declares its own `prefix` and `tags`; the prefix is **not** repeated in the
decorator. `chat.py` uses `@router.post("")` with `prefix="/chat"`, so the real
path is exactly `/chat` — note that a client POSTing to `/chat/` gets a 307
redirect, and some HTTP clients drop the body on redirect. The frontend posts to
`/chat` with no trailing slash; keep it that way.

---

## Validation happens before your handler runs

Request bodies are Pydantic models from `backend/schema.py`. Consequences:

- `ChatRequest.thread_id` is typed `UUID`, so a malformed id is a **422 from
  FastAPI**, not something the handler ever sees. Handlers convert back with
  `str(payload.thread_id)` before touching the db layer, because the Supabase
  client serialises to JSON and a `UUID` object is not JSON-serialisable.
- **Undeclared fields are silently dropped.** If a client sends a field and it
  seems to have no effect, check `schema.py` first.
- **`ChatRequest.model` is a plain `str | None`, not a `Literal`**, so an
  unrecognised model is **not** a 422 from Pydantic. The valid set lives in
  `config.SELECTABLE_MODELS`, and the registry rejects a bad one with a 400.
  `None` means "the client did not choose", and the router falls back to
  `DEFAULT_MODEL` — that is what keeps a client that omits the field working.
- Return annotations (`-> list[ThreadSummary]`) are enforced as **response**
  models. `retrieve_thread_conversation` hands back raw dicts from PostgREST; if
  a row's `role` is not `"user"` or `"advising_bot"`, response validation fails
  and the client gets a 500. That is deliberate — it catches a bad row here
  rather than rendering as an unstyled bubble in the UI. The DB `CHECK`
  constraint and the `Literal` in `schema.py` must stay in sync.

---

## `POST /chat` — lifecycle, in order

The ordering in `chat.py::chat` is load-bearing. Read this before editing it.

1. **`asked_at = datetime.now(TIMEZONE)`** is captured first, before any slow
   call, so the stored question timestamp reflects arrival rather than
   completion. `TIMEZONE` is UTC from `config.py`; never use a naive
   `datetime.now()` here.

2. **`graph_registry.get(payload.model)` resolves the model before anything
   else is spent.** An unknown id raises `UnknownModelError` → 400 here, so a
   bad selection costs no Pinecone query and writes no `threads` row. This is
   also where a model is **built**, on the first request that selects it, so the
   call is fallible and must stay above the `return` with everything else. The
   selection is logged here; the model that *actually* answers is logged by
   `generate_response_stream`. Two lines, on purpose — see
   `agent_graph/CLAUDE.md`.

3. **All fallible work happens before the `StreamingResponse` is returned.**
   Retrieval (`get_pc_index` → `pc_search` → `retrieve_topk_text`) runs up front
   and raises `HTTPException(500)` on failure.
   **This is not stylistic.** Once a streaming response has begun, the status
   line and headers are already on the wire and cannot be changed — a failure
   after that point can only be reported as text inside a `200 OK`. Any new
   fallible step you add must go **above** the `return`.

4. **`create_thread_table_entry(thread_id, thread_title)` runs before anything
   can write to `conversations`,** because `conversations.thread_id` is a
   foreign key. Reversing these two calls silently loses every message.
   `tests/test_conversation_persistence.py::test_save_conversation_rejects_unknown_thread`
   exists to pin exactly this. This call is intentionally **not** wrapped in a
   `try` — its `DatabaseError` propagates to `app.py`'s handlers and becomes a
   real 503/400/500, which is still possible because streaming has not started.

5. **A `collected_convo: list[str]` sink is shared by reference** between the
   generator and the background task. `token_generator` appends each chunk as it
   yields; `persist_conversation` reads the same list object after the stream
   ends.
   **Never rebind the sink** — `sink = [...]`, `sink = sink + [...]`, or
   reassigning inside the generator leaves the background task holding the
   original, empty list. Only `.append()`.

6. **`BackgroundTasks` is attached to the response**, so persistence runs after
   the last byte is sent. This is why the reply feels instant and the DB write
   never blocks the stream.

### Streaming contract

- The body is **raw concatenated token text**, not SSE and not JSON. There is no
  framing, no event names, no terminator. `frontend/app/page.tsx` just appends
  every decoded chunk. Adding a JSON envelope means rewriting that reader loop.
- `token_generator` catches everything, logs it, and yields
  `"\n\nAdvising Bot failed to finish generating this response."`. It
  **deliberately does not clear the sink**: a partial answer is still worth
  persisting, and a client that disconnects mid-stream still gets what it saw
  saved.
- `persist_conversation` early-returns on an empty sink. This matters —
  `save_conversation` raises `ValueError` on empty `bot_response`, and inside a
  background task no exception handler can turn that into a response. It also
  wraps everything in `try/except` + `logger.exception`, because a persistence
  failure must never break an already-delivered stream.
- `answered_at` is stamped inside `persist_conversation`, i.e. when the stream
  finished, not when it started. The two timestamps bracket the turn.

### Error surfaces on `/chat`

| Failure | What the client sees |
|---|---|
| Bad UUID / missing field | 422 (FastAPI validation) |
| Unknown `model` value | 400 `"Unsupported model selection."` |
| Pinecone retrieval fails | 500 `"Failed to extract factual information for model"` |
| `create_thread_table_entry` fails | 503 / 400 / 500 from `app.py`'s DB handlers |
| LLM fails mid-stream | 200, with the failure marker appended to the body |
| Persistence fails | 200, nothing visible — logged server-side only |
| Anything else | generic JSON 500 from `catch_unexpected_exceptions` middleware |

---

## `threads.py`

- **`get_all_threads`** — the sidebar. Returns `id` and `title` only; message
  content is loaded lazily by the second route. Ordered `updated_at desc`, but
  be aware **nothing ever writes `updated_at`** (see `backend/db/CLAUDE.md`), so
  in practice this is creation order.
- **`get_thread_messages`** — the lazy half. **Catches nothing on purpose.** The
  comment in the code says why: the db layer raises `DatabaseError` subclasses
  that `app.py` maps to 503/400/500, and swallowing them would flatten a
  transient outage into an indistinguishable 500, so the frontend would stop
  retrying. An empty list is a valid answer for a thread that exists only in the
  browser (started but never chatted in) — it is **not** a 404.

`get_all_threads` still wraps everything in a blanket `except Exception` → 500.
That is older code and contradicts the rule above; prefer the
`get_thread_messages` style for anything new.

---

## Adding a route

1. Define request/response models in `backend/schema.py`, and mirror them in
   `frontend/lib/types.ts` if the browser touches them.
2. Put it on an existing router if the prefix fits, otherwise create a new
   module here and `include_router` it in `app.py`.
3. **Let `DatabaseError` subclasses propagate.** Do not catch them.
4. If the route streams, do every fallible thing before returning the response.
5. Add an integration test for the db property the route depends on.
6. Update this file and, if the contract crosses the wire, the root `CLAUDE.md`.

---

## Known issues (delete when fixed)

1. **The Pinecone `except` in `chat()` discards the exception.** `except Exception as exc:` binds
   `exc` and never uses it — no `logger.exception`, so the original Pinecone
   error is lost and only the generic detail string survives. Log it before
   raising.
2. **`get_all_threads` flattens the semantic error layer** (see above).
