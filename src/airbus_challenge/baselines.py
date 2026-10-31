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
# Tracked in git: a claim outlives a crash and reaches other worktrees once pushed.
LOCKED_LEDGER = Path("reports/locked_runs")

TARGET = EXPERIMENT["targets"]["throughput"]
TARGET_LABEL = "arrival throughput (AAR proxy)"
TASK = "throughput"
UNIT = "touchdowns/hour"
VERSION = "baseline-v1"
SCHEMA_VERSION = "0.1.0"
HOUR = pd.Timedelta(hours=1)
WEEK = pd.Timedelta(days=7)
# A thinner airport x local hour x weekday cell is unavailable: no fallback is
# validated yet (WP-D7), so none is served as degraded.
MIN_CELL_N = 8
KEYS = ["airport_icao", "hour_start_utc"]
# Outcome-free, so a bad locked run is refused before it is claimed.
CONTEXT_COLUMNS = [*KEYS, "source_snapshot_id", "data_mode", "schedule_knowledge_basis"]
OUTCOME_COLUMNS = [*KEYS, TARGET, "coverage_status", "scheduled_arrivals"]

# BTS publishes months later, so no live feed existed.
SIMULATED_FEED = "simulated_feed"
# BTS holds the schedule as flown.
RETROSPECTIVE_SCHEDULE = "retrospective_schedule"

# Persistence assumes the last complete hour is known at T, which flatters it.
FEED_LATENCY_H = 0
SOURCE_PATHS = ("src", "configs", "pyproject.toml", "uv.lock")

DATA_MODES = {"real", "fixture"}
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
    # P12: a partial hour with a target is valid, and these cluster in bad weather.
    return hourly[hourly["coverage_status"].ne("missing") & hourly[TARGET].notna()]


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
    keys = pd.MultiIndex.from_arrays([requests["airport_icao"], source_hour])
    source = observed(hourly).set_index(KEYS)[[TARGET, "coverage_status"]].reindex(keys)
    estimate = source[TARGET].astype("float64").to_numpy()
    found = ~np.isnan(estimate)
    # P12: a partial hour has unresolved arrivals, so its count may be low.
    partial = source["coverage_status"].eq("partial").to_numpy()
    reasons = [
        [SIMULATED_FEED]
        + ([] if ok else ["source_hour_incomplete"])
        + (["source_hour_partial"] if low else [])
        for ok, low in zip(found, partial)
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


CELL = ["airport_icao", "local_hour", "local_weekday"]


def fit_climatology(train: pd.DataFrame) -> pd.DataFrame:
    rows = pd.concat([train, _local_time(train, "hour_start_utc")], axis=1)
    rows[TARGET] = rows[TARGET].astype("float64")
    return rows.groupby(CELL)[TARGET].agg(["mean", "size"])


def climatology(requests: pd.DataFrame, fit: pd.DataFrame) -> pd.DataFrame:
    keys = _local_time(requests, "target_start_utc").assign(
        airport_icao=requests["airport_icao"]
    )
    cells = fit.reindex(pd.MultiIndex.from_frame(keys[CELL]))
    estimate = cells["mean"].where(cells["size"].ge(MIN_CELL_N)).to_numpy()
    seen = requests["airport_icao"].isin(fit.index.get_level_values("airport_icao"))
    reasons = [
        [] if ok else ["climatology_cell_sparse"] if in_train else ["no_train_history"]
        for ok, in_train in zip(~np.isnan(estimate), seen)
    ]
    status = np.where(np.isnan(estimate), "unavailable", "available")
    return _predictions(requests, "baseline_climatology_v1", estimate, status, reasons)


def _schedule_line(rows: pd.DataFrame) -> dict[str, float]:
    slope, intercept = np.polyfit(
        rows["scheduled_arrivals"].astype("float64"), rows[TARGET].astype("float64"), 1
    )
    return {"slope": float(slope), "intercept": float(intercept), "n_train": len(rows)}


def fit_schedule(train: pd.DataFrame) -> dict:
    rows = train[train["scheduled_arrivals"].notna()]
    return {
        "airports": {
            icao: _schedule_line(g) for icao, g in rows.groupby("airport_icao")
        }
    }


def schedule_only(
    requests: pd.DataFrame, hourly: pd.DataFrame, fit: dict
) -> pd.DataFrame:
    schedule = hourly.set_index(KEYS)["scheduled_arrivals"]
    keys = pd.MultiIndex.from_arrays(
        [requests["airport_icao"], requests["target_start_utc"]]
    )
    scheduled = schedule.astype("float64").reindex(keys).to_numpy()
    # A held-out airport has no line; a pooled one is unvalidated (WP-D7).
    lines = pd.DataFrame(fit["airports"]).T.reindex(requests["airport_icao"])
    estimate = np.clip(
        lines["intercept"].to_numpy() + lines["slope"].to_numpy() * scheduled, 0, None
    )
    has_schedule = ~np.isnan(scheduled)
    seen = requests["airport_icao"].isin(fit["airports"]).to_numpy()
    reasons = [
        [RETROSPECTIVE_SCHEDULE]
        + ([] if ok else ["schedule_missing"])
        + ([] if in_train else ["airport_not_in_train"])
        for ok, in_train in zip(has_schedule, seen)
    ]
    status = np.where(np.isnan(estimate), "unavailable", "available")
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
    hours = hourly["hour_start_utc"]
    if hours.ne(hours.dt.floor("h")).any():
        raise ValueError("hour grid must start on the hour")
    span = hourly.groupby("airport_icao")["hour_start_utc"].agg(["min", "max", "size"])
    gaps = span[(span["max"] - span["min"]) / HOUR + 1 != span["size"]]
    if len(gaps):
        raise ValueError(f"hour grid has gaps for {gaps.index.tolist()}")
    short = span[span["min"].gt(start) | span["max"].lt(end - HOUR)]
    if len(short):
        raise ValueError(
            f"hour grid must span {start} to {end} for {short.index.tolist()}"
        )
    if requests["prediction_id"].duplicated().any():
        raise ValueError("duplicate prediction_id in requests")
    horizon = (requests["target_start_utc"] - requests["as_of_utc"]) / HOUR
    wrong = requests[horizon != requests["horizon_h"]]
    if len(wrong):
        raise ValueError(
            f"horizon_h != target - as_of for {wrong['prediction_id'].iloc[0]}"
        )
    wrong = requests[~requests["horizon_h"].isin(EXPERIMENT["horizons_h"])]
    if len(wrong):
        raise ValueError(
            f"horizon_h outside {EXPERIMENT['horizons_h']} "
            f"for {wrong['prediction_id'].iloc[0]}"
        )
    airport = requests[requests["task"].eq(TASK)]
    target = airport["target_start_utc"]
    wrong = airport[
        target.ne(target.dt.floor("h")) | airport["target_end_utc"].ne(target + HOUR)
    ]
    if len(wrong):
        raise ValueError(
            f"target is not one whole UTC hour for {wrong['prediction_id'].iloc[0]}"
        )
    unknown = set(airport["airport_icao"]) - set(hourly["airport_icao"])
    if unknown:
        raise ValueError(f"requests for airports without an hour grid: {unknown}")


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


def scored_requests(
    hourly: pd.DataFrame, requests: pd.DataFrame, locked_test: bool
) -> pd.DataFrame:
    splits = ["test"] if locked_test else ["validation", "calibration"]
    check_inputs(
        hourly, requests, split_bounds("train")[0], split_bounds(splits[-1])[1]
    )
    airport_requests = requests[requests["task"].eq(TASK)]
    scored = pd.concat(
        [in_split(airport_requests, s, "target_start_utc") for s in splits]
    )
    # At the start of validation, T can precede the fit cutoff the fits rely on.
    scored = scored[scored["as_of_utc"].ge(split_bounds("train")[1])]
    if scored.empty:
        raise ValueError(f"no {TASK} requests in {splits}")
    return scored


def baseline_predictions(
    hourly: pd.DataFrame, requests: pd.DataFrame, locked_test: bool = False
) -> tuple[pd.DataFrame, dict]:
    return predict_scored(hourly, scored_requests(hourly, requests, locked_test))


def predict_scored(
    hourly: pd.DataFrame, scored: pd.DataFrame
) -> tuple[pd.DataFrame, dict]:
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


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def source_dirty() -> bool:
    return bool(git("status", "--porcelain", "--", *SOURCE_PATHS))


def claim_locked_run(
    name: str,
    approved_by: str,
    commit: str,
    ledger: Path = LOCKED_LEDGER,
    predictions_sha256: str | None = None,
) -> None:
    ledger.mkdir(parents=True, exist_ok=True)
    if predictions_sha256:
        for path in sorted(ledger.glob("*.json")):
            if json.loads(path.read_text()).get("predictions_sha256") == (
                predictions_sha256
            ):
                raise FileExistsError(
                    f"these predictions were claimed as {path.stem}; "
                    "the locked test runs once"
                )
    claim = {
        "run": name,
        "approved_by": approved_by,
        "commit": commit,
        "predictions_sha256": predictions_sha256,
        "claimed_at_utc": datetime.now(UTC).isoformat(),
    }
    try:
        with open(ledger / f"{name}.json", "x") as file:
            json.dump(claim, file, indent=2)
    except FileExistsError as error:
        raise FileExistsError(
            f"{name} was claimed in {ledger}; the locked test runs once"
        ) from error


def main(
    hourly_path: Path = HOURLY,
    requests_path: Path = REQUESTS,
    artifacts: Path = ARTIFACTS,
    locked_test: bool = False,
    approved_by: str | None = None,
    ledger: Path = LOCKED_LEDGER,
) -> Path:
    run_id = "baselines_locked_test" if locked_test else "baselines_dev"
    path = artifacts / run_id / "predictions.parquet"
    commit, commit_dirty = git("rev-parse", "HEAD"), source_dirty()
    if locked_test and not approved_by:
        raise ValueError("locked test needs approved_by, after the model is frozen")
    if locked_test and commit_dirty:
        raise ValueError(f"locked test needs {SOURCE_PATHS} committed")
    # Hashed before the read, because worktrees share data/.
    hourly_sha256, requests_sha256 = sha256(hourly_path), sha256(requests_path)
    if "data_mode" not in pq.read_schema(hourly_path).names:
        raise ValueError("airport_hourly needs a data_mode column of real or fixture")
    test_start, _ = split_bounds("test")
    # Dev runs never load 2025 outcomes (docs/WORK_PLAN.md test-set rule).
    filters = None if locked_test else [("hour_start_utc", "<", test_start)]
    context = pd.read_parquet(hourly_path, columns=CONTEXT_COLUMNS, filters=filters)
    requests = pd.read_parquet(requests_path)
    snapshots = context["source_snapshot_id"].unique()
    if len(snapshots) != 1:
        raise ValueError(f"expected one airport_hourly snapshot, found {snapshots}")
    modes = set(context["data_mode"]) | set(requests["data_mode"])
    if len(modes) != 1:
        raise ValueError(f"mixed data_mode {sorted(modes)}")
    data_mode = modes.pop()
    if data_mode not in DATA_MODES:
        raise ValueError(f"data_mode {data_mode} outside {DATA_MODES}")
    if locked_test and data_mode != "real":
        raise ValueError(f"locked test needs real data, got {data_mode}")
    schedule_bases = context["schedule_knowledge_basis"].unique()
    if len(schedule_bases) != 1 or pd.isna(schedule_bases[0]):
        raise ValueError(f"expected one schedule basis, found {schedule_bases}")
    scored = scored_requests(context, requests, locked_test)
    if locked_test:
        claim_locked_run(run_id, approved_by, commit, ledger)
    outcomes = pd.read_parquet(hourly_path, columns=OUTCOME_COLUMNS, filters=filters)
    hourly = context.merge(outcomes, on=KEYS, validate="one_to_one")
    predictions, schedule_fit = predict_scored(hourly, scored)
    predictions = predictions.assign(
        data_snapshot_id=str(snapshots[0]), generated_at_utc=datetime.now(UTC)
    )
    counts = pd.crosstab(predictions["model_version"], predictions["status"])
    codes = predictions[["model_version", "reason_codes"]].explode("reason_codes")
    reason_counts = pd.crosstab(codes["model_version"], codes["reason_codes"]).reindex(
        index=counts.index,
        columns=sorted({*codes["reason_codes"].dropna(), "source_hour_partial"}),
        fill_value=0,
    )
    manifest = {
        "run_id": run_id,
        "producer": "airbus_challenge.baselines",
        "producer_version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "commit": commit,
        "commit_dirty": commit_dirty,
        "approved_by": approved_by,
        "data_mode": data_mode,
        "data_snapshot_id": str(snapshots[0]),
        "target": TARGET,
        "target_label": TARGET_LABEL,
        "airport_hourly_sha256": hourly_sha256,
        "prediction_requests_sha256": requests_sha256,
        "uv_lock_sha256": sha256(Path("uv.lock")),
        "schedule_knowledge_basis": str(schedule_bases[0]),
        "feed_latency_h": FEED_LATENCY_H,
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
        "reason_counts": reason_counts.to_dict("index"),
    }
    write_predictions(predictions, path)
    part = path.with_name("manifest.json.part")
    part.write_text(json.dumps(manifest, indent=2, default=int))
    part.replace(path.with_name("manifest.json"))
    print(path, f"data_mode={data_mode}")
    print(counts)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--locked-test", action="store_true")
    parser.add_argument("--approved-by")
    args = parser.parse_args()
    main(locked_test=args.locked_test, approved_by=args.approved_by)
