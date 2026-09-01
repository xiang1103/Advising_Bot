# `frontend/components/ui/` — presentational components

Four components, only two of which carry real behaviour.

```
ui/
├── ai-chat-input.tsx     the composer — owns draft text and model selection
├── markdown-message.tsx  renders assistant replies, including mid-stream
├── dropdown-menu.tsx     vendored shadcn/Radix primitive — do not hand-edit
└── demo.tsx              unused example
```

**None of these fetch anything.** All network calls live in `frontend/lib/` or,
for the stream, in `app/page.tsx`. Components receive callbacks and render.
Keep it that way — a component that knows a URL is a component that cannot be
reused or tested.

---

## ⚠️ Maintaining this file

**Update this file in the same commit as any change here.** Especially: a change
to a component's props contract, a change to which state a component owns versus
receives, a new component with behaviour, or a change to how streamed content is
rendered. Purely visual tweaks (spacing, colour, animation timing) do **not**
need an entry. If you fix an item under "Known issues", delete the entry.

---

## Who owns which state

This is the thing to understand before editing anything here.

| State | Owner | Notes |
|---|---|---|
| `messagesByThread`, `activeThreadId`, `threadList` | `app/page.tsx` | the conversation itself |
| `isStreaming` / `streamingRef` | `app/page.tsx` | passed down as `disabled` |
| `loadingThreadId` | `app/page.tsx` | also folded into `disabled` |
| draft input text | `AIChatInput` | **never lifted** — page.tsx does not see keystrokes |
| selected model | `AIChatInput` | local; only surfaces as an `onSend` argument |

`AIChatInput` is deliberately uncontrolled from the page's perspective: the page
learns about the draft exactly once, when the user sends. That keeps every
keystroke from re-rendering the message list.

---

## `ai-chat-input.tsx`

```ts
type AIChatInputProps = {
  onSend: (text: string, model: "gemini" | "qwen") => Promise<void>;
  disabled?: boolean;   // true while a reply streams OR history loads
};
```

### The send path

1. `handleSend` returns immediately if `disabled` — a second guard on top of the
   page's `streamingRef`, since the button and the Enter key are separate entry
   points.
2. The text is trimmed; empty input is a no-op.
3. **The input is cleared and deactivated *before* `await onSend(...)`.** This is
   deliberate: `onSend` does not resolve until the entire reply has streamed,
   which can be many seconds, and leaving the sent text sitting in the box that
   whole time reads as a failure to send.
4. `onSend` is awaited but its result is ignored, and **it is not wrapped in
   `try/catch`** — `page.tsx::handleSend` handles its own errors internally and
   always resolves, so a rejection here would be unhandled. If you ever make
   `onSend` able to reject, add the catch.

Enter submits (`preventDefault` then `void handleSend()`); Shift+Enter is **not**
handled separately, so there is no way to type a newline — the field is a
single-line `<input>`, not a textarea.

### `disabled` covers two different conditions

The page passes `isStreaming || isLoadingHistory`. The second matters: sending
into a thread whose history is still in flight would make `page.tsx` read an
empty message array, treat an existing thread as brand new (retitling it from
the new message), and then discard the history when it arrives. The input being
disabled is what prevents that race — do not narrow this prop to just streaming.

### The model dropdown

Model selection is local state, surfaced only as the second `onSend` argument.
`page.tsx` forwards it in the `/chat` body as `model`.

**The backend currently ignores it.** `ChatRequest` in `backend/schema.py`
declares no `model` field, so Pydantic drops it silently, and the provider is
fixed at process startup from `LLM_PROVIDER`. The dropdown changes nothing
today. See `backend/clients/llm/CLAUDE.md` for what honouring it would require —
it is not just adding a field. Until then, treat this control as aspirational
UI.

`MODELS` here (`gemini`, `qwen`) is a separate list from the backend's provider
names (`gemini`, `ollama`) — note `qwen` names the *model*, `ollama` names the
*runtime*. Any real wiring has to reconcile those.

---

## `markdown-message.tsx`

Renders assistant content as markdown (`react-markdown` + `remark-gfm`) with a
Tailwind renderer per element. The LLM emits markdown, so raw text would show
literal `**` and `-` characters.

**The critical property: this component re-parses on every streamed chunk.**
`page.tsx` appends each chunk to `content` and re-renders, so this receives
*partially complete* markdown many times per reply — an unclosed `**`, half a
table, a code fence with no terminator. `react-markdown` handles that gracefully
(it renders the partial tree and corrects as more arrives), which is why the
streaming bubble does not flicker between broken states. Two consequences:

- **Do not add expensive work to this render path.** It runs on every chunk of
  every reply.
- **Do not add anything that assumes well-formed input** — no "extract the first
  heading", no parse-then-validate. Mid-stream, the input is legitimately
  malformed.

Links render with `target="_blank"` and `rel="noopener noreferrer"`. Keep the
`rel` — the content is model-generated and may contain arbitrary URLs.

There is **no `rehype-raw`**, so embedded HTML in a reply is escaped rather than
rendered. That is the safe default for model output; do not add raw HTML support
without thinking about what the model can be induced to emit.

Only the assistant's messages go through this. User messages render as plain
text, so a user typing `**bold**` sees their literal input — intentional.

---

## `dropdown-menu.tsx`

A **vendored shadcn/ui component** wrapping `@radix-ui/react-dropdown-menu`.
Generated, not authored. Treat it as a dependency:

- **Do not hand-edit it** to change how one menu looks — pass `className` at the
  call site, or wrap it. Local edits are lost the moment anyone regenerates it.
- It imports `cn` from `@/lib/utils`, which in this repo is a plain class joiner
  rather than shadcn's `clsx` + `tailwind-merge`. Conflicting Tailwind classes
  are therefore **not** de-duplicated — see `frontend/lib/CLAUDE.md`.
- It exports far more than is used (submenus, checkbox items, shortcuts). Only
  `DropdownMenu`, `Trigger`, `Content`, `Label`, `Separator`, `RadioGroup`, and
  `RadioItem` are consumed, by `ai-chat-input.tsx`.
- Its classes reference shadcn CSS variables (`bg-accent`,
  `text-muted-foreground`) which come from `app/globals.css` and
  `tailwind.config.ts`. Removing those breaks this file silently.

---

## Adding a component

1. Presentational only — take data and callbacks as props, no `fetch`.
2. Lift state to `app/page.tsx` **only** if something outside the component
   needs it. The composer's draft text is the model to follow: keep it local.
3. Mark it `"use client"` if it uses hooks or event handlers.
4. If it renders model-generated content, apply the `markdown-message.tsx`
   rules above.
5. Update this file if it has behaviour; skip it if it is purely visual.

---

## Known issues (delete when fixed)

1. **The model dropdown does nothing** — see above. This is the most likely
   thing to confuse someone new: the UI is complete, the backend seam is not.
2. **`demo.tsx` is dead code.** It renders `AIChatInput` with a no-op `onSend`
   and is imported by nothing.
3. **`onSubmit={handleSend}` on the `motion.div`** in `ai-chat-input.tsx` is
   inert — a `div` never fires submit, and there is no `<form>`. Sending works
   only via the button's `onClick` and the input's Enter handler.
4. **`containerVariants` declares only a `collapsed` state**, while the
   component sets both `initial` and `animate` to it, so the "expand on focus"
   animation the `isActive` state implies never happens. `isActive` now only
   gates the placeholder rotation.
5. **No Shift+Enter for newlines** — the composer is a single-line `<input>`, so
   multi-line questions cannot be typed.
