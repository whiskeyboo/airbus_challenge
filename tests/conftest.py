import numpy as np
import pandas as pd
import pytest

FIXTURE_AIRPORTS = {
    "KATL": ("America/New_York", 100),
    "KDFW": ("America/Chicago", 80),
}


def make_hourly(start="2022-12-29", end="2025-08-01", seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    hours = pd.date_range(start, end, freq="h", tz="UTC", inclusive="left")
    frames = []
    for icao, (timezone, peak) in FIXTURE_AIRPORTS.items():
        local = hours.tz_convert(timezone)
        daily = np.clip(np.sin(np.pi * (local.hour - 5) / 19), 0.02, None)
        weekly = np.where(local.day_of_week >= 5, 0.85, 1.0)
        scheduled = rng.poisson(peak * daily * weekly)
        frames.append(
            pd.DataFrame(
                {
                    "airport_icao": icao,
                    "source_snapshot_id": "fixture-0",
                    "hour_start_utc": hours,
                    "hour_end_utc": hours + pd.Timedelta(hours=1),
                    "scheduled_arrivals": pd.array(scheduled, dtype="Int32"),
                    "scheduled_departures": pd.array(scheduled, dtype="Int32"),
                    "reporting_carrier_touchdowns": pd.array(
                        rng.binomial(scheduled, 0.95), dtype="Int32"
                    ),
                    "reporting_carrier_takeoffs": pd.array(scheduled, dtype="Int32"),
                    "official_aar": np.nan,
                    "aar_source": None,
                    "aar_aggregation_version": None,
                    "coverage_status": "complete_for_source_scope",
                    "coverage_fraction": 1.0,
                    "schedule_knowledge_basis": "fixture",
                    "data_mode": "fixture",
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def make_requests(icao, targets, horizons=(3, 6, 9, 12)) -> pd.DataFrame:
    grid = pd.MultiIndex.from_product(
        [pd.DatetimeIndex(targets), horizons], names=["target_start_utc", "horizon_h"]
    ).to_frame(index=False)
    return grid.assign(
        prediction_id=lambda d: (
            f"fixture|{icao}|"
            + d["target_start_utc"].astype(str)
            + "|"
            + d["horizon_h"].astype(str)
        ),
        task="throughput",
        airport_icao=icao,
        flight_id=None,
        as_of_utc=lambda d: (
            d["target_start_utc"] - pd.to_timedelta(d["horizon_h"], unit="h")
        ),
        target_end_utc=lambda d: d["target_start_utc"] + pd.Timedelta(hours=1),
        schedule_snapshot_id="fixture-0",
        cohort_version="fixture-v0",
        data_mode="fixture",
    )


@pytest.fixture(scope="session")
def hourly_table() -> pd.DataFrame:
    return make_hourly()


@pytest.fixture
def hourly(hourly_table) -> pd.DataFrame:
    return hourly_table.copy()
