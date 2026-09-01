# `backend/db/` — persistence layer

All reads and writes to the `threads` / `conversations` tables. Nothing else in
the codebase may touch Supabase directly.

- `supabase_operations.py` — the operations themselves.
- `error_handler.py` — turns driver failures into semantic exceptions.

This layer stores **what the user sees** in the UI. The model's own memory lives
in a separate LangGraph checkpoint store — see the root `CLAUDE.md`. Do not
treat either as a backup of the other.

---

## ⚠️ Maintaining this file

**Update this file in the same commit as any change here.** Especially: a new or
removed operation, a change to sort order or pagination, a new exception class
or a change to the SQLSTATE classification table, a schema change, or a new
invariant a caller now depends on. If you fix an item under "Known issues",
delete the entry.

Schema changes additionally need a migration in `supabase/migrations/` **and an
explicit grant to `service_role`** — see "Schema" below.

---

## The cardinal rule: this layer decides *what kind* of failure, never the status code

```
supabase_operations  ──►  db_operation()  ──►  DatabaseError subclass
                                                      │
                                       app.py handlers ──► 503 / 400 / 500
```

`db/` raises `DatabaseError`, `DatabaseUnavailable`, or `DatabaseRequestError`.
It never imports `fastapi` and never picks a status code. That keeps the module
usable from scripts and tests with no web layer, and it keeps the HTTP mapping
in exactly one place. Routers must **not** catch these — swallowing a
`DatabaseUnavailable` flattens a retryable outage into an indistinguishable 500.

### `db_operation(operation: str)`

A context manager wrapping every Supabase call. It catches `postgrest.APIError`
and `httpx.HTTPError`, classifies them, and re-raises with the original
preserved as `__cause__`. The `operation` string is what appears in logs, so it
should name the function.

**Every new Supabase call must be inside a `db_operation` block.** A call
outside one leaks a raw `APIError` past the semantic layer, and `app.py`'s
handlers will not recognise it.

### Classification (`_classify`)

| Signal | Class | HTTP | Rationale |
|---|---|---|---|
| any `httpx.HTTPError` | `DatabaseUnavailable` | 503 | no response ever arrived: DNS, refused connection, TLS, timeout |
| SQLSTATE `57014` (statement timeout), `53300` (too many connections), `53400` (config limit), `40001` (serialization failure), `40P01` (deadlock) | `DatabaseUnavailable` | 503 | the DB gave up on its own; retry is meaningful |
| SQLSTATE prefix `08` | `DatabaseUnavailable` | 503 | connection exception |
| SQLSTATE prefix `22` (data exception) or `23` (integrity constraint) | `DatabaseRequestError` | 400 | identical retry fails identically |
| `PGRST103` | `DatabaseRequestError` | 400 | requested range not satisfiable |
| integer `code` in `{408,429,500,502,503,504}` | `DatabaseUnavailable` | 503 | postgrest falls back to the raw HTTP status when the error body was not JSON (a proxy or Cloudflare page) |
| any other integer `code` | `DatabaseError` | 500 | |
| any other string `code` | `DatabaseError` | 500 | |
| no `code` at all | `DatabaseError` | 500 | a 401 from the gateway looks like this → our credentials |

**The default is deliberately `DatabaseError` (500):** an unrecognised code is
our bug until proven otherwise. When adding a code to `_TRANSIENT_CODES` or
`_BAD_REQUEST_PREFIXES`, write down why in a comment.

Note that a foreign-key violation is SQLSTATE class `23`, so persisting into a
non-existent thread surfaces as a **400**, not a 500.

Handlers in `app.py` log the full exception and return a fixed generic `detail`.
**Driver messages are never sent to the client.**

---

## Client construction — read this before writing a test or a script

```python
backend_server = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
```

This runs at **module import time**, not on first use. Importing this module
with the wrong environment either raises or — far worse — silently binds to
whatever project the developer's `.env` names. There is no way to repoint it
afterwards short of `importlib.reload`.

This single fact drives the entire design of `backend/tests/conftest.py`, which
sets the environment at conftest import time and imports this module lazily
through a fixture. Any new script that uses these operations must set the
environment before the import, not after.

The service role key **bypasses RLS**. The backend is the only writer; the
browser never talks to PostgREST.

---

## Operations

| Function | Sort order | Called by |
|---|---|---|
| `create_thread_table_entry(id, title)` | — | `routers/chat.py`, on **every** message |
| `save_conversation(thread_id, user_msg, bot_response, ask_time, answer_time)` | inserts user row then bot row | `routers/chat.py` background task |
| `list_all_threads(limit=50)` | `updated_at desc` | `routers/threads.py` |
| `retrieve_thread_conversation(thread_id)` | **oldest first** | `routers/threads.py` |
| `get_history(thread_id, page_num=1, page_size=10)` | **newest first**, paginated | tests only — no route uses it |

### Invariants callers depend on

- **FK ordering.** `conversations.thread_id` references `threads(id)`.
  `create_thread_table_entry` must complete before `save_conversation`.
  Pinned by `test_save_conversation_rejects_unknown_thread`.
- **Idempotent thread creation.** The upsert uses
  `on_conflict="id", ignore_duplicates=True`, so **a title is never updated
  after the row exists.** The frontend cooperates by sending `""` for non-first
  messages, and `create_thread_table_entry` omits the `title` key entirely when
  it is falsy so the column default applies. A rename feature needs a separate
  `.update()`, not a change to this upsert. Pinned by
  `test_create_thread_table_entry_is_idempotent`.
- **A turn is one insert.** `save_conversation` writes both rows in a single
  `insert([...])` call so the user/bot pair is atomic — the UI never renders a
  question with no answer row, or vice versa.
- **`id` is the ordering tiebreak.** `created_at` is `clock_timestamp()`
  precision and the two rows of one turn can tie, which would render the bot
  before the user. Both history queries add a secondary `.order("id")` for this
  reason. Keep it on any new ordered query.
- **Two functions sort in opposite directions.** `retrieve_thread_conversation`
  is oldest-first because that is the order the frontend renders bubbles;
  `get_history` is newest-first for pagination. Do not substitute one for the
  other.
- **Timestamps are normalised to UTC ISO strings** in `save_conversation`
  (`.astimezone(timezone.utc).isoformat()`) for JSON serialisability. A naive
  datetime passed in is interpreted as local time; callers should use
  `config.TIMEZONE` (UTC).
- **`get_history` validates `page_num >= 1` locally** because a `page_num` of 0
  produces a negative `OFFSET`, which Postgres rejects with a 400 only after a
  full round trip.

---

## Schema

Defined in `supabase/migrations/`, applied with `supabase db reset`.

```sql
threads(
  id uuid primary key,                      -- minted in the BROWSER, not here
  title text not null default 'New Conversation',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()   -- no touch trigger
)

conversations(
  id bigint generated always as identity primary key,
  thread_id uuid not null references threads(id) on delete cascade,
  role text not null check (role in ('user','advising_bot')),
  content text not null,
  created_at timestamptz not null default clock_timestamp()
)
```

Two traps already paid for once:

- **Grants are not automatic.** Tables created by migration have no Data API
  grants, and every backend write fails with
  `permission denied for table threads (42501)`. The remote project does not hit
  this only because its tables were made by hand in the dashboard, which grants
  automatically. `20260825180158_grant_data_api_access.sql` fixes it.
  **Any new table needs `grant select, insert, update, delete … to service_role`
  in its own migration.** `anon` and `authenticated` are deliberately granted
  nothing.
- **RLS is enabled on both tables** and `service_role` bypasses it, so it is
  free for the backend today. It exists so the tables stay closed by default if
  `anon`/`authenticated` are ever granted access. Revisit only alongside real
  policies.

`role` values must stay in sync across three places: the SQL `CHECK`, the
`Literal["user","advising_bot"]` in `backend/schema.py`, and the union in
`frontend/lib/types.ts`.

---

## Adding an operation

1. Wrap the Supabase call in `with db_operation("your_function_name"):`.
2. Validate arguments that would otherwise cost a round trip to reject (see
   `get_history`'s page bounds).
3. Raise `DatabaseRequestError` — not `ValueError` — for caller mistakes, so the
   error reaches `app.py`'s handlers as a 400.
4. Add a secondary `.order("id")` to any ordered query.
5. If it touches a new table, add the migration **and** the `service_role` grant.
6. Add an integration test for the property the routers depend on (ordering,
   idempotency, FK behaviour), not for the Supabase client itself.
7. Update this file.

---

## Known issues (delete when fixed)

1. **`list_all_threads` orders by `updated_at`, which nothing ever writes.**
   There is no touch trigger (the migration only sets a default) and no code
   path updates the column, so the sidebar is effectively ordered by *creation*
   time. `test_list_all_threads_is_newest_first_and_respects_limit` sets
   `updated_at` by hand precisely because the app never does. To make the
   sidebar reflect recent activity, add a trigger or an explicit update inside
   `save_conversation`.
2. **`get_history`'s secondary `.order("id")` is ascending while `created_at` is
   descending.** On a tie this reverses the pair within a turn. It has not
   mattered because a question and its answer have different timestamps, but a
   caller relying on strict newest-first should change it to
   `.order("id", desc=True)`.
3. **Inconsistent argument-validation exceptions.** `create_thread_table_entry`
   intends `DatabaseRequestError` (→ 400) for a falsy id — though see (4) — while
   `save_conversation` raises a plain `ValueError` for empty inputs, and
   `get_history` a `ValueError` for bad paging. `ValueError` is not caught by
   `app.py`'s handlers and would become a generic 500 from the middleware. This
   is only safe today because its sole caller (`persist_conversation`)
   pre-checks for an empty response and catches everything.
4. **`create_thread_table_entry` raises `TypeError`, not `DatabaseRequestError`,
   on a falsy id.** It calls
   `DatabaseRequestError(operation="create_thread_table_entry requires a thread id")`
   with no positional `message`, but `DatabaseError.__init__(self, message, *, operation, code=None)`
   requires one — so the guard raises
   `TypeError: DatabaseError.__init__() missing 1 required positional argument: 'message'`
   instead. That escapes the semantic layer entirely and becomes a generic 500
   from the middleware. Unreachable today only because `ChatRequest.thread_id`
   is a validated `UUID` and can never be falsy. Fix:
   `DatabaseRequestError("thread id is required", operation="create_thread_table_entry")`.
5. **`get_history` is reachable only from tests** — no route calls it. Either
   wire up paginated history or delete it; a query nothing exercises in
   production will drift out of sync with the UI's needs.
