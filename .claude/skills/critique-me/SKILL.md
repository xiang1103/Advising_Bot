---
name: critique-me
description: >-
  Adversarial design review of code before it goes up for a pull request. Use this
  skill whenever the user asks you to critique, review, roast, sanity-check, tear
  apart, or "look over" code they wrote — especially before a PR, merge, or commit.
  Trigger on phrases like "critique me", "review my code", "before I open a PR",
  "challenge my design", "any anti-patterns here?", "is this idiomatic?", "how would
  you have done this?", or when the user hands over files or folders and asks what
  they would change. Also use it when the user wants the review written to a file
  rather than dumped in chat. This is not a linter pass and not a compliment machine
  — it produces a severity-ranked markdown report that traces the logic for
  correctness and then challenges the design thinking behind it, covering data
  structures, module boundaries, control flow, imports, abstraction level, and
  over-engineering.
---

# Critique Me

The user is about to put this code in front of other engineers. Your job is to be the reviewer they'd rather hear from now than in the PR comments.

Two distinct passes, in order, because they fail differently:

1. **Correctness** — trace the logic. Does it actually do what it claims, on every path?
2. **Design** — challenge the thinking. Is this the shape the solution should have?

Most reviews stop at pass 1, or degrade into style nits. The value the user is asking for is pass 2. Spend your effort there. You should not run the program to save the time at writing the report. Unless the user explicitly told you to try running the program. The focus is to ask as many questions as possible. Make each suggestion simple to understand. 

## Rules of engagement

The user explicitly asked to be challenged. Take that seriously — but challenge is only useful when it's grounded. Four things keep a critique honest:

**Evidence, not vibes.** Every finding points at a real location (`src/parser.py:88-104`) and quotes or paraphrases what's actually there. If you can't cite it, you're guessing, and a hallucinated line number destroys trust in the whole document.

**A concrete alternative.** "This is tightly coupled" is noise. "`OrderService` reaches through `order.customer.address.country` to pick a tax strategy — pass a `TaxRegion` in from the caller instead, so the service stops depending on the shape of three objects it doesn't own" is a review. If you can't articulate the better version, you're expressing a preference, so say so and mark it a Question.

**Honest cost.** Every suggestion has a price: churn, indirection, a new abstraction to learn. State it. A finding that pretends its fix is free is one the user will correctly ignore. Sometimes the right conclusion is "this is worse in theory but the fix isn't worth it today" — say that.

**Chesterton's Fence.** Odd code often encodes a constraint you can't see: a flaky upstream API, a deadline, a bug someone hit in production. Before calling something wrong, ask whether there's a reason for it. Frame those as questions in the report rather than assertions, and let the user answer.

Two failure modes to actively avoid, because they're the ones that make reviews worthless:

- **Manufacturing findings to look thorough.** If the code is good, the report should be short. Padding a review with invented problems trains the user to skim it.
- **Bikeshedding dressed as architecture.** Import ordering and brace placement are formatter's work, not yours. Mention style only where it genuinely impedes reading, and file it as a Nit.

Skip the praise sandwich. A short "What's working" section that names two or three specific, non-obvious good decisions is useful — it tells the user which instincts to keep. Generic encouragement is filler.

## Workflow

### 1. Establish scope

Review what the user pointed at. If they gave files or folders, that's the scope. If they gave nothing, check for a diff (`git diff main...HEAD`, `git status`) and review the changed files — this skill is aimed at pre-PR work, so the delta is usually the right unit.

Read the surrounding code too, even when it's out of scope. You cannot judge whether a function is in the right place without knowing what else lives in that module, and you cannot judge an abstraction without seeing its call sites. Note in the report when you reviewed something without full context.

Also look for what the project already decided: `README`, `CONTRIBUTING`, existing patterns in sibling modules, linter and formatter config, type checker settings. Code that diverges from house style is a finding; code that follows a house style you personally dislike is not.

### 2. Read everything before judging

Resist the urge to comment on file one. Build a picture first:

- Entry points and the public surface — what can outside callers actually touch?
- The data: what shapes exist, where they're constructed, where they're mutated, where they cross a boundary.
- The dependency direction between modules. Does anything point the wrong way, or point in a circle?

Only then start forming opinions. First-file-first reviews consistently flag things that are answered on page three.

### 3. Trace the logic

Walk the important paths by hand and verify them. At minimum:

- The happy path, end to end, with a concrete input in mind.
- What happens on each failure: exception thrown, network call times out, empty collection, `None`/`null`/undefined arriving where an object was expected.
- Boundaries: zero, one, many; first and last iteration; off-by-one in slicing and indexing.
- State: is anything mutated while being iterated? Does an early `return` skip cleanup? Can two paths leave the object in different states?

For anything concurrent, async, or resource-holding, be specific about shared mutable state, await points where invariants can break, and whether every acquired resource is released on every path including the error path.

Correctness findings outrank everything else in the report. A beautiful architecture that drops the last element of a list is still broken.

### 4. Challenge the design

This is the main event. Work through the lenses in `references/design-lenses.md` — it has the interrogation questions for each one:

| Lens | The question underneath it |
|---|---|
| Data structures & modeling | Is this the shape the data actually has? Can illegal states be represented? |
| Control flow | Is the flow as simple as the problem allows, or simpler than the problem allows? |
| Placement & boundaries | Does each thing live where a reader would look for it? |
| Imports & dependencies | Which way do dependencies point, and should they? |
| Abstraction level | Too much ceremony, or not enough? |
| Naming & readability | Do the names tell the truth? |
| Error handling | Who is responsible when this fails? |
| Interfaces & contracts | What has been promised to callers, and can it be kept? |
| Testing | What would have to break for a test to notice? |
| Performance & resources | Is there an accidental quadratic or an unbounded thing? |
| Security & trust | Where does untrusted input cross a boundary? |

Read that reference file rather than working from memory — the questions are the point, and they're what turn a checklist into an actual challenge.

Name the principle when one applies (SOLID, YAGNI, Law of Demeter, composition over inheritance, make illegal states unrepresentable, and so on) but never as the whole argument. "This violates SRP" is an appeal to authority; "this class changes for two unrelated reasons — a new payment provider and a new report format both force edits here" is the argument, and SRP is just its name. `references/design-lenses.md` has the glossary.

### 5. Write the report

Write to `critiques/YYYY-MM-DD-<scope>-critique.md` at the repository root, creating the directory if needed. `<scope>` is a short slug for what was reviewed — the branch name, the feature, or the top-level folder (e.g. `critiques/2026-07-23-auth-refactor-critique.md`). Never overwrite an existing critique; append `-2` if the name is taken, so the user keeps the history.

Tell the user the path when you're done, and give them a 3-4 sentence summary in chat — the headline finding and the overall verdict. Don't paste the whole report into the conversation; the file is the deliverable.

Do not edit their code unless they ask. The point is to challenge their thinking, and handing over a rewrite short-circuits that. Small illustrative snippets in the report are fine and encouraged.

## Report structure

Use this template. Drop sections that would be empty rather than filling them with "N/A".

```markdown
# Code Critique: <scope>

**Reviewed:** <files/folders, and the diff range if applicable>
**Date:** <YYYY-MM-DD>
**Verdict:** <one of: Ship it | Ship after addressing blockers | Needs a design conversation first>

## Summary

<3-6 sentences. What this code does, the single most important thing to fix,
and the overall shape of the feedback. Someone reading only this should know
whether to open a PR.>

## What's working

<2-4 specific, non-obvious good decisions worth keeping. Skip if there
genuinely aren't any — do not invent them.>

## Findings

### 🔴 Blockers
<Wrong behavior, data loss, security holes, or design choices that will be
expensive to undo once merged.>

### 🟠 Major
<Real design problems. Worth fixing now, cheaper now than later.>

### 🟡 Minor
<Improvements that make the code better but wouldn't block a merge.>

### 🔵 Nits
<Style, naming, formatting. Keep this section short.>

### ❓ Questions
<Things that look wrong but might encode a constraint you can't see.
Genuine questions, not rhetorical ones.>

## Design challenge

<The heart of the review. 2-5 sustained arguments about the approach itself,
not individual lines — the data structure that fights the problem, the layering
that will make the next feature painful, the abstraction that isn't earning its
indirection. Each one states the current approach, why it will hurt, a concrete
alternative, and what the alternative costs. This section is where you disagree
with the author, so make the reasoning strong enough to argue with.>

## Suggested order of work

<A short ordered list. What to fix before the PR, what can be a follow-up
ticket, what to deliberately leave alone.>
```

### Finding format

Each finding stands alone — a reader should be able to act on it without reading the rest of the document.

```markdown
**[Descriptive title]** — `path/to/file.py:88-104`

What's there and why it's a problem. One or two sentences of the actual
mechanism, not a category label.

*Suggestion:* The concrete alternative, with a snippet if it clarifies.

*Cost:* What this trades away — churn, a new concept, migration work.
```

**Example:**

```markdown
**Retry state lives in a dict keyed by stringified IDs** — `worker/queue.py:41-77`

`self._attempts` is a `dict[str, int]` keyed by `str(job.id)`, but `job.id` is a
`UUID` everywhere else. Two call sites already pass the UUID directly (`:112`,
`:158`), so those lookups silently miss and the job restarts its retry count
from zero — meaning a permanently failing job never hits the max-attempts cap.

*Suggestion:* Key on the `UUID` itself and drop the `str()` calls. If the dict
needs to be serialized, convert at the serialization boundary rather than at
every write.

*Cost:* Touches five call sites. If anything persists this dict as JSON, that
code needs a converter — worth checking before the change.
```

## Calibration

The severity ladder only works if you use the whole thing. Some guidance on where the lines sit:

- **Blocker** means the PR shouldn't merge: wrong output, a security hole, a resource leak, or a public interface that will be painful to change once other code depends on it.
- **Major** means it works but the design will cost real time later. A data structure that forces linear scans in a hot path. A module that will need editing for three unrelated reasons.
- **Minor** and **Nit** are genuinely optional. If a section is long, you're probably inflating severity elsewhere.

If everything is Major, nothing is. A review with fifteen findings and no ranking is a review that gets ignored.

Match depth to what's in front of you. A 60-line utility module gets a short report; a new service with five modules and a migration earns the full treatment. Length signals importance — a long document about a small change teaches the user to stop reading these.

## After Writing Report 
The report should contain both the findings and your suggestions. Write the report markdown file inside critique-me-reports folder in the root directory. Also add this folder into .gitignore if not already, so it won't be accidentally pushed to github. Write the file report and save it to folder first, then ask user if they want to make the change. You do not need to ask permission to create the folder, but let the user know the file has been created and its name. 