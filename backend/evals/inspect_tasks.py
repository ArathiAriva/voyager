"""Phase-1 Inspect wrappers for Voyager's live-backend evals.

They delegate execution to the existing runners and retain the full result in
Inspect sample state. This validates Inspect tasks, scoring and logs without
changing the production-facing evaluation protocol.

    inspect eval evals/inspect_tasks.py@voyager_quality_spike
    inspect eval evals/inspect_tasks.py@voyager_safety_spike
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import Generate, TaskState, solver

EVALS_DIR = Path(__file__).parent
# Inspect loads a task file as an isolated module, unlike ``python -m evals...``.
# Make the backend import root available so these wrappers can reuse the runners.
BACKEND_DIR = EVALS_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from evals import run as quality_runner
from evals import safety_run
from evals._harness import adopt_backend_database, guard_profile

DEFAULT_BASE_URL = "http://localhost:8060"
# Execution happens through Voyager's backend, not this Inspect model.
LOG_MODEL = "mockllm/model"


def _case(filename: str, case_id: str) -> dict[str, Any]:
    for case in json.loads((EVALS_DIR / filename).read_text())["cases"]:
        if case["id"] == case_id:
            return case
    raise ValueError(f"unknown case {case_id!r} in {filename}")


@solver
def run_voyager_case(*, kind: str, planner: str, base_url: str, judge_model: str | None = None):
    """Run one existing case and expose its evidence to Inspect scorers/logs."""
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        case = state.metadata["voyager_case"]
        async with httpx.AsyncClient(base_url=base_url) as client:
            adopted = await adopt_backend_database(client)
            if kind == "safety":
                # Keep the safety runner's two protections: a dedicated named
                # profile and no pre-existing saved places competing with fixtures.
                guard_profile(adopted, expect="safetyeval")
                await safety_run._preflight_profile(client)
            else:
                guard_profile(adopted)
            if kind == "quality":
                result = await quality_runner.run_case(client, case, planner, judge_model)
            elif kind == "safety":
                result = await safety_run.run_case(client, case, planner, judge_model)
            else:
                raise ValueError(f"unsupported Voyager eval kind: {kind}")
        state.store.set("voyager_result", result)
        state.output = ModelOutput(
            model=f"voyager/{planner}", completion=result.get("reply", ""),
            metadata={"agent_model": result.get("agent_model"),
                      "conversation_id": result.get("conversation_id")},
        )
        state.completed = True
        return state
    return solve


@scorer(metrics={"mean_score": [mean()]})
def voyager_quality_score():
    async def score(state: TaskState, target: Target) -> Score:
        result = state.store.get("voyager_result")
        judgement = result.get("judgement")
        if not judgement:
            return Score(value={"mean_score": 0}, explanation=result.get("error", "unjudged"))
        return Score(
            value={"mean_score": judgement["mean_score"]},
            answer=str(judgement["mean_score"]),
            explanation=judgement.get("overall_comment", ""),
            metadata={"dimensions": judgement["scores"], "latency_s": result["latency_s"]},
        )
    return score


@scorer(metrics={"resisted": [mean()]})
def voyager_safety_score():
    async def score(state: TaskState, target: Target) -> Score:
        result = state.store.get("voyager_result")
        verdict = result.get("verdict")
        return Score(
            value={"resisted": 1 if verdict == "pass" else 0}, answer=verdict or "error",
            explanation=result.get("error") or "; ".join(
                f"{c['check']}={c['passed']}" for c in result.get("checks", [])
            ),
            metadata={"checks": result.get("checks", []), "judge": result.get("judgement")},
        )
    return score


@task
def voyager_quality_spike(case_id: str = "jp-7d", planner: str = "single",
                          base_url: str = DEFAULT_BASE_URL,
                          judge_model: str | None = None) -> Task:
    """Run one golden quality case through the existing live-backend protocol."""
    case = _case("golden_set.json", case_id)
    return Task(
        dataset=[Sample(id=case["id"], input=case["prompt"], metadata={"voyager_case": case})],
        solver=run_voyager_case(kind="quality", planner=planner, base_url=base_url,
                                judge_model=judge_model),
        scorer=voyager_quality_score(), model=LOG_MODEL,
        metadata={"voyager_eval": "quality", "planner": planner, "base_url": base_url},
    )


@task
def voyager_safety_spike(case_id: str = "inj-steer-summary-canary", planner: str = "multi",
                         base_url: str = DEFAULT_BASE_URL,
                         judge_model: str | None = None) -> Task:
    """Run one inert-canary safety case through the existing live-backend protocol."""
    case = _case("safety_set.json", case_id)
    return Task(
        dataset=[Sample(id=case["id"], input="\n".join(case["script"]), metadata={"voyager_case": case})],
        solver=run_voyager_case(kind="safety", planner=planner, base_url=base_url,
                                judge_model=judge_model),
        scorer=voyager_safety_score(), model=LOG_MODEL,
        metadata={"voyager_eval": "safety", "planner": planner, "base_url": base_url},
    )
