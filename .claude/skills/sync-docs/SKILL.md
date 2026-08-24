description: Check whether this session's changes made any project doc stale, and update the ones that drifted. Use before committing architectural work, or when asked to audit/update the docs.

# Sync Docs — Voyager

Docs drift silently. The failure mode is not a missing doc — it is a doc that still
reads as correct while describing code that changed months ago, so a future session
trusts it and builds on a false premise.

Run this **before committing** any change that alters architecture, data flow, a
schema, an interface, or an operational procedure. Not needed for a bug fix that
changes no contract.

## What lives where

| Doc | Covers | Update when |
|---|---|---|
| `.agents/AGENTS.md` | One-screen orientation, system diagram, key facts | Phase changes, a new subsystem, a new "you must know this before touching anything" fact |
| `.agents/backend.md` | FastAPI layout, routers, tools, env vars | New router/tool/executor, changed tool schema |
| `.agents/planning.md` | LangGraph graph, agents, revision scoping | Node added/removed, state shape, routing rules |
| `.agents/memory.md` | Chroma collections, extraction pipeline, retrieval | New collection or writer, changed retrieval scoping |
| `.agents/data-model.md` | SQLite tables, Chroma collections, migrations | Schema change, new migration |
| `.agents/frontend.md` | Next.js structure and conventions | New page/pattern |
| `.agents/evals-ops.md` | Eval harnesses, feature flag, tracing, cost | New eval script, new usage context, changed run procedure |
| `README.md` | Setup, status table, architecture diagram, how to run | Anything a newcomer would follow and find wrong |
| `VISION.md` | Phase roadmap and scope decisions | A phase completes, or scope is deliberately added/dropped |
| `OPEN-ITEMS.md` | Bugs, debt, open decisions | Every fix, every newly-found bug, every resolved decision |
| `INCIDENTS.md` | Postmortems for things that went wrong | Data loss, an outage, a silent-corruption class of bug |
| `docs/*.md` | Deep design docs | The design they describe changes |

## Procedure

**1. List what actually changed.**

```bash
git diff --stat main..HEAD   # or: git status --short for uncommitted work
```

For each changed file, ask: does any doc *describe* this file's behaviour?

**2. Verify claims against code — do not trust the doc.**

Grep the doc for concrete assertions (collection names, function names, CLI flags,
context labels, table names) and check each against the source. Docs are most often
wrong in specifics, not in shape. Real examples caught this way:

```bash
# doc said "(places)"; the collection is actually saved_places
grep -n 'get_or_create_collection' backend/app/memory.py
# doc listed 4 usage contexts; code sets 5
grep -rho 'usage_context.set("[a-z_]*")' backend/app | sort -u
```

**3. Update the docs that drifted.** Match the existing voice — these are terse
reference docs for a future agent, not prose. State the *why* when a design is
non-obvious or was arrived at the hard way; that is the part that stops someone
re-litigating a decision or re-introducing a bug.

**4. Reconcile `OPEN-ITEMS.md`.**
- Strike fixed items (`### ~~B-6 — ...~~ · **fixed YYYY-MM-DD**`) — keep the body,
  since the reasoning outlives the status.
- File anything discovered mid-session, even if unfixed and unrelated.
- Re-scope items that events overtook, rather than leaving a stale decision request.
- Re-check the "Priority right now" list still reflects reality.

**5. Report what you changed and what you deliberately left.**

## Rules

- **Verify, don't assume.** A doc claim you did not check is a claim you should not
  ship. If you cannot verify something, say so rather than restating it.
- **Record failed approaches and their cost.** "We tried a different-provider judge
  for bias and it was measurably worse" is worth more than the final answer alone.
- **Don't invent status.** If a suite has never run, the doc says so — never imply
  results that don't exist.
- **Keep numbers attributable.** A rate without its sample size, model, and date is
  not a fact.
