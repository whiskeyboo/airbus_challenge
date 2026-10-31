import numpy as np
import pandas as pd
import pytest
from conftest import make_requests

from airbus_challenge.baselines import TARGET, scored_requests
from airbus_challenge.extra_baselines import (
    RATIO,
    RATIO_UNIT,
    TRANSFER_SCHEDULE,
    fit_transfer_schedule,
    ratio_predictions,
    transfer_predictions,
)

TARGETS = pd.date_range("2024-03-05 12:00", periods=6, freq="h", tz="UTC")


@pytest.fixture
def ratio_hourly(hourly):
    ceiling = hourly.groupby("airport_icao")[TARGET].transform("max").astype("float64")
    return hourly.assign(**{RATIO: hourly[TARGET].astype("float64") / ceiling})


def model(predictions, name):
    return predictions[predictions["model_version"].eq(name)].reset_index(drop=True)


def test_ratio_climatology_is_fitted_on_2023_only(ratio_hourly):
    requests = make_requests("KATL", TARGETS)
    before = model(ratio_predictions(ratio_hourly, requests), "baseline_climatology_v1")
    after_2023 = ratio_hourly["hour_start_utc"].ge(pd.Timestamp("2024-01-01", tz="UTC"))
    ratio_hourly.loc[after_2023, RATIO] = 9.0
    after = model(ratio_predictions(ratio_hourly, requests), "baseline_climatology_v1")
    pd.testing.assert_series_equal(before["estimate"], after["estimate"])
    assert before["target_kind"].eq(RATIO).all() and before["unit"].eq(RATIO_UNIT).all()


@pytest.mark.parametrize("h", [3, 6, 9, 12])
def test_ratio_persistence_reads_hour_starting_target_minus_h_minus_1(ratio_hourly, h):
    ratio_hourly[RATIO] = np.arange(len(ratio_hourly), dtype="float64")
    target = TARGETS[0]
    result = model(
        ratio_predictions(ratio_hourly, make_requests("KATL", [target], [h])),
        "baseline_persistence_v1",
    )
    hour = ratio_hourly["airport_icao"].eq("KATL") & ratio_hourly["hour_start_utc"].eq(
        target - pd.Timedelta(hours=h + 1)
    )
    assert result["estimate"].item() == ratio_hourly.loc[hour, RATIO].item()


def test_transfer_fit_never_uses_held_out_rows(hourly):
    requests = make_requests("KATL", TARGETS)
    fit = fit_transfer_schedule(hourly, "KATL")
    before, _ = transfer_predictions(hourly, requests, "KATL")
    held_out = hourly["airport_icao"].eq("KATL")
    hourly.loc[held_out, TARGET] = 0
    hourly.loc[
        held_out & hourly["hour_start_utc"].dt.year.eq(2023), "scheduled_arrivals"
    ] = 1
    assert fit_transfer_schedule(hourly, "KATL") == fit
    assert fit["source_airports"] == ["KDFW"]
    after, _ = transfer_predictions(hourly, requests, "KATL")
    pd.testing.assert_series_equal(
        model(before, TRANSFER_SCHEDULE)["estimate"],
        model(after, TRANSFER_SCHEDULE)["estimate"],
    )


def test_transfer_scores_only_the_held_out_airport(hourly):
    requests = pd.concat([make_requests(i, TARGETS) for i in ("KATL", "KDFW")])
    predictions, _ = transfer_predictions(hourly, requests, "KDFW")
    assert set(predictions["airport_icao"]) == {"KDFW"}
    assert len(model(predictions, TRANSFER_SCHEDULE)) == len(TARGETS) * 4


def test_no_test_split_rows_are_predicted(ratio_hourly):
    targets = [
        pd.Timestamp("2024-12-31 23:00", tz="UTC"),
        pd.Timestamp("2025-02-01", tz="UTC"),
    ]
    requests = make_requests("KATL", targets).assign(task="throughput")
    scored = scored_requests(ratio_hourly, requests, locked_test=False)
    for predictions in (
        ratio_predictions(ratio_hourly, scored),
        transfer_predictions(ratio_hourly, scored, "KATL")[0],
    ):
        assert predictions["target_start_utc"].max() < pd.Timestamp(
            "2025-01-01", tz="UTC"
        )
        assert len(predictions)
