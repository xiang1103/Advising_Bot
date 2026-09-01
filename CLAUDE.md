# Advising Bot — Repository Guide

Stony Brook University advising chatbot. A Next.js chat UI talks to a FastAPI
backend that answers questions by retrieving bulletin text from Pinecone (RAG)
and streaming a reply from an LLM orchestrated by LangGraph, while persisting
the conversation to Supabase Postgres.

**This file is the system-level map.** It covers how the pieces fit together and
anything that spans frontend↔backend. Per-area detail lives in the nested
`CLAUDE.md` files — go there before editing code in that area.

---

## ⚠️ Maintaining these files

**Every code change must update the `CLAUDE.md` files it invalidates, in the
same commit as the code.** These files are the only durable memory future
sessions have; a stale one is worse than a missing one because it is trusted.

Update one when you:

- add, delete, move, or rename a module, route, table, or column;
- change a contract between layers (request/response shape, exception types,
  ordering guarantees, who is allowed to catch what);
- fix or introduce an edge case that is not obvious from reading the code;
- change how the app is run, configured, or tested;
- resolve a listed known issue — **delete the entry**, don't mark it fixed.

**Scope rule: put each fact in the nearest file that owns it, and only there.**
Duplicating a detail up the tree is how these files go stale — the copy gets
missed and then contradicts the code. This file stays general; the children
carry specifics.

| File | Owns |
|---|---|
| `CLAUDE.md` (here) | system architecture, layout, how to run it, environment, frontend↔backend contract |
| `backend/CLAUDE.md` | backend layering rules, composition root, cross-layer invariants |
| `backend/routers/CLAUDE.md` | endpoints, the `/chat` lifecycle, the streaming contract |
| `backend/agent_graph/CLAUDE.md` | graph state, nodes, prompt, summarisation, checkpointing |
| `backend/db/CLAUDE.md` | db operations, exception classification, table invariants |
| `backend/clients/CLAUDE.md` | Pinecone adapter |
| `backend/clients/llm/CLAUDE.md` | LLM provider factory |
| `backend/tests/CLAUDE.md` | the integration suite and its safety guards |
| `frontend/lib/CLAUDE.md` | the API wrappers, their failure semantics, shared types |
| `frontend/components/ui/CLAUDE.md` | component props contracts, which state lives where |
| `supabase/CLAUDE.md` | migrations, DDL, grants, local stack config |
| `ingestion/CLAUDE.md` | scraper, cleaning rules, Pinecone upsert |

`frontend/app/` has no `CLAUDE.md` yet — `page.tsx` is the whole chat
orchestrator (thread state, the streaming `POST /chat` call, the message cache),
so facts about it live here until it gets one.

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

A request is: retrieve context → stream a reply → persist the turn in the
background. The corpus behind the retrieval step is built offline and separately
(`ingestion/`); nothing in that pipeline runs at request time.

### Two independent persistence systems — the single most important thing to know

The same conversation is stored **twice**, by two systems that do not know about
each other:

| | LangGraph checkpointer | Application tables |
|---|---|---|
| Written by | `PostgresSaver` inside the graph | `backend/db/supabase_operations.py` |
| Connects via | `LANGGRAPH_CHECKPOINT_URL` (raw Postgres) | `SUPABASE_URL` + service role key (PostgREST) |
| Purpose | what the *model* sees as memory | what the *user* sees as history in the UI |
| Keyed by | `config.configurable.thread_id` | `threads.id` / `conversations.thread_id` |

They stay aligned only because they share the **same thread UUID**, generated in
the browser. Consequences:

- **They can diverge.** Persistence to the app tables happens in a background
  task after the stream ends; if it fails, the model still remembers the turn
  but the UI will not show it after a reload.
- **The checkpoint is deliberately lossy** — LangGraph summarises and deletes
  old messages. The `conversations` table is the complete record. Neither is a
  backup of the other.
- **Deletes only cascade on one side.** Removing a `threads` row cascades to
  `conversations` but orphans the checkpoint rows. A delete-thread feature must
  clear both stores.

---

## Layout

| Path | What lives there |
|---|---|
| `backend/` | FastAPI app, routers, LangGraph agent, db layer, clients → `backend/CLAUDE.md` |
| `frontend/` | Next.js 16 App Router + React 19 + Tailwind. Single-page chat UI → `frontend/lib/CLAUDE.md`, `frontend/components/ui/CLAUDE.md` |
| `ingestion/` | Offline corpus pipeline: scraper → CSV → Pinecone → `ingestion/CLAUDE.md` |
| `supabase/` | CLI project: local stack config and the SQL migrations → `supabase/CLAUDE.md` |
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

# tests — needs Docker
supabase start && supabase db reset && pytest
```

**Always run the backend from the repo root.** Every backend module imports
absolutely (`from backend.config import ...`), so the repo root must be the
import root. `pytest.ini` sets `pythonpath = .` to reproduce this for tests.

### Environment (`.env` at repo root, gitignored)

| Variable | Used by | Notes |
|---|---|---|
| `PINECONE_KEY` | `backend/clients/pinecone_driver.py` | read at import time |
| `GEMINI_KEY` | `backend/clients/llm/factory.py` | read at import time |
| `LLM_PROVIDER` | `backend/clients/llm/factory.py` | `gemini` (default) or `ollama`; read per call |
| `SUPABASE_URL` | `backend/db/supabase_operations.py` | read at import time |
| `SUPABASE_SERVICE_ROLE_KEY` | `backend/db/supabase_operations.py` | backend is the only writer; bypasses RLS |
| `LANGGRAPH_CHECKPOINT_URL` | `backend/app.py` lifespan | **hard requirement** — startup raises `RuntimeError` without it |
| `SUPABASE_ACCESS_TOKEN` | `supabase` CLI | or use `supabase login` |

"Read at import time" means setting the variable after importing that module has
no effect. See `backend/CLAUDE.md` for why this shapes the test setup.

---

## Database

`supabase/CLAUDE.md` owns the DDL, migrations, grants, and local-stack workflow.
`backend/db/CLAUDE.md` owns how the application uses the tables.

Architecturally: two tables, `threads` (one row per conversation, id minted in
the browser) and `conversations` (one row per message, `ON DELETE CASCADE` from
its thread). The backend is the only client — it connects with the service role
key and bypasses RLS; the browser never talks to PostgREST.

---

## Frontend ↔ backend contract

`frontend/lib/types.ts` mirrors `backend/schema.py`. **Change them together.**

| Frontend type | Backend model |
|---|---|
| `Thread { id, title }` | `ThreadSummary` |
| `Message { role, content, pending? }` | — (`pending` is client-only) |
| `ConversationBlock = Message & { id: number }` | `ConversationBlock` |

The `role` union appears in a third place too — the SQL `CHECK` constraint. All
three must agree.

- **`POST /chat` streams raw `text/plain` token chunks** — no SSE, no JSON, no
  framing; the client just concatenates. Changing that means rewriting the
  reader loop in `frontend/app/page.tsx`. Details in `backend/routers/CLAUDE.md`.
- **The thread UUID is minted client-side** before the first message; the server
  never allocates one. This is what ties the two persistence systems together.
- **Titles are first-message-only.** The client sends a title on the first
  message and `""` afterwards, and the backend never updates an existing title.
- **The backend URL is hardcoded** to `http://localhost:8000` in
  `frontend/lib/api/threads.ts` and inline in `frontend/app/page.tsx`. Deploying
  means introducing an env-based base URL in **both** places.
- **CORS allows only `localhost`/`127.0.0.1`** on any port, via
  `allow_origin_regex` in `backend/app.py`; `allow_origins` is intentionally
  empty. A deployed frontend origin must be added there or every request fails
  preflight.

---

## Known issues

Each area's issues are listed at the bottom of its own `CLAUDE.md`. Two are
worth knowing before you touch anything:

1. **The server does not currently start.** `backend/app.py` imports a module
   that was deleted — see `backend/CLAUDE.md`.
2. **`**/__init__.py` is gitignored.** Packages work as implicit namespace
   packages, which is fine for imports, but a deliberately added `__init__.py`
   will never be committed. Change `.gitignore` first if you need one.
