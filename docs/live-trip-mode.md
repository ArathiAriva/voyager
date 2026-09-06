# Live Trip Mode — design

**Status:** Stages 1, 3 (planner half) and 4 built 2026-09-05. Stage 2 and journal chat-capture not built.
**Phase:** not in the current phase list. Filed as a Phase 5 candidate for the
user to weigh against retrieval observability and memory maturity.

---

## 1. What it is

Today Voyager is a *planning* tool: you talk to it before a trip and read the
itinerary during one. Live Trip Mode makes it a *companion* — while a trip is
underway, the agent knows the trip is happening, which day it is, and what today's
plan says, without being told.

The difference is entirely one of default context. Compare:

| | Today | With live mode |
|---|---|---|
| "where should I eat" | Asks which trip, or guesses from history | Knows you are on day 2 in Halifax, near the waterfront |
| "is it going to rain" | Asks the destination | Checks Halifax, today |
| "what's next" | Meaningless | Reads today's plan |
| journal entry | Retrospective, date typed by hand | Live capture, dated and trip-attached automatically |

Nothing here needs a new model or a new architecture. It needs the agent to know
one fact — *this trip is happening now* — and to have that fact reach the places
that already make decisions.

## 2. Why it is not already possible

`trips.status` has an `active` value, but it is decorative: a green badge and a
ring on the card. Grepping the backend for `"active"` returns nothing — no
behaviour branches on it. It is also set manually and never expires, so a trip
marked active in March is still "active" in September.

The blocker underneath is that **`trips.dates` is free text**, and so cannot be
compared to today. Across the seven dev profiles the 22 distinct values fall into
three classes:

```
explicit range   "September 18–21, 2025"   "October 10–14, 2025"   "August 29 – September 7, 2026"
month only       "April 2024"   "March 2026"   "June 2026"
unparseable      "3 days (dates not specified)"   "2 days (current trip)"
```

Only the first class can support a live mode. Month-only values identify a month,
not a window — "March 2026" cannot tell you whether today is day 2 of the trip.

**The itinerary is a better source than `dates`.** Itinerary days already carry
ISO dates, written by the planner:

```json
{"day": 1, "date": "2025-09-18", "title": "Arrival & Downtown Waterfront", "plan": "..."}
```

That is machine-readable *today*, with no migration, and it is exactly the data a
live mode needs — not just the window, but which day maps to which plan. Any trip
with a planned itinerary is already live-capable. This is the single most useful
finding in this document and it shapes the staging below.

## 3. Design

### 3.1 Trip temporality

One helper answers "is this trip happening now, and which day is it", from the
best available source:

```
resolve_trip_window(trip) -> TripWindow | None
    1. itinerary day dates (ISO, authoritative — written by the planner)
    2. trips.start_date / trips.end_date (Stage 2, once the columns exist)
    3. parsed trips.dates, explicit ranges only
    else None — the trip has no usable window, and live mode simply does not engage
```

Returning `None` is a first-class outcome, not a failure. Most existing trips will
return `None` and must keep working exactly as they do now.

### 3.2 Derived status, not stored status

`status` stays as the user's declared intent. Liveness is **computed** on read:

```
is_live(trip, today) = window is not None and window.start <= today <= window.end
```

Computing rather than storing avoids a scheduler, avoids a migration, and avoids
the stale-state bug that `status = "active"` already has. A trip cannot be
wrongly live tomorrow because nothing was written today.

The manual `active` status is kept and treated as an override, so a user can force
live mode for a trip whose dates are unparseable.

### 3.3 Where liveness is injected

Three places, in increasing order of intrusiveness:

**a. A tool the agent can call — `get_current_trip`.** Returns the live trip, the
day number, today's plan, and the remaining days, or `{"live": false}`. This is
the lowest-risk surface: the agent asks when it judges the question is
location-or-time dependent, exactly as it already does with `get_trips`.

**b. System prompt line, only when a trip is live.** One sentence naming the trip,
the day, and today's title. Costs a few tokens per turn, and only during a trip.
This is what makes "where should I eat" work without the user naming the city.

**c. Planner brief.** `load_user_context` adds the live trip so a mid-trip replan
starts from where the user actually is. This one matters most for revisions and
is the most likely to interact badly with the existing planning graph, so it goes
last.

### 3.4 What is deliberately excluded

- **No geolocation.** "Near me" is out of scope; the day's `area_focus` is a good
  enough proxy and needs no permissions, no new privacy surface, no device APIs.
- **No push notifications or background jobs.** Nothing runs when the user is not
  asking. A daily-digest feature would need a scheduler and belongs in Phase 6.
- **No auto-transition of `status`.** Writing status on a timer is the stale-state
  bug again; derive it instead.
- **No new LLM calls.** Every part of this is deterministic date arithmetic over
  data the app already has.

## 4. Staging

Each stage is independently useful and independently revertible.

| Stage | Scope | Migration | Status |
|---|---|---|---|
| **1** | `resolve_trip_window` + `is_live` + `get_current_trip` tool + system-prompt injection | none | **built 2026-09-05** |
| **2** | `start_date`/`end_date` columns, backfilled from itineraries; date picker in the trip form | Alembic | not built |
| **3** | Planner brief carries the live trip; journal entries default to today's trip and date | none | **planner half built 2026-09-05**; journal entries already defaulted (trip from the URL, date to today), so only chat capture remains |
| **4** | UI: "Day 2 of 4" badge on the trip card and detail page | none | **built 2026-09-05** |

Stage 4's badge was pulled forward, because Stage 1 created an inconsistency by
itself: the agent knew the user was on day 2 while the trip card still read
"upcoming" from the stored `status`. `GET /trips` now returns derived
`is_live`/`live_day`/`live_total_days` alongside the untouched `status`, and the
card and detail page prefer them. Today's plan on the trips page is still not
surfaced.

Stage 1 is built because it is the whole idea in miniature and needs no schema
change — it works today for any trip with a planned itinerary. Stages 2–4 are
deliberately left for after the priority call, since Stage 2 is the only one with
a migration and the rest depend on it being wanted at all.

## 5. Risks and how they are handled

**Wrong trip selected.** Two trips could overlap. `get_current_trip` returns the
one whose window started most recently, and reports ties rather than guessing
silently.

**Timezone.** The user's "today" is not the server's. Stage 1 uses the server's
local date, which is correct for a single-user local app and wrong the moment
this is deployed. Documented as a known limitation rather than solved with a
timezone column nobody has asked for yet.

**Stale liveness in a long conversation.** A conversation spanning midnight would
carry yesterday's day number. The prompt line is rebuilt per request, so this
self-corrects on the next message.

**Prompt bloat.** The injected line is one sentence and only present while a trip
is live. Measured at ~35 tokens.

**The planner already has a `revision` path.** Stage 3 must not double-inject the
itinerary — the graph loads `existing_itinerary` itself. Deferred partly for this
reason.

## 6. Open questions for the priority call

1. **Is this Phase 5, or does it displace something?** It is a genuine new
   capability, not maintenance, so guiding principle 2 says it should not jump the
   queue ahead of retrieval observability without a deliberate decision.
2. **Does Stage 2 earn its migration?** Stage 1 covers any trip with an itinerary.
   Explicit columns mainly help trips that were never planned in-app.
3. **Is the journal the real prize?** Live capture — "add to my journal: the fish
   was excellent" attaching to the right trip and date with no ceremony — may be
   more valuable than the retrieval improvements, and is Stage 3.

   **Constraint on that stage: the agent must never author or edit journal text.**
   The journal is the one place in Voyager that is the user's own voice rather
   than agent-generated or agent-summarised, and it feeds both `journals` RAG and
   preference extraction, so distortion there propagates into what Voyager
   believes about the user. An LLM asked to "add this to my journal" will tidy the
   wording by default, producing entries in the model's register attributed to the
   user. Capture must pass the text through verbatim (echo-back before writing, or
   client-side capture that never routes the text through the model); the agent's
   contribution is the *metadata* — trip and date — not the words.

4. **Does this want [trip-scoped chats](trip-scoped-chats.md) first?** Journal
   capture needs an unambiguous trip. Live mode supplies one while a trip is
   underway; a scoped conversation supplies one always.
