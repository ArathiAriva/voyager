# Visited Places & Anecdotes — design

**Status:** Stages 1–3 built 2026-09-05. Stage 4 (chat capture) not built.
**Phase:** not in the current phase list. Filed as a candidate alongside
[Live Trip Mode](live-trip-mode.md) and [Trip-Scoped Chats](trip-scoped-chats.md).

---

## 1. Two gaps, one shape

**a. A saved place cannot be marked as visited.** `SavedPlaceORM` has no such
field. A restaurant you booked and loved and one you bookmarked and skipped are
the same row. So Voyager cannot answer "where did I actually eat in Rome", cannot
avoid re-recommending somewhere you already went, and cannot weight what you
*did* above what you merely *considered* — which is the stronger preference
signal by a wide margin.

**b. There is nowhere to put an anecdote.** The only user-writable text on a
place is `notes`, and on the `egwene` profile **all 73 places have notes, every
one of them agent-written**:

```
"6th-century Byzantine masterpiece; architectural innovation that influenced..."
"Former Ottoman sultan residence with stunning gardens, harem, and treasury..."
```

Those are descriptions, not memories. Writing "the queue was 40 minutes but the
mosaics were worth it" into the same field would mix your voice with generated
copy in a field that is **also a documented prompt-injection channel** — the
safety suite plants payloads in `saved_places.notes` precisely because that text
reaches the agent.

Both gaps are the same shape: the model has room for what Voyager *suggests*, and
none for what the user *experienced*.

## 2. Why this is worth more than it looks

The journal already stores experience, but it is trip-level prose. An anecdote
attached to a *place* is different, and better, for three reasons:

- **It is retrievable at recommendation time.** Planning a return trip to Rome,
  "you went to Roscioli and said the carbonara was worth the queue" is exactly
  the context that should surface. A journal entry mentioning Roscioli might
  surface; a place-attached anecdote reliably does.
- **Visited-ness is a preference signal the extractor cannot infer.** Today
  preference extraction reads conversations and journal entries. "Went and loved
  it" versus "bookmarked and never went" is a stronger signal than anything in
  either, and it is currently unrecorded.
- **It closes the loop.** Voyager plans a trip, the user takes it, and nothing
  flows back. Visited-marking is the smallest possible feedback edge.

## 3. Design

### 3.1 Schema

```
saved_places.visited      BOOLEAN NOT NULL DEFAULT 0
saved_places.visited_at   TEXT NULL              -- ISO date, when known

place_anecdotes
  id          TEXT PRIMARY KEY
  place_id    TEXT NOT NULL REFERENCES saved_places(id) ON DELETE CASCADE
  body        TEXT NOT NULL                      -- the user's words, verbatim
  created_at  DATETIME NOT NULL
  source      TEXT NOT NULL DEFAULT 'app'        -- 'app' | 'chat'
```

**A separate table, not another column on `saved_places`.** Three reasons:

1. **Provenance stays clean.** `notes` and `summary` are agent- or web-authored
   and treated as untrusted. Anecdotes are the user's own words. Mixing them into
   one field would make it impossible to tell later which is which — the same
   mistake that made `semantic` memory unusable before M-2 added `source`.
2. **More than one anecdote per place** is normal — you go twice, or note
   different things.
3. **`ON DELETE CASCADE`** is right here (unlike conversations in the trip-scoped
   design): an anecdote about a deleted place has no meaning on its own.

`visited` as a real boolean rather than a status enum: "planned / visited /
skipped" invites a third state nobody maintains. Not-visited is the default and
needs no user action.

### 3.2 The anecdote is the user's voice — verbatim

The same constraint as journal capture (see
[live-trip-mode.md](live-trip-mode.md) §6): **the agent never authors or edits
anecdote text.** It stores what the user said, unchanged.

This matters more here than for the journal, because anecdotes are *retrieved
into future recommendations*. An LLM-tidied anecdote would feed the model's own
register back to itself as though it were the user's experience.

Mechanically: echo-back before writing, or client-side capture that never routes
the text through the model. The agent's contribution is identifying **which
place** — that is inference over app state, not over the user's words.

### 3.3 Retrieval

Anecdotes are embedded and searchable, but **kept separate from the place's
descriptive text**:

- A new `anecdotes` Chroma collection, metadata `place_id`, `trip_id`,
  `destination`. Not folded into the `saved_places` embedding, whose `embed_text`
  is currently `summary or notes or name` — appending an anecdote there would
  blur "what this place is" with "what happened to me there", and both queries
  are real.
- `visited` becomes a filter on `search_places`, so the agent can ask for places
  the user actually went to.
- Anecdotes rank *above* descriptions when both match, since first-hand
  experience beats a scraped summary.

### 3.4 Where it surfaces

- **Place card** — a "Visited" toggle, and a visual state (the card is already
  category-coloured; visited could be a check or a muted treatment).
- **Place detail modal** — an anecdote list plus an "Add a note" box, clearly
  labelled as *your* words, separate from the description.
- **Chat** — "we finally made it to Roscioli, the carbonara was worth the queue"
  → the agent offers to mark it visited and store the anecdote verbatim.
- **Trip page** — a visited count ("12 of 27 places"), which is also a quiet
  prompt to record the rest.

### 3.5 Deliberately excluded

- **No rating or score.** A 1–5 star field invites a schema everyone half-fills.
  The anecdote carries the sentiment, and an extractor can read it.
- **No auto-marking from the itinerary.** Being *scheduled* for day 2 is not
  evidence you went. Inferring it would put unearned confidence into a signal
  whose whole value is that it is ground truth.
- **No agent-authored anecdotes** (§3.2).
- **No backfill.** Existing places stay unvisited; that is the honest default.

## 4. Staging

| Stage | Scope | Migration | Notes |
|---|---|---|---|
| **1** | `visited` / `visited_at` columns; toggle on the place card and modal; `visited` filter on `search_places` | Alembic | **built 2026-09-05** |
| **2** | `place_anecdotes` table; UI list + add box on the place modal | Alembic | **built 2026-09-05** |
| **3** | `anecdotes` Chroma collection + `search_anecdotes` tool | none | **built 2026-09-05** — separate collection; explicit ranking above descriptions not implemented |
| **4** | Chat capture — `mark_visited` and `add_anecdote` tools, verbatim, with echo-back | none | Needs [trip-scoped chats](trip-scoped-chats.md) or Live Trip Mode for an unambiguous place |

Stage 1 is independently worth shipping: a visited flag with no anecdotes still
answers "where did I actually go" and still improves recommendations.

## 5. Risks

**Another write tool is another injection target.** Stage 4 adds `mark_visited`
and `add_anecdote` to the agent's surface. The safety suite already plants
payloads in `saved_places.notes`; a tool that writes user-attributed text is a
case worth adding when that suite resumes. Verbatim capture helps — there is no
generation step to hijack — but the *call* can still be induced.

**Anecdote text becomes retrieval input.** It is user-authored and therefore
trusted, unlike `summary`. That is correct, but it means a user pasting web text
into an anecdote launders it into the trusted channel. Worth noting, not worth
guarding against yet.

**Two migrations.** `egwene` has 73 places and 120 conversations;
`scripts/migrate.sh` backs up first (INC-001). Both changes are additive.

## 6. Open questions

1. **Should visited places feed preference extraction?** "Went to and wrote
   warmly about" is the strongest preference signal in the app and is currently
   ignored by the extractor. This may be the highest-value part of the whole
   design, and it is Stage 3-adjacent rather than requiring the chat UI.
2. **Does an anecdote belong in the journal too?** They overlap. Keeping them
   separate risks the user writing the same thing twice; merging them loses the
   place attachment. A journal entry that *references* a place is a third option.
3. **Is `visited` per-place or per-trip-per-place?** The same restaurant saved to
   two trips is two rows today, so per-place works — but that is an artifact of
   `saved_places.trip_id` being non-nullable, not a deliberate choice.
