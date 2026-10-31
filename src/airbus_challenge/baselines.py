import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from airbus_challenge.download import sha256

AIRPORTS = yaml.safe_load(Path("configs/airports.yaml").read_text())["airports"]
EXPERIMENT = yaml.safe_load(Path("configs/experiment.yaml").read_text())
HOURLY = Path("data/processed/airport_hourly.parquet")
REQUESTS = Path("data/processed/prediction_requests.parquet")
ARTIFACTS = Path("artifacts")

TARGET = EXPERIMENT["targets"]["throughput"]
TASK = "airport_throughput"
UNIT = "touchdowns/hour"
VERSION = "baseline-v1"
SCHEMA_VERSION = "0.1.0"
COMPLETE = "complete_for_source_scope"
HOUR = pd.Timedelta(hours=1)
WEEK = pd.Timedelta(days=7)
# A thinner airport x local hour x weekday cell uses airport x local hour.
MIN_CELL_N = 8

# BTS publishes months later, so no live feed existed.
SIMULATED_FEED = "simulated_feed"
# BTS holds the schedule as flown.
RETROSPECTIVE_SCHEDULE = "retrospective_schedule"

STATUSES = {"available", "degraded", "unavailable"}
REQUEST_COLUMNS = [
    "prediction_id",
    "task",
    "airport_icao",
    "flight_id",
    "as_of_utc",
    "target_start_utc",
    "target_end_utc",
    "horizon_h",
    "schedule_snapshot_id",
    "cohort_version",
    "data_mode",
]
UTC_US = pa.timestamp("us", tz="UTC")
PREDICTION_SCHEMA = pa.schema(
    [
        ("prediction_id", pa.string()),
        ("task", pa.string()),
        ("airport_icao", pa.string()),
        ("flight_id", pa.string()),
        ("as_of_utc", UTC_US),
        ("target_start_utc", UTC_US),
        ("target_end_utc", UTC_US),
        ("horizon_h", pa.int32()),
        ("schedule_snapshot_id", pa.string()),
        ("cohort_version", pa.string()),
        ("data_mode", pa.string()),
        ("target_kind", pa.string()),
        ("estimate", pa.float64()),
        ("p10", pa.float64()),
        ("p90", pa.float64()),
        ("unit", pa.string()),
        ("status", pa.string()),
        ("reason_codes", pa.list_(pa.string())),
        ("model_version", pa.string()),
        ("feature_version", pa.string()),
        ("data_snapshot_id", pa.string()),
        ("generated_at_utc", UTC_US),
    ]
)


def split_bounds(name: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    bounds = EXPERIMENT["splits"][name]
    return pd.Timestamp(bounds["start"], tz="UTC"), pd.Timestamp(
        bounds["end"], tz="UTC"
    )


def in_split(df: pd.DataFrame, name: str, column: str) -> pd.DataFrame:
    start, end = split_bounds(name)
    return df[df[column].ge(start) & df[column].lt(end)]


def observed(hourly: pd.DataFrame) -> pd.DataFrame:
    return hourly[hourly["coverage_status"].eq(COMPLETE) & hourly[TARGET].notna()]


def _local_time(df: pd.DataFrame, column: str) -> pd.DataFrame:
    local = df.groupby("airport_icao")[column].transform(
        lambda s: s.dt.tz_convert(AIRPORTS[s.name]["timezone"]).dt.tz_localize(None)
    )
    return pd.DataFrame(
        {"local_hour": local.dt.hour, "local_weekday": local.dt.day_of_week},
        index=df.index,
    )


def _predictions(
    requests: pd.DataFrame, model: str, estimate, status, reasons: list[list[str]]
) -> pd.DataFrame:
    return requests[REQUEST_COLUMNS].assign(
        target_kind=TARGET,
        estimate=estimate,
        p10=np.nan,
        p90=np.nan,
        unit=UNIT,
        status=status,
        reason_codes=reasons,
        model_version=model,
        feature_version=VERSION,
    )


def _from_feed(
    requests: pd.DataFrame, hourly: pd.DataFrame, source_hour: pd.Series, model: str
) -> pd.DataFrame:
    if (source_hour + HOUR > requests["as_of_utc"]).any():
        raise ValueError(f"{model}: source hour ends after issue time")
    values = observed(hourly).set_index(["airport_icao", "hour_start_utc"])[TARGET]
    keys = pd.MultiIndex.from_arrays([requests["airport_icao"], source_hour])
    estimate = values.astype("float64").reindex(keys).to_numpy()
    found = ~np.isnan(estimate)
    reasons = [
        [SIMULATED_FEED] if ok else [SIMULATED_FEED, "source_hour_incomplete"]
        for ok in found
    ]
    status = np.where(found, "available", "unavailable")
    return _predictions(requests, model, estimate, status, reasons)


def persistence(requests: pd.DataFrame, hourly: pd.DataFrame) -> pd.DataFrame:
    source_hour = requests["as_of_utc"] - HOUR
    return _from_feed(requests, hourly, source_hour, "baseline_persistence_v1")


def _week_earlier(requests: pd.DataFrame) -> pd.Series:
    def shift(target: pd.Series) -> pd.Series:
        zone = AIRPORTS[target.name]["timezone"]
        wall_clock = target.dt.tz_convert(zone).dt.tz_localize(None) - WEEK
        # A repeated clock hour takes its first occurrence; a skipped one moves forward.
        local = wall_clock.dt.tz_localize(
            zone, ambiguous=np.ones(len(target), bool), nonexistent="shift_forward"
        )
        return local.dt.tz_convert("UTC")

    return requests.groupby("airport_icao")["target_start_utc"].transform(shift)


def seasonal_persistence(requests: pd.DataFrame, hourly: pd.DataFrame) -> pd.DataFrame:
    source_hour = _week_earlier(requests)
    return _from_feed(requests, hourly, source_hour, "baseline_seasonal_persistence_v1")


def fit_climatology(train: pd.DataFrame) -> dict[str, pd.Series]:
    rows = pd.concat([train, _local_time(train, "hour_start_utc")], axis=1)
    rows[TARGET] = rows[TARGET].astype("float64")
    cells = rows.groupby(["airport_icao", "local_hour", "local_weekday"])[TARGET]
    means = cells.mean()
    return {
        "cell": means[cells.size() >= MIN_CELL_N],
        "hour": rows.groupby(["airport_icao", "local_hour"])[TARGET].mean(),
    }


def climatology(requests: pd.DataFrame, fit: dict[str, pd.Series]) -> pd.DataFrame:
    keys = _local_time(requests, "target_start_utc").assign(
        airport_icao=requests["airport_icao"]
    )
    cell_keys = pd.MultiIndex.from_frame(
        keys[["airport_icao", "local_hour", "local_weekday"]]
    )
    hour_keys = pd.MultiIndex.from_frame(keys[["airport_icao", "local_hour"]])
    cell = fit["cell"].reindex(cell_keys).to_numpy()
    estimate = np.where(np.isnan(cell), fit["hour"].reindex(hour_keys).to_numpy(), cell)
    fallback = np.isnan(cell) & ~np.isnan(estimate)
    status = np.select(
        [np.isnan(estimate), fallback], ["unavailable", "degraded"], "available"
    )
    reason_by_status = {
        "unavailable": ["no_train_history"],
        "degraded": ["climatology_hour_fallback"],
        "available": [],
    }
    reasons = [reason_by_status[s] for s in status]
    return _predictions(requests, "baseline_climatology_v1", estimate, status, reasons)


def _schedule_line(rows: pd.DataFrame) -> dict[str, float]:
    slope, intercept = np.polyfit(
        rows["scheduled_arrivals"].astype("float64"), rows[TARGET].astype("float64"), 1
    )
    return {"slope": float(slope), "intercept": float(intercept), "n_train": len(rows)}


def fit_schedule(train: pd.DataFrame) -> dict:
    rows = train[train["scheduled_arrivals"].notna()]
    airports = {icao: _schedule_line(g) for icao, g in rows.groupby("airport_icao")}
    return {"airports": airports, "pooled": _schedule_line(rows)}


def schedule_only(
    requests: pd.DataFrame, hourly: pd.DataFrame, fit: dict
) -> pd.DataFrame:
    schedule = hourly.set_index(["airport_icao", "hour_start_utc"])[
        "scheduled_arrivals"
    ]
    keys = pd.MultiIndex.from_arrays(
        [requests["airport_icao"], requests["target_start_utc"]]
    )
    scheduled = schedule.astype("float64").reindex(keys).to_numpy()
    # An airport held out of train has no fit of its own, so it gets the pooled line.
    lines = [
        fit["airports"].get(icao, fit["pooled"]) for icao in requests["airport_icao"]
    ]
    slope = np.array([line["slope"] for line in lines])
    intercept = np.array([line["intercept"] for line in lines])
    estimate = np.clip(intercept + slope * scheduled, 0, None)
    found = ~np.isnan(estimate)
    seen = requests["airport_icao"].isin(fit["airports"]).to_numpy()
    reasons = [
        [RETROSPECTIVE_SCHEDULE]
        + ([] if ok else ["schedule_missing"])
        + ([] if in_train else ["airport_not_in_train"])
        for ok, in_train in zip(found, seen)
    ]
    status = np.select([~found, ~seen], ["unavailable", "degraded"], "available")
    return _predictions(requests, "baseline_schedule_v1", estimate, status, reasons)


def check_inputs(
    hourly: pd.DataFrame,
    requests: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> None:
    duplicate = hourly.duplicated(["airport_icao", "hour_start_utc"])
    if duplicate.any():
        row = hourly[duplicate].iloc[0]
        raise ValueError(
            f"duplicate airport hour {row['airport_icao']} {row['hour_start_utc']}"
        )
    span = hourly.groupby("airport_icao")["hour_start_utc"].agg(["min", "max", "size"])
    gaps = span[(span["max"] - span["min"]) / HOUR + 1 != span["size"]]
    if len(gaps):
        raise ValueError(f"hour grid has gaps for {gaps.index.tolist()}")
    short = span[span["min"].gt(start) | span["max"].lt(end - HOUR)]
    if len(short):
        raise ValueError(
            f"hour grid must span {start} to {end} for {short.index.tolist()}"
        )
    horizon = (requests["target_start_utc"] - requests["as_of_utc"]) / HOUR
    wrong = requests[horizon != requests["horizon_h"]]
    if len(wrong):
        raise ValueError(
            f"horizon_h != target - as_of for {wrong['prediction_id'].iloc[0]}"
        )


def check_predictions(predictions: pd.DataFrame) -> None:
    key = ["prediction_id", "target_kind", "model_version"]
    if predictions.duplicated(key).any():
        raise ValueError(f"duplicate prediction key {key}")
    if not set(predictions["status"]) <= STATUSES:
        raise ValueError(f"status outside {STATUSES}")
    unavailable = predictions["status"].eq("unavailable")
    if not unavailable.eq(predictions["estimate"].isna()).all():
        raise ValueError("estimate must be null exactly when status is unavailable")
    if not predictions.loc[unavailable, "reason_codes"].map(len).all():
        raise ValueError("unavailable prediction without a reason")


def baseline_predictions(
    hourly: pd.DataFrame, requests: pd.DataFrame, locked_test: bool = False
) -> tuple[pd.DataFrame, dict]:
    splits = ["test"] if locked_test else ["validation", "calibration"]
    check_inputs(
        hourly, requests, split_bounds("train")[0], split_bounds(splits[-1])[1]
    )
    airport_requests = requests[requests["task"].eq(TASK)]
    scored = pd.concat(
        [in_split(airport_requests, s, "target_start_utc") for s in splits]
    )
    if scored.empty:
        raise ValueError(f"no {TASK} requests in {splits}")
    train = observed(in_split(hourly, "train", "hour_start_utc"))
    schedule_fit = fit_schedule(train)
    return pd.concat(
        [
            persistence(scored, hourly),
            seasonal_persistence(scored, hourly),
            climatology(scored, fit_climatology(train)),
            schedule_only(scored, hourly, schedule_fit),
        ],
        ignore_index=True,
    ), schedule_fit


def write_predictions(predictions: pd.DataFrame, path: Path) -> None:
    check_predictions(predictions)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".parquet.part")
    table = pa.Table.from_pandas(
        predictions, schema=PREDICTION_SCHEMA, preserve_index=False
    )
    pq.write_table(table, part)
    part.replace(path)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def main(
    hourly_path: Path = HOURLY,
    requests_path: Path = REQUESTS,
    artifacts: Path = ARTIFACTS,
    locked_test: bool = False,
) -> Path:
    run_id = "baselines_locked_test" if locked_test else "baselines_dev"
    path = artifacts / run_id / "predictions.parquet"
    if locked_test and path.exists():
        raise FileExistsError(f"{path} exists; the locked test runs once")
    commit_dirty = bool(_git("status", "--porcelain", "--", "src", "configs"))
    if locked_test and commit_dirty:
        raise ValueError("locked test needs src and configs committed")
    test_start, _ = split_bounds("test")
    # Dev runs never load 2025 outcomes (docs/WORK_PLAN.md test-set rule).
    filters = None if locked_test else [("hour_start_utc", "<", test_start)]
    hourly = pd.read_parquet(hourly_path, filters=filters)
    requests = pd.read_parquet(requests_path)
    snapshots = hourly["source_snapshot_id"].unique()
    if len(snapshots) != 1:
        raise ValueError(f"expected one airport_hourly snapshot, found {snapshots}")
    if "data_mode" not in hourly:
        raise ValueError("airport_hourly needs a data_mode column of real or fixture")
    modes = set(hourly["data_mode"]) | set(requests["data_mode"])
    if len(modes) != 1:
        raise ValueError(f"mixed data_mode {sorted(modes)}")
    data_mode = modes.pop()
    if locked_test and data_mode != "real":
        raise ValueError(f"locked test needs real data, got {data_mode}")
    predictions, schedule_fit = baseline_predictions(hourly, requests, locked_test)
    predictions = predictions.assign(
        data_snapshot_id=str(snapshots[0]), generated_at_utc=datetime.now(UTC)
    )
    counts = pd.crosstab(predictions["model_version"], predictions["status"])
    manifest = {
        "run_id": run_id,
        "producer": "airbus_challenge.baselines",
        "producer_version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "commit": _git("rev-parse", "HEAD"),
        "commit_dirty": commit_dirty,
        "data_mode": data_mode,
        "data_snapshot_id": str(snapshots[0]),
        "airport_hourly_sha256": sha256(hourly_path),
        "prediction_requests_sha256": sha256(requests_path),
        "fit_split": EXPERIMENT["splits"]["train"],
        "fit_cutoff_utc": split_bounds("train")[1].isoformat(),
        "fit_availability": "simulated: train outcomes are treated as known at the "
        "cutoff, though BTS publishes months later",
        "schedule_fit": schedule_fit,
        "min_cell_n": MIN_CELL_N,
        "target_start_min_utc": predictions["target_start_utc"].min().isoformat(),
        "target_start_max_utc": predictions["target_start_utc"].max().isoformat(),
        "rows": len(predictions),
        "status_counts": counts.to_dict("index"),
    }
    manifest_text = json.dumps(manifest, indent=2, default=int)
    write_predictions(predictions, path)
    path.with_name("manifest.json").write_text(manifest_text)
    print(path, f"data_mode={data_mode}")
    print(counts)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--locked-test", action="store_true")
    main(locked_test=parser.parse_args().locked_test)
