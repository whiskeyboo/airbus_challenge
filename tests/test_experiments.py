from itertools import pairwise

import numpy as np
import pandas as pd
import pytest
from conftest import make_requests

from airbus_challenge import experiments as exp


def utc(values):
    return pd.to_datetime(values, utc=True)


@pytest.mark.parametrize("task", ["throughput", "severe_delay"])
def test_ablation_stages_nest_and_add_directional_wind_together(task):
    stages = [set(exp.feature_names(v, task)) for v in exp.VARIANTS]
    assert all(a < b for a, b in pairwise(stages))
    assert not any(c.startswith(("metar_", "taf_")) for c in stages[0])
    assert any(c.startswith("metar_") for c in stages[1])
    assert not any(c.startswith("taf_") for c in stages[1])
    assert any(c.startswith("taf_") for c in stages[2])
    for names in stages[:3]:
        assert not any("wind" in c or "gust" in c for c in names)
    assert any("crosswind" in c for c in stages[3])
    assert stages[4] - stages[3] == set(exp.OPS_INPUTS)
    assert all(len(exp.feature_names(v, task)) == len(set(exp.feature_names(v, task)))
               for v in exp.VARIANTS)


def test_unknown_variants_and_cohorts_are_refused():
    with pytest.raises(ValueError, match="unknown variant"):
        exp.feature_names("all_outcomes", "throughput")
    with pytest.raises(ValueError, match="unknown cohort"):
        exp.paths("loao_UNKNOWN_v1")


@pytest.mark.parametrize("held_out", ["KATL", "KDFW"])
def test_holdout_fitting_and_scoring_airports_are_disjoint(held_out):
    fit, score = exp.memberships(f"loao_{held_out}_v1")
    assert score == [held_out]
    assert held_out not in fit
    assert set(fit) | set(score) == set(exp.baselines.AIRPORTS)


def test_source_categories_are_frozen_and_heldout_or_new_values_become_missing():
    source = pd.DataFrame({"airport_icao": ["KDFW", "KDFW"],
                           "metar_wind_status": ["known", "calm"],
                           "horizon_h": [3, 6]})
    levels = exp.categorical_levels(source)
    heldout = pd.DataFrame({"airport_icao": ["KATL", "KDFW"],
                            "metar_wind_status": ["new_status", "known"],
                            "horizon_h": [3, 6]})
    encoded = exp.encode(heldout, levels)
    assert list(encoded.airport_icao.cat.categories) == ["KDFW"]
    assert encoded.airport_icao.isna().tolist() == [True, False]
    assert encoded.metar_wind_status.isna().tolist() == [True, False]
    assert levels == {"airport_icao": ["KDFW"],
                      "metar_wind_status": ["calm", "known"]}
    assert encoded.horizon_h.dtype == np.dtype("float32")
    assert heldout.airport_icao.tolist() == ["KATL", "KDFW"]


def training_export(tmp_path):
    labels = pd.DataFrame({
        "prediction_id": ["jan", "nov", "source_other"],
        "target_kind": exp.train.TARGET,
        "airport_icao": ["KDFW", "KDFW", "KATL"],
        "target_start_utc": utc(["2023-01-01", "2023-11-01", "2023-02-01"]),
        "outcome_available_at_utc": utc(["2023-01-02", "2023-11-02", "2023-02-02"]),
        "eligible": True, "y_true": [10.0, 20.0, 99.0],
    })
    path = tmp_path / "labels.parquet"
    labels.to_parquet(path, index=False)
    return path, labels


def test_training_export_enforces_source_airport_and_requested_target(tmp_path, monkeypatch):
    path, labels = training_export(tmp_path)
    read = []
    def inputs(processed, task, split, variant, airports):
        read.append((task, split, variant, airports))
        return labels[["prediction_id", "target_start_utc"]]
    monkeypatch.setattr(exp, "read_inputs", inputs)
    got = exp.training_rows(tmp_path, path, "throughput", exp.train.TARGET,
                            "schedule", ["KDFW"], 0)
    assert got.prediction_id.tolist() == ["jan", "nov"]
    assert read == [("throughput", "train", "schedule", ["KDFW"])]


@pytest.mark.parametrize("column,value", [
    ("eligible", False),
    ("y_true", np.nan),
    ("outcome_available_at_utc", pd.Timestamp("2024-01-01 00:00:01", tz="UTC")),
    ("outcome_available_at_utc", pd.NaT),
    ("target_start_utc", pd.Timestamp("2025-01-01", tz="UTC")),
])
def test_unavailable_ineligible_or_post_train_labels_fail_before_inputs(
    tmp_path, monkeypatch, column, value
):
    path, labels = training_export(tmp_path)
    labels.loc[0, column] = value
    labels.to_parquet(path, index=False)
    def never(*args, **kwargs):
        raise AssertionError("features read before label eligibility checked")
    monkeypatch.setattr(exp, "read_inputs", never)
    with pytest.raises(ValueError, match="ineligible or unavailable"):
        exp.training_rows(tmp_path, path, "throughput", exp.train.TARGET,
                          "schedule", ["KDFW"], 0)


def test_training_sample_membership_is_identical_between_feature_variants(tmp_path, monkeypatch):
    path, labels = training_export(tmp_path)
    monkeypatch.setattr(exp, "read_inputs", lambda *args: labels[["prediction_id", "target_start_utc"]])
    outputs = [exp.training_rows(tmp_path, path, "throughput", exp.train.TARGET,
                                variant, ["KDFW"], 1).prediction_id.tolist()
               for variant in ("schedule", "runway")]
    assert outputs[0] == outputs[1] and len(outputs[0]) == 1


def test_model_selection_fits_source_training_and_early_stops_on_source_validation(monkeypatch):
    rows = pd.DataFrame({"airport_icao": ["KDFW", "KDFW"],
                         "metar_wind_status": ["known", "calm"],
                         "target_start_utc": utc(["2023-01-01", "2023-12-01"]),
                         "y_true": [1.0, 2.0]})
    validation = pd.DataFrame({"airport_icao": ["KDFW", "KDFW"],
                               "metar_wind_status": ["new_2024", "known"],
                               "target_start_utc": utc(["2024-01-01", "2024-06-01"]),
                               "y_true": [3.0, 4.0]})
    calls = []
    class Booster:
        best_iteration = 7
    def fake_train(params, data, **kwargs):
        calls.append((params, data, kwargs))
        return Booster()
    monkeypatch.setattr(exp.lgb, "train", fake_train)
    models, levels, counts = exp.fit_model(
        rows, ["airport_icao", "metar_wind_status"], True, 25, validation)
    assert len(models) == len(calls) == 1
    _, fit, kwargs = calls[0]
    assert list(fit.get_label()) == [1.0, 2.0]
    assert list(kwargs["valid_sets"][0].get_label()) == [3.0, 4.0]
    assert levels["metar_wind_status"] == ["calm", "known"]
    assert counts == {"selected_rounds": [7], "fit_rows": 2,
                      "selection_rows": 2, "refit_rows": 0}


def test_requests_exclude_2025_pre_cutoff_and_other_airports(tmp_path):
    req = pd.concat([
        make_requests("KATL", utc(["2023-12-31 15:00", "2024-01-01 02:00",
                                   "2024-03-01 15:00", "2024-09-01 15:00",
                                   "2025-01-01 15:00"]), [3]),
        make_requests("KDFW", utc(["2024-03-01 15:00"]), [3]),
    ], ignore_index=True)
    req.to_parquet(tmp_path / "prediction_requests.parquet", index=False)
    got = exp.requests(tmp_path, "throughput", ["KATL"])
    assert got.target_start_utc.tolist() == list(utc(["2024-03-01 15:00", "2024-09-01 15:00"]))
    assert got.airport_icao.eq("KATL").all()


class FixedModel:
    def __init__(self, value):
        self.value = value
    def predict(self, frame):
        return np.full(len(frame), self.value)


def test_predict_keeps_all_requests_and_abstains_for_missing_inputs():
    req = make_requests("KATL", utc(["2024-03-01 15:00", "2024-03-02 15:00"]), [3])
    frame = pd.DataFrame({"prediction_id": [req.prediction_id.iloc[0]],
                          "airport_icao": ["KATL"], "horizon_h": [3],
                          "demand_status": ["ok"], "status": ["ok"],
                          "demand_reason_codes": [[]], "reason_codes": [[]]})
    got = exp.predict(req, frame, ["horizon_h"],
                      [FixedModel(12), FixedModel(15), FixedModel(9)],
                      {}, "runway", exp.train.TARGET, "fixture-model")
    assert got.prediction_id.tolist() == req.prediction_id.tolist()
    assert got.status.tolist() == ["available", "unavailable"]
    assert np.isnan(got.estimate.iloc[1]) and np.isnan(got.p10.iloc[1])
    assert got.p10.iloc[0] == 9 and got.p90.iloc[0] == 15
    assert "snapshot_missing" in got.reason_codes.iloc[1]


def test_schedule_prediction_does_not_require_weather_and_operations_does_require_feed():
    req = make_requests("KATL", utc(["2024-03-01 15:00"]), [3])
    frame = req[["prediction_id", "horizon_h"]].assign(
        demand_status="ok", status="partial", demand_reason_codes=[[]],
        reason_codes=[["taf_missing"]], ops_status="partial")
    schedule = exp.predict(req, frame, ["horizon_h"], [FixedModel(10)], {},
                            "schedule", exp.train.TARGET, "fixture-model")
    assert schedule.status.tolist() == ["available"]
    assert "taf_missing" not in schedule.reason_codes.iloc[0]
    operations = exp.predict(req, frame.assign(status="ok"), ["horizon_h"],
                              [FixedModel(10)], {}, "operations",
                              exp.train.TARGET, "fixture-model")
    assert operations.status.tolist() == ["unavailable"]
    assert "simulated_operations_unavailable" in operations.reason_codes.iloc[0]
    assert "simulated_feed" in operations.reason_codes.iloc[0]


def test_heldout_outcome_mutation_cannot_change_source_training_membership_or_values(
    tmp_path, monkeypatch
):
    path, labels = training_export(tmp_path)
    monkeypatch.setattr(exp, "read_inputs", lambda *args: labels[["prediction_id", "target_start_utc"]])
    first = exp.training_rows(tmp_path, path, "throughput", exp.train.TARGET,
                              "schedule", ["KDFW"], 0)
    labels.loc[labels.airport_icao.eq("KATL"), "y_true"] = -999999.0
    labels.to_parquet(path, index=False)
    second = exp.training_rows(tmp_path, path, "throughput", exp.train.TARGET,
                               "schedule", ["KDFW"], 0)
    pd.testing.assert_frame_equal(first, second)


def test_csv_training_uses_only_cohort_feature_members_not_all_bts_labels(tmp_path, monkeypatch):
    path, labels = training_export(tmp_path)
    csv_processed = tmp_path / "cohorts" / "csv_only_v1"
    seen = []
    def csv_inputs(processed, *args):
        seen.append(processed)
        return labels.loc[labels.prediction_id.eq("jan"),
                          ["prediction_id", "target_start_utc"]]
    monkeypatch.setattr(exp, "read_inputs", csv_inputs)
    got = exp.training_rows(csv_processed, path, "throughput", exp.train.TARGET,
                            "schedule", ["KDFW"], 0)
    assert seen == [csv_processed]
    assert got.prediction_id.tolist() == ["jan"]
    assert got.y_true.tolist() == [10.0]


@pytest.mark.parametrize("variant", exp.VARIANTS)
def test_transfer_features_omit_airport_category_and_airport_fitted_normalizers(variant):
    names = exp.feature_names(variant, "throughput", transfer=True)
    assert "airport_icao" not in names
    assert not any("2023" in n for n in names)
    assert "horizon_h" in names


def test_validation_labels_are_read_only_for_source_cohort_prediction_ids(tmp_path, monkeypatch):
    features = pd.DataFrame({"prediction_id": ["source_csv_val"], "horizon_h": [3]})
    labels = pd.DataFrame({"prediction_id": ["source_csv_val", "heldout_val", "all_bts_val"],
                           "target_kind": exp.train.TARGET,
                           "y_true": [10.0, 999.0, 888.0], "eligible": True})
    path = tmp_path / "labels.parquet"
    labels.to_parquet(path, index=False)
    seen = []
    def source_inputs(processed, task, split, variant, airports):
        seen.append((processed, split, airports))
        return features
    monkeypatch.setattr(exp, "read_inputs", source_inputs)
    first = exp.validation_rows(tmp_path, path, "throughput", exp.train.TARGET,
                                "schedule", ["KDFW"], 0)
    labels.loc[labels.prediction_id.ne("source_csv_val"), "y_true"] = -9999.0
    labels.to_parquet(path, index=False)
    second = exp.validation_rows(tmp_path, path, "throughput", exp.train.TARGET,
                                 "schedule", ["KDFW"], 0)
    pd.testing.assert_frame_equal(first, second)
    assert first.prediction_id.tolist() == ["source_csv_val"]
    assert seen == [(tmp_path, "validation", ["KDFW"])] * 2


@pytest.mark.parametrize("cohort", ["loao_KATL_v1", "csv_only_v1"])
def test_run_preserves_cohort_requests_and_binds_exact_request_hash(
    tmp_path, monkeypatch, cohort
):
    import json

    processed = tmp_path / cohort
    processed.mkdir()
    (processed / "feature_snapshots.manifest.json").write_text(
        json.dumps({"data_snapshot_id": "fixture-snapshot"}))
    for name in (exp.registry.WEATHER_TABLE, exp.registry.DEMAND_TABLE):
        (processed / name).write_text("fixture-feature-bytes")
    label_path, training_path = tmp_path / "labels", tmp_path / "training"
    label_path.write_text("fixture-label-bytes")
    training_path.write_text("fixture-training-bytes")
    task = "severe_delay" if cohort == "csv_only_v1" else "throughput"
    all_req = pd.concat([
        make_requests(airport, utc(["2024-03-01 15:00", "2024-09-01 15:00"]), [3])
        for airport in ("KATL", "KDFW")
    ], ignore_index=True).assign(task=task, cohort_version=cohort)
    all_req["prediction_id"] = cohort + "|" + all_req.prediction_id
    request_path = processed / "prediction_requests.parquet"
    all_req.to_parquet(request_path, index=False)
    request_hash = exp.sha256(request_path)
    monkeypatch.setattr(exp, "paths", lambda c: (processed, label_path, training_path))
    monkeypatch.setattr(exp, "feature_names", lambda variant, task, transfer=False:
                        ["horizon_h"] if transfer else ["airport_icao", "horizon_h"])
    fitted = []
    def rows(processed, path, task, target, variant, airports, max_rows):
        fitted.append(tuple(airports))
        return pd.DataFrame({"airport_icao": airports,
                             "horizon_h": [3] * len(airports),
                             "y_true": [1.0] * len(airports)})
    monkeypatch.setattr(exp, "training_rows", rows)
    monkeypatch.setattr(exp, "validation_rows", rows)
    def inputs(processed, task, split, variant, airports):
        lo, hi = exp.train.bounds(split)
        req = all_req[all_req.airport_icao.isin(airports)
                      & all_req.target_start_utc.ge(lo) & all_req.target_start_utc.lt(hi)]
        return req[["prediction_id", "airport_icao", "horizon_h"]].assign(
            demand_status="ok", status="ok", demand_reason_codes=[[]] * len(req),
            reason_codes=[[]] * len(req))
    monkeypatch.setattr(exp, "read_inputs", inputs)
    class Model(FixedModel):
        def save_model(self, path):
            path.write_text("fixture-model")
    monkeypatch.setattr(exp, "fit_model", lambda *args: (
        [Model(0.2)], exp.categorical_levels(args[0][args[1]]),
        {"fit_rows": 2, "selection_rows": 2, "selected_rounds": [1]}))
    out = exp.run(cohort, "runway", artifacts=tmp_path / "artifacts", rounds=1)
    manifest = json.loads((out / "manifest.json").read_text())
    predictions = pd.read_parquet(out / "predictions.parquet")
    assert manifest["prediction_requests_sha256"] == request_hash
    assert exp.sha256(request_path) == request_hash
    assert predictions.cohort_version.eq(cohort).all()
    assert set(predictions.prediction_id) <= set(all_req.prediction_id)
    assert predictions.target_start_utc.lt(pd.Timestamp("2025-01-01", tz="UTC")).all()
    if cohort.startswith("loao_"):
        assert fitted == [("KDFW",), ("KDFW",)]
        assert predictions.airport_icao.eq("KATL").all()
        assert manifest["train_airports"] == ["KDFW"]
        assert manifest["calibration_airports"] == ["KDFW"]
        assert manifest["held_out_calibration"] is False
        assert "airport_icao" not in manifest["fits"][exp.train.TARGET]["features"]
        source = pd.read_parquet(out / "source_calibration_predictions.parquet")
        assert source.airport_icao.eq("KDFW").all()
    else:
        assert predictions.target_kind.eq("departure_delay_gt45").all()
        assert predictions.model_version.eq("lgbm_delay_csv_only_v1").all()


def test_heldout_training_and_validation_outcomes_cannot_change_fitted_predictions(
    tmp_path, monkeypatch
):
    rng = np.random.default_rng(42)
    parts = []
    for airport in ("KDFW", "KATL"):
        for start, n in (("2023-01-01 15:00", 160), ("2024-01-10 15:00", 60)):
            req = make_requests(airport, pd.date_range(start, periods=n, freq="D", tz="UTC"), [3])
            req["prediction_id"] = "loao_KATL_v1|" + req.prediction_id
            req["cohort_version"] = "loao_KATL_v1"
            req["metar_age_min"] = rng.uniform(0, 90, n)
            parts.append(req)
    features = pd.concat(parts, ignore_index=True)
    features = features.assign(status="ok", demand_status="ok",
                               reason_codes=[[] for _ in range(len(features))],
                               demand_reason_codes=[[] for _ in range(len(features))])
    labels = features[["prediction_id", "airport_icao", "target_start_utc"]].assign(
        target_kind=exp.train.TARGET, eligible=True,
        y_true=10 + features.metar_age_min * 0.7,
        outcome_available_at_utc=features.target_start_utc + pd.Timedelta(hours=1))
    train_labels = labels[labels.target_start_utc.lt(pd.Timestamp("2024-01-01", tz="UTC"))].copy()
    training_path, labels_path = tmp_path / "train.parquet", tmp_path / "labels.parquet"
    train_labels.to_parquet(training_path, index=False)
    labels.to_parquet(labels_path, index=False)
    def selected_inputs(processed, task, split, variant, airports):
        lo, hi = exp.train.bounds(split)
        return features[features.airport_icao.isin(airports)
                        & features.target_start_utc.ge(lo) & features.target_start_utc.lt(hi)].copy()
    monkeypatch.setattr(exp, "read_inputs", selected_inputs)
    inference = selected_inputs(tmp_path, "throughput", "validation", "runway", ["KATL"])
    req = inference[exp.baselines.REQUEST_COLUMNS]
    names = ["horizon_h", "metar_age_min"]
    def fitted_predictions():
        tr = exp.training_rows(tmp_path, training_path, "throughput", exp.train.TARGET,
                               "runway", ["KDFW"], 0)
        va = exp.validation_rows(tmp_path, labels_path, "throughput", exp.train.TARGET,
                                 "runway", ["KDFW"], 0)
        models, levels, _ = exp.fit_model(tr, names, False, 10, va)
        return exp.predict(req, inference, names, models, levels, "runway",
                           exp.train.TARGET, "fixture-heldout")
    first = fitted_predictions()
    train_labels.loc[train_labels.airport_icao.eq("KATL"), "y_true"] = -99999.0
    labels.loc[labels.airport_icao.eq("KATL"), "y_true"] = 99999.0
    train_labels.to_parquet(training_path, index=False)
    labels.to_parquet(labels_path, index=False)
    second = fitted_predictions()
    pd.testing.assert_frame_equal(first, second)
    assert first.status.eq("available").all()
    assert first.estimate.notna().all() and len(first) == 60
