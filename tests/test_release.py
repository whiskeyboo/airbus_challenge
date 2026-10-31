import json

import numpy as np
import pandas as pd
import pytest

from airbus_challenge import evaluate
from airbus_challenge import release as r


def test_matrix_keeps_sample_and_holdout_memberships_separate():
    matrix = r.matrix()
    assert set(matrix) == {"primary", "csv_only", "leave_out_KATL", "leave_out_KDFW"}
    assert matrix["csv_only"]["targets"] == [r.fb.SEVERE]
    for name, slot in matrix.items():
        if name.startswith("leave_out_"):
            assert slot["held_out"] not in slot["train_airports"]
            assert slot["scoring_airports"] == [slot["held_out"]]
            assert slot["targets"] == [r.train.TARGET]


def test_calibration_only_reads_requested_released_development_labels(tmp_path):
    labels = pd.DataFrame({
        "prediction_id": ["known", "late", "future"], "target_kind": r.fb.SEVERE,
        "y_true": [0., 1., 1.], "eligible": True, "label_version": "0.4.0",
        "outcome_available_at_utc": pd.to_datetime([
            "2024-10-01", "2025-01-01 00:01", "2025-04-01"], utc=True, format="mixed")})
    path = tmp_path / "labels.parquet"
    labels.to_parquet(path)
    first = r.development_labels(path, ["known", "late"])
    labels.loc[labels.prediction_id.eq("future"), "y_true"] = 999.
    labels.to_parquet(path)
    pd.testing.assert_frame_equal(first, r.development_labels(path, ["known", "late"]))
    assert first.prediction_id.tolist() == ["known"]


def test_test_requests_require_issue_at_or_after_final_calibration_freeze(tmp_path):
    path = tmp_path / "req.parquet"
    times = pd.to_datetime(["2025-01-01 03:00", "2025-01-01 06:00", "2025-08-01"], utc=True, format="mixed")
    frame = pd.DataFrame({c: [None] * 3 for c in r.b.REQUEST_COLUMNS})
    frame = frame.assign(prediction_id=["early", "valid", "after"], task="throughput",
        airport_icao="KATL", cohort_version=r.ex.PRIMARY, target_start_utc=times,
        as_of_utc=times-pd.Timedelta(hours=6))
    frame.to_parquet(path)
    out = r.request_rows({"requests": str(path), "cohort": r.ex.PRIMARY,
                          "scoring_airports": ["KATL"]}, "throughput", "test")
    assert out.prediction_id.tolist() == ["valid"]


def test_unvalidated_degraded_rows_are_unavailable_never_zero():
    frame = pd.DataFrame({"status": ["available", "degraded"], "estimate": [0., 4.],
                          "p10": [0., 1.], "p90": [3., 7.], "reason_codes": [[], ["taf_unavailable"]]})
    out = r.clean_status(frame)
    assert out.status.tolist() == ["available", "unavailable"]
    assert out.estimate.iloc[0] == 0 and out.iloc[1][["estimate", "p10", "p90"]].isna().all()
    assert "unvalidated_degraded_input" in out.reason_codes.iloc[1]


def test_frozen_calibration_applies_once_and_uses_distinct_output_identity():
    frame = pd.DataFrame({"status": ["available"], "estimate": [.5], "p10": [np.nan],
        "p90": [np.nan], "reason_codes": [[]], "target_kind": r.fb.SEVERE,
        "model_version": "model", "airport_icao": "KATL"})
    policy = {"calibrators": {r.fb.SEVERE: {"model": {"x": [0., 1.], "y": [0., .5]}}}}
    first = r.apply_policy(frame, policy)
    assert first.estimate.iloc[0] == .25
    assert first.model_version.iloc[0] == "model_calibrated"
    pd.testing.assert_frame_equal(first, r.apply_policy(first, policy))


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "FREEZE", tmp_path / "release.json")
    monkeypatch.setattr(r.b, "LEDGER", tmp_path / "ledger")
    monkeypatch.setattr(r.b, "LEDGER_MIRROR", tmp_path / "mirror")
    monkeypatch.setattr(r.b, "git", lambda *args: "commit")
    monkeypatch.setattr(r.b, "source_dirty", lambda: False)
    source = tmp_path / "model.txt"
    source.write_text("frozen model")
    doc = {"approved_by": "lead", "commit": "commit", "commit_dirty": False,
           "fit_cutoff_utc": r.CUTOFF.isoformat(), "experiments": {},
           "files_sha256": {str(source): r.sha256(source)}}
    r.FREEZE.write_text(json.dumps(doc))
    return doc, source


def test_frozen_source_and_model_tampering_are_refused(frozen, monkeypatch):
    doc, model = frozen
    assert r.verify_frozen() == doc
    monkeypatch.setattr(r.b, "source_dirty", lambda: True)
    with pytest.raises(ValueError, match="clean frozen commit"):
        r.verify_frozen()
    monkeypatch.setattr(r.b, "source_dirty", lambda: False)
    model.write_text("different model")
    with pytest.raises(ValueError, match="frozen input changed"):
        r.verify_frozen()


def test_claim_survives_failures_and_cannot_be_restarted_or_relabelled(frozen):
    doc, _ = frozen
    r.claim_batch(doc)
    assert r.verify_frozen(require_claim=True) == doc
    with pytest.raises(FileExistsError, match="already claimed"):
        r.claim_batch(doc)
    doc["experiments"]["renamed"] = {}
    r.FREEZE.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="changed after the locked claim"):
        r.verify_frozen(require_claim=True)


def test_generation_refuses_test_outcome_reads_without_claim(frozen, monkeypatch):
    doc, _ = frozen
    doc["experiments"]["primary"] = {"run_id": "new"}
    monkeypatch.setattr(r.b, "ARTIFACTS", r.FREEZE.parent / "artifacts")
    with pytest.raises(ValueError, match="before reading test outcomes"):
        r.generate(doc, "primary")


def test_batch_is_claimed_before_any_generation_even_if_generation_fails(frozen, monkeypatch):
    doc, _ = frozen
    doc["experiments"]["primary"] = {}
    r.FREEZE.write_text(json.dumps(doc))
    def fail(*args):
        assert (r.b.LEDGER / f"{r.BINDING}.json").exists()
        raise RuntimeError("infrastructure failed")
    monkeypatch.setattr(r, "generate", fail)
    with pytest.raises(RuntimeError, match="infrastructure failed"):
        r.assess()
    assert (r.b.LEDGER / f"{r.BINDING}.json").exists()


def test_frozen_release_only_accepts_bound_runs_before_opening_predictions(frozen, monkeypatch):
    doc, _ = frozen
    doc["experiments"]["primary"] = {"run_id": "frozen", "requests": "bound_requests", "labels": "bound_labels"}
    r.FREEZE.write_text(json.dumps(doc))
    r.claim_batch(doc)
    with pytest.raises(ValueError, match="runs differ"):
        evaluate.main(["another_run"], locked_test=True, release=True)
    with pytest.raises(ValueError, match="only used for the locked"):
        evaluate.main(["frozen"], release=True)
