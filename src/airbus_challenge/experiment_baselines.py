"""Development baselines fitted on the declared CSV or source-airport cohort."""

import collections
import json
import resource
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from airbus_challenge import baselines, extra_baselines, flight_baselines
from airbus_challenge.download import sha256

TRAIN_COLUMNS = [
    *baselines.REQUEST_COLUMNS,
    "target_kind", "y_true", "eligible", "outcome_available_at_utc",
]


def training_rows(labels: pd.DataFrame, target: str, source_airports: list[str]):
    """One eligible source-cohort training outcome per flight, released by cutoff."""
    lo, hi = baselines.split_bounds("train")
    rows = labels.loc[
        labels["target_kind"].eq(target)
        & labels["eligible"].fillna(False)
        & labels["airport_icao"].isin(source_airports)
        & labels["target_start_utc"].ge(lo)
        & labels["target_start_utc"].lt(hi)
        & labels["outcome_available_at_utc"].le(hi)
    ].sort_values("horizon_h").drop_duplicates("flight_id")
    return pd.concat(
        [flight_baselines.calendar(rows), rows["y_true"].rename("y")], axis=1
    ).dropna()


def flight_predictions(scored, training, source_airports):
    """Yield each binary target and comparator separately to bound memory."""
    keys = flight_baselines.calendar(scored)
    for target in flight_baselines.TARGETS:
        rows = training_rows(training, target, source_airports)
        if rows.empty:
            raise ValueError(f"no eligible source training rows for {target}")
        rates = flight_baselines.fit_rates(rows)
        yield flight_baselines._predictions(
            scored, target, flight_baselines.CONDITIONAL_RATE,
            *flight_baselines.conditional_rate(scored, keys, rates),
        )
        if rows["y"].nunique() < 2:
            yield flight_baselines._predictions(
                scored, target, flight_baselines.LOGISTIC,
                np.full(len(scored), np.nan),
                [["source_training_has_one_class"] for _ in range(len(scored))],
            )
        else:
            model = flight_baselines.fit_logistic(rows)
            yield flight_baselines._predictions(
                scored, target, flight_baselines.LOGISTIC,
                *flight_baselines.logistic(scored, keys, model, set(source_airports)),
            )



def source_hours(hourly, training, source_airports):
    lo, hi = baselines.split_bounds("train")
    available = training.loc[
        training["target_kind"].eq(baselines.TARGET)
        & training["eligible"].fillna(False)
        & training["airport_icao"].isin(source_airports)
        & training["target_start_utc"].ge(lo)
        & training["target_start_utc"].lt(hi)
        & training["outcome_available_at_utc"].le(hi),
        ["airport_icao", "target_start_utc"],
    ].drop_duplicates().rename(columns={"target_start_utc": "hour_start_utc"})
    return hourly.merge(available, on=baselines.KEYS, how="inner", validate="one_to_one")


def throughput_predictions(hourly, scored, training, source_airports, held_out=None):
    fit_rows = baselines.observed(source_hours(hourly, training, source_airports))
    if held_out:
        line = extra_baselines.fit_transfer_schedule(fit_rows, held_out)
        applied = {"airports": {held_out: {k: line[k] for k in ("slope", "intercept")}}}
        schedule = baselines.schedule_only(scored, hourly, applied).assign(
            model_version=extra_baselines.TRANSFER_SCHEDULE
        )
        return pd.concat([
            schedule, baselines.persistence(scored, hourly)
        ], ignore_index=True), line
    return pd.concat([
        baselines.persistence(scored, hourly),
        baselines.seasonal_persistence(scored, hourly),
        baselines.climatology(scored, baselines.fit_climatology(fit_rows)),
        baselines.schedule_only(scored, hourly, baselines.fit_schedule(fit_rows)),
    ], ignore_index=True), None


def run(
    cohort: str,
    processed: Path,
    labels_path: Path,
    training_labels_path: Path,
    artifacts: Path = Path("artifacts"),
    tasks: list[str] | None = None,
) -> str:
    started = time.perf_counter()
    processed, labels_path = Path(processed), Path(labels_path)
    training_labels_path, artifacts = Path(training_labels_path), Path(artifacts)
    request_path = processed / "prediction_requests.parquet"
    source = json.loads(request_path.with_suffix(".manifest.json").read_text())
    training_manifest = json.loads(
        training_labels_path.with_suffix(".manifest.json").read_text()
    )
    if "cohorts" in source:
        interface = source["cohorts"][cohort]
    elif source.get("cohort_version") == cohort:
        interface = training_manifest["cohort"]
    else:
        raise ValueError("request manifest does not declare the requested cohort")
    allowed_tasks = set(interface.get("tasks", ["throughput", "severe_delay"]))
    tasks = list(allowed_tasks) if tasks is None else tasks
    if not tasks or not set(tasks) <= allowed_tasks:
        raise ValueError(f"tasks must be a nonempty subset of {sorted(allowed_tasks)}")
    train_airports, score_airports = (
        interface["train_airports"], interface["score_airports"]
    )
    if training_manifest["cohort_version"] != cohort:
        raise ValueError("training-label cohort differs from request cohort")
    if training_manifest["cohort"]["train_airports"] != train_airports:
        raise ValueError("training-label source airports differ from request cohort")
    training_sha = sha256(training_labels_path)
    if training_sha != training_manifest["parquet_sha256"]:
        raise ValueError("training-label hash differs from manifest")
    request_sha = sha256(request_path)
    if request_sha != source["parquet_sha256"]:
        raise ValueError("request hash differs from manifest")
    start = baselines.split_bounds("validation")[0]
    end = baselines.split_bounds("calibration")[1]
    requests = pd.read_parquet(
        request_path, columns=baselines.REQUEST_COLUMNS,
        filters=[
            ("target_start_utc", ">=", start), ("target_start_utc", "<", end),
            ("as_of_utc", ">=", start), ("airport_icao", "in", score_airports),
            ("cohort_version", "==", cohort), ("task", "in", tasks),
        ],
    )
    training = pd.read_parquet(
        training_labels_path, columns=TRAIN_COLUMNS,
        filters=[("task", "in", tasks), ("cohort_version", "==", cohort)],
    )
    modes = set(requests["data_mode"]) | set(training["data_mode"])
    if len(modes) != 1 or not modes <= baselines.DATA_MODES:
        raise ValueError(f"expected one data_mode, got {modes}")
    run_id = f"experiment_baselines_{cohort}"
    output = artifacts / run_id
    output.mkdir(parents=True, exist_ok=True)
    path = output / "predictions.parquet"
    tmp = path.with_suffix(".parquet.part")
    stamp = {
        "data_snapshot_id": source["source_flights_sha256"],
        "generated_at_utc": datetime.now(UTC),
    }
    counts, rows = collections.Counter(), 0
    hourly_path = labels_path.parent / "airport_hourly.parquet"
    if not hourly_path.exists():
        hourly_path = baselines.HOURLY
    hourly_sha, transfer_fit = None, None
    with pq.ParquetWriter(tmp, baselines.PREDICTION_SCHEMA) as writer:
        def write(frame):
            nonlocal rows
            frame = frame.assign(**stamp)
            baselines.check_predictions(frame)
            writer.write_table(pa.Table.from_pandas(
                frame, schema=baselines.PREDICTION_SCHEMA, preserve_index=False
            ))
            rows += len(frame)
            counts.update({
                "|".join(key): int(n) for key, n in frame.groupby(
                    ["model_version", "target_kind", "status"]
                ).size().items()
            })

        throughput = requests[requests["task"].eq("throughput")]
        if not throughput.empty:
            columns = list(dict.fromkeys([
                *baselines.CONTEXT_COLUMNS, *baselines.OUTCOME_COLUMNS,
            ]))
            hourly = pd.read_parquet(
                hourly_path, columns=columns,
                filters=[("hour_start_utc", "<", end)],
            )
            hourly_sha = sha256(hourly_path)
            held_out = interface.get("held_out_airport")
            frame, transfer_fit = throughput_predictions(
                hourly, throughput, training, train_airports, held_out
            )
            write(frame)
        flights = requests[requests["task"].eq("severe_delay")]
        if not flights.empty:
            for frame in flight_predictions(flights, training, train_airports):
                write(frame)
    tmp.replace(path)
    held_out = interface.get("held_out_airport")
    manifest = {
        "run_id": run_id,
        "producer": "airbus_challenge.experiment_baselines",
        "commit": baselines.git("rev-parse", "HEAD"),
        "commit_dirty": baselines.source_dirty(),
        "data_mode": next(iter(modes)),
        "data_snapshot_id": stamp["data_snapshot_id"],
        "cohort_version": cohort,
        "tasks": sorted(tasks),
        "experiment": f"leave_out_{held_out}" if held_out else (
            "csv_only" if cohort.startswith("csv_only") else "primary"
        ),
        "train_airports": train_airports,
        "scoring_airports": score_airports,
        "fit_cutoff_utc": baselines.split_bounds("train")[1].isoformat(),
        "prediction_requests_sha256": request_sha,
        "training_labels_sha256": training_sha,
        "labels_sha256": sha256(labels_path),
        "airport_hourly_sha256": hourly_sha,
        "fit_availability": "simulated; outcome_available_at_utc <= fit cutoff",
        "feed_latency_h": baselines.FEED_LATENCY_H,
        "schedule_knowledge_basis": baselines.RETROSPECTIVE_SCHEDULE,
        "transfer_schedule_fit": transfer_fit,
        "rows": rows,
        "runtime_s": round(time.perf_counter() - started, 3),
        "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        / (1024 ** 2 if sys.platform == "darwin" else 1024),
        "status_counts": dict(counts),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(output, f"rows={rows}", flush=True)
    return run_id
