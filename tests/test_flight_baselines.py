import json

import numpy as np
import pandas as pd
import pytest

from airbus_challenge import baselines, evaluate, flight_baselines
from airbus_challenge.evaluate import CONDITIONAL_RATE, LOGISTIC, SEVERE
from airbus_challenge.flight_baselines import (
    CANCELLATION,
    MIN_GROUP_N,
    TARGETS,
    calendar,
    fit_rates,
    scored_requests,
    training_rows,
)
from airbus_challenge.flight_baselines import (
    flight_baselines as run_baselines,
)
from airbus_challenge.requests import flight_requests
from airbus_challenge.targets import label_rows

HORIZONS = [3, 6, 9, 12]
START, END = pd.Timestamp("2023-01-01", tz="UTC"), pd.Timestamp("2025-01-01", tz="UTC")


def make_flights(departures: dict[str, list], seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames = []
    for icao, times in departures.items():
        times = pd.DatetimeIndex(times)
        frames.append(
            pd.DataFrame(
                {
                    "flight_id": [f"{icao}-{t.isoformat()}" for t in times],
                    "origin_icao": icao,
                    "scheduled_dep_utc": times,
                    "schedule_snapshot_id": "fixture-0",
                    "dep_delay_min": rng.choice([-5, 10, 45, 60, 120], len(times)),
                    "cancelled": rng.random(len(times)) < 0.05,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def build(flights: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    icaos = flights["origin_icao"].unique().tolist()
    requests = flight_requests(flights, icaos, HORIZONS, START, END, "fixture")
    outcomes = flights[["flight_id", "dep_delay_min", "cancelled", "scheduled_dep_utc"]]
    return requests, label_rows(requests, outcomes, None, data_mode="fixture")


def regular(airports=("KATL", "KDFW")) -> pd.DataFrame:
    times = pd.date_range(START, END, freq="5h", inclusive="left")
    return make_flights({icao: times for icao in airports})


@pytest.fixture(scope="module")
def fixture_tables():
    return build(regular())


def one_group(delays, cancelled) -> pd.DataFrame:
    times = pd.date_range("2023-03-01 15:00", periods=len(delays), freq="D", tz="UTC")
    flights = make_flights({"KATL": times})
    return flights.assign(dep_delay_min=delays, cancelled=cancelled)


def group_fit(flights: pd.DataFrame, target: str = SEVERE) -> pd.Series:
    rows = training_rows(*build(flights), target)
    return fit_rates(rows)["group"].iloc[0]


def test_probabilities_lie_in_unit_interval(fixture_tables):
    predictions, _ = run_baselines(*fixture_tables)
    usable = predictions[predictions["status"].ne("unavailable")]
    assert len(usable) == len(predictions)
    assert usable["estimate"].between(0, 1).all()
    assert set(predictions["model_version"]) == {CONDITIONAL_RATE, LOGISTIC}
    assert set(predictions["target_kind"]) == set(TARGETS)


def test_cancelled_flights_leave_the_severe_denominator():
    flights = one_group([60, 60, 0, 0, 200, 200], [False] * 4 + [True] * 2)
    severe = group_fit(flights)
    assert (severe["size"], severe["sum"]) == (4, 2)
    cancel = group_fit(flights, CANCELLATION)
    assert (cancel["size"], cancel["sum"]) == (6, 2)


def test_delay_of_exactly_45_is_negative():
    severe = group_fit(one_group([45, 45, 46], [False] * 3))
    assert (severe["size"], severe["sum"]) == (3, 1)


def test_dev_period_outcomes_do_not_move_the_fit(fixture_tables):
    requests, labels = fixture_tables
    before, summary = run_baselines(requests, labels)
    dev = scored_requests(requests)["prediction_id"]
    flipped = labels.copy()
    hit = flipped["prediction_id"].isin(dev) & flipped["eligible"]
    flipped.loc[hit, "y_true"] = 1 - flipped.loc[hit, "y_true"]
    after, summary_after = run_baselines(requests, flipped)
    pd.testing.assert_series_equal(before["estimate"], after["estimate"])
    assert summary == summary_after


def test_unseen_group_and_unknown_airport_fall_back_with_reason():
    train = pd.date_range("2023-01-01 15:00", "2023-12-31", freq="D", tz="UTC")
    flights = pd.concat(
        [
            make_flights({"KATL": train}),
            make_flights(
                {
                    "KATL": [pd.Timestamp("2024-03-01 08:00", tz="UTC")],
                    "KXXX": [pd.Timestamp("2024-03-01 15:00", tz="UTC")],
                }
            ),
        ],
        ignore_index=True,
    )
    requests, labels = build(flights)
    predictions, summary = run_baselines(requests, labels)
    rate = predictions[predictions["model_version"].eq(CONDITIONAL_RATE)]
    unseen = rate[rate["airport_icao"].eq("KATL")]
    assert unseen["status"].eq("degraded").all()
    assert unseen["reason_codes"].map(lambda r: "unseen_group_airport_rate" in r).all()
    for target, rows in unseen.groupby("target_kind"):
        assert rows["estimate"].eq(summary[target]["airport_rate"]["KATL"]).all()
    unknown = predictions[predictions["airport_icao"].eq("KXXX")]
    assert unknown["status"].eq("unavailable").all()
    assert unknown["estimate"].isna().all()
    assert unknown["reason_codes"].map(lambda r: "airport_not_configured" in r).all()


def test_rare_group_falls_back_to_airport_rate(fixture_tables):
    predictions, _ = run_baselines(*fixture_tables)
    rate = predictions[predictions["model_version"].eq(CONDITIONAL_RATE)]
    rare = rate["reason_codes"].map(lambda r: "rare_group_airport_rate" in r)
    full = rate["reason_codes"].map(len).eq(1)
    assert MIN_GROUP_N > 0 and full.any()
    assert rate.loc[rare | ~full, "status"].eq("degraded").all()


def test_every_in_scope_request_gets_one_row_per_model_and_target(fixture_tables):
    requests, labels = fixture_tables
    predictions, _ = run_baselines(requests, labels)
    wanted = requests[
        requests["target_start_utc"].ge(pd.Timestamp("2024-01-01", tz="UTC"))
        & requests["as_of_utc"].ge(pd.Timestamp("2024-01-01", tz="UTC"))
    ]
    assert len(predictions) == 4 * len(wanted)
    for _, rows in predictions.groupby(["model_version", "target_kind"]):
        assert set(rows["prediction_id"]) == set(wanted["prediction_id"])
    assert predictions["as_of_utc"].min() >= pd.Timestamp("2024-01-01", tz="UTC")


def test_calendar_uses_airport_local_time():
    requests = pd.DataFrame(
        {
            "airport_icao": ["KATL", "KDFW"],
            "target_start_utc": pd.to_datetime(["2024-07-01 15:00"] * 2, utc=True),
        }
    )
    assert calendar(requests)["local_hour"].tolist() == [11, 10]


@pytest.fixture
def clean_git(monkeypatch):
    for module in (baselines, evaluate, flight_baselines):
        monkeypatch.setattr(module, "git", lambda *args: "")
    monkeypatch.setattr(flight_baselines, "source_dirty", lambda: False)


def test_end_to_end_with_evaluator(tmp_path, clean_git, fixture_tables):
    requests, labels = fixture_tables
    requests_path = tmp_path / "prediction_requests.parquet"
    labels_path = tmp_path / "labels.parquet"
    requests.to_parquet(requests_path)
    requests_path.with_suffix(".manifest.json").write_text(
        json.dumps({"source_flights_sha256": "fixture-0"})
    )
    labels.to_parquet(labels_path)
    artifacts = tmp_path / "artifacts"
    path = flight_baselines.main(requests_path, labels_path, artifacts)
    manifest = json.loads(path.with_name("manifest.json").read_text())
    assert manifest["fit_cutoff_utc"] == "2024-01-01T00:00:00+00:00"
    assert manifest["data_mode"] == "fixture"
    candidate = pd.read_parquet(path)
    candidate = candidate[candidate["model_version"].eq(LOGISTIC)].assign(
        model_version="dummy_v1"
    )
    baselines.write_predictions(candidate, artifacts / "dummy" / "predictions.parquet")
    (artifacts / "dummy" / "manifest.json").write_text(
        json.dumps({**manifest, "run_id": "dummy"})
    )
    report_path = evaluate.main(
        [flight_baselines.RUN_ID, "dummy"],
        labels_path,
        requests_path,
        artifacts,
        tmp_path / "reports",
        tmp_path / "ledger",
    )
    report = json.loads(report_path.read_text())
    assert {CONDITIONAL_RATE, LOGISTIC, "dummy_v1"} <= set(report["model_ids"])
    assert {m["target"] for m in report["metrics"]} >= set(TARGETS)
