from types import SimpleNamespace

import pytest

from airbus_challenge import experiment_csv


def test_paired_uses_frozen_booster_categories_in_original_column_order():
    model = SimpleNamespace(pandas_categorical=[["KATL", "KDFW"], ["calm", "variable"]])
    levels = experiment_csv.source_levels(
        model, ["horizon_h", "airport_icao", "metar_wind_status"]
    )
    assert levels == {"airport_icao": ["KATL", "KDFW"],
                      "metar_wind_status": ["calm", "variable"]}


def test_paired_refuses_absent_booster_instead_of_refitting(tmp_path):
    with pytest.raises(FileNotFoundError, match="frozen all-BTS delay booster"):
        experiment_csv.paired(tmp_path)


def test_paired_refuses_unknown_features_and_mismatched_categories():
    model = SimpleNamespace(pandas_categorical=[])
    with pytest.raises(ValueError, match="unregistered predictors"):
        experiment_csv.source_levels(model, ["y_true"])
    with pytest.raises(ValueError, match="categorical vocabulary"):
        experiment_csv.source_levels(model, ["airport_icao"])


def test_paired_scores_csv_requests_from_saved_model_without_fitting(tmp_path, monkeypatch):
    import json

    import numpy as np
    import pandas as pd

    from airbus_challenge import baselines

    artifacts = tmp_path / "artifacts"
    source = artifacts / "lgbm_dev"
    source.mkdir(parents=True)
    (source / experiment_csv.MODEL_FILE).write_text("frozen-source-booster")
    (source / "manifest.json").write_text(json.dumps({
        "data_mode": "fixture", "train_airports": ["KATL", "KDFW"],
        "fit_cutoff_utc": "2024-01-01T00:00:00+00:00",
        "prediction_requests_sha256": "all-bts-request-hash", "data_snapshot_id": "all-bts",
    }))
    processed = tmp_path / "processed"
    processed.mkdir()
    for table in ["prediction_requests.parquet", "labels.parquet",
                  "feature_snapshots.parquet", "demand_features.parquet"]:
        (processed / table).write_text(table)
    (processed / "feature_snapshots.manifest.json").write_text(
        json.dumps({"data_snapshot_id": "csv-snapshot"})
    )
    rows = []
    for ident, date in [("val", "2024-03-01"), ("cal", "2024-09-01")]:
        t = pd.Timestamp(date, tz="UTC")
        rows.append({
            "prediction_id": ident, "task": "severe_delay", "airport_icao": "KATL",
            "flight_id": ident, "as_of_utc": t - pd.Timedelta(hours=3),
            "target_start_utc": t, "target_end_utc": t, "horizon_h": 3,
            "schedule_snapshot_id": "schedule", "cohort_version": "csv_only_v1",
            "data_mode": "fixture",
        })
    req = pd.DataFrame(rows)
    monkeypatch.setattr(experiment_csv.experiments, "paths", lambda _: (
        processed, processed / "labels.parquet", None
    ))
    monkeypatch.setattr(experiment_csv.experiments, "requests", lambda *_: req)
    def read_inputs(*args):
        lo, hi = experiment_csv.train.bounds(args[2])
        return req[req.target_start_utc.ge(lo) & req.target_start_utc.lt(hi)].assign(
            status="ok", demand_status="ok", reason_codes=lambda x: [[] for _ in x.index],
            demand_reason_codes=lambda x: [[] for _ in x.index],
        )
    monkeypatch.setattr(experiment_csv.experiments, "read_inputs", read_inputs)
    booster = SimpleNamespace(
        pandas_categorical=[["KATL", "KDFW"]], feature_name=lambda: ["airport_icao", "horizon_h"],
        predict=lambda frame: np.full(len(frame), 0.25),
    )
    monkeypatch.setattr(experiment_csv.lgb, "Booster", lambda **_: booster)
    def forbid_fit(*args, **kwargs):
        raise AssertionError("paired comparison must not fit a model")
    monkeypatch.setattr(experiment_csv.lgb, "train", forbid_fit)
    output = experiment_csv.paired(artifacts)
    predicted = pd.read_parquet(output / "predictions.parquet")
    baselines.check_predictions(predicted)
    assert predicted.prediction_id.tolist() == ["val", "cal"]
    assert predicted.estimate.eq(0.25).all()
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["model_refitted"] is False
    assert manifest["source_prediction_requests_sha256"] == "all-bts-request-hash"
    assert manifest["prediction_requests_sha256"] != "all-bts-request-hash"
