# `backend/tests/` — integration suite

The whole suite is **integration tests against a real local Supabase stack**.
There are no unit tests and no mocks, by design: the thing under test is the
persistence seam that `/chat` depends on — real Postgres, the real schema, the
real foreign key, and the real PostgREST layer in between — and that is exactly
what mocking cannot verify.

Every test asserts a property `backend/routers/chat.py` already relies on today.
**A failure here means the endpoint is broken, not that a test is fussy.**

---

## ⚠️ Maintaining this file

**Update this file in the same commit as any change here.** Especially: a new
fixture, a change to the credential discovery or the localhost guard, a change
to the truncation strategy, or new coverage that closes one of the gaps listed
below. When you add a db operation, add a test for the property the routers
depend on and record it here.

---

## Running

```bash
supabase start && supabase db reset     # Docker must be running
pip install -r requirements-dev.txt     # pytest + psycopg
pytest                                  # from the REPO ROOT
```

`pytest.ini` at the repo root sets `pythonpath = .` and `testpaths =
backend/tests`, so bare `pytest` works and `import backend.*` resolves the same
way it does under `python -m uvicorn backend.app:app`. Running pytest from
inside `backend/` will not.

Everything is marked `pytest.mark.integration` (declared in `pytest.ini`), so
`-m "not integration"` skips the lot.

**The suite skips, rather than fails, when the stack is down** — CLI missing,
Docker down, `supabase start` not run. A skip here is not a pass; it means
nothing was verified.

---

## `conftest.py` — why it is as complicated as it is

### Credentials are discovered at conftest *import* time

`backend/db/supabase_operations.py` builds its Supabase client at **module
import time** from `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`. So the
environment has to be correct before that import happens, not before the first
test runs. Hence:

- the module-level block in `conftest.py` shells out to `supabase status -o env`
  and writes `os.environ` immediately, before any test module is imported;
- the `ops` fixture imports the module **lazily** via `importlib.import_module`.

Import it at the top of a test file instead and it either blows up or — worse —
silently binds to whatever project the developer's `.env` names.

`supabase status -o env` prints shell-style `KEY="value"` lines, which is a
stable contract across CLI versions even as key *names* change; `_pick` accepts
either spelling (`SERVICE_ROLE_KEY`/`SECRET_KEY`,
`ANON_KEY`/`PUBLISHABLE_KEY`) so a CLI upgrade does not break the suite.

### The localhost guard is not optional

`clean_tables` runs `truncate table public.threads restart identity cascade`
before **every** test. Pointed at a real project, that is unrecoverable.

`_assert_local` checks both `SUPABASE_URL` and `DB_URL` against
`("127.0.0.1", "localhost", "0.0.0.0")` and calls `pytest.exit(returncode=1)` —
aborting the whole session, not just failing one test — if either is not local.
**Never weaken or bypass this.** The environment override in the module-level
block also deliberately clobbers whatever the developer's shell or `.env` says.

### Truncation happens *before* each test, not after

So a failed test leaves its rows behind for inspection. `RESTART IDENTITY` keeps
`conversations.id` predictable run to run; `CASCADE` follows the
`conversations → threads` foreign key.

### Fixtures

| Fixture | Scope | Purpose |
|---|---|---|
| `local_supabase` | session | the discovered credentials, or a clean skip if the stack is down; asserts localhost |
| `ops` | session | `backend.db.supabase_operations`, imported lazily *after* the env is set |
| `db` | session | a direct `psycopg` connection for setup/teardown |
| `clean_tables` | function, autouse | truncates before each test |

`db` talks to Postgres **directly, bypassing PostgREST**, so teardown stays
independent of the layer the tests are exercising. A broken PostgREST must fail
the assertions, not silently break cleanup.

---

## Current coverage (`test_conversation_persistence.py`)

| Test | Property pinned |
|---|---|
| `test_thread_and_conversation_round_trip` | a turn goes in and comes back as `[user, advising_bot]` with content intact |
| `test_create_thread_table_entry_is_idempotent` | called on every message, it neither errors nor clobbers the stored title (`ignore_duplicates=True`) |
| `test_save_conversation_rejects_unknown_thread` | the FK fails loudly rather than dropping the exchange — this is what pins the call ordering inside `/chat` |
| `test_history_preserves_turn_order_across_many_turns` | strict user→bot alternation across turns |
| `test_history_is_scoped_to_its_thread` | no bleed between conversations (the bot would answer with another student's context) |
| `test_get_history_paginates_without_gaps_or_duplicates` | paging partitions the thread exactly; past-the-end is `[]` |
| `test_list_all_threads_is_newest_first_and_respects_limit` | sidebar ordering and `limit` |
| `test_deleting_a_thread_removes_its_conversations` | `ON DELETE CASCADE` still holds |

Helpers: `record_turn` saves one exchange the way
`routers.chat.persist_conversation` does (question stamped on arrival, answer
when the stream ends); `chronological` reverses one full page of the newest-first
`get_history` for readable order assertions. `BASE_TIME` is a fixed UTC instant
so timestamps never depend on the clock.

`test_list_all_threads_is_newest_first_and_respects_limit` sets `updated_at` by
hand **because the application never does** — there is no touch trigger on that
column. It is testing the query's ordering, not the app's.

---

## Writing a new test

1. Assert a property a **router actually depends on** — ordering, idempotency,
   FK behaviour, scoping. Do not test the Supabase client.
2. Go through `ops`, not raw SQL, for the thing under test; use the `db` fixture
   only for setup and teardown.
3. Use `uuid4()` for thread ids and fixed offsets from `BASE_TIME` for
   timestamps.
4. Say in the docstring *what breaks in production* if the assertion fails. Every
   existing test does this and it is why they are worth keeping.

---

## Known gaps

Nothing here covers, and none of it is currently tested anywhere:

1. **The routers.** No `TestClient` coverage of `/chat`, `/threads`, or
   `/threads/{id}/messages` — including the streaming contract, the background
   task actually firing, and the `create_thread_table_entry`-before-
   `save_conversation` ordering *as invoked by the endpoint* (only the db-level
   consequence is pinned).
2. **`db/error_handler.py`.** The SQLSTATE → exception classification table is
   pure logic with no I/O and would be cheap to unit test; today it is entirely
   unverified, and a wrong entry silently changes a 503 into a 500.
3. **`agent_graph/langgraph.py`.** No coverage of the summarisation trigger, the
   `RemoveMessage` pruning, or the two content shapes in
   `generate_response_stream` — the last of which fails *silently* (empty
   reply) rather than raising.
4. **`clients/`.** No coverage of the soft-hyphen strip or the `top_k` clamp.
5. **Response-model validation.** A `conversations` row with an out-of-range
   `role` should surface as a failed response validation; untested.
