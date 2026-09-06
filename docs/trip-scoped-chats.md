# Trip-Scoped Chats — design

**Status:** Stages 1–4 built 2026-09-05.
**Phase:** not in the current phase list. Filed as a candidate alongside
[Live Trip Mode](live-trip-mode.md) and
[Conversational Onboarding](conversational-onboarding.md) for the priority call.

---

## 1. The problem

`ConversationORM` has `id`, `title`, `created_at`, `updated_at` and its messages.
There is **no `trip_id`, and no link in either direction**. A conversation about
Halifax and a conversation about nothing in particular are indistinguishable
rows.

So trip context is re-derived from text on every turn, by two different
mechanisms:

- **Single-agent loop** — the model calls `get_trips` and picks a trip by
  whatever destination it reads in the message.
- **Planning graph** — `_resolve_trip_id` (`planning/graph.py`) fuzzy-matches the
  brief's destination against every trip, and **creates a new trip when nothing
  matches**.

Three consequences, in rising order of severity:

**a. Chats are not findable by trip.** "What did I discuss about Halifax" has no
answer except semantic search over episodes. On `egwene` there are 120
conversations against 7 trips; nothing connects them.

**b. Context is re-derived every turn.** Reopen an old chat and the agent works
out afresh which trip it is about, from the transcript, every time.

**c. A fuzzy-match miss silently creates a duplicate trip.** This is the sharp
edge. `_resolve_trip_id` has no failure branch — if the brief says "Halifax" and
the stored trip is "Halifax, Nova Scotia", `dest_matches` happens to cover it,
but the general case is a new trip appearing with no warning. Same class as B-10
(`create_trip` not idempotent), and the user's first sight of it is a duplicate
card on the trips page.

## 2. What this is not

**Not every chat is about a trip, and the design must not assume otherwise.**
Real titles from `egwene`:

```
Plan my 5 days in Tokyo...                    → clearly one trip
What is the best time of year to visit Japan? → no trip; general knowledge
Which was my most reflective trip?            → spans every trip
Let's plan a trip to Hawaii                   → a trip that does not exist yet
```

The third case matters most. A cross-trip question is a first-class use of
Voyager's memory, so scoping must never become mandatory, and selecting a trip
must not blind the agent to the others.

## 3. Design

### 3.1 Schema

```
conversations.trip_id  TEXT NULL  REFERENCES trips(id) ON DELETE SET NULL
```

**Nullable, and nullable forever.** Unscoped is a legitimate permanent state, not
a missing value to be backfilled. `ON DELETE SET NULL` rather than `CASCADE`:
deleting a trip must not delete the conversations about it — that would be a far
worse data loss than the one B-9's confirmation dialog guards against, and the
transcript is still worth keeping.

This needs an Alembic migration — the first in a while. Existing conversations
get `NULL`, which is the correct value for them: nothing reliable links a
historical chat to a trip, and guessing from titles would be inventing data.

### 3.2 Defaults, not constraints

A selected trip **defaults** tool arguments; it does not restrict them.

- `search_journal` and `search_places` default `trip_id` to the conversation's.
- `set_itinerary` / `update_trip` default to it, removing the `get_trips`
  round-trip and the fuzzy match.
- `_resolve_trip_id` uses it directly and **never creates a trip** when the
  conversation is already scoped. That closes (c).

The agent can still reach other trips — `get_trips` is unchanged — so "how does
this compare to my Kyoto trip" keeps working. Constraining retrieval to one trip
would be simpler to implement and would break exactly the queries that make the
memory system worth having.

### 3.3 Choosing the trip

Three entry points, in order of how often they will be used:

1. **Live trip as the default.** If a trip is underway
   (`find_live_trip`, Live Trip Mode Stage 1), preselect it. Mid-trip, nearly
   every chat is about that trip.
2. **A picker on "New chat".** Both creation sites — `chats/page.tsx` and
   `chat/page.tsx` — offer a trip list plus "No specific trip". Not a modal
   gate: "No specific trip" must be one click, or the general-question case gets
   taxed for the trip-specific case's benefit.
3. **Changeable mid-conversation.** Conversations wander — one starts as "best
   time to visit Japan" and becomes "plan my Tokyo trip". A small control in the
   chat header sets or clears the trip at any point. This is also the only
   sensible path for the 120 existing unscoped conversations.

**Set, do not infer.** The agent should not silently set `trip_id` from what it
reads in the transcript; that reintroduces the guessing this design removes, and
a wrong guess would now be *persisted* rather than re-derived each turn. It may
*offer*: "This looks like it's about your Halifax trip — want me to link it?"

### 3.4 Where it surfaces

- **Chats list** — a trip badge on each row; filter by trip.
- **Chat header** — the current trip, click to change or clear.
- **Trip detail page** — a "Conversations" count or tab, the reverse lookup that
  is impossible today.

### 3.5 Deliberately excluded

- **No backfill of existing conversations.** Guessing from titles would invent
  associations that read as fact afterwards. `NULL` is honest.
- **No auto-linking by the agent** (§3.3).
- **No hard scoping** of retrieval (§3.2).
- **No new LLM calls.** Everything here is a foreign key and UI.

## 4. Staging

| Stage | Scope | Migration | Notes |
|---|---|---|---|
| **1** | `trip_id` column + migration; `POST /conversations` accepts it; `PATCH` sets/clears it; returned in the API | Alembic | **built 2026-09-05** |
| **2** | `_resolve_trip_id` prefers the conversation's trip and never creates a duplicate when scoped | none | **built 2026-09-05** — the B-13 fix |
| **3** | Trip picker on new chat, live trip preselected; change/clear in the chat header | none | **built 2026-09-05** |
| **4** | Trip badge on the chats list; `GET /conversations?trip_id=` for the reverse lookup | none | **built 2026-09-05** — the trip-page tab is not built |

Stage 2 is worth pulling forward: it fixes silent duplicate-trip creation and
depends only on Stage 1's column, not on any UI.

## 5. Risks

**A wrong trip is now sticky.** Today a bad inference lasts one turn; once
persisted it misleads every later turn. Mitigated by §3.3 — the user sets it, the
agent only offers — and by making it changeable and clearable.

**Migration on real profiles.** `egwene` has 120 conversations and `scripts/migrate.sh`
backs up first (INC-001). The column is nullable with no default beyond `NULL`, so
the migration is additive and reversible.

**Scope creep into the planner.** `_resolve_trip_id` is load-bearing for persistence.
Stage 2 must keep its existing destination-matching path intact for unscoped
conversations rather than replacing it.

**A trip deleted mid-conversation.** `ON DELETE SET NULL` leaves the chat intact and
unscoped; the UI should say so rather than showing a dangling reference.

## 6. Open questions

1. **Does this displace Phase 4?** Same question as Live Trip Mode. Stage 2 is
   arguably a bug fix rather than a feature, which may let it jump the queue on
   its own.
2. **Should scoping affect memory extraction?** A trip-scoped conversation's
   preferences could carry `trip_id`, which is the exact missing back-reference
   behind B-2 (revoking preferences from an edited entry) and M-5 (destination
   scoping). Possibly the most valuable side effect here, and worth weighing
   before the UI work.
3. **Does this unblock [visited places & anecdotes](visited-places-and-anecdotes.md)?**
   That design's Stage 4 (chat capture of an anecdote) needs an unambiguous place,
   which needs an unambiguous trip. A scoped conversation supplies one always;
   Live Trip Mode supplies one only while a trip is underway.
4. **One trip per conversation, or several?** A single nullable FK assumes one.
   "Compare my Kyoto and Florence trips" suggests otherwise. Starting with one is
   right; a join table later if it proves wrong.
