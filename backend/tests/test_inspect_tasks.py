"""Phase-1 Inspect task wiring; no live backend or model calls."""
import pytest
from inspect_ai.model import ModelOutput
from inspect_ai.solver import TaskState

from evals.inspect_tasks import (voyager_quality, voyager_quality_score,
                                 voyager_quality_spike, voyager_safety,
                                 voyager_safety_score, voyager_safety_spike)


def test_quality_spike_uses_one_golden_case():
    task = voyager_quality_spike()
    assert len(task.dataset) == 1
    assert task.dataset[0].id == "jp-7d:single"
    assert task.metadata["planner"] == "single"


def test_safety_spike_uses_one_inert_canary_case():
    task = voyager_safety_spike()
    assert len(task.dataset) == 1
    assert task.dataset[0].id == "inj-steer-summary-canary:multi"
    assert task.metadata["planner"] == "multi"


def test_quality_task_includes_every_case_for_both_planners():
    task = voyager_quality()
    assert len(task.dataset) == 30
    assert {sample.metadata["planner"] for sample in task.dataset} == {"single", "multi"}
    assert task.dataset[0].id.endswith(":single")


def test_safety_task_uses_epochs_and_honours_case_planner_restrictions():
    task = voyager_safety(planner="both", runs=2)
    assert task.epochs == 2
    assert all(sample.metadata["planner"] in {"single", "multi"} for sample in task.dataset)
    assert not any(sample.id.startswith("inj-unsafe-tool-call:multi") for sample in task.dataset)


def _state(result):
    return TaskState(model="mockllm/model", sample_id="case", epoch=1,
                     input="prompt", messages=[], output=ModelOutput(completion=""),
                     store={"voyager_result": result})


@pytest.mark.asyncio
async def test_quality_scorer_exposes_existing_judgement():
    score = await voyager_quality_score()(_state({
        "latency_s": 1.2,
        "judgement": {"mean_score": 4.2, "overall_comment": "good", "scores": {}},
    }), None)
    assert score.value == {"mean_score": 4.2}


@pytest.mark.asyncio
async def test_safety_scorer_marks_only_pass_as_resisted():
    score = await voyager_safety_score()(_state({"verdict": "fail", "checks": []}), None)
    assert score.value == {"resisted": 0}
