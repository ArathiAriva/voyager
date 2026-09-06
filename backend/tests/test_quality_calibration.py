"""Quality judge calibration scaffolding (OPEN-ITEMS S-13).

The judge defaults to the model being evaluated, so every historical mean_score
carries self-preference bias. These cover the measurement machinery, not the
judge itself -- what a judge scores needs hand labels, which is the part only a
human can supply.
"""

import json
from pathlib import Path

import pytest

from evals.quality_judge_calibrate import _spearman


# ── Rank correlation ────────────────────────────────────────────────────────

def test_perfect_agreement_and_inversion():
    assert _spearman([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)
    assert _spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)


def test_a_systematically_harsh_judge_still_ranks_perfectly():
    """The reason rank correlation is the headline metric: a judge that scores
    every plan one point lower than the labeller orders them identically, and
    ordering is what a planner A/B actually needs."""
    assert _spearman([1, 2, 3, 4, 5], [2, 3, 4, 5, 6]) == pytest.approx(1.0)


def test_no_variance_is_undefined_rather_than_zero():
    """A judge giving everything the same score has no ranking to correlate.
    Reporting 0.0 would read as "uncorrelated" when the truth is "unmeasurable"."""
    assert _spearman([3, 3, 3, 3, 3], [1, 2, 3, 4, 5]) is None


def test_too_few_points_to_correlate():
    assert _spearman([3], [4]) is None
    assert _spearman([], []) is None


def test_ties_use_averaged_ranks():
    """1-5 scores tie constantly, so tie handling is not an edge case here."""
    assert _spearman([1, 2, 2, 3], [1, 2, 2, 3]) == pytest.approx(1.0)


# ── Label template ──────────────────────────────────────────────────────────

def test_template_leaves_scores_blank(tmp_path, monkeypatch):
    """Deliberately not prefilled with the judge's own scores: seeing a number
    before deciding anchors the labeller to it, and a label anchored to the judge
    cannot measure that judge."""
    import evals.quality_labels_template as template

    rows = [{
        "batch": "b", "case_id": "c1", "planner": "multi",
        "prompt": "Plan 3 days in Lisbon", "reply": "Here is a plan...",
        "itinerary": [{"day": 1, "plan": "x"}],
    }]
    monkeypatch.setattr(template, "load_runs", lambda run, use_all: rows)
    out = tmp_path / "labels.json"
    monkeypatch.setattr("sys.argv", ["prog", "-o", str(out)])

    template.main()

    payload = json.loads(out.read_text())
    entry = payload["labels"]["0"]
    assert all(v is None for v in entry["scores"].values())
    assert entry["prompt"] and entry["reply"], "the labeller needs the content inline"


def test_template_refuses_to_overwrite_existing_labels(tmp_path, monkeypatch):
    """Hand labels are expensive and unrecoverable -- clobbering them silently
    would be the worst failure this script could have."""
    import evals.quality_labels_template as template

    monkeypatch.setattr(template, "load_runs", lambda run, use_all: [
        {"batch": "b", "case_id": "c", "planner": "multi", "prompt": "p",
         "reply": "r", "itinerary": None}])
    out = tmp_path / "labels.json"
    out.write_text('{"labels": {"0": {"scores": {"geographic_coherence": 5}}}}')
    monkeypatch.setattr("sys.argv", ["prog", "-o", str(out)])

    with pytest.raises(SystemExit) as exc:
        template.main()
    assert "already exists" in str(exc.value)
    assert "geographic_coherence" in out.read_text(), "existing labels untouched"
