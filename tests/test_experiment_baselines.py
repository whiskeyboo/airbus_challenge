import json

import numpy as np
import pandas as pd
import pytest

from airbus_challenge import baselines
from airbus_challenge import experiment_baselines as experiments
from airbus_challenge.download import sha256


def request(ident, airport, when, cohort="loao_KATL_v1"):
    target = pd.Timestamp(when, tz="UTC")
    return {
        "prediction_id": ident, "task": "severe_delay", "airport_icao": airport,
        "flight_id": ident, "as_of_utc": target - pd.Timedelta(hours=3),
        "target_start_utc": target, "target_end_utc": target,
        "horizon_h": 3, "schedule_snapshot_id": "schedule", "cohort_version": cohort,
        "data_mode": "fixture",
    }


def training():
    return pd.DataFrame([
        request(f"train-{airport}-{i}", airport, f"2023-06-{i+1:02} 15:00")
        | {"target_kind": target, "y_true": float(i % 2), "eligible": True,
           "outcome_available_at_utc": pd.Timestamp("2023-07-01", tz="UTC")}
        for airport in ["KATL", "KDFW"] for i in range(6)
        for target in ["departure_delay_gt45", "cancellation"]
    ])


def test_heldout_labels_cannot_change_source_fitted_binary_predictions():
    scored = pd.DataFrame([
        request("val", "KATL", "2024-03-01 15:00"),
        request("cal", "KATL", "2024-09-01 15:00"),
    ])
    labels = training()
    before = list(experiments.flight_predictions(scored, labels, ["KDFW"]))
    labels.loc[labels.airport_icao.eq("KATL"), "y_true"] = 1000
    after = list(experiments.flight_predictions(scored, labels, ["KDFW"]))
    assert len(before) == 4
    for left, right in zip(before, after):
        pd.testing.assert_frame_equal(left, right)
        assert set(left.prediction_id) == {"val", "cal"}
        assert left.status.eq("available").all()
        assert left.estimate.between(0, 1).all()


def test_training_uses_source_eligible_released_2023_rows_only():
    labels = training()
    extra = labels.iloc[[0]].copy()
    extra["airport_icao"] = "KDFW"
    extra["flight_id"] = "late"
    extra["outcome_available_at_utc"] = pd.Timestamp("2024-01-01 00:01", tz="UTC")
    labels = pd.concat([labels, extra], ignore_index=True)
    labels.loc[labels.flight_id.eq("train-KDFW-0"), "eligible"] = False
    labels.loc[labels.flight_id.eq("train-KDFW-1"), "target_start_utc"] = pd.Timestamp(
        "2025-03-01", tz="UTC"
    )
    rows = experiments.training_rows(labels, "cancellation", ["KDFW"])
    assert len(rows) == 4
    assert set(rows.airport_icao) == {"KDFW"}


def test_one_class_source_logistic_is_explicitly_unavailable():
    labels = training().assign(y_true=0.0)
    scored = pd.DataFrame([request("val", "KATL", "2024-03-01 15:00")])
    frames = list(experiments.flight_predictions(scored, labels, ["KDFW"]))
    for frame in frames:
        if frame.model_version.iloc[0] == "baseline_logistic_v1":
            assert frame.status.eq("unavailable").all()
            assert frame.estimate.isna().all()
            assert "source_training_has_one_class" in frame.reason_codes.iloc[0]
        else:
            assert np.array_equal(frame.estimate, [0])


def test_csv_run_has_exact_dev_membership_and_real_request_hash(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    cohort = "csv_only_v1"
    req = pd.DataFrame([
        request("before", "KATL", "2024-01-01 01:00", cohort),
        request("val", "KATL", "2024-03-01 15:00", cohort),
        request("cal", "KDFW", "2024-09-01 15:00", cohort),
        request("test", "KATL", "2025-03-01 15:00", cohort),
    ])
    path = processed / "prediction_requests.parquet"
    req.to_parquet(path)
    interface = {
        "tasks": ["severe_delay"],
        "train_airports": ["KATL", "KDFW"],
        "score_airports": ["KATL", "KDFW"],
    }
    path.with_suffix(".manifest.json").write_text(json.dumps({
        "cohorts": {cohort: interface}, "parquet_sha256": sha256(path),
        "source_flights_sha256": "fixture-source",
    }))
    train_path = tmp_path / "training_labels.parquet"
    train_rows = training().assign(cohort_version=cohort)
    train_rows.to_parquet(train_path)
    train_path.with_suffix(".manifest.json").write_text(json.dumps({
        "cohort_version": cohort, "cohort": interface,
        "parquet_sha256": sha256(train_path),
    }))
    labels_path = tmp_path / "labels.parquet"
    pd.DataFrame({"irrelevant": [1]}).to_parquet(labels_path)
    artifacts = tmp_path / "artifacts"
    with pytest.raises(ValueError, match="tasks must be"):
        experiments.run(cohort, processed, labels_path, train_path, artifacts, tasks=["throughput"])
    run_id = experiments.run(
        cohort, processed, labels_path, train_path, artifacts, tasks=["severe_delay"]
    )
    predictions = pd.read_parquet(artifacts / run_id / "predictions.parquet")
    assert len(predictions) == 8
    assert set(predictions.prediction_id) == {"val", "cal"}
    baselines.check_predictions(predictions)
    manifest = json.loads((artifacts / run_id / "manifest.json").read_text())
    assert manifest["prediction_requests_sha256"] == sha256(path)
    assert manifest["experiment"] == "csv_only"
    assert manifest["data_mode"] == "fixture"
    assert manifest["tasks"] == ["severe_delay"]
    assert manifest["runtime_s"] > 0 and manifest["peak_rss_mb"] > 0


def test_source_hourly_fit_excludes_heldout_and_unreleased_training_hours():
    times = pd.to_datetime(["2023-01-01", "2023-01-02"], utc=True)
    hourly = pd.DataFrame({
        "airport_icao": ["KDFW", "KDFW", "KATL"],
        "hour_start_utc": [times[0], times[1], times[0]],
        "scheduled_arrivals": [10., 20., 1000.],
        baselines.TARGET: [8., 17., 1000.],
    })
    exported = pd.DataFrame({
        "airport_icao": ["KDFW", "KDFW", "KATL"],
        "target_start_utc": [times[0], times[1], times[0]],
        "target_kind": baselines.TARGET, "eligible": True,
        "outcome_available_at_utc": pd.to_datetime([
            "2023-02-01", "2024-01-02", "2023-02-01"
        ], utc=True),
    })
    rows = experiments.source_hours(hourly, exported, ["KDFW"])
    assert len(rows) == 1 and rows[baselines.TARGET].iloc[0] == 8
