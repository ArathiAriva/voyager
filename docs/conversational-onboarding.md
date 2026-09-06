# Conversational Onboarding — design

**Status:** proposed, nothing built.
**Phase:** not in the current phase list. Filed as a candidate alongside
[Live Trip Mode](live-trip-mode.md), [Trip-Scoped Chats](trip-scoped-chats.md) and
[Visited Places & Anecdotes](visited-places-and-anecdotes.md).

---

## 1. The problem

A new profile is empty and the app has nothing to personalise with. Memory builds
from ordinary use, which works — but slowly, and the first several conversations
are the ones least able to show what Voyager is for.

There is **no onboarding at all** today: grepping `app/` and `frontend/src/` for
"onboard" returns nothing. A new user meets four empty states ("No memories yet",
"No trips yet", "No planning runs yet") and an agent that knows nothing about them.

## 2. Why not a survey

The obvious solution is a setup form: budget band, pace, dietary needs, travel
style. Most apps do this. Three reasons it is the wrong fit *here specifically* —
this is an architectural argument about Voyager, not a general claim about surveys.

**a. It bypasses the pipeline this app is built on.** Extraction, write-time dedup,
reconciliation, journal RAG, saved places — all of it reads free-text traits. A
dropdown writes `budget: mid-range` into a structured field nothing else consumes.
Conversation feeds the machinery; a form routes around it.

**b. It produces the wrong *kind* of data.** Compare what is actually stored today:

```
prefers coastal walks to woodland trails when available
enjoys spending time lounging at indie cafes on solo trips
does not drink alcohol
```

against what a form yields: `pace: relaxed`, `budget: mid-range`. The first are
specific enough to retrieve against and to quote back; the second are categories
with no texture. `search_memory` on "what do they like to eat" cannot do anything
useful with an enum.

**c. People are bad at introspecting, and good at remembering.** "Rate your budget"
gets an aspirational answer. "Tell me about the best meal you've had travelling"
gets *"this tiny place in Lisbon, we queued 40 minutes and it was worth it"* — from
which the extractor derives budget tolerance, food priority, crowd tolerance, and a
saveable place, none of which the person would have self-reported accurately.

**And the first impression is wrong.** Fifteen questions before the app has done
anything is a tax paid up front for value delivered later, in an app whose entire
pitch is that it talks to you.

## 3. What surveys get right

Two real problems that a naive "just chat with it" onboarding does **not** solve,
and which this design has to:

- **The blank page.** "Tell me about your past trips" is an essay prompt. People
  freeze. A form at least tells you what is being asked.
- **Knowing when you are done.** A form has a progress bar and a submit button. An
  open conversation has no visible end, so the user either stops too early or feels
  interrogated.

Any design that ignores these will feel worse than the survey it replaced.

## 4. Design

### 4.1 Ask about one trip, not about preferences

The opening question is concrete and answerable from memory:

> "Let's start with somewhere you've been. What's a trip you'd happily do again?"

Not "what's your travel style". A specific trip is a story, and a story carries the
traits an abstract question asks for directly and gets wrong.

It also produces a **visible artifact** — a real `past` trip on the trips page —
rather than an invisible profile update. The user sees the app do something.

### 4.2 Two or three follow-ups, chosen by what is missing

Not a fixed script. After extraction runs on the first answer, the agent asks about
a facet nothing has been learned about yet — the same facets
`PREFERENCE_FACETS` already enumerates for retrieval (food, accommodation, pace,
activities, budget, transport):

- nothing about food yet → "What did you eat there that you still think about?"
- nothing about pace yet → "Were you up early, or slow mornings?"

**Hard cap at three follow-ups.** The goal is a warm start, not a complete profile.

### 4.3 Stop and show the work

The step that solves both survey problems at once:

> "Here's what I picked up — anything wrong?"
> - enjoys queuing for food that's worth it
> - prefers walkable neighbourhoods
> - travels with a partner
> `[looks right]  [remove this one ✕]`

Progress becomes visible, the end becomes obvious, and the user can correct
extraction *before* it shapes anything. The Memories page already has per-row
delete, so the affordance exists — this surfaces it at the moment it matters.

### 4.4 Chips as affordances, not fields

When the agent asks about pace, offer three tappable suggestions —
*early starts · slow mornings · depends* — which removes the blank page without
becoming a form. Tapping one sends it as an ordinary message; typing something else
behaves identically. The chips are a hint about what a good answer looks like, not
an enumeration of allowed answers.

### 4.5 Always skippable

"Skip" on every prompt, and the app works with zero onboarding. Memory already
builds from ordinary use — this is a head start, not a gate. A user who skips
should never be nagged again.

## 5. The real risk: extraction quality

**Onboarding extraction is higher-stakes than ordinary extraction**, and this is the
part most likely to cause quiet damage.

- It is **uncorrected**. It lands before the user knows the system well enough to
  notice a wrong inference.
- It is **front-loaded**. Everything extracted here shapes every recommendation that
  follows, and M-4's reconciliation only fires when a *contradiction* shows up later.
- One story is **thin evidence**. A splurge anniversary trip could yield "prefers
  luxury hotels", which is then true of the user forever.

Mitigations, in order of importance:

1. **§4.3's confirmation is not optional.** It is the whole safety mechanism, not a
   nicety. A friendly "got it!" would be strictly worse than a survey, because the
   user would neither see nor be able to correct what was inferred.
2. **Mark the provenance.** `store_preferences(source="onboarding")` — the field
   already exists (M-2). A preference derived from one story with no corroboration
   deserves to be distinguishable later, and it makes a bad onboarding batch
   removable as a unit.
3. **Prompt for hedging.** The extraction prompt already demands durability. For
   onboarding it should also prefer the weaker claim: "enjoyed a splurge on that
   trip" over "prefers luxury hotels".

## 6. Deliberately excluded

- **No structured profile fields.** Nothing downstream reads them, and adding a
  parallel representation of preference would guarantee the two disagree.
- **No completion score or progress bar.** They imply a target, which invites
  answering to fill the bar rather than truthfully.
- **No agent-authored journal entries or anecdotes.** The verbatim constraint from
  [live-trip-mode.md](live-trip-mode.md) §6 holds here too — onboarding may create
  *trips* and *preferences*, never the user's own words.
- **No re-prompting.** Skipped means skipped.

## 7. Staging

| Stage | Scope | Migration | Notes |
|---|---|---|---|
| **1** | Empty-state prompt on the chats page + an onboarding system-prompt block; existing extraction does the rest | none | Smallest thing that works; no new tools |
| **2** | Facet-gap follow-ups (reuse `PREFERENCE_FACETS`) and the hard cap | none | |
| **3** | The confirm-and-correct step | none | **Ships with Stage 1 or not at all** — see §5 |
| **4** | Suggestion chips in the composer | none | Polish |

Stage 3 is listed third but is **not optional relative to Stage 1**: shipping
extraction-from-onboarding without correction is the failure mode in §5.

## 8. Open questions

1. **Where does it live?** A first-run screen, or just a warmer empty state on the
   chats page that seeds the first message? The latter is far less code and cannot
   strand anyone — but it is also easy to miss.
2. **Does it create trips, or only preferences?** Creating a `past` trip is the
   visible artifact that makes the exchange feel worthwhile. But `create_trip`'s
   description says never to call it without explicit confirmation, so onboarding
   must ask rather than assume — which adds a turn.
3. **How does this interact with [trip-scoped chats](trip-scoped-chats.md)?** An
   onboarding conversation is about a past trip that does not exist yet. It would
   have to create the trip and then scope itself to it, which is a new ordering.
4. **Is one story enough to be worth it?** Unmeasurable in advance. Worth building
   Stage 1 narrowly and reading the resulting preferences before adding follow-ups —
   if one story yields two useful traits, the follow-ups matter; if it yields six,
   they may not.
