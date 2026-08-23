# Semantic Memory Quality Analysis

**Scope:** the Chroma `semantic` collection ("user preferences") — how entries get written, how they get retrieved, and how the resulting noise reaches the planner.
**Evidence base:** code read at the cited lines, plus read-only probes against the live `chroma_egwene` collection (289 preferences, 97 episodes). Nothing was modified.
**Status:** investigation only. No fixes applied.

---

## 1. Summary of findings

The `semantic` collection is an **append-only, unbounded, unscoped, untyped bag of strings**. There is no cap, no TTL, no metadata, no contradiction handling, and — because of a hash bug — not even working exact deduplication. Every confirmed symptom follows from that one architectural fact.

Confirmed by direct measurement on `chroma_egwene`:

| Metric | Value |
|---|---|
| Total preferences | 289 |
| Total episodes | 97 |
| Exact-duplicate groups | 6 (7 redundant rows) |
| Food/dining-related entries | 129 / 289 (45%) |
| Transient/episodic entries misfiled as preferences | ~33 |
| Distinct concepts at cosine ≥ 0.90 | 256 (33 rows redundant) |
| Distinct concepts at cosine ≥ 0.80 | 189 (**100 rows redundant, 35%**) |
| Rows carrying any metadata | **0** — all `None` |

The single most consequential finding is not any of the three already measured. It is **item 2.4 below: the `semantic` collection has no per-user, per-profile, or per-trip scoping in code at all.** Isolation today is an accident of process-level environment configuration, and it silently fails the moment anything runs in-process against more than one profile.

---

## 2. Failure modes

### 2.1 Non-deterministic IDs defeat exact dedup (confirmed, already known)

`backend/app/memory.py:53`:

```python
pref_id = str(abs(hash(pref)))
```

The comment at `memory.py:52` claims this is deterministic. `hash()` on `str` is randomized per process via `PYTHONHASHSEED`, so the same text yields a different ID in every server process. Upsert dedup therefore only holds within one process lifetime. This is a two-line fix (see §5.1).

Two secondary consequences worth noting, both distinct from the duplicate-rows symptom:

- **Deletion and correction are impossible.** Nothing in the codebase can address a specific stored preference by ID, because no caller can recompute the ID a previous process used. Any future "forget this preference" feature, cleanup job, or contradiction-reconciler is blocked on fixing this first. Grep confirms no `delete` call anywhere against `_semantic()`.
- **`abs(hash(...))` is collision-prone by construction.** `abs()` folds the 64-bit hash space onto its positive half and maps `hash(x)` and `-hash(x)` to the same ID. At 289 rows this is harmless, but it means the ID scheme is not merely non-deterministic — it is also not injective. Any fix should use a content hash (`hashlib.sha256`), not just a stabilized `hash()`.

### 2.2 The extraction prompts actively invite transient facts (confirmed)

This is the root cause of the ~33 misfiled entries, and it is a prompt bug, not a code bug.

`backend/app/routers/conversations.py:59`:

> 2. A list of specific user preferences **or facts** revealed (empty list if none).

`backend/app/routers/journal.py:23` is identical wording. The phrase **"or facts"** is doing the damage. It explicitly authorizes the model to emit non-preferences, and the model complies. The guidance at `conversations.py:67` ("Preferences should be concrete and reusable ... Omit vague or uninformative entries") does not correct this, because it filters on the wrong axis: it screens out *vague* entries, never *time-bound* ones. "Traveling to Bangkok in September" is maximally concrete and passes the stated bar cleanly — it is just not durable.

Measured output of that instruction:

```
planning a 7-day trip          prefers 3-day trip duration      Planning for 4 days
interested in 4-day trips      visiting Mexico City for 4 days  traveling to Barcelona for 3 days
Traveling to Bangkok in September   currently in Rome           Expects rainy season weather
visited Kyoto in April 2024    planning trips to Lisbon         planning a 3-day trip to Istanbul
planning a food-focused day in Rome
```

Note there are **five** mutually contradictory duration claims, not the three cited in the brief. There is no timestamp on any of them (§2.5), so nothing downstream can tell which is current — not even by recency.

Two entries are worse than transient; they are **app-mechanics artifacts, not user traits at all**:

```
uses saved places feature for travel planning
uses saved places for trip planning
```

The extractor is describing the user's product usage back to itself. These are pure retrieval noise with no possible downstream value.

Also note the journal prompt is structurally misapplied. `journal.py:41` passes only `Destination: ... / Journal entry: ...` — journal entries are *retrospective trip records by nature*, so nearly everything in them is episodic. Asking the same "preferences or facts" question of a journal entry is close to a guarantee of transient output. `journal.py:56` correctly routes the episode to episodic memory, then `journal.py:58` routes the "facts" into the durable semantic store.

### 2.3 Semantic near-duplicates, and the measured retrieval collapse

The 45% food skew is real (129/289), and it is **not** redundancy that ID-based dedup could ever catch — the strings genuinely differ. Clustering the live embeddings by cosine similarity:

| Threshold | Near-dup pairs | Distinct components | Redundant rows |
|---|---|---|---|
| 0.95 | 14 | 277 | 12 (4%) |
| 0.90 | 60 | 256 | 33 (11%) |
| 0.85 | 106 | 232 | 57 (20%) |
| 0.80 | 204 | 189 | **100 (35%)** |

**Does `n_results=5` mitigate the noise, or sample randomly from near-duplicates?** Neither, exactly — and the real answer is worse than "random sampling." Chroma's ranking is deterministic by distance, so retrieval is not random. It is *deterministically biased*: when 129 rows crowd one region of embedding space, that region reliably wins the top-5 for any query with even mild food valence, and the paraphrase that happens to sit nearest the query wins each slot.

Measured (`n_results=5`, matching `memory.py:177` and the `search_memory` default):

```
Q: "what does the user like to eat"
   enjoys chef-driven dining experiences
   enjoys culturally immersive food experiences
   enjoys food-centric travel experiences
   prefers chef-driven dining experiences        <- paraphrase of row 1
   Enjoys food-focused travel experiences        <- paraphrase of row 3

Q: "dining style"
   appreciates both traditional and chef-driven dining
   enjoys chef-driven dining experiences
   prefers chef-driven dining experiences        <- paraphrase of row 2
   enjoys authentic, locally-focused dining experiences
   values historic and culturally significant dining locations
```

Effective diversity of the top-5 is roughly **2–3 distinct traits out of 5 slots** on food-adjacent queries. The user pays 5 slots of planner context and receives 2–3 bits of information.

The exact-duplicate bug compounds this visibly — a duplicate pair has *identical* embeddings, so it occupies two adjacent slots by construction:

```
Q: "budget accommodation preferences"
   budget-conscious about dining
   travels on a tight budget
   considers fine-dining splurges when budget allows
   prefers local neighbourhoods over tourist areas   <- duplicate
   prefers local neighbourhoods over tourist areas   <- duplicate
```

Two of five slots are the same string. Note also that this accommodation query returned **three dining entries and zero accommodation entries**. The food skew is not merely diluting food queries; it is crowding out unrelated categories entirely. That is the concrete retrieval-quality cost.

### 2.4 No per-user / per-trip scoping exists in code (highest-severity finding)

`store_preferences(preferences: list[str])` at `memory.py:46` takes **no user ID, no profile ID, and no trip ID**, and writes no metadata. Confirmed against live data: every `metadatas` value in the collection is `None`. The collection is one flat global bag.

Isolation today comes entirely from process-level environment configuration:

- `memory.py:19`: `_CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")` — read **once at module import**, into a module-level constant.
- `backend/scripts/run.sh:41-44` sources `profiles/.env.<name>` with `set -a` before exec'ing uvicorn.
- Each profile sets a distinct path — `profiles/.env.egwene:CHROMA_PATH=./chroma_egwene`, `.env.mat:./chroma_mat`, and so on across 7 profiles.

So **profile isolation is real but structural, not logical**, and it carries three sharp edges:

1. `_CHROMA_PATH` is captured at import time (`memory.py:19`) and `_client` is a module-level singleton (`memory.py:18,22-29`). Changing `CHROMA_PATH` at runtime has no effect. Any future in-process multi-user path — a real auth layer in Month 6, a batch eval sweeping profiles, a worker serving two users — will silently pool every user's preferences into whichever profile loaded first. There is no error, no warning; just cross-user contamination.
2. `.env` at `backend/.env` sets `CHROMA_PATH=./chroma_egwene`, the same path as the `egwene` profile. Running the server *without* `run.sh` writes into the dev profile's collection. There is nothing preventing that.
3. **Within a profile there is no trip scoping whatsoever, and this is a live correctness problem today.** Compare with the sibling collections, which do it correctly: `store_journal_entry` (`memory.py:62-68`) writes `trip_id` metadata and `search_journals` (`memory.py:91`) filters on it; `store_saved_place` (`memory.py:117-125`) and `search_saved_places` (`memory.py:147-154`) do the same. The `semantic` collection is the **only** one of the four that omits this — so preferences learned on a Lisbon trip are retrieved with full authority when planning Bangkok.

The live data shows exactly this bleed. Destination-locked entries sitting in a global store include `enjoys traditional Portuguese cuisine and fado music`, `likes fado dining and traditional Portuguese petiscos`, `wants to try local food specialties like pastéis de Nata`, and `prefers curated food market experiences (Time Out Market)` — all Lisbon-specific, all globally retrievable. Probing confirms the mechanism fires in both directions:

```
Q: "Where should I eat in Lisbon?"
   planning trips to Lisbon                       <- transient entry, top hit
   enjoys traditional Portuguese cuisine and fado music
   likes fado dining and traditional Portuguese petiscos
   ...
```

Here the Lisbon entries are correctly relevant. But nothing distinguishes "Portuguese cuisine" as *destination-conditional* from "prefers street food" as *durable*, so on a Tokyo plan the same rows compete for slots on any food query, and a critic instructed to enforce "the user's stated preferences" may treat a Lisbon-specific trait as a global requirement.

The Tokyo probe shows the transient class dominating in the same way:

```
Q: "Plan a 5-day trip to Tokyo"
   interested in visiting Tokyo and Kyoto
   visited Kyoto in April 2024                    <- transient
   planning a 7-day trip                          <- transient, contradicts the 5-day request
   has visited Kyoto and Florence previously
   Has previously traveled to Kyoto and Florence (...)   <- paraphrase of row 4
```

Three of five slots are transient or duplicated. Worse, `planning a 7-day trip` is retrieved for a user who *just asked for 5 days* — a stale fact ranking above the live request, handed to the critic as authoritative intent.

### 2.5 No timestamps, provenance, confidence, or type

Confirmed: `store_preferences` (`memory.py:46-55`) passes only `ids` and `documents` to `upsert` — no `metadatas` argument. Live data confirms all-`None`. This is the structural blocker under every other fix:

- **No recency** → contradictions cannot be resolved by "latest wins," the cheapest possible reconciliation strategy.
- **No provenance** → cannot tell a conversation-derived preference from a journal-derived one, cannot trace a bad preference to its source, cannot bulk-remove entries from one extraction run.
- **No confidence** → a preference stated once in passing outranks nothing and is outranked by nothing.
- **No type/durability tag** → cannot filter transient from durable at query time even after classifying them.
- **No trip/destination binding** → §2.4.

### 2.6 No growth cap, no aging, no compaction, no reconciliation

Explicitly verified absent. A grep for `prune|ttl|compact|max_prefs` across `app/`, `tests/`, `scripts/`, and `alembic/` returns only the word "semantic" in identifiers and docstrings. There is **no** `delete` call against `_semantic()` anywhere in the codebase. Growth is strictly monotonic: every message exchange (`conversations.py:357`, fired unconditionally per exchange via `asyncio.create_task`) and every journal create (`journal.py:98`) can append.

**The confirmed growth rate is the alarming part.** 289 preferences from 97 episodes ≈ **3.0 new preferences per conversation**, with no ceiling and no decay. Nothing in the pipeline reconciles a new preference against existing ones — `store_preferences` never reads before writing. At this rate the collection reaches ~1000 rows within a few hundred more exchanges, at which point `n_results=5` retrieves a vanishingly biased sample and the food cluster swallows nearly every query.

### 2.7 The critic receives raw, unfiltered preferences (confirmed)

`backend/app/agents/critic.py:61` passes `state["user_preferences"]` straight into the LLM payload with no filtering:

```python
"user_preferences": state.get("user_preferences", []),
```

Those values originate at `graph.py:53` from `planner.load_user_context` (`planner.py:123-136`), which returns `mem.get("preferences", [])` verbatim from `search_memory` — no dedup, no filter, no ranking beyond Chroma's distance ordering.

The asymmetry the brief identified is confirmed in code. `build_brief` (`planner.py:139-149`) sends the same context through an LLM whose prompt (`BRIEF_PROMPT`, `planner.py:66-87`) asks for `"list of relevant preferences from memory"` — the word **"relevant"** gives the model license to drop contradictions and noise, which is why build_brief compresses. The critic gets no such instruction. Its prompt at `critic.py:23` reads:

> 2. Preference alignment — does the plan match the user's stated preferences from memory?

The phrasing **"stated preferences"** frames whatever arrives as authoritative user intent. So the critic is told to enforce a list that may contain `planning a 7-day trip` alongside `prefers 3-day trip duration` — a contradiction it cannot resolve and was not told exists. `critic.py:66` also passes `brief` in the same payload, so the critic sees *both* the filtered and unfiltered views with no signal about which to trust.

The failure is bounded but real: it manifests as unstable critique scores and spurious "preference mismatch" issues. Since `should_revise` loops up to twice on a low score (per the module docstring at `graph.py:1-12`), spurious critic issues translate directly into wasted revision loops and wasted tokens.

### 2.8 Additional issues not in the original brief

- **Episodic memory has a parallel duplicate problem.** 3 duplicate document groups among 97 episodes. Here the ID is `conversation_id` (`memory.py:42`), which *is* stable — so these are genuinely distinct conversations that produced identical summaries. Lower severity, but it means episodic retrieval also wastes slots.
- **Journal episodes are being overwritten or lost.** `journal.py:56` stores episodes under `f"journal-{entry_id}"`, but the live episodic collection contains **zero** IDs with a `journal-` prefix. Either no journal entries have been created in this profile, or journal extraction is silently failing. `journal.py:60-61` swallows all exceptions into a log line, so a persistent failure here would be invisible. Worth checking whether `chroma_egwene` has journal entries at all — if it does, this is a live bug.
- **Journal updates re-embed but never re-extract.** `journal.py:118` calls `store_journal_entry` on PATCH but does **not** call `_extract_journal_memory`. Preferences extracted from the original text persist unchanged after an edit, including preferences the user just edited away. Note this is asymmetric with delete: `journal.py:132` removes the journal embedding but has no way to remove derived preferences (blocked by §2.1).
- **Extraction is fire-and-forget with no backpressure.** `conversations.py:357` spawns an unawaited `asyncio.create_task` per exchange. Failures are logged and dropped (`conversations.py:105-106`). Nothing bounds concurrency, and no reference to the task is retained — under CPython the task may be garbage-collected mid-flight.
- **Duplicate extraction cost.** Every message exchange re-sends the *entire* transcript (`conversations.py:75-79`) to the LLM and re-extracts from scratch. A 20-message conversation re-extracts the same early preferences ~10 times, which is a significant contributor to both the duplicate rate and the usage bill logged via `usage_context.set("memory_extraction")` (`conversations.py:73`).
- **The memories API surfaces raw, unbounded output.** `app/routers/memories.py:14` returns every row via `.get()` with no pagination. At 289 rows it is merely ugly; it scales linearly with the collection.
- **A silent behavioral asymmetry in extraction.** `conversations.py:73` sets `usage_context.set("memory_extraction")`, but `_extract_journal_memory` (`journal.py:34-43`) does not set any usage context. Journal extraction cost is therefore attributed to whatever context was last set — a cost-accounting leak, minor but real given the project's eval/cost-tracking focus.

---

## 3. Ranked recommendations

Ranked by (impact × confidence) / cost. Items 1–3 are the ones that matter.

### 3.1 Fix the hash ID — content-addressed, normalized  *(code fix, trivial, no migration)*

`memory.py:53` → `hashlib.sha256(pref.strip().lower().encode()).hexdigest()[:32]`.

Normalizing case and whitespace before hashing catches a class the raw hash never would — the live data contains `enjoys food-focused travel experiences` and `Enjoys food-focused travel experiences` as separate rows purely on capitalization.

**Do this first regardless of what else you choose.** It is the prerequisite for every other fix: stable IDs are what make deletion, cleanup, compaction, and correction possible at all (§2.1). Prefer `sha256` over stabilizing `hash()` to also close the `abs()` collision issue.

**Tradeoff:** none of substance. Existing 289 rows keep their old random IDs and will not collide with new SHA-based ones, so a one-time cleanup is needed to collapse the historical duplicates. Not a schema migration — a script.

### 3.2 Add metadata to `store_preferences`  *(data-model change, needs backfill)*

Change the signature to accept and store:

```python
{"created_at": iso8601, "source": "conversation"|"journal", "source_id": str,
 "kind": "durable"|"transient", "destination": str|None}
```

This is the **highest-leverage change in the document**, because §2.5 is the blocker under contradiction reconciliation, recency weighting, provenance-based cleanup, trip scoping, and transient filtering. Every one of those is cheap once metadata exists and impossible until it does. It also brings `semantic` in line with `journals` and `saved_places`, which already carry metadata correctly (`memory.py:62-68`, `memory.py:117-125`) — this is closing an inconsistency, not inventing a pattern.

**Tradeoff:** Chroma metadata is schemaless, so this needs no Alembic migration — but the existing 289 rows have `None` metadata and cannot be backfilled with real timestamps or provenance, that information is gone. Options: backfill a sentinel (`{"created_at": null, "kind": "unknown"}`) and have query filters treat missing metadata as permissive, or drop and rebuild the collection. Given this is a learning project at Month 4.5 with a dev profile, **rebuilding is cleaner and I would recommend it** — the historical 289 rows have low value and known-bad composition.

### 3.3 Separate transient from durable  *(prompt fix + code fix)*

Three layered options, best combined:

**(a) Prompt fix — cheapest, do it now.** In `conversations.py:56-67` and `journal.py:20-31`:
- Delete **"or facts"** from line 59 / line 23. It is the specific token authorizing transient output (§2.2).
- Add an explicit durability test with negative examples, e.g.: *"Only include traits that would still be true on a completely different trip a year from now. Exclude anything about a current or planned trip — destinations, dates, durations, weather, or what the user is doing right now. Exclude observations about the user's use of the app itself."*
- The current guidance filters on vagueness, not time-boundedness. Both axes need stating.

**(b) Structured output — more robust.** Have the extractor return `{"text": ..., "kind": "durable"|"transient"}` and either drop transient entries or route them to episodic memory, where they belong. Pairs naturally with 3.2's `kind` field.

**(c) Post-filter — belt and braces.** A cheap regex/classifier gate in `store_preferences` rejecting entries matching planning/date/duration/location-present patterns. Catches model non-compliance, which will happen.

**Tradeoff:** (a) alone is one prompt edit and will meaningfully reduce inflow, but is unreliable — LLM extractors drift and there is no enforcement. (c) risks false positives (`prefers 3-day trips` is arguably a durable pacing preference, while `planning a 7-day trip` is not; the regex cannot distinguish them). **(b) is the right long-term answer** because it makes the model state its own intent explicitly rather than having a regex guess it. None of these touch the existing 33 transient rows — that needs a one-time cleanup pass.

### 3.4 Consolidate semantic near-duplicates  *(code fix; three strategies)*

**(a) Write-time embedding dedup — recommended.** In `store_preferences`, query the collection with the incoming text first; if the nearest existing entry is within a cosine threshold, skip the write (or merge by bumping a confidence counter in metadata). Measured data suggests a **0.85–0.90 threshold**: 0.90 catches clear paraphrases (33 rows, 11%) with low false-merge risk, while 0.80 is too aggressive at 100 rows (35%) and would start merging genuinely distinct traits. Cost is one embedding + one query per stored preference — negligible relative to the extraction LLM call already being made.

**(b) Periodic compaction.** Cluster the collection, feed each cluster to an LLM, write back one canonical phrasing. Better output quality than (a) — it produces genuinely clean text rather than an arbitrary surviving paraphrase — but needs a job runner, costs tokens, and risks losing nuance during merges. Good as an occasional maintenance script; overkill as infrastructure at this stage.

**(c) Cap + LRU.** Reject as the primary strategy. A cap does not fix composition, it just truncates it — with a 45% food skew, an LRU cap evicts *rare and valuable* preferences (the one accommodation trait) while the food cluster keeps refreshing itself. Retain only as a backstop ceiling behind (a).

**Recommendation: (a) as the standing mechanism + a one-time (b) pass over the existing 289 rows.** (a) stops the bleeding; (b) cleans the wound.

**Tradeoff on all three:** any merge is lossy and irreversible. `prefers street food over restaurants` and `enjoys chef-driven dining experiences` sit close in embedding space but encode genuinely different — arguably contradictory — signals. Set the threshold conservatively and log every merge.

### 3.5 Reconcile contradictions  *(depends entirely on 3.2)*

Options in ascending cost:

- **Recency wins.** With `created_at` from 3.2, sort retrieved preferences by timestamp and let the newest claim in a conflicting group survive. Cheap, handles the duration case correctly (the newest duration statement is the right one), no LLM call.
- **Trip-scope them out.** Most observed "contradictions" are not contradictions at all — they are trip-specific facts leaking into a global store (§2.4). `prefers 3-day trip duration` and `planning a 7-day trip` do not conflict if each is bound to its own trip. **Fixing scoping dissolves most of this category for free**, which makes it a better investment than a reconciliation engine.
- **LLM reconciliation at write time.** Retrieve neighbors, ask the model whether the new preference supersedes or coexists. Highest quality, adds an LLM call per stored preference, and introduces a new failure mode (bad reconciliation silently destroying a correct preference).

**Recommendation: recency + scoping.** Skip LLM reconciliation for now — it is the expensive answer to a problem that scoping largely eliminates.

### 3.6 Filter what reaches the critic  *(code fix, tiny, high value)*

Independent of everything above and shippable today. At `critic.py:61`, dedup and cap `user_preferences` before it enters the payload — at minimum exact-dedup and truncate. Better: pass `brief["user_context"]["preferences"]` (already filtered by `build_brief`) instead of the raw list, so the critic and the planner are evaluated against the *same* preference set.

That last point is a correctness argument, not just a noise argument: today the critic is scoring a plan against a **different** preference list than the one the plan was built from (§2.7). That is an unfair evaluation by construction, and given `should_revise` loops on the score, it converts memory noise directly into wasted revision cycles and tokens.

**Tradeoff:** if the critic only ever sees build_brief's filtered view, it loses the ability to catch preferences build_brief wrongly dropped. Acceptable — build_brief's filtering is currently the only thing working correctly in this path.

### 3.7 Add trip/destination scoping to preferences  *(data-model change; follows 3.2)*

Store `destination` metadata where a preference is destination-bound, and have `search_memory` accept an optional filter so `enjoys traditional Portuguese cuisine` does not surface when planning Bangkok. The pattern already exists and works — copy `search_journals`' `where={"trip_id": ...}` (`memory.py:91`) or `search_saved_places`' filter construction (`memory.py:147-154`).

**Tradeoff:** requires the extractor to distinguish destination-bound from global preferences, which is the same classification problem as 3.3(b) and should be solved in the same change.

### 3.8 Lower-priority cleanups

- Re-extract journal memory on PATCH (`journal.py:118`), or accept and document the staleness.
- Investigate the missing `journal-` episode IDs (§2.8) — possibly a live silent failure.
- Set `usage_context` in `_extract_journal_memory` (`journal.py:34`) for correct cost attribution.
- Extract incrementally from new turns only, rather than re-sending the whole transcript (`conversations.py:75-79`) — cuts both duplicate generation and token spend.
- Hold a reference to the task spawned at `conversations.py:357` to prevent GC mid-flight.
- Paginate `app/routers/memories.py:14`.

---

## 4. Suggested sequencing

1. **3.1** (hash) + **3.6** (critic filter) — two small code changes, immediate benefit, no data implications. Ship together.
2. **3.3(a)** — delete "or facts" and add the durability test to both prompts. One edit each, stops the largest inflow of noise.
3. **3.2** (metadata) — the structural unlock. Decide rebuild-vs-backfill here; **rebuild is recommended** given the dev-profile context and the known-bad composition of the existing rows.
4. **3.4(a)** (write-time embedding dedup at ~0.88) + a one-time **3.4(b)** compaction pass over whatever survives step 3.
5. **3.5** (recency) and **3.7** (scoping) once metadata is in place.

Steps 1–2 are roughly an hour and address the majority of ongoing damage. Step 3 is the real decision point.

---

## 5. Mitigations assumed to exist that do not

Stated explicitly, since the brief asked:

- **No deduplication that survives a process restart.** `memory.py:53` — §2.1.
- **No semantic/near-duplicate dedup at any point,** write-time or read-time.
- **No cap, TTL, aging, decay, or compaction.** Verified by grep across `app/`, `tests/`, `scripts/`, `alembic/`. Growth is strictly monotonic at ~3 preferences per conversation.
- **No contradiction detection or reconciliation.** `store_preferences` never reads before writing.
- **No metadata of any kind** — no timestamp, provenance, confidence, type, or trip binding. Confirmed `None` on all 289 live rows.
- **No per-user or per-trip scoping in code.** Profile isolation is a side effect of `CHROMA_PATH` being read once at import (`memory.py:19`) into a process-global singleton — not a logical guarantee, and it breaks silently in any in-process multi-profile scenario.
- **No deletion path.** Nothing in the codebase can remove a stored preference. Journal deletion (`journal.py:132`) removes the entry embedding but leaves derived preferences orphaned forever.
- **`n_results=5` is not a mitigation.** It is deterministic distance ranking over a skewed corpus, so it reliably over-samples the dominant cluster rather than sampling neutrally — measured at 2–3 distinct traits per 5 slots on food-adjacent queries, and returning zero relevant rows on an accommodation query.

---

*Status: recommendations 3.1, 3.3(a), and 3.6 shipped in `e966e9f`. Everything still
open from this analysis is tracked as items M-1 … M-8 in [OPEN-ITEMS.md](../OPEN-ITEMS.md).*
