import json

from airbus_challenge import summary
from airbus_challenge.evaluate import (
    CLIMATOLOGY,
    CONDITIONAL_RATE,
    LOGISTIC,
    SEVERE,
    TARGET,
)

CANDIDATE = "lgbm_v1"


def record(model, metric, value, target=TARGET, slice_="common_support", **extra):
    return {
        "split": "validation",
        "cohort": "c1",
        "task": "throughput" if target == TARGET else "severe_delay",
        "target": target,
        "model": model,
        "airport": "KATL",
        "horizon": "all",
        "slice": slice_,
        "metric": metric,
        "value": value,
        "unit": "arrivals/h",
        "ci_low": None,
        "ci_high": None,
        "ci_reason": None,
        "reason": None,
        "n_eligible": 100,
        "n_predicted": 90,
        "n_excluded": 10,
        "n_degraded": 2,
        "exclusions": {"coverage_incomplete": 10},
        "prevalence": None,
        **extra,
    }


def report(metrics, data_mode="real", scope=None):
    return {
        "run_id": "evaluate_dev",
        "scope": "dev",
        "data_mode": data_mode,
        "commit": "abc123",
        "commit_dirty": False,
        "generated_at_utc": "2026-10-31T00:00:00Z",
        "label_versions": ["v1"],
        "split_bounds": {
            "validation": ["2024-01-01T00:00:00Z", "2024-07-01T00:00:00Z"]
        },
        "availability_basis": {},
        "scoring_scope": scope or [],
        "metrics": metrics,
    }


def skill(value, low, high):
    return record(
        CANDIDATE,
        f"skill_vs_{CLIMATOLOGY}",
        value,
        slice_="baseline_support",
        ci_low=low,
        ci_high=high,
    )


def test_null_renders_as_na_with_reason():
    metrics = [
        record(CANDIDATE, "rmse", 4.2),
        record(CLIMATOLOGY, "rmse", None, reason="no_predicted_rows"),
        record(
            CONDITIONAL_RATE,
            "average_precision",
            None,
            target=SEVERE,
            reason="single_class",
        ),
        record(LOGISTIC, "brier", 0.1, target=SEVERE),
    ]
    text = summary.render(report(metrics))
    assert "n/a (no_predicted_rows)" in text
    assert "n/a (single_class)" in text
    assert "| 0.000" not in text
    assert (
        summary.fmt({"value": None, "reason": "too_few_days"}) == "n/a (too_few_days)"
    )


def test_better_only_when_ci_excludes_baseline():
    assert (
        summary.verdict(skill(0.1, 0.02, 0.2), CLIMATOLOGY) == "better than climatology"
    )
    assert summary.verdict(skill(0.1, -0.01, 0.2), CLIMATOLOGY) == (
        "not distinguishable from climatology"
    )
    assert summary.verdict(skill(0.1, None, None), CLIMATOLOGY).startswith(
        "not distinguishable from climatology"
    )
    assert summary.verdict(None, CLIMATOLOGY).startswith("not distinguishable")
    text = summary.render(
        report([record(CANDIDATE, "rmse", 4.0), skill(0.1, -0.05, 0.3)])
    )
    assert "not distinguishable from climatology" in text
    assert "better than" not in text


def test_fixture_writes_under_fixture(tmp_path):
    metrics = tmp_path / "metrics_dev.json"
    metrics.write_text(json.dumps(report([record(CANDIDATE, "rmse", 4.0)], "fixture")))
    path = summary.main(metrics, tmp_path / "reports")
    assert path == tmp_path / "reports" / "fixture" / "RESULTS_dev.md"
    assert "Fixture data" in path.read_text()


def test_scope_table_lists_dropped_rows():
    scope = [
        {
            "split": "validation",
            "task": "throughput",
            "cohort": "c1",
            "target": TARGET,
            "fit_cutoff_utc": "2024-03-01T00:00:00Z",
            "set_by": ["lgbm_run"],
            "rows_dropped": {CANDIDATE: 1416, CLIMATOLOGY: 1416},
            "rows_scored": 2000,
            "models": [CANDIDATE, CLIMATOLOGY],
            "reason": None,
        },
        {
            "split": "calibration",
            "task": "throughput",
            "cohort": "c1",
            "target": TARGET,
            "fit_cutoff_utc": "2025-01-01T00:00:00Z",
            "set_by": ["late_run"],
            "rows_dropped": {CANDIDATE: 0},
            "rows_scored": 0,
            "models": [CANDIDATE],
            "reason": "no_rows_after_fit_cutoff",
        },
    ]
    text = summary.render(report([record(CANDIDATE, "rmse", 4.0)], scope=scope))
    line = next(x for x in text.splitlines() if "2024-03-01" in x)
    assert "1416" in line and "lgbm_run" in line and "2000" in line
    assert "n/a (no_rows_after_fit_cutoff)" in text
