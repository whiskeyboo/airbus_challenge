import json

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
from conftest import make_requests

from airbus_challenge import baselines
from airbus_challenge.baselines import (
    FEED_LATENCY_H,
    PREDICTION_SCHEMA,
    RETROSPECTIVE_SCHEDULE,
    SIMULATED_FEED,
    SOURCE_PATHS,
    TARGET,
    TARGET_LABEL,
    _local_time,
    baseline_predictions,
    check_predictions,
    climatology,
    fit_climatology,
    fit_schedule,
    in_split,
    main,
    observed,
    persistence,
    schedule_only,
    seasonal_persistence,
    source_dirty,
)

UTC_TIME = "2024-03-05 15:00"


def ts(text: str) -> pd.Timestamp:
    return pd.Timestamp(text, tz="UTC")


def train_rows(hourly: pd.DataFrame) -> pd.DataFrame:
    return observed(in_split(hourly, "train", "hour_start_utc"))


def airport_rows(hourly: pd.DataFrame, icao: str, mask: pd.Series) -> pd.Series:
    return hourly["airport_icao"].eq(icao) & mask


def value_at(hourly: pd.DataFrame, icao: str, hour: pd.Timestamp) -> float:
    rows = hourly[hourly["airport_icao"].eq(icao) & hourly["hour_start_utc"].eq(hour)]
    return float(rows[TARGET].iloc[0])


@pytest.mark.parametrize("h", [3, 6, 9, 12])
def test_persistence_reads_hour_starting_s_minus_h_minus_1(hourly, h):
    hourly[TARGET] = pd.array(np.arange(len(hourly)), dtype="Int32")
    s = ts(UTC_TIME)
    result = persistence(make_requests("KATL", [s], [h]), hourly)
    last_complete = s - pd.Timedelta(hours=h + 1)
    unfinished = s - pd.Timedelta(hours=h)
    assert result["estimate"].item() == value_at(hourly, "KATL", last_complete)
    assert result["estimate"].item() != value_at(hourly, "KATL", unfinished)


def test_persistence_ignores_hours_from_issue_time_onward(hourly):
    requests = make_requests("KATL", [ts(UTC_TIME)])
    before = persistence(requests, hourly)
    latest_as_of = requests["as_of_utc"].max()
    # Every row at or after the latest T changes, including the hour starting at T.
    hourly.loc[hourly["hour_start_utc"].ge(latest_as_of), TARGET] = 999
    after = persistence(requests, hourly)
    pd.testing.assert_series_equal(before["estimate"], after["estimate"])


def test_persistence_changes_with_the_last_complete_hour(hourly):
    requests = make_requests("KATL", [ts(UTC_TIME)], [3])
    before = persistence(requests, hourly)["estimate"].item()
    source = airport_rows(
        hourly, "KATL", hourly["hour_start_utc"].eq(ts("2024-03-05 11:00"))
    )
    hourly.loc[source, TARGET] = 999
    assert persistence(requests, hourly)["estimate"].item() == 999 != before


@pytest.mark.parametrize("coverage", ["partial", "missing"])
def test_persistence_is_unavailable_when_source_hour_is_incomplete(hourly, coverage):
    source = airport_rows(
        hourly, "KATL", hourly["hour_start_utc"].eq(ts("2024-03-05 11:00"))
    )
    hourly.loc[source, "coverage_status"] = coverage
    result = persistence(make_requests("KATL", [ts(UTC_TIME)], [3]), hourly).iloc[0]
    assert np.isnan(result["estimate"])
    assert result["status"] == "unavailable"
    assert result["reason_codes"] == [SIMULATED_FEED, "source_hour_incomplete"]


def test_persistence_is_marked_as_simulated_feed(hourly):
    result = persistence(make_requests("KATL", [ts(UTC_TIME)]), hourly)
    assert all(codes == [SIMULATED_FEED] for codes in result["reason_codes"])


def test_seasonal_persistence_reads_same_hour_a_week_earlier(hourly):
    s = ts(UTC_TIME)
    result = seasonal_persistence(make_requests("KDFW", [s], [12]), hourly)
    assert result["estimate"].item() == value_at(
        hourly, "KDFW", s - pd.Timedelta(days=7)
    )


@pytest.mark.parametrize(
    ("icao", "target", "source"),
    [
        # 11:00 EDT reads 11:00 EST, the week after clocks go forward.
        ("KATL", "2024-03-12 15:00", "2024-03-05 16:00"),
        ("KDFW", "2024-03-12 15:00", "2024-03-05 16:00"),
        # 10:00 EST reads 10:00 EDT, the week after clocks go back.
        ("KATL", "2024-11-05 15:00", "2024-10-29 14:00"),
        # 01:00 happened twice a week earlier: take the first, in EDT.
        ("KATL", "2024-11-10 06:00", "2024-11-03 05:00"),
        # 02:00 did not exist a week earlier: move forward to 03:00 EDT.
        ("KATL", "2024-03-17 06:00", "2024-03-10 07:00"),
        # The hour between the two airports' clock changes pins each zone.
        ("KATL", "2024-03-17 07:00", "2024-03-10 07:00"),
        ("KDFW", "2024-03-17 07:00", "2024-03-10 08:00"),
    ],
)
def test_seasonal_persistence_keeps_local_clock_across_dst(
    hourly, icao, target, source
):
    hourly[TARGET] = pd.array(np.arange(len(hourly)), dtype="Int32")
    requests = make_requests(icao, [ts(target)], [3])
    result = seasonal_persistence(requests, hourly)
    assert result["estimate"].item() == value_at(hourly, icao, ts(source))


def test_seasonal_persistence_refuses_a_source_hour_after_issue_time(hourly):
    requests = make_requests("KATL", [ts(UTC_TIME)], [3, 168])
    with pytest.raises(ValueError, match="after issue time"):
        seasonal_persistence(requests, hourly)


@pytest.mark.parametrize("h", [3, 6, 9, 12])
def test_hours_from_issue_time_change_no_baseline(hourly, h):
    requests = make_requests("KATL", [ts(UTC_TIME)], [h])
    train = train_rows(hourly)
    climatology_fit, schedule_fit = fit_climatology(train), fit_schedule(train)

    def predict(table: pd.DataFrame) -> pd.DataFrame:
        return pd.concat(
            [
                persistence(requests, table),
                seasonal_persistence(requests, table),
                climatology(requests, climatology_fit),
                schedule_only(requests, table, schedule_fit),
            ],
            ignore_index=True,
        )

    before = predict(hourly)
    later = hourly["hour_start_utc"].ge(requests["as_of_utc"].item())
    changed = hourly.copy()
    changed.loc[later, TARGET] = 999
    changed.loc[later, "coverage_status"] = "partial"
    pd.testing.assert_frame_equal(before, predict(changed))

    # The target-hour schedule is the one declared exception (TEMPORAL_RULES §3).
    removed = predict(hourly[~later])
    no_schedule = before["model_version"].ne("baseline_schedule_v1")
    pd.testing.assert_frame_equal(before[no_schedule], removed[no_schedule])


def test_climatology_changes_with_train_rows(hourly):
    requests = make_requests("KATL", [ts("2024-03-05 15:00")], [3])
    before = climatology(requests, fit_climatology(train_rows(hourly)))
    train = airport_rows(hourly, "KATL", hourly["hour_start_utc"].lt(ts("2024-01-01")))
    hourly.loc[train, TARGET] = 999
    after = climatology(requests, fit_climatology(train_rows(hourly)))
    assert after["estimate"].item() == 999 != before["estimate"].item()


def test_local_time_uses_each_airports_own_zone(hourly):
    rows = pd.DataFrame(
        {
            "airport_icao": ["KATL", "KDFW", "KATL", "KDFW"],
            "hour_start_utc": [
                ts("2024-03-05 02:00"),  # A UTC Tuesday, still Monday locally.
                ts("2024-03-05 02:00"),
                ts("2024-07-01 23:00"),
                ts("2024-07-02 01:00"),
            ],
        }
    )
    local = _local_time(rows, "hour_start_utc")
    assert local["local_hour"].tolist() == [21, 20, 19, 20]
    assert local["local_weekday"].tolist() == [0, 0, 0, 0]


@pytest.mark.parametrize(
    ("icao", "winter_utc_hour", "summer_0800_local"),
    [("KATL", 13, "2024-07-03 12:00"), ("KDFW", 14, "2024-07-03 13:00")],
)
def test_climatology_keys_on_local_hour_across_dst(
    hourly, icao, winter_utc_hour, summer_0800_local
):
    train = train_rows(hourly)
    train = train[train["airport_icao"].eq(icao)].copy()
    train = train[train["hour_start_utc"].lt(ts("2023-03-01"))]
    train[TARGET] = 0
    train.loc[train["hour_start_utc"].dt.hour.eq(winter_utc_hour), TARGET] = 100
    fit = fit_climatology(train)
    result = climatology(make_requests(icao, [ts(summer_0800_local)], [3]), fit)
    assert result["estimate"].item() == 100


def test_climatology_keys_on_local_weekday(hourly):
    # 19:00 on a winter local Monday is a UTC Tuesday; on a summer one it is a UTC Monday.
    train = train_rows(hourly)
    train = train[train["airport_icao"].eq("KATL")].copy()
    train = train[train["hour_start_utc"].lt(ts("2023-03-11"))]
    local = train["hour_start_utc"].dt.tz_convert("America/New_York")
    train[TARGET] = 0
    train.loc[local.dt.day_of_week.eq(0), TARGET] = 100
    fit = fit_climatology(train)
    monday, tuesday = ts("2024-07-01 23:00"), ts("2024-07-02 23:00")
    result = climatology(make_requests("KATL", [monday, tuesday], [3]), fit)
    assert result["estimate"].tolist() == [100, 0]


def test_climatology_falls_back_on_a_sparse_cell(hourly):
    train = train_rows(hourly)
    train = train[train["hour_start_utc"].lt(ts("2023-02-15"))]  # About 6 per weekday.
    target = ts("2024-03-05 15:00")
    result = climatology(make_requests("KATL", [target], [3]), fit_climatology(train))
    assert result["status"].item() == "degraded"
    assert result["reason_codes"].item() == ["climatology_hour_fallback"]
    assert result["estimate"].notna().item()


def test_climatology_is_unavailable_for_an_airport_held_out_of_train(hourly):
    train = train_rows(hourly)
    fit = fit_climatology(train[train["airport_icao"].eq("KATL")])
    result = climatology(make_requests("KDFW", [ts(UTC_TIME)], [3]), fit)
    assert result["status"].item() == "unavailable"
    assert result["reason_codes"].item() == ["no_train_history"]


def schedule_fit_for(icao: str, slope: float, intercept: float) -> dict:
    line = {"slope": slope, "intercept": intercept, "n_train": 1}
    return {"airports": {icao: line}, "pooled": line}


def test_schedule_fit_recovers_each_airports_train_relation(hourly):
    scheduled = hourly["scheduled_arrivals"].astype("float64")
    is_atl = hourly["airport_icao"].eq("KATL")
    hourly[TARGET] = np.where(is_atl, scheduled * 0.9 + 2, scheduled * 0.7 + 1)
    fit = fit_schedule(train_rows(hourly))
    assert fit["airports"]["KATL"]["slope"] == pytest.approx(0.9)
    assert fit["airports"]["KATL"]["intercept"] == pytest.approx(2)
    assert fit["airports"]["KDFW"]["slope"] == pytest.approx(0.7)
    assert fit["airports"]["KDFW"]["intercept"] == pytest.approx(1)
    assert 0.7 < fit["pooled"]["slope"] < 0.9


def test_schedule_only_uses_the_airports_own_line(hourly):
    target = airport_rows(hourly, "KDFW", hourly["hour_start_utc"].eq(ts(UTC_TIME)))
    hourly.loc[target, "scheduled_arrivals"] = 10
    fit = schedule_fit_for("KDFW", 0.5, 1.0)
    fit["pooled"] = {"slope": 2.0, "intercept": 0.0, "n_train": 1}
    result = schedule_only(make_requests("KDFW", [ts(UTC_TIME)], [3]), hourly, fit)
    assert result["estimate"].item() == 6
    assert result["status"].item() == "available"
    assert result["reason_codes"].item() == [RETROSPECTIVE_SCHEDULE]


def test_schedule_only_uses_pooled_line_for_an_airport_held_out_of_train(hourly):
    target = airport_rows(hourly, "KDFW", hourly["hour_start_utc"].eq(ts(UTC_TIME)))
    hourly.loc[target, "scheduled_arrivals"] = 10
    fit = schedule_fit_for("KATL", 0.5, 1.0)
    result = schedule_only(make_requests("KDFW", [ts(UTC_TIME)], [3]), hourly, fit)
    assert result["estimate"].item() == 6
    assert result["status"].item() == "degraded"
    assert result["reason_codes"].item() == [
        RETROSPECTIVE_SCHEDULE,
        "airport_not_in_train",
    ]


def test_schedule_only_clips_at_zero(hourly):
    requests = make_requests("KATL", [ts(UTC_TIME)], [3])
    fit = schedule_fit_for("KATL", -1.0, 0.0)
    assert schedule_only(requests, hourly, fit)["estimate"].item() == 0


def test_schedule_only_is_unavailable_without_a_schedule(hourly):
    target = airport_rows(hourly, "KATL", hourly["hour_start_utc"].eq(ts(UTC_TIME)))
    hourly.loc[target, "scheduled_arrivals"] = pd.NA
    requests = make_requests("KATL", [ts(UTC_TIME)], [3])
    fit = schedule_fit_for("KATL", 1.0, 0.0)
    result = schedule_only(requests, hourly, fit).iloc[0]
    assert result["status"] == "unavailable"
    assert "schedule_missing" in result["reason_codes"]


@pytest.mark.parametrize(
    ("column", "value"),
    [
        (TARGET, pd.NA),
        (TARGET, 0),
        (TARGET, 999),
        ("reporting_carrier_takeoffs", 0),
        ("coverage_status", "partial"),
        ("coverage_status", "missing"),
        ("coverage_fraction", 0.1),
    ],
)
def test_target_hour_outcome_reaches_no_baseline_for_that_hour(hourly, column, value):
    requests = make_requests("KATL", [ts(UTC_TIME)])
    before, _ = baseline_predictions(hourly, requests)
    target = airport_rows(hourly, "KATL", hourly["hour_start_utc"].eq(ts(UTC_TIME)))
    hourly.loc[target, column] = value
    after, _ = baseline_predictions(hourly, requests)
    pd.testing.assert_frame_equal(before, after)


def _sample_requests() -> pd.DataFrame:
    targets = [
        ts("2023-06-01 12:00"),  # train
        ts("2024-03-01 12:00"),  # validation
        ts("2024-09-01 12:00"),  # calibration
        ts("2025-03-01 12:00"),  # test
    ]
    return pd.concat(
        [make_requests(icao, targets) for icao in ("KATL", "KDFW")], ignore_index=True
    )


def test_dev_run_scores_validation_and_calibration_only(hourly):
    predictions, _ = baseline_predictions(hourly, _sample_requests())
    assert set(predictions["target_start_utc"].dt.year) == {2024}
    assert predictions["data_mode"].eq("fixture").all()
    assert predictions["model_version"].nunique() == 4


def test_fitted_baselines_read_train_outcomes_only(hourly):
    requests = _sample_requests()
    before, fit_before = baseline_predictions(hourly, requests)
    after_cutoff = hourly["hour_start_utc"].ge(ts("2024-01-01"))
    hourly.loc[after_cutoff, TARGET] = 999
    hourly.loc[after_cutoff, "coverage_status"] = "partial"
    hourly.loc[after_cutoff, "coverage_fraction"] = 0.1
    after, fit_after = baseline_predictions(hourly, requests)
    fitted = before["model_version"].isin(
        ["baseline_climatology_v1", "baseline_schedule_v1"]
    )
    assert fit_before == fit_after
    pd.testing.assert_frame_equal(before[fitted], after[fitted])


def test_requests_issued_before_the_fit_cutoff_are_not_scored(hourly):
    requests = make_requests("KATL", [ts("2024-01-01 02:00"), ts("2024-01-01 11:00")])
    predictions, _ = baseline_predictions(hourly, requests)
    assert predictions["as_of_utc"].min() >= ts("2024-01-01 00:00")
    # 02:00 keeps no horizon; 11:00 loses only 12h, whose T is 23:00 on 31 Dec.
    assert set(predictions["target_start_utc"]) == {ts("2024-01-01 11:00")}
    assert set(predictions["horizon_h"]) == {3, 6, 9}


def test_fits_skip_incomplete_train_hours(hourly):
    requests = _sample_requests()
    in_train = hourly["hour_start_utc"].between(ts("2023-05-01"), ts("2023-06-01"))
    hourly.loc[in_train, "coverage_status"] = "partial"
    before, fit_before = baseline_predictions(hourly, requests)
    hourly.loc[in_train, TARGET] = 999
    after, fit_after = baseline_predictions(hourly, requests)
    fitted = before["model_version"].isin(
        ["baseline_climatology_v1", "baseline_schedule_v1"]
    )
    assert fit_before == fit_after
    pd.testing.assert_frame_equal(before[fitted], after[fitted])


@pytest.fixture
def clean_git(monkeypatch):
    monkeypatch.setattr(baselines, "git", lambda *args: "")


def locked_args(tmp_path) -> dict:
    return {
        "locked_test": True,
        "approved_by": "tester",
        "ledger": tmp_path / "locked_runs",
    }


def write_inputs(hourly, requests, tmp_path):
    hourly_path = tmp_path / "airport_hourly.parquet"
    requests_path = tmp_path / "prediction_requests.parquet"
    hourly.to_parquet(hourly_path)
    requests.to_parquet(requests_path)
    return hourly_path, requests_path


def test_dev_main_does_not_load_test_rows(hourly, tmp_path, clean_git):
    # A second snapshot in 2025 only fails the run if those rows are loaded.
    in_test = hourly["hour_start_utc"].ge(ts("2025-01-01"))
    hourly.loc[in_test, "source_snapshot_id"] = "later"
    hourly["data_mode"] = "real"
    requests = _sample_requests().assign(data_mode="real")
    inputs = write_inputs(hourly, requests, tmp_path)

    main(*inputs, tmp_path / "artifacts")
    with pytest.raises(ValueError, match="one airport_hourly snapshot"):
        main(*inputs, tmp_path / "artifacts", **locked_args(tmp_path))


def test_locked_main_writes_once_to_its_own_directory(hourly, tmp_path, clean_git):
    hourly["data_mode"] = "real"
    requests = _sample_requests().assign(data_mode="real")
    inputs = write_inputs(hourly, requests, tmp_path)
    artifacts = tmp_path / "artifacts"
    dev = main(*inputs, artifacts)
    dev_bytes = dev.read_bytes()

    locked = main(*inputs, artifacts, **locked_args(tmp_path))

    assert locked.parent.name == "baselines_locked_test"
    assert dev.read_bytes() == dev_bytes
    locked_bytes = locked.read_bytes()
    with pytest.raises(FileExistsError, match="runs once"):
        main(*inputs, artifacts, **locked_args(tmp_path))
    assert locked.read_bytes() == locked_bytes


def test_a_crashed_locked_run_cannot_be_retried(
    hourly, tmp_path, clean_git, monkeypatch
):
    hourly["data_mode"] = "real"
    requests = _sample_requests().assign(data_mode="real")
    inputs = write_inputs(hourly, requests, tmp_path)

    def crash(*args):
        raise RuntimeError("crash after reading 2025")

    monkeypatch.setattr(baselines, "write_predictions", crash)
    with pytest.raises(RuntimeError, match="crash"):
        main(*inputs, tmp_path / "artifacts", **locked_args(tmp_path))
    monkeypatch.undo()
    monkeypatch.setattr(baselines, "git", lambda *args: "")
    with pytest.raises(FileExistsError, match="runs once"):
        main(*inputs, tmp_path / "other_artifacts", **locked_args(tmp_path))


def test_locked_claim_records_approval_and_commit(tmp_path):
    baselines.claim_locked_run("run", "tester", "abc123", tmp_path)
    claim = json.loads((tmp_path / "run.json").read_text())
    assert (claim["approved_by"], claim["commit"]) == ("tester", "abc123")


def test_locked_main_needs_approval(hourly, tmp_path, clean_git):
    hourly["data_mode"] = "real"
    requests = _sample_requests().assign(data_mode="real")
    inputs = write_inputs(hourly, requests, tmp_path)
    args = {**locked_args(tmp_path), "approved_by": None}
    with pytest.raises(ValueError, match="approved_by"):
        main(*inputs, tmp_path / "artifacts", **args)
    assert not (tmp_path / "locked_runs").exists()


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("data_mode", "Real", "outside"),
        ("schedule_knowledge_basis", None, "schedule basis"),
        ("source_snapshot_id", None, "unused"),
    ],
)
def test_refused_inputs_never_claim_the_locked_run(
    hourly, tmp_path, clean_git, column, value, message
):
    hourly["data_mode"] = "real"
    requests = _sample_requests().assign(data_mode="real")
    if message == "unused":
        hourly.loc[0, column] = "second"
        message = "one airport_hourly snapshot"
    else:
        hourly[column] = value
        if column == "data_mode":
            requests["data_mode"] = value
    inputs = write_inputs(hourly, requests, tmp_path)
    with pytest.raises(ValueError, match=message):
        main(*inputs, tmp_path / "artifacts", **locked_args(tmp_path))
    assert not (tmp_path / "locked_runs").exists()


def test_locked_main_writes_nothing_if_the_manifest_fails(
    hourly, tmp_path, monkeypatch
):
    hourly["data_mode"] = "real"
    requests = _sample_requests().assign(data_mode="real")
    inputs = write_inputs(hourly, requests, tmp_path)

    def no_commit(*args):
        if args[0] == "rev-parse":
            raise RuntimeError("git unavailable")
        return ""

    monkeypatch.setattr(baselines, "git", no_commit)
    with pytest.raises(RuntimeError, match="git unavailable"):
        main(*inputs, tmp_path / "artifacts", **locked_args(tmp_path))
    assert not (tmp_path / "artifacts").exists()
    assert not (tmp_path / "locked_runs").exists()


def test_locked_main_refuses_uncommitted_code(hourly, tmp_path, monkeypatch):
    hourly["data_mode"] = "real"
    requests = _sample_requests().assign(data_mode="real")
    inputs = write_inputs(hourly, requests, tmp_path)
    monkeypatch.setattr(baselines, "git", lambda *args: " M uv.lock")

    path = main(*inputs, tmp_path / "artifacts")
    manifest = json.loads(path.with_name("manifest.json").read_text())
    assert manifest["commit_dirty"] is True
    with pytest.raises(ValueError, match="committed"):
        main(*inputs, tmp_path / "artifacts", **locked_args(tmp_path))


def test_dirty_check_covers_code_and_locked_dependencies(monkeypatch):
    seen = []
    monkeypatch.setattr(baselines, "git", lambda *args: seen.append(args) or "")
    assert source_dirty() is False
    assert seen == [("status", "--porcelain", "--", *SOURCE_PATHS)]
    assert {"src", "configs", "pyproject.toml", "uv.lock"} == set(SOURCE_PATHS)


def test_manifest_declares_assumptions(hourly, tmp_path, clean_git):
    inputs = write_inputs(hourly, _sample_requests(), tmp_path)
    path = main(*inputs, tmp_path / "artifacts")
    manifest = json.loads(path.with_name("manifest.json").read_text())
    assert manifest["target_label"] == TARGET_LABEL
    assert manifest["schedule_knowledge_basis"] == "fixture"
    assert manifest["feed_latency_h"] == FEED_LATENCY_H
    assert len(manifest["uv_lock_sha256"]) == 64


@pytest.mark.parametrize("bases", [["a", "b"], [None, None]])
def test_schedule_basis_must_be_declared_once(hourly, tmp_path, clean_git, bases):
    half = len(hourly) // 2
    hourly["schedule_knowledge_basis"] = [bases[0]] * half + [bases[1]] * (
        len(hourly) - half
    )
    inputs = write_inputs(hourly, _sample_requests(), tmp_path)
    with pytest.raises(ValueError, match="schedule basis"):
        main(*inputs, tmp_path / "artifacts")


def test_locked_main_refuses_fixture_data(hourly, tmp_path, clean_git):
    inputs = write_inputs(hourly, _sample_requests(), tmp_path)
    with pytest.raises(ValueError, match="needs real data"):
        main(*inputs, tmp_path / "artifacts", **locked_args(tmp_path))
    assert not (tmp_path / "artifacts").exists()


@pytest.mark.parametrize(("hourly_mode", "requests_mode"), [("fixture", "real")])
def test_mixed_data_mode_is_rejected(hourly, tmp_path, hourly_mode, requests_mode):
    hourly["data_mode"] = hourly_mode
    requests = _sample_requests().assign(data_mode=requests_mode)
    inputs = write_inputs(hourly, requests, tmp_path)
    with pytest.raises(ValueError, match="mixed data_mode"):
        main(*inputs, tmp_path / "artifacts")


def test_locked_run_scores_test_only(hourly):
    predictions, _ = baseline_predictions(hourly, _sample_requests(), locked_test=True)
    assert set(predictions["target_start_utc"].dt.year) == {2025}


def test_wrong_horizon_is_rejected(hourly):
    requests = _sample_requests()
    requests.loc[0, "horizon_h"] = 4
    with pytest.raises(ValueError, match="horizon_h"):
        baseline_predictions(hourly, requests)


def test_issue_time_after_the_target_is_rejected(hourly):
    target = ts(UTC_TIME)
    requests = make_requests("KATL", [target], [3]).assign(
        as_of_utc=target + pd.Timedelta(hours=1), horizon_h=-1
    )
    with pytest.raises(ValueError, match="horizon_h outside"):
        baseline_predictions(hourly, requests)


def test_horizon_outside_config_is_rejected(hourly):
    requests = make_requests("KATL", [ts(UTC_TIME)], [1])
    with pytest.raises(ValueError, match="horizon_h outside"):
        baseline_predictions(hourly, requests)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.assign(
            target_start_utc=d["target_start_utc"] + pd.Timedelta(minutes=30),
            target_end_utc=d["target_end_utc"] + pd.Timedelta(minutes=30),
            as_of_utc=d["as_of_utc"] + pd.Timedelta(minutes=30),
        ),
        lambda d: d.assign(target_end_utc=d["target_end_utc"] + pd.Timedelta(hours=1)),
    ],
)
def test_target_must_be_one_whole_utc_hour(hourly, change):
    requests = change(make_requests("KATL", [ts(UTC_TIME)], [3]))
    with pytest.raises(ValueError, match="whole UTC hour"):
        baseline_predictions(hourly, requests)


def valid_predictions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "prediction_id": ["a", "b"],
            "target_kind": TARGET,
            "model_version": "m",
            "status": ["available", "unavailable"],
            "estimate": [1.0, np.nan],
            "reason_codes": [[], ["why"]],
        }
    )


def test_check_predictions_accepts_valid_rows():
    check_predictions(valid_predictions())


@pytest.mark.parametrize(
    ("column", "row", "bad", "message"),
    [
        ("prediction_id", 1, "a", "duplicate prediction"),
        ("status", 0, "stale", "status outside"),
        ("estimate", 1, 2.0, "null exactly when"),
        ("estimate", 0, np.nan, "null exactly when"),
        ("reason_codes", 1, [], "without a reason"),
    ],
)
def test_check_predictions_enforces_each_rule(column, row, bad, message):
    predictions = valid_predictions()
    predictions.at[row, column] = bad
    with pytest.raises(ValueError, match=message):
        check_predictions(predictions)


def test_invalid_predictions_are_never_written(tmp_path):
    path = tmp_path / "predictions.parquet"
    predictions = valid_predictions().assign(status="stale")
    with pytest.raises(ValueError, match="status outside"):
        baselines.write_predictions(predictions, path)
    assert not path.exists()


def test_duplicate_airport_hour_is_rejected(hourly):
    duplicated = pd.concat([hourly, hourly.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate airport hour"):
        baseline_predictions(duplicated, _sample_requests())


def test_missing_hourly_data_mode_is_named(hourly, tmp_path):
    without = hourly.drop(columns="data_mode")
    inputs = write_inputs(without, _sample_requests(), tmp_path)
    with pytest.raises(ValueError, match="needs a data_mode column"):
        main(*inputs, tmp_path / "artifacts")


@pytest.mark.parametrize(
    "keep",
    ["2023-06-01", "2024-06-01"],
    ids=["starts_late", "ends_early"],
)
def test_hour_grid_must_span_train_and_scored_splits(hourly, keep):
    cut = ts(keep)
    late = hourly["hour_start_utc"].ge(cut)
    table = hourly[late if keep == "2023-06-01" else ~late]
    with pytest.raises(ValueError, match="hour grid must span"):
        baseline_predictions(table, _sample_requests())


def test_dev_grid_need_not_reach_the_test_split(hourly):
    table = hourly[hourly["hour_start_utc"].lt(ts("2025-01-01"))]
    baseline_predictions(table, _sample_requests())


def test_hour_grid_gap_is_rejected(hourly):
    with_gap = hourly.drop(hourly.index[100])
    with pytest.raises(ValueError, match="hour grid has gaps"):
        baseline_predictions(with_gap, _sample_requests())


def test_unknown_task_is_rejected(hourly):
    with pytest.raises(ValueError, match="no airport_throughput requests"):
        baseline_predictions(hourly, _sample_requests().assign(task="other"))


def test_main_writes_contract_schema_and_fixture_manifest(hourly, tmp_path):
    target = hourly["hour_start_utc"].eq(ts("2024-03-01 08:00"))  # h=3 source hour.
    hourly.loc[target, "coverage_status"] = "partial"
    inputs = write_inputs(hourly, _sample_requests(), tmp_path)

    path = main(*inputs, tmp_path / "artifacts")

    table = pq.read_table(path)
    assert table.schema.equals(PREDICTION_SCHEMA)
    assert table["estimate"].null_count > 0  # Explicit null, not NaN.
    assert table["p10"].null_count == table.num_rows
    assert path.parent.name == "baselines_dev"
    manifest = json.loads(path.with_name("manifest.json").read_text())
    assert manifest["data_mode"] == "fixture"
    assert manifest["rows"] == table.num_rows
    assert len(manifest["commit"]) == 40
    assert set(manifest["schedule_fit"]["airports"]) == {"KATL", "KDFW"}
    persistence_counts = manifest["status_counts"]["baseline_persistence_v1"]
    assert persistence_counts["unavailable"] == 2  # One source hour, both airports.
    assert manifest["fit_cutoff_utc"] == "2024-01-01T00:00:00+00:00"
