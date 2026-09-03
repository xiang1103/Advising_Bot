# `backend/clients/llm/` — LLM provider factory

One job: return a configured LangChain chat model. `factory.py` is the **only**
place that decides which provider is used. `agent_graph/langgraph.py` consumes
whatever it hands back and must stay provider-agnostic.

---

## ⚠️ Maintaining this file

**Update this file in the same commit as any change here.** Especially: adding
or removing a provider, changing default model ids or generation parameters,
changing how the provider is resolved, or adding a dependency. If you fix an
item under "Known issues", delete the entry.

Adding a provider also means checking the streaming content-shape branch in
`agent_graph/langgraph.py` — see "Adding a provider" below.

---

## `create_model(provider=None, model_name=None) -> BaseChatModel`

Provider resolution, in order:

1. the explicit `provider` argument,
2. the `LLM_PROVIDER` environment variable,
3. `"gemini"`.

The value is `.strip().lower()`-ed, so `" Gemini "` works. An unrecognised
provider raises `ValueError("Unknown LLM provider")`.

`provider` is passed explicitly by the graph registry on the request path, so
`LLM_PROVIDER` only applies to callers that pass nothing.

| Provider | Class | Default model | Settings |
|---|---|---|---|
| `gemini` | `ChatGoogleGenerativeAI` | `config.GEMINI_MODEL` (`gemini-3-flash-preview`) | `temperature=1.0`, `max_retries=2` |
| `ollama` | `ChatOllama` | `config.OLLAMA_MODEL` (`qwen3:8b`) | `temperature=1.0`, `reasoning=False` |

- **Model ids live in `config.py`, not here.** Change them there.
- **`langchain_ollama` is imported lazily inside its branch**, so Gemini users
  do not need the package installed. Keep any future optional provider's import
  inside its branch for the same reason.
- **`reasoning=False` on Ollama suppresses `qwen3`'s thinking blocks.** Without
  it, chain-of-thought text streams straight into the user's chat bubble.
- `gemini_key = os.getenv("GEMINI_KEY")` is read at **module import time** into
  a module-level constant, so changing the environment after import has no
  effect on the key (unlike `LLM_PROVIDER`, which is read per call).
- The local model runs on Ollama's default port 11434; start it with
  `ollama serve` before selecting `qwen` in the composer. Nothing checks that it
  is up: `ChatOllama` constructs fine without a server, so the failure appears
  as a dead stream at generation time, not at model-build time.

---

## When the model is chosen

**Per request, by the client — but each model is built only once.**
`agent_graph/registry.py` calls `create_model(provider=...)` the first time a
request selects a given model, then caches the compiled graph for the life of
the process. `app.py` builds nothing at startup.

Two consequences for this file:

- **`LLM_PROVIDER` no longer decides what the app serves.** The registry always
  passes an explicit `provider`, so the env var is now only a default for
  callers that pass none — scripts, tests, and a bare `create_model()`. The
  browser's choice wins on the request path.
- **A provider that cannot be constructed fails on first selection, not at
  startup.** Missing `langchain_ollama`, a bad key: the server still boots and
  every other model keeps working. The failed build is not cached, so it is
  retried on the next request that asks for it.

The user-visible model ids and the providers they map to live in
`config.SELECTABLE_MODELS`; see `agent_graph/CLAUDE.md` for the registry itself.

---

## Adding a provider

1. Add a branch to `create_model`, importing the integration package **inside**
   the branch.
2. Add its default model id to `config.py`.
3. **Check the streaming content shape.** `generate_response_stream` in
   `agent_graph/langgraph.py` handles exactly two shapes: a plain `str`, and a
   list of content blocks with the text at `content[0]["text"]` (Gemini). A
   provider emitting anything else streams **nothing at all** — no exception,
   just an empty reply. This is the single most likely failure when wiring up a
   new model.
4. Suppress any provider-specific reasoning/thinking output, as
   `reasoning=False` does for Ollama.
5. Document the env var in the root `CLAUDE.md` and update this file.

---

## History worth knowing

This directory used to hold `gemini.py` with its own `create_model`. It was
deleted in commit `44be6f7` ("feat: integrate local model capability") and
replaced by `factory.py`. A stale `__pycache__/gemini.cpython-312.pyc` is still
on disk, but Python will not import from it without the source file.

---

## Known issues (delete when fixed)

1. **`temperature=1.0` for a factual advising bot** is high; retrieval-grounded
   answers usually want something much lower. Untuned, not deliberate as far as
   the history shows.
2. **`load_dotenv()` at module import** — side effect on the process
   environment; belongs at the entry point.
3. **No timeout on the Gemini client.** `max_retries=2` bounds retries but not
   total wall time, and this call sits on the request path.
