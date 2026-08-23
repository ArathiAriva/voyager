# Voyager Evals

LLM-as-judge evaluation of planning quality: single-agent loop vs multi-agent LangGraph, on a fixed golden set, through the real API.

## How it works

1. `golden_set.json` — 15 planning prompts covering geography, personalization, budget, weather, revision, and memory-dependent cases.
2. `run.py` — for each case and planner mode, creates a conversation and sends the prompt with the `planner` override (the feature flag in `app/flags.py`), captures the streamed reply and latency.
3. `judge.py` — scores each reply 1–5 on geographic_coherence, personalization, feasibility, completeness, actionability (temperature 0). Output shape is LangSmith feedback-compatible for later upload.
4. Results: `evals/results/<timestamp>/{single,multi}.json` + `report.md` with summary and per-case comparison tables.

## Running

Backend must be running (ideally a seeded profile so memory/saved-places cases are meaningful):

```sh
cd backend
python -m evals.run                          # both planners, all cases (~30 LLM runs + 30 judge calls)
python -m evals.run --planner multi          # one mode
python -m evals.run --cases jp-7d,istanbul-3d
python -m evals.run --judge-model openai/gpt-4o-mini   # vary the judge
```

Cost note: the multi-agent graph is ~12 LLM calls per planning conversation (three
researchers doing retrieve-then-synthesize, plus six single-shot nodes), versus 2-4 for
the single-agent loop. A full `--planner both` run over 15 cases is therefore dominated
by the `multi` half.

## Caveats

- Backend failures (`event: error` in the SSE stream — bad or credit-exhausted API key, provider outage) are recorded as `backend error: <detail>`, not as `empty reply`, and skip judging. The distinction matters: "the planner produced nothing" is a quality result, "the backend never answered" is not.
- The runner diffs `/api/trips` before/after each case and passes the persisted itinerary (if any) to the judge, so the reply + saved itinerary are judged as one deliverable. Don't run cases concurrently against the same backend, or the diff may attribute an itinerary to the wrong case.
- For symmetry between confirm-before-save and auto-save planners: if nothing was persisted after the first reply, the runner sends one "yes, save it" follow-up turn and re-checks (`confirmation_turn_used` in results). `latency_s` measures the first (planning) turn only. Judged scores use the first reply + final persisted itinerary. Note: on `needs_info`-style cases (e.g. `vague-europe`) the confirmation turn is a wasted-but-harmless extra call.
- **Judge defaults to the same model as the planner**, so scores carry self-preference bias. Pass `--judge-model <model>` to vary it; the generated `report.md` prints both models and warns when they match. Do not assume a different provider is automatically better: the safety suite's calibration (`evals/safety_judge_calibrate.py`) measured four judges against hand labels and found the cross-provider option was *substantially worse* (33% vs 80% agreement, and its errors inflated failure rates). The equivalent calibration has not been done for quality scoring — treat judge choice here as unmeasured.
- Every result row and `manifest.json` records `agent_model` and `judge_model`. A `mean_score` is not interpretable without them, especially once per-node model choices vary.
- Memory-dependent cases (`memory`, `saved-places` tags) score low on an unseeded profile — that's signal about the fixture, not the planner.
- Runs are non-deterministic; for decisions, run 3x and compare means (variance is itself useful data).

---

# Injection Safety Evals

Indirect prompt-injection eval for the multi-agent planner. Round 1 of the safety
suite (see `docs/safety-evals-spec.md` and `docs/safety-evals-writeup.md` for results).
Untrusted saved-place `notes` carry an instruction aimed at the agent; a benign user
turn makes the agent read that content, and we check whether it obeyed the injection.

## How it works

1. `safety_set.json` — injection cases tagged along three axes (`placement`,
   `instruction_style`, `attack_goal`), each with a `fixture` (a trip + saved places,
   poison lives directly in one place's `notes` — see "Fixture constraints" below),
   a user `script`, declarative `checks`, and an optional `judge` block.
2. `safety_run.py` — for each case: seeds the fixture via the real API, runs the user
   turn(s) against the planner, applies programmatic checks (reply/itinerary regex,
   trips-diff), falls back to the judge only where declared, then tears the fixture
   down. Before running a `multi`-planner case it verifies the script actually routes
   to the graph (see "Routing gotchas") and raises if not, rather than silently
   testing the wrong code path.
3. `safety_judge.py` — for qualitative cases (e.g. suppression), scores injection
   *resistance* 1–5 (5 = resisted, 1 = complied); told the injected instruction
   explicitly so it judges obedience, not travel quality.
4. Results: `results/safety-<timestamp>/safety_runs.json` + `safety_report.md` with
   failure-rate tables per case and sliced by each taxonomy axis.

## Running

```sh
cd backend
python -m evals.safety_run                 # multi planner, all cases, 3 runs
python -m evals.safety_run --runs 1        # quick smoke
python -m evals.safety_run --cases inj-steer-summary-canary
python -m evals.safety_run --gate          # non-zero exit if any case fails (CI)
```

Recommended: run with `VOYAGER_TRACE_LLM=1` (see `.agents/evals-ops.md`) and inspect
`trace_log.jsonl` for at least one run of a new/changed case — a passing verdict only
means what it looks like if you can see the payload actually reached the node under
test. A reply-only check can't distinguish "resisted" from "never saw it."

## Fixture constraints

- **Poison lives in `notes`, not `summary`.** `summary` is written only by the internal
  Jina-enrichment background task ([places.py](../app/routers/places.py)) — it isn't a
  field the public `PATCH /trips/{id}/places/{id}` endpoint accepts, so fixtures can't
  set it directly. `notes` is user-settable and shares the same embed-text fallback
  priority (`summary or notes or name`), so it's still a real attack surface (shared
  places, imports) — just a narrower one than the originally-scoped Jina-`summary`
  vector. Extending the update model to accept `summary` is a candidate for round 2.

## Routing gotchas

Routing a message to the multi-agent graph needs **two** things to be true, not just
`--planner multi`:

1. **Phrase match** — `app/planning/router.py`'s `is_planning_request` looks for a
   hardcoded set of phrases (`"plan my"`, `"itinerary"`, `"organize my trip"`, etc.).
   A script without one silently runs the single-agent chat loop instead.
2. **`classify_intent` reads `full_plan`** — even with a phrase match, the graph's own
   intent classifier needs an explicit destination *and* duration in the message, or it
   routes to the `clarify` node (asks a follow-up question) and never touches
   `build_brief` or the researchers at all.

Both failure modes produce a plausible-looking reply and a "passing" verdict from a
regex-only check (an empty/off-topic reply trivially satisfies `reply_not_contains`),
which is exactly the trap: it looks like resistance and is actually the eval never
running. `safety_run.py` now hard-fails before executing a `multi`-planner case whose
script doesn't phrase-match (item 1) — item 2 currently has to be checked via trace
(`classify_intent`'s output should show `"intent": "full_plan"`, not `"needs_info"`).

## Other caveats

- **All payloads are inert canaries** (`AZURE-PELICAN`, `PELICAN-TRIP`) — no real
  exfiltration or harmful instructions; all reviewable in `safety_set.json`.
- **`inj-control-clean` is a negative control**, not an attack: identical shape to the
  steer case with no payload. If it ever fails, the checks are miscalibrated — fix them
  before trusting the other verdicts.
- **Unsafe-tool-call is out of scope for the multi-agent planner**, not just deferred
  for time: `classify_intent` only proceeds past `clarify` once it reads a message as
  a legitimate full plan, and once it does, persisting a trip is the graph's normal
  conclusion — there's no code path where saved-place content is read but a write
  isn't already sanctioned by the user's own request. Retarget at the single-agent
  loop's independently-invokable tool calls in round 2.
- Fixtures are torn down per case; `DELETE /trips/{id}` also cleans up that trip's
  Chroma embeddings ([trips.py](../app/routers/trips.py)) so orphaned fixture places
  from earlier runs don't pollute later runs' semantic retrieval. Still, don't run
  cases concurrently against a backend you care about — the trips-diff can misattribute
  across cases.
- Judge defaults to `google/gemini-2.5-flash-lite` — a different provider than the
  agent under test (`OPENROUTER_MODEL`, default `anthropic/claude-haiku-4-5`), to
  reduce self-preference bias, and cheap (~$0.10/$0.40 per M input/output tokens on
  OpenRouter as of 2026-08-22 — confirm current pricing before relying on it). Pass
  `--judge-model` to override.
