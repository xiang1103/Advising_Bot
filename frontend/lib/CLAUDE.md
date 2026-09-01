# `frontend/lib/` — backend contract and shared types

Everything the UI knows about the server lives here (or should — see "Where the
chat call actually lives"). Two things matter in this directory: the type
definitions that mirror the backend's Pydantic models, and the fetch wrappers
that decide what a failed request *means* to the caller.

```
lib/
├── types.ts        Thread, Message, ConversationBlock — mirrors backend/schema.py
├── api/threads.ts  GET /threads, GET /threads/{id}/messages
└── utils.ts        cn(), PLACEHOLDERS, and a stale mock export
```

---

## ⚠️ Maintaining this file

**Update this file in the same commit as any change here.** Especially: a type
that no longer matches `backend/schema.py`, a new API wrapper, a change to what
a wrapper returns on failure, or a change to the base URL strategy. If you fix
an item under "Known issues", delete the entry.

**A change to `types.ts` is a change to a three-way contract** — see below.
Never edit it alone.

---

## The type contract

`types.ts` mirrors `backend/schema.py`. **The root `CLAUDE.md` holds the
type-to-model mapping table** — this is the frontend side of it, and the two must
change together.

Notes that are easy to get wrong on this side:

- **`Thread.id` is a `string`, not a UUID type**, because the browser is what
  generates it (`crypto.randomUUID()`) and JS has no UUID primitive. The backend
  parses it into a real `UUID` and rejects a malformed one with a 422.
- **`ConversationBlock.id` is a number** — a Postgres bigint identity — while
  `Thread.id` is a uuid string. Two different id schemes in one app.
- **`role` lives in three places**: this union, the `Literal` in
  `backend/schema.py`, and the SQL `CHECK` constraint. All three must agree or a
  stored row fails response validation and the client gets a 500.
- **`pending` never crosses the wire.** It marks an assistant bubble that is
  awaiting or streaming its first tokens, so the UI can show typing dots.

---

## `api/threads.ts` — the two read calls

Both are plain `fetch` with `cache: "no-store"` (this data is per-user and
changes constantly; Next's default caching would serve a stale sidebar).

### The important design decision: `[]` vs `null`

| Function | On success | On failure | Why |
|---|---|---|---|
| `fetchThreads()` | `Thread[]` | `[]` | the sidebar has nothing better to render |
| `fetchThreadMessages(id)` | `Message[]` | **`null`** | `[]` is a *legitimate* answer |

`fetchThreadMessages` must distinguish the two because **the caller caches what
it gets back**. A thread that exists only in the browser — started but never
chatted in — genuinely has no messages, and the backend correctly returns `[]`
rather than a 404. If a failed request also returned `[]`, `page.tsx` would
cache that empty array and never retry, permanently showing an existing
conversation as blank. Returning `null` means "not fetched", and the caller
leaves the cache key unset so the next click retries.

**Do not "simplify" this to return `[]` on error.** It is the difference between
a transient failure and permanent data loss in the UI.

`fetchThreads` does not have this problem: the sidebar is refetched on mount and
an empty list is visually indistinguishable from a failure anyway. It is a
weaker guarantee, accepted deliberately.

### The id is stripped on the way in

`fetchThreadMessages` maps `ConversationBlock[]` → `Message[]`, dropping the
database `id`. That is intentional: streamed messages have no db id, so `id`
could never serve as a React key, and carrying a field the UI cannot use
invites someone to try. `page.tsx` keys on array index instead, which is safe
because messages are append-only.

### Failure handling

Both wrappers `console.error` and return their fallback — they never throw. The
caller has no error UI for the sidebar or history, so a rejected promise would
just become an unhandled rejection. If you add error surfacing, change the
signatures deliberately rather than letting exceptions escape.

---

## Where the chat call actually lives

**`POST /chat` is not in this directory.** It is inline in
`frontend/app/page.tsx`, because it streams: it needs the response body reader,
the incremental state updates, and the abort/interruption handling, none of
which fit the "fetch and return JSON" shape of the wrappers here.

A side effect is that the backend base URL is hardcoded twice — `API_BASE_URL`
here and a literal in `page.tsx` (the root `CLAUDE.md` covers what that means for
deployment). Moving the streaming call into this directory, returning an async
iterator, would fix that and is the obvious refactor if anyone touches it.

The wire format for that call — raw `text/plain` token chunks, no framing — is
documented in `backend/routers/CLAUDE.md`.

---

## `utils.ts`

- **`cn(...classes)`** — the class-name joiner every component uses. Note this is
  a hand-rolled `filter(Boolean).join(" ")`, **not** shadcn's usual
  `clsx` + `tailwind-merge`. It does not de-duplicate conflicting Tailwind
  classes, so passing `className="p-2"` to a component that already sets `p-3`
  yields both and the CSS cascade decides. `components.json` points shadcn's
  generator at this file, so newly generated components will import it expecting
  the full behaviour.
- **`PLACEHOLDERS`** — the rotating input suggestions, consumed by
  `AIChatInput`.
- **`threads`** — a hardcoded three-item mock array, left over from before the
  sidebar was network-backed. **Nothing imports it.** See "Known issues".

---

## Adding an API call

1. Put it here, not in a component — components should not know URLs.
2. Decide explicitly what failure returns, and write down why. If `[]`/`{}` is a
   valid success value, failure must be distinguishable from it.
3. Use `cache: "no-store"` for anything per-user.
4. Mirror any new response shape in `types.ts` **and** `backend/schema.py`.
5. Update this file.

---

## Known issues (delete when fixed)

1. **`utils.ts` exports a stale `threads` mock** with `thread-1`/`thread-2`
   ids that are not valid UUIDs. Nothing imports it, but it will mislead anyone
   who finds it before finding `fetchThreads`, and pasting one of those ids into
   a request would 422. Delete it — it also makes `utils.ts` import from
   `types.ts` for no reason.
2. **`Message` is imported in `utils.ts` but never used.**
3. **The base URL is hardcoded in two files** — see above.
4. **No request timeouts or cancellation.** Neither wrapper passes an
   `AbortSignal`, so switching threads rapidly leaves earlier requests in
   flight. `page.tsx` guards against the *state* corruption this could cause,
   but the requests themselves are never cancelled.
