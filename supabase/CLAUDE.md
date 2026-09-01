# `supabase/` — database project (migrations, local stack, config)

The Supabase CLI project that defines the `threads` / `conversations` schema and
runs the local Postgres + PostgREST stack the integration tests need.

**This directory is the source of truth for the schema.** The backend only ever
reads and writes through `backend/db/`; it never creates or alters anything. If
the database needs to change, it changes here, in a migration.

Related: `backend/db/CLAUDE.md` documents how the application *uses* these
tables and the invariants its callers depend on.

---

## ⚠️ Maintaining this file

**Update this file in the same commit as any change here.** Especially: a new
migration, a change to `config.toml` that affects ports or the API schema
exposure, a change to seeding, or a new operational gotcha you had to debug. If
you fix an item under "Known issues", delete the entry.

**A schema change is not done until:** the migration exists here, the grant is
included (see below), `backend/db/CLAUDE.md` reflects the new shape,
`backend/schema.py` and `frontend/lib/types.ts` agree with any changed
enum/column, and there is an integration test for whatever the routers now rely
on.

---

## Layout

```
supabase/
├── config.toml     local stack configuration (ports, API schemas, auth, storage)
├── migrations/     the schema, in timestamp order — the source of truth
├── snippets/       empty; Studio SQL snippets land here
├── .branches/      CLI state (gitignored)  — currently "main"
└── .temp/          CLI state (gitignored)  — linked project ref, versions
```

`.branches/` and `.temp/` are gitignored and are **CLI scratch state, not
inputs**. `.temp/project-ref` and `.temp/linked-project.json` identify the linked
remote project; do not edit them by hand, and do not commit them.

---

## Commands

```bash
supabase login                  # or set SUPABASE_ACCESS_TOKEN
supabase start                  # boot the local stack (needs Docker Desktop)
supabase db reset               # drop, recreate, replay every migration, re-seed
supabase migration list         # what is tracked locally vs. applied remotely
supabase migration new <name>   # scaffold a timestamped file
supabase db push                # apply local migrations to the REMOTE project
supabase status -o env          # print URLs + keys (what tests/conftest.py parses)
supabase stop
```

- **`supabase db reset` is the local workflow.** It is destructive and that is
  the point — it proves the migrations alone can build the database from
  nothing, which is exactly what the "grants" trap below breaks.
- **`supabase db push` writes to the remote project.** Check
  `supabase migration list` first, and be aware the remote's tables were
  originally created by hand in the dashboard, so its state is not purely a
  replay of this folder.
- `supabase status -o env` prints shell-style `KEY="value"` lines. That output
  is a contract: `backend/tests/conftest.py` parses it to discover local
  credentials. Do not assume specific key *names* — the CLI has renamed them
  (`SERVICE_ROLE_KEY`→`SECRET_KEY`, `ANON_KEY`→`PUBLISHABLE_KEY`) and the
  conftest accepts either.

---

## Migrations

Applied in filename timestamp order. Never edit an applied migration — add a new
one.

| File | What it does |
|---|---|
| `20260730230602_create_conversations.sql` | `drop table if exists public.conversations cascade` — wipes the hand-made table that was never tracked |
| `20260804181422_create_conversations_table.sql` | creates `public.threads` and `public.conversations`; enables RLS on `threads` |
| `20260825180158_grant_data_api_access.sql` | grants `service_role` on both tables; enables RLS on `conversations` |

Note the first migration is a **teardown**, not a creation — its name is
misleading. It exists because the original tables were created by hand in the
dashboard and never tracked, and the remote data was disposable. On a fresh
database it is a harmless no-op (`if exists`).

### Current schema

```sql
threads(
  id          uuid primary key,                 -- minted in the BROWSER, not by the db
  title       text not null default 'New Conversation',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()      -- no touch trigger
)

conversations(
  id          bigint generated always as identity primary key,
  thread_id   uuid not null references public.threads(id) on delete cascade,
  role        text not null check (role in ('user','advising_bot')),
  content     text not null,
  created_at  timestamptz not null default clock_timestamp()
)
```

Design notes recorded in the SQL and worth keeping in mind:

- **`threads.id` is a client-generated UUID.** Postgres does the implicit cast
  from the string the backend sends. There is no server-side default and no
  sequence — the browser is the allocator.
- **`conversations.id` is a bigint identity, not a uuid**, unlike `threads.id`.
  It is also the ordering tiebreak within a turn, because
  `clock_timestamp()` can produce a tie between a question and its answer.
- **`ON DELETE CASCADE`** means deleting a thread removes its messages.
  `test_deleting_a_thread_removes_its_conversations` pins this. It does **not**
  touch the LangGraph checkpoint rows, which live in their own tables — a
  delete-thread feature must clear both stores.
- **The `role` CHECK is one of three places that enum lives.** The others are
  `Literal["user","advising_bot"]` in `backend/schema.py` and the union in
  `frontend/lib/types.ts`. Change all three together.

### ⚠️ Grants are not automatic — the trap this project already hit

Tables created **by migration** get no Supabase Data API grants, so every
backend write fails with:

```
permission denied for table threads (42501)
```

The remote project does not hit this only because its tables were originally
created by hand in the dashboard, which applies grants automatically. Anything
provisioned from migrations alone — a fresh local stack, staging, a restored
project — is broken without an explicit grant.

**Every new table needs, in its own migration:**

```sql
grant select, insert, update, delete on public.<table> to service_role;
```

`anon` and `authenticated` are deliberately granted **nothing**: the browser
talks to FastAPI, never to PostgREST. Only revisit that alongside real RLS
policies.

### RLS

Enabled on both tables. `service_role` bypasses RLS, so today this costs the
backend nothing — it exists so the tables stay closed by default if
`anon`/`authenticated` are ever granted access. There are **no policies defined**,
which means the moment a non-service role is granted access it will read
nothing until policies are written. That is the intended failure direction.

---

## `config.toml` — what actually matters here

Mostly CLI defaults. The parts that interact with this project:

| Setting | Value | Why it matters |
|---|---|---|
| `project_id` | `Advising_Bot` | names the local Docker containers |
| `api.port` | `54321` | the local `SUPABASE_URL` base; tests discover it rather than hardcode it |
| `api.schemas` | `["public", "graphql_public"]` | a table outside `public` is **not** reachable through PostgREST |
| `api.max_rows` | `1000` | hard cap on rows per PostgREST request — `list_all_threads(limit=50)` is well under, but a future unpaginated query would silently truncate at 1000 |
| `db.port` | `54322` | the direct Postgres port the tests' `psycopg` connection uses |
| `db.major_version` | `17` | should match the remote project's Postgres major version |
| `db.seed.sql_paths` | `["./seed.sql"]` | seeding is **enabled but the file does not exist** — see Known issues |
| `auth.site_url` | `http://127.0.0.1:3000` | vestigial; this project has no auth flow |
| `studio.port` | `54323` | local dashboard |

Auth, storage, realtime, and the third-party auth providers are all at defaults
and **unused** — the app has no users and the browser never talks to Supabase.
Do not read the auth config as a statement of intent.

---

## Adding a migration

1. `supabase migration new <descriptive_name>` — never hand-name a file, the
   timestamp prefix is the ordering.
2. Write forward-only SQL. Do not edit a migration that has already been
   applied anywhere.
3. **Include the `service_role` grant** for any new table, in the same file.
4. Enable RLS on any new table, for the same defence-in-depth reason as above.
5. `supabase db reset` locally and run `pytest` — reset is what proves the
   migrations are self-sufficient.
6. Update this file, `backend/db/CLAUDE.md`, and any of `backend/schema.py` /
   `frontend/lib/types.ts` the change touches.
7. `supabase db push` only when you mean to change the remote.

---

## Known issues (delete when fixed)

1. **`db.seed.sql_paths` points at `./seed.sql`, which does not exist.** Seeding
   is enabled in config but there is no seed file, so `supabase db reset`
   produces an empty database. Fine today — the tests build their own
   fixtures — but create the file or disable seeding rather than leaving the
   config lying.
2. **`threads.updated_at` has no touch trigger.** The column exists and defaults
   to `now()`, but nothing ever updates it, while `list_all_threads` orders by
   it. The sidebar is therefore ordered by creation time, not activity. Fix
   either with a trigger here or an explicit update in `save_conversation`.
3. **The first migration's filename says "create" but its body drops a table.**
   Harmless, but misleading when scanning `supabase migration list`.
4. **Local and remote schemas are not provably identical.** The remote was
   bootstrapped by hand before migrations existed; only the local stack is
   guaranteed to be a pure replay of this folder. Treat a remote-only surprise
   as plausible rather than impossible.
