import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from airbus_challenge.baselines import (
    AIRPORTS,
    ARTIFACTS,
    CONTEXT_COLUMNS,
    EXPERIMENT,
    FEED_LATENCY_H,
    HOURLY,
    OUTCOME_COLUMNS,
    REQUESTS,
    SCHEMA_VERSION,
    TARGET,
    TARGET_LABEL,
    _schedule_line,
    climatology,
    fit_climatology,
    git,
    in_split,
    observed,
    persistence,
    schedule_only,
    scored_requests,
    source_dirty,
    split_bounds,
    write_predictions,
)
from airbus_challenge.download import sha256

RATIO = EXPERIMENT["targets"]["capacity_ratio"]
RATIO_UNIT = "ratio"
RATIO_COLUMNS = [RATIO, "capacity_ratio_status", "clear_weather_reference_id"]
TRANSFER_SCHEDULE = "baseline_transfer_schedule_v1"
VERSION = "extra-baseline-v1"
LABELS = Path("data/labels/labels.parquet")
RATIO_LABELS = Path("data/labels/ratio_labels_primary.parquet")
METRICS = Path("reports/dev/extra_baselines_dev.json")


def as_ratio(hourly: pd.DataFrame) -> pd.DataFrame:
    # The baselines read TARGET, so the ratio stands in for it; observed() drops NaN.
    return hourly.assign(**{TARGET: hourly[RATIO].astype("float64")})


def ratio_predictions(hourly: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
    ratio = as_ratio(hourly)
    train = observed(in_split(ratio, "train", "hour_start_utc"))
    return pd.concat(
        [persistence(scored, ratio), climatology(scored, fit_climatology(train))],
        ignore_index=True,
    ).assign(target_kind=RATIO, unit=RATIO_UNIT, feature_version=VERSION)


def fit_transfer_schedule(train: pd.DataFrame, held_out: str) -> dict:
    # WP-D6: the held-out airport's rows never reach the fit.
    rows = train[
        train["airport_icao"].ne(held_out) & train["scheduled_arrivals"].notna()
    ]
    return {
        "source_airports": sorted(rows["airport_icao"].unique()),
        **_schedule_line(rows),
    }


def transfer_predictions(
    hourly: pd.DataFrame, scored: pd.DataFrame, held_out: str
) -> tuple[pd.DataFrame, dict]:
    train = observed(in_split(hourly, "train", "hour_start_utc"))
    line = fit_transfer_schedule(train, held_out)
    target = scored[scored["airport_icao"].eq(held_out)]
    applied = {"airports": {held_out: {k: line[k] for k in ("slope", "intercept")}}}
    schedule = schedule_only(target, hourly, applied).assign(
        model_version=TRANSFER_SCHEDULE
    )
    return pd.concat([schedule, persistence(target, hourly)], ignore_index=True).assign(
        feature_version=VERSION
    ), line


def load(hourly_path: Path, requests_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Dev only: 2025 outcomes are never read.
    filters = [("hour_start_utc", "<", split_bounds("test")[0])]
    columns = list(dict.fromkeys([*CONTEXT_COLUMNS, *OUTCOME_COLUMNS, *RATIO_COLUMNS]))
    hourly = pd.read_parquet(hourly_path, columns=columns, filters=filters)
    requests = pd.read_parquet(requests_path, filters=[("task", "==", "throughput")])
    return hourly, scored_requests(hourly, requests, locked_test=False)


def write_run(
    predictions: pd.DataFrame, run_id: str, artifacts: Path, inputs: dict, **extra
) -> Path:
    snapshots = predictions["data_snapshot_id"].unique()
    counts = pd.crosstab(predictions["model_version"], predictions["status"])
    manifest = {
        "run_id": run_id,
        "producer": "airbus_challenge.extra_baselines",
        "producer_version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "commit": git("rev-parse", "HEAD"),
        "commit_dirty": source_dirty(),
        "approved_by": None,
        "data_mode": predictions["data_mode"].iloc[0],
        "data_snapshot_id": str(snapshots[0]),
        **inputs,
        "uv_lock_sha256": sha256(Path("uv.lock")),
        "feed_latency_h": FEED_LATENCY_H,
        "fit_split": EXPERIMENT["splits"]["train"],
        "fit_cutoff_utc": split_bounds("train")[1].isoformat(),
        "fit_availability": "simulated: train outcomes are treated as known at the "
        "cutoff, though BTS publishes months later",
        **extra,
        "target_start_min_utc": predictions["target_start_utc"].min().isoformat(),
        "target_start_max_utc": predictions["target_start_utc"].max().isoformat(),
        "rows": len(predictions),
        "status_counts": counts.to_dict("index"),
    }
    path = artifacts / run_id / "predictions.parquet"
    write_predictions(predictions, path)
    path.with_name("manifest.json").write_text(
        json.dumps(manifest, indent=2, default=int)
    )
    print(path)
    print(counts)
    return path


def labels_for(
    predictions: pd.DataFrame, labels_path: Path, target: str
) -> pd.DataFrame:
    ids = predictions["prediction_id"].unique().tolist()
    return pd.read_parquet(
        labels_path,
        columns=["prediction_id", "target_kind", "y_true", "eligible"],
        filters=[("target_kind", "==", target), ("prediction_id", "in", ids)],
    )


def ratio_labels(
    predictions: pd.DataFrame, hourly: pd.DataFrame
) -> tuple[pd.DataFrame, str]:
    if RATIO_LABELS.exists():
        return labels_for(predictions, RATIO_LABELS, RATIO), str(RATIO_LABELS)
    # Same rule as targets.py: throughput-eligible and an available ratio.
    base = labels_for(predictions, LABELS, TARGET)
    keys = predictions.drop_duplicates("prediction_id")[
        ["prediction_id", "airport_icao", "target_start_utc"]
    ]
    hours = hourly.rename(columns={"hour_start_utc": "target_start_utc"})
    joined = base.merge(keys, on="prediction_id").merge(
        hours[["airport_icao", "target_start_utc", RATIO, "capacity_ratio_status"]],
        on=["airport_icao", "target_start_utc"],
        how="left",
    )
    value = joined[RATIO].astype("float64")
    eligible = joined["eligible"] & joined["capacity_ratio_status"].eq("available")
    eligible &= value.notna()
    derived = joined.assign(
        target_kind=RATIO, eligible=eligible, y_true=value.where(eligible)
    )
    return derived, f"derived: {LABELS} throughput eligibility x {HOURLY} {RATIO}"


def rmse_table(predictions: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    # Common support: every model in the frame has an estimate and the label is eligible.
    rows = predictions.merge(
        labels[["prediction_id", "y_true", "eligible"]], on="prediction_id"
    )
    rows = rows[rows["eligible"] & rows["estimate"].notna()]
    n_models = rows["model_version"].nunique()
    rows = rows[
        rows.groupby("prediction_id")["model_version"].transform("nunique").eq(n_models)
    ]
    rows = rows.assign(
        split=np.where(
            rows["target_start_utc"].lt(split_bounds("calibration")[0]),
            "validation",
            "calibration",
        ),
        sq=(rows["estimate"] - rows["y_true"]) ** 2,
    )
    table = rows.groupby(["split", "airport_icao", "model_version"]).agg(
        rmse=("sq", lambda s: float(np.sqrt(s.mean()))), n=("sq", "size")
    )
    return table.reset_index()


def main(
    hourly_path: Path | None = None,
    requests_path: Path | None = None,
    artifacts: Path | None = None,
) -> dict:
    hourly_path, requests_path = hourly_path or HOURLY, requests_path or REQUESTS
    artifacts = artifacts or ARTIFACTS
    inputs = {
        "airport_hourly_sha256": sha256(hourly_path),
        "prediction_requests_sha256": sha256(requests_path),
    }
    hourly, scored = load(hourly_path, requests_path)
    stamp = {
        "data_snapshot_id": str(hourly["source_snapshot_id"].unique().item()),
        "generated_at_utc": datetime.now(UTC),
    }
    reference = hourly["clear_weather_reference_id"].dropna().unique().tolist()
    ratio = ratio_predictions(hourly, scored).assign(**stamp)
    write_run(
        ratio,
        "ratio_baselines_dev",
        artifacts,
        inputs,
        experiment="primary",
        target=RATIO,
        target_label=f"{TARGET_LABEL} over clear-weather ceiling",
        clear_weather_reference_id=reference,
        train_airports=sorted(AIRPORTS),
    )
    labels, label_source = ratio_labels(ratio, hourly)
    report = {
        "generated_at_utc": stamp["generated_at_utc"].isoformat(),
        "commit": git("rev-parse", "HEAD"),
        "scope": "dev (validation H1 2024, calibration H2 2024), all horizons, "
        "common support per table",
        "ratio": {
            "label_source": label_source,
            "rmse": rmse_table(ratio, labels).to_dict("records"),
        },
        "transfer": {},
    }
    climatology_dev = artifacts / "baselines_dev" / "predictions.parquet"
    throughput = labels_for(scored, LABELS, TARGET)
    for held_out in sorted(AIRPORTS):
        predictions, line = transfer_predictions(hourly, scored, held_out)
        predictions = predictions.assign(**stamp)
        write_run(
            predictions,
            f"transfer_baselines_dev_leave_out_{held_out}",
            artifacts,
            inputs,
            experiment=f"leave_out_{held_out}",
            experiment_detail="WP-D6 strict zero-shot transfer: schedule-only line "
            "fitted on the source airport's 2023 rows, applied to the held-out "
            "airport; held-out persistence (simulated feed). No held-out fitting or "
            "calibration; capacity ratio omitted",
            target=TARGET,
            target_label=TARGET_LABEL,
            train_airports=line["source_airports"],
            scoring_airports=[held_out],
            transfer_schedule_fit=line,
        )
        # In-airport climatology is a reference only: it is fitted on the held-out airport.
        reference_rows = pd.read_parquet(
            climatology_dev,
            filters=[
                ("model_version", "==", "baseline_climatology_v1"),
                ("airport_icao", "==", held_out),
            ],
        )
        both = pd.concat([predictions, reference_rows], ignore_index=True)
        report["transfer"][held_out] = {
            "train_airports": line["source_airports"],
            "fit": line,
            "rmse": rmse_table(both, throughput).to_dict("records"),
        }
    METRICS.parent.mkdir(parents=True, exist_ok=True)
    METRICS.write_text(json.dumps(report, indent=2, default=int))
    print(METRICS)
    return report


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    main()
