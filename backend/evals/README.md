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
```

## Caveats

- The runner diffs `/api/trips` before/after each case and passes the persisted itinerary (if any) to the judge, so the reply + saved itinerary are judged as one deliverable. Don't run cases concurrently against the same backend, or the diff may attribute an itinerary to the wrong case.
- For symmetry between confirm-before-save and auto-save planners: if nothing was persisted after the first reply, the runner sends one "yes, save it" follow-up turn and re-checks (`confirmation_turn_used` in results). `latency_s` measures the first (planning) turn only. Judged scores use the first reply + final persisted itinerary. Note: on `needs_info`-style cases (e.g. `vague-europe`) the confirmation turn is a wasted-but-harmless extra call.
- Same judge model as the planner by default; pass `judge_model` in code or set `OPENROUTER_MODEL` differently to reduce self-preference bias.
- Memory-dependent cases (`memory`, `saved-places` tags) score low on an unseeded profile — that's signal about the fixture, not the planner.
- Runs are non-deterministic; for decisions, run 3x and compare means (variance is itself useful data).
