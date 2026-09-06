# Conversational Onboarding & Conditional Preferences — design

**Status:** proposed, nothing built.
**Phase:** not in the current phase list. Filed as a candidate alongside
[Live Trip Mode](live-trip-mode.md), [Trip-Scoped Chats](trip-scoped-chats.md) and
[Visited Places & Anecdotes](visited-places-and-anecdotes.md).

---

## 1. Two problems, and the second is the real one

**a. There is no onboarding.** Grepping `app/` and `frontend/src/` for "onboard"
returns nothing. A new profile meets four empty states ("No memories yet", "No trips
yet", "No planning runs yet") and an agent that knows nothing about the user.

**b. Preferences are stored as unconditional facts about a person, and many of them
are not.** This is the deeper problem, and onboarding is downstream of it.

Look at what is actually stored on the `moiraine` profile today:

```
does not drink alcohol                          ← unconditional, always true
prefers coastal walks to woodland trails        ← mostly true, mildly contextual
travels solo                                    ← NOT A PREFERENCE
```

The third is a fact about *a subset of trips*, stored as a claim about the person.
A family trip next year would **contradict** it, and M-4's reconciliation would
retire one in favour of the other. Both are true. Neither should win.

**A trip with friends is a different trip from one with family or one alone** —
different budget, pace, food, accommodation, risk tolerance. Those differences are
larger than the differences between destinations, and the model has no way to
express them.

### M-5 is this problem wearing a different hat

M-5 is filed as *destination* scoping: "enjoys traditional Portuguese cuisine"
should not apply when planning Tokyo. But destination is one condition among
several, and probably not the strongest. The general question is:

> Under what conditions does this preference hold?

Framing it as destination-only produces a filter that solves one twelfth of the
problem and discards most of the collection whenever the destination changes.

### This also invalidates a conclusion reached earlier

M-5 was nearly deferred on the grounds that "moiraine's 9 preferences contain
nothing destination-bound, so there is nothing for a scope filter to exclude." That
reasoning was wrong: those 9 rows describe **one travel mode** (solo, Halifax), so
the absence of conflict is an artifact of thin data, not evidence of no problem.
The same trap M-4's premise fell into — reasoning from a sample that could not
contain the phenomenon.

## 2. Why not a survey

The obvious answer to (a) is a setup form: budget band, pace, dietary needs. Three
reasons it is the wrong fit *for this app specifically* — an architectural argument,
not a general claim about surveys.

**It bypasses the pipeline this app is built on.** Extraction, write-time dedup,
reconciliation, journal RAG, saved places — all read free-text traits. A dropdown
writes `budget: mid-range` into a structured field nothing downstream consumes.

**It produces the wrong kind of data.** `prefers coastal walks to woodland trails
when available` is specific enough to retrieve against and quote back. `pace:
relaxed` is a category with no texture; `search_memory` can do nothing useful with
an enum.

**People are bad at introspecting and good at remembering.** "Rate your budget"
gets an aspirational answer. "Tell me about the best meal you've had travelling"
gets *"this tiny place in Lisbon, we queued 40 minutes and it was worth it"* — from
which the extractor derives budget tolerance, food priority, crowd tolerance, and a
saveable place, none of which the person would self-report accurately.

**A survey also cannot express condition.** "Budget: mid-range" is exactly the flat,
unconditional shape problem (b) is about. It would harden the bug rather than fix it.

## 3. What surveys get right

Two problems a naive "just chat with it" onboarding does **not** solve:

- **The blank page.** "Tell me about your past trips" is an essay prompt. People
  freeze.
- **Knowing when you are done.** A form has a progress bar and a submit button; an
  open conversation has no visible end, so the user stops too early or feels
  interrogated.

## 4. Design

### 4.1 Conditional preferences

Preferences carry an optional free-text **condition**:

```
{"trait": "prefers cheap street food",        "when": "travelling solo"}
{"trait": "enjoys long sit-down dinners",     "when": "travelling with a partner"}
{"trait": "needs a kitchen and early nights", "when": "travelling with kids"}
{"trait": "does not drink alcohol",           "when": null}
```

**Free text, not an enum.** An enum of companion modes invites a taxonomy —
companions, purpose, season, duration, budget, weather — which is a survey in a
different shape, mostly-empty fields nobody maintains. A free-text condition
extracted by the same LLM pass that already produces the trait costs one prompt
change and degrades to today's behaviour when absent.

`when: null` is the common case and means unconditional. Existing rows have no
condition and are read as unconditional, which is correct for most of them.

### 4.2 Ask about more than one trip

Onboarding asks about **two or three different trips**, chosen to differ:

> "Let's start with somewhere you've been. What's a trip you'd happily do again?"
> …
> "Was that a solo trip, or with people? Tell me about one that was the opposite."

One story teaches you about one travel *mode*, not about the traveller. Asking for
a contrasting trip is what surfaces the conditions — and it is a better opening
anyway, because comparing two trips is easier to talk about than describing
yourself.

It also produces **visible artifacts**: real `past` trips on the trips page, rather
than an invisible profile update.

### 4.3 Follow-ups chosen by what is missing

After extraction, ask about a facet nothing has been learned about — reusing the
`PREFERENCE_FACETS` list that already exists for retrieval (food, accommodation,
pace, activities, budget, transport). **Hard cap at three.** The goal is a warm
start, not a complete profile.

### 4.4 Stop and show the work

> "Here's what I picked up — anything wrong?"
> - enjoys queuing for food that's worth it
> - prefers walkable neighbourhoods · *when travelling solo*
> `[looks right]  [remove ✕]`

Solves both survey problems at once: progress becomes visible, the end becomes
obvious, and extraction can be corrected **before** it shapes anything. The
Memories page already has per-row delete, so the affordance exists.

### 4.5 Chips, and always skippable

Tappable suggestions (*early starts · slow mornings · depends*) remove the blank
page without becoming a form — tapping sends an ordinary message, typing something
else behaves identically. "Skip" on every prompt; memory already builds from
ordinary use, so onboarding is a head start, not a gate.

## 5. What changes in the existing architecture

The condition field is the invasive part. Ordered by blast radius:

### 5.1 Storage — additive, no migration

`store_preferences` gains a `condition` argument, written to Chroma metadata beside
`created_at`/`source`/`destination`. **Chroma metadata is schemaless, so no Alembic
migration** — the same reason M-2 was cheap.

```python
store_preferences(["prefers cheap street food"], condition="travelling solo")
```

Existing rows have no `condition` and read as unconditional. Null-safe by default.

### 5.2 Extraction — one prompt change, one shape change

`EXTRACTION_PROMPT` currently returns `{"episode": ..., "preferences": ["...", ...]}`
— a flat list of strings, in **both** `conversations.py` and `journal.py`. It would
return objects:

```json
{"preferences": [{"trait": "prefers cheap street food", "when": "travelling solo"}]}
```

Both call sites parse `extracted.get("preferences", [])` and pass strings straight
to `store_preferences`. Both need updating together, and the parser must tolerate
the old shape — a model will occasionally return bare strings, and that must not
lose the write (the B-14 lesson).

**The prompt also needs teaching what a condition is**, or it will over-apply one.
"Prefers street food" learned on a solo trip is probably unconditional; "travels
solo" is a condition, not a trait at all. The prompt should prefer `null` unless the
trip context clearly scopes the trait.

### 5.3 Dedup and reconciliation — the subtle part

**M-3's write-time dedup would wrongly merge across conditions.** "Prefers cheap
street food (solo)" and "enjoys long dinners (with partner)" may be far enough apart
to survive, but "prefers early starts (solo)" and "prefers slow mornings (with kids)"
are close and *not* duplicates. `_nearest_preference` must compare within the same
condition, or treat differing conditions as automatically distinct.

**M-4's reconciliation has the same issue, and it is worse there** because a
contradiction across conditions is exactly what conditional preferences are *for*.
`prefers 3-day trips (solo)` vs `prefers week-long trips (with family)` is not a
contradiction to resolve — it is two true things. The judge prompt must be told the
conditions, and instructed that differing conditions make a pair compatible by
default.

Without this, adding conditions makes reconciliation *actively harmful*: it would
retire real preferences as contradictions.

### 5.4 Retrieval — needs a trip context to filter on

`search_memory` would filter or rank by the current trip's condition. That needs the
planner to know it, which is where this **converges with existing work**:

- [Trip-scoped chats](trip-scoped-chats.md) already puts `trip_id` on a conversation
- [Live Trip Mode](live-trip-mode.md) already supplies the current trip to the brief
- A trip would need its own companion context to match against — a `companions`
  field, or inference from the itinerary and conversation

**Filtering should not be hard.** A conditional preference whose condition does not
match should rank lower, not vanish — the same lesson as B-6's destination scoping,
where over-scoping starves results. Unconditional preferences always apply.

### 5.5 Planner and critic — mostly free, one hazard

`build_brief` passes preferences through as a list of strings, and `critic.py` scores
"preference alignment" against them. If conditions are rendered into the text
(`"prefers cheap street food (when travelling solo)"`) both keep working unchanged.

**The hazard is the critic.** It is instructed to enforce "the user's stated
preferences", and it already produced spurious issues when handed a contradictory
blob. Handing it preferences whose conditions do not match the trip would produce
exactly that failure again — so the filtering in §5.4 has to happen *before* the
brief, not after.

### 5.6 Trips — a new field, and this one does need a migration

Matching a condition needs the trip to have one. `trips.companions` (free text:
"solo", "with partner", "family with two kids") is the minimum. That is an Alembic
migration, and the only one this design requires.

It could be inferred rather than stored — from the conversation, or from the
itinerary — but inference is what the flat model already does badly, and a wrong
inference here would mis-scope every preference for that trip.

### 5.7 What does *not* change

- The `episodic` collection. Episodes are already trip-specific by nature.
- Journal and anecdote storage. Both are already attached to a trip.
- The retirement/drift mechanism. A conditional preference supersedes within its own
  condition, which is the same logic.

## 6. The risk: extraction quality

**Onboarding extraction is higher-stakes than ordinary extraction.** It is
uncorrected (it lands before the user can judge the system), front-loaded
(everything after is shaped by it), and drawn from thin evidence (one story could
yield "prefers luxury hotels" forever).

Conditions make this **better and worse**. Better, because a wrong trait scoped to
one condition does less damage than a wrong global one. Worse, because the extractor
now has two things to get wrong, and a mis-assigned condition hides a real preference
from retrieval entirely.

Mitigations, in order:

1. **§4.4's confirmation is not optional.** It is the safety mechanism, not a
   nicety. A friendly "got it!" would be strictly worse than the survey it replaces.
2. **`source="onboarding"`** — the field already exists (M-2). Makes a bad batch
   removable as a unit and distinguishable later.
3. **Prompt for hedging**, and for `null` conditions by default. Prefer "enjoyed a
   splurge on that trip" over "prefers luxury hotels", and prefer unconditional over
   a guessed condition.

## 7. Deliberately excluded

- **No condition taxonomy or enum** (§4.1). Free text, or nothing.
- **No structured profile fields.** A parallel representation of preference would
  guarantee the two disagree.
- **No completion score.** It implies a target, which invites answering to fill it.
- **No agent-authored journal entries or anecdotes.** The verbatim constraint from
  [live-trip-mode.md](live-trip-mode.md) §6 holds — onboarding may create *trips*
  and *preferences*, never the user's own words.
- **No hard filtering** on condition (§5.4). Rank, do not exclude.

## 8. Staging

Conditions and onboarding are separable, and **conditions should come first** —
onboarding without them would extract flat traits from multiple trips and store
mutually-contradictory facts, which is worse than not asking.

| Stage | Scope | Migration | Notes |
|---|---|---|---|
| **1** | `condition` on `store_preferences` + extraction emits `{trait, when}`; parser tolerates both shapes | none | Inert until something reads it |
| **2** | Dedup and reconciliation become condition-aware (§5.3) | none | **Required before Stage 1 sees real use** — otherwise reconciliation retires true preferences |
| **3** | `trips.companions`; retrieval ranks by condition match | Alembic | Where the value appears |
| **4** | Onboarding: multi-trip prompts, facet follow-ups, confirm-and-correct | none | Depends on 1–3 |

Stage 2 is listed second but is **not optional relative to Stage 1**: shipping
conditions without teaching reconciliation about them makes M-4 destructive.

## 9. Open questions

1. **Is `companions` the right first condition, or should it be general?** Free-text
   conditions can express anything ("when it rains", "on work trips"), but only
   companions has an obvious home on the trip record. Starting narrow risks building
   a companion-shaped hole; starting general risks a field nothing can match against.
2. **How is a trip's condition known?** Asked at trip creation, inferred from the
   conversation, or left blank and matched loosely? Inference is what the flat model
   already does badly.
3. **Does this subsume M-5, or sit beside it?** Destination is a condition. If
   `condition` is free text, "in Portugal" is expressible — but destination already
   has its own metadata field, and two mechanisms for one idea will drift.
4. **Should existing rows be re-examined?** `travels solo` is mislabelled *today* —
   it is a condition masquerading as a trait. A one-off pass could reclassify, but
   that is an LLM judgement over the whole collection with no ground truth.
