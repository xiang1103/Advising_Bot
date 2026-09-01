# Advising Bot — Repository Guide

Stony Brook University advising chatbot. A Next.js chat UI talks to a FastAPI
backend that answers questions by retrieving bulletin text from Pinecone (RAG)
and streaming a reply from an LLM orchestrated by LangGraph, while persisting
the conversation to Supabase Postgres.

---

## ⚠️ Maintaining this file

**Every code change must update the `CLAUDE.md` files it invalidates, in the
same commit as the code.** These files are the only durable memory future
sessions have; a stale one is worse than a missing one because it is trusted.

Update the relevant `CLAUDE.md` when you:

- add, delete, move, or rename a module, route, table, or column;
- change a contract between layers (request/response shape, exception types,
  ordering guarantees, who is allowed to catch what);
- fix or introduce an edge case that is not obvious from reading the code;
- change how the app is run, configured, or tested;
- resolve one of the "Known drift" items below — delete the entry, don't leave it.

Scope rule: put a fact in the **nearest** `CLAUDE.md` that owns it. Cross-cutting
architecture and anything spanning frontend↔backend belongs here in the root
file. Backend internals belong in `backend/CLAUDE.md`.

---

## System architecture

```
 browser
   │  POST /chat            (streams text/plain chunks back)
   │  GET  /threads         (sidebar list)
   │  GET  /threads/{id}/messages   (lazy history load)
   ▼
 FastAPI  (backend/app.py)
   ├── Pinecone  ── top-k bulletin chunks ──┐
   ├── LangGraph (backend/agent_graph)  ◄───┘  builds prompt, streams tokens
   │      └── PostgresSaver checkpointer  → Postgres  (conversation MEMORY)
   ├── LLM factory → Gemini API | local Ollama
   └── Supabase client (backend/db)       → Postgres  (threads / conversations tables)
```

### Two independent persistence systems — the single most important thing to know

The same conversation is stored **twice**, by two systems that do not know about
each other:

| | LangGraph checkpointer | Application tables |
|---|---|---|
| Written by | `PostgresSaver` inside the graph | `backend/db/supabase_operations.py` |
| Connects via | `LANGGRAPH_CHECKPOINT_URL` (raw Postgres) | `SUPABASE_URL` + service role key (PostgREST) |
| Purpose | what the *model* sees as memory (with summarisation) | what the *user* sees as history in the UI |
| Keyed by | `config.configurable.thread_id` | `threads.id` / `conversations.thread_id` |

They share the **same thread UUID**, generated in the browser
(`crypto.randomUUID()` in `frontend/app/page.tsx`), which is what keeps them
aligned. Consequences to keep in mind:

- These two stores can and do diverge. Persistence to the app tables happens in
  a background task *after* the stream ends; if it fails, the model still
  remembers the turn but the UI will not show it after a reload.
- LangGraph *summarises and deletes* old messages (see `backend/CLAUDE.md`), so
  the checkpoint is deliberately lossy. The `conversations` table is the
  complete record. Never treat one as a backup of the other.
- Deleting a row from `threads` cascades to `conversations` but leaves the
  LangGraph checkpoint rows orphaned. Any future "delete thread" feature must
  clear both.

---

## Layout

| Path | What lives there |
|---|---|
| `backend/` | FastAPI app, routers, LangGraph agent, db layer, clients. See `backend/CLAUDE.md`. |
| `frontend/` | Next.js 16 App Router + React 19 + Tailwind. Single-page chat UI. |
| `ingestion/` | Offline scripts: bulletin scraper → CSV → Pinecone upsert. Not imported by the server at runtime. |
| `supabase/` | Supabase CLI project: `config.toml` and the SQL migrations that define `threads` / `conversations`. |
| `data/` | Scraped CSVs. Gitignored. |
| `pytest.ini` | Sets `pythonpath = .` and `testpaths = backend/tests`. |

---

## Running it

```bash
# terminal 1 — frontend (http://localhost:3000)
cd frontend && npm install && npm run dev

# terminal 2 — backend, from the REPO ROOT (not from backend/)
python -m uvicorn backend.app:app --reload --port 8000

# optional — local model
ollama serve            # port 11434, then set LLM_PROVIDER=ollama
```

**Always run the backend from the repo root.** Every backend module imports
absolutely (`from backend.config import ...`), so the repo root must be the
import root. `pytest.ini` sets `pythonpath = .` to reproduce this for tests.

### Environment (`.env` at repo root, gitignored)

| Variable | Used by | Notes |
|---|---|---|
| `PINECONE_KEY` | `backend/clients/pinecone_driver.py` | read at import time |
| `GEMINI_KEY` | `backend/clients/llm/factory.py` | read at import time |
| `LLM_PROVIDER` | `backend/clients/llm/factory.py` | `gemini` (default) or `ollama` |
| `SUPABASE_URL` | `backend/db/supabase_operations.py` | read at import time |
| `SUPABASE_SERVICE_ROLE_KEY` | `backend/db/supabase_operations.py` | backend is the only writer; bypasses RLS |
| `LANGGRAPH_CHECKPOINT_URL` | `backend/app.py` lifespan | **hard requirement** — startup raises `RuntimeError` without it |

Several modules read `os.getenv` at *import* time, not call time. Setting an env
var after importing the module has no effect — this is why
`backend/tests/conftest.py` goes to such lengths to set the environment before
importing `backend.db.supabase_operations`.

---

## Database

Schema lives in `supabase/migrations/`, applied with `supabase db reset`.

- `threads` — `id uuid PK`, `title text not null default 'New Conversation'`,
  `created_at`, `updated_at`. RLS enabled.
- `conversations` — `id bigint identity PK`, `thread_id uuid → threads(id) ON DELETE CASCADE`,
  `role text CHECK (role in ('user','advising_bot'))`, `content text`, `created_at`.
  RLS enabled.

Two migration-level gotchas already paid for once, documented in the SQL:

- **Grants are not automatic.** Tables created by migration have no Data API
  grants; the `20260825180158_grant_data_api_access.sql` migration grants
  `service_role`. Without it every backend write fails with
  `permission denied for table threads (42501)`. The remote project doesn't hit
  this only because its tables were originally made by hand in the dashboard.
  **Any new table needs an explicit grant to `service_role` in its migration.**
- `anon` and `authenticated` are deliberately granted **nothing**. The browser
  talks to FastAPI, never to PostgREST. Only revisit this alongside real RLS
  policies.
- `threads.updated_at` has **no touch trigger**. Nothing in the app writes it,
  so it always equals `created_at` in practice — see `backend/CLAUDE.md`.

---

## Frontend ↔ backend contract

`frontend/lib/types.ts` mirrors `backend/schema.py`. **Change them together.**

| Frontend type | Backend model |
|---|---|
| `Thread { id, title }` | `ThreadSummary` |
| `Message { role, content, pending? }` | — (`pending` is client-only) |
| `ConversationBlock = Message & { id: number }` | `ConversationBlock` |

- `POST /chat` returns `text/plain` **raw token chunks**, not SSE and not JSON.
  There is no framing, so the client just concatenates. Do not add a JSON
  envelope without updating the reader loop in `frontend/app/page.tsx`.
- The backend URL is hardcoded to `http://localhost:8000` in
  `frontend/lib/api/threads.ts` and inline in `frontend/app/page.tsx`. Deploying
  anywhere means introducing an env-based base URL in **both** places.
- CORS (`backend/app.py`) allows only `localhost`/`127.0.0.1` on any port, via
  `allow_origin_regex`. `allow_origins` is intentionally empty. A deployed
  frontend origin must be added here or every request fails preflight.
- The thread UUID is minted **client-side** before the first message. The server
  never allocates it. `create_thread_table_entry` is therefore called on every
  message, not just the first.
- Title is sent only on the first message of a thread (`""` afterwards), and the
  backend never updates an existing title — see `backend/CLAUDE.md`.

---

## Known drift (fix or delete these entries as they are resolved)

1. **`backend/app.py:13` imports a deleted module.**
   `from backend.clients.llm.gemini import create_model` — `gemini.py` was
   removed in commit `44be6f7` when the provider factory was introduced. The
   surviving module is `backend/clients/llm/factory.py`. The app cannot start
   until this import is corrected. `backend/agent_graph/langgraph.py` already
   imports the factory correctly.
2. **The model picker is inert.** `frontend/app/page.tsx` sends
   `model: "gemini" | "qwen"` in the `/chat` body, but `ChatRequest` in
   `backend/schema.py` declares no `model` field, so Pydantic drops it silently.
   The provider is chosen once at startup from `LLM_PROVIDER`, and the graph is
   compiled with a single model instance for the whole process lifetime.
   Honouring per-request model selection means threading it through
   `build_advising_graph` / `generate_response_stream`, not just adding a field.
3. **`**/__init__.py` is gitignored.** Packages work as implicit namespace
   packages, which is fine for imports but means a deliberately added
   `__init__.py` will never be committed. If you need package-level init code,
   change `.gitignore` first.
