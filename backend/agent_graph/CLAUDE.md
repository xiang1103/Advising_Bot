# `backend/agent_graph/` — LangGraph conversation engine

`langgraph.py` owns everything about how a reply is produced: the conversation
state, the prompt, the summarisation policy that keeps context bounded, and the
token stream handed to `routers/chat.py`. It is the only place that talks to the
LLM at request time.

This module knows nothing about HTTP, and nothing about the `threads` /
`conversations` tables. Its memory is the **LangGraph checkpoint**, which is a
separate store — see the root `CLAUDE.md`.

---

## ⚠️ Maintaining this file

**Update this file in the same commit as any change here.** Especially: adding
or renaming a node or edge, changing `AdvisingState`, changing `SYSTEM_ROLE`,
changing the summarisation policy or `max_messages`, or adding a provider whose
streamed content has a different shape. If you fix an item under "Known issues",
delete the entry.

---

## The graph

```
START ──► chatbot ──┬──► summarize_node ──► END      when len(messages) > max_messages
                    └──► END                          otherwise
```

Built by `build_advising_graph(model=None, max_messages=8)`, which returns an
**uncompiled** `StateGraph`. `app.py` compiles it once at startup with the
Postgres checkpointer and stores the result on `app.state.advising_app`. Nodes
are bound to the model with `functools.partial`, so the model instance is fixed
for the process lifetime.

### `AdvisingState(MessagesState)`

| Key | Source | Notes |
|---|---|---|
| `messages` | inherited from `MessagesState` | append-reducer; `RemoveMessage` deletes by id |
| `summary` | written by `summarize_node` | running digest of everything already pruned |
| `context_results` | written by the caller each turn | the RAG hits for *this* question |

All three are **checkpointed**. `context_results` is overwritten on every
invocation, so it always reflects the current turn — it is not accumulated.

---

## Nodes

### `chatbot_node`

Rebuilds the system message from scratch on every call:

```
SYSTEM_ROLE
  + "\n\nSummary of earlier conversation: {summary}"        (if summary)
  + "\n\nRelevant SBU Information:\n<context>…</context>"   (if context_results)
```

then invokes the model with `[SystemMessage(...)] + state["messages"]`.

**Retrieved context goes into the system message, never as a user turn.** The
jailbreak-resistance behaviour documented in the README depends on that
separation — bulletin text is scraped from the web and must not be able to
address the model as the user. Do not move it into a `HumanMessage`.

`SYSTEM_ROLE` encodes several behaviours the project treats as requirements:
answer from `<context>` or internal knowledge; say *"I do not have this
information available"* for missing or non-SBU topics; process multi-part
queries step by step, refusing invalid segments while answering valid SBU ones;
and pivot back to SBU information rather than following off-topic dependencies.
Edit it deliberately, and re-check the README's two documented jailbreak cases.

Context entries are joined with `" \n- "`. Note the leading space and that the
**first** entry gets no bullet — cosmetic, but it is what the model sees.

### `summarize_node`

```python
messages_to_summarize = messages[:-2]     # keep the latest question + its answer
```

Summarises everything older, folds the **previous** `summary` into the prompt so
it compounds rather than being lost, then returns a `RemoveMessage(id=…)` for
each summarised message.

- **This is destructive and irreversible in the checkpoint.** Once pruned, the
  full text of those turns exists only in the `conversations` table.
- Returns `{}` when there is nothing to summarise. That is the correct no-op.
- The summarising call uses a bare `HumanMessage` prompt with no system message,
  and it uses the **same model** as the chat itself. A cheaper model here would
  be a reasonable optimisation, but it needs a second model instance threaded
  through `build_advising_graph`.
- `RemoveMessage` matches on `message.id`. Messages restored from the
  checkpointer carry ids; ones you construct by hand may not. Never build state
  messages without letting LangChain assign an id.

### `should_summarize`

```python
if len(state["messages"]) > max_messages: return "summarize_node"
return END
```

- Registered with `add_conditional_edges("chatbot", …)` and **no path map**, so
  the returned string *is* the destination node name. Renaming the node without
  updating this string breaks the graph.
- It runs **after** `chatbot`, so the count already includes the reply just
  produced. `max_messages=8` therefore means roughly four exchanges before the
  first prune, after which the count settles near the threshold.
- The count is of total messages, user + assistant, not turns.

---

## `generate_response_stream(app, query, context_results, thread_id)`

The single entry point used by `routers/chat.py`. A generator of `str` chunks.

- Input state is `{"messages": [HumanMessage(query)], "context_results": [...]}`.
  The message list is *appended* to whatever the checkpoint holds; only the new
  question is passed.
- `config = {"configurable": {"thread_id": thread_id}}` — **this is the same
  UUID as `threads.id`**, minted in the browser. It is what keeps the checkpoint
  and the application tables aligned. Do not derive, prefix, or transform it.
- Streams with `stream_mode="messages"` and filters on
  `metadata["langgraph_node"] == "chatbot"`, so summarisation tokens never leak
  into the user's reply. Any new node that calls the model needs to stay out of
  that filter, or be added to it deliberately.
- Handles **two content shapes**: a plain `str`, and a list of content blocks
  where the text is at `content[0].get("text")` (what Gemini emits). A provider
  that emits a third shape will silently stream **nothing** — no error, just an
  empty reply. That is the first thing to check when a new model "doesn't
  respond".
- `thread_id` defaults to `"cli-thread"`, a leftover from the terminal-CLI era.
  Every real caller passes an explicit id; the default would silently pool
  unrelated conversations into one checkpoint.

---

## Checkpointing

The `PostgresSaver` is created in `app.py`'s lifespan:

```python
with PostgresSaver.from_conn_string(db_url) as checkpointer:
    checkpointer.setup()
    app.state.advising_app = build_advising_graph(...).compile(checkpointer=checkpointer)
    yield
```

- `checkpointer.setup()` creates the LangGraph tables on first run. It is
  idempotent.
- The connection is held open for the whole application lifespan by the `with`
  block. **Do not move the compile out of the `with`** — the connection closes
  on exit and every request then fails.
- `LANGGRAPH_CHECKPOINT_URL` is a hard requirement; startup raises `RuntimeError`
  without it.
- Checkpoint rows are **not** cascaded when a `threads` row is deleted. A future
  delete-thread feature must clear both stores.

---

## Adding a node

1. Add the function taking `(state, model)` and bind it with `partial`.
2. `workflow.add_node("name", …)` — then make sure every conditional edge that
   should reach it returns that exact string.
3. Decide whether its tokens should reach the user; if not, the
   `langgraph_node` filter in `generate_response_stream` already excludes it.
4. If it needs new state, add the key to `AdvisingState` and remember it will be
   checkpointed from then on.
5. Update this file.

---

## Known issues (delete when fixed)

1. **Unused imports.** `ChatGoogleGenerativeAI` is imported but never used (the
   model comes from `clients/llm/factory.py`), as are `Any` and `List` from
   `typing`. The `ChatGoogleGenerativeAI` import in particular is misleading —
   it suggests this module picks the provider, which it does not.
2. **`load_dotenv()` at module import.** Harmless today, but it means importing
   this module has a side effect on the process environment. Environment loading
   belongs at the entry point.
3. **Commented-out `logging.basicConfig` and logger-silencing block** at the top
   of the file, superseded by `utils.setup_logging()`. `logging` is imported
   solely for those dead lines and is otherwise unused — this module logs
   nothing at all, which makes a silent empty stream (see above) harder to
   diagnose than it needs to be.
4. **No cheap-model split for summarisation** — see `summarize_node` above.
