"""Score the frozen all-BTS delay model on CSV-member requests without refitting."""

import json
import resource
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from airbus_challenge import baselines, experiments, registry, train
from airbus_challenge.download import sha256

RUN_ID = "lgbm_delay_csv_paired_dev"
MODEL_VERSION = "lgbm_delay_all_bts_csv_subset_v1"
COHORT = "csv_only_v1"
TARGET = "departure_delay_gt45"
MODEL_FILE = "model_departure_delay_gt45.txt"


def source_levels(model, names: list[str]) -> dict:
    types = {f.name: f.dtype for f in registry.build() if f.predictor}
    if unknown := set(names) - set(types):
        raise ValueError(f"source booster has unregistered predictors: {sorted(unknown)}")
    categorical = [name for name in names if types[name] == "string"]
    levels = model.pandas_categorical or []
    if len(levels) != len(categorical):
        raise ValueError("source booster categorical vocabulary differs from registry")
    return dict(zip(categorical, levels, strict=True))


def paired(artifacts: Path = Path("artifacts")) -> Path:
    started = time.perf_counter()
    artifacts = Path(artifacts)
    source = artifacts / "lgbm_dev"
    booster_path = source / MODEL_FILE
    if not booster_path.is_file():
        raise FileNotFoundError(f"frozen all-BTS delay booster is required: {booster_path}")
    source_manifest = json.loads((source / "manifest.json").read_text())
    model = lgb.Booster(model_file=str(booster_path))
    names = model.feature_name()
    levels = source_levels(model, names)
    processed, labels_path, _ = experiments.paths(COHORT)
    _, airports = experiments.memberships(COHORT)
    req = experiments.requests(processed, "severe_delay", airports)
    snapshots = json.loads((processed / "feature_snapshots.manifest.json").read_text())
    frames = []
    for split in train.DEV_SPLITS:
        lo, hi = train.bounds(split)
        rows = req[req.target_start_utc.ge(lo) & req.target_start_utc.lt(hi)]
        frame = experiments.read_inputs(processed, "severe_delay", split, "runway", airports)
        frames.append(experiments.predict(
            rows, frame, names, [model], levels, "runway", TARGET, MODEL_VERSION
        ))
    predictions = pd.concat(frames, ignore_index=True).assign(
        data_snapshot_id=snapshots["data_snapshot_id"], generated_at_utc=datetime.now(UTC)
    )
    output = artifacts / RUN_ID
    output.mkdir(parents=True, exist_ok=True)
    baselines.write_predictions(predictions, output / "predictions.parquet")
    copied = output / MODEL_FILE
    shutil.copyfile(booster_path, copied)
    model_hash = sha256(booster_path)
    if sha256(copied) != model_hash:
        raise ValueError("copied source booster hash mismatch")
    manifest = {
        "run_id": RUN_ID, "producer": "airbus_challenge.experiment_csv",
        "commit": baselines.git("rev-parse", "HEAD"),
        "commit_dirty": baselines.source_dirty(), "data_mode": source_manifest["data_mode"],
        "data_snapshot_id": snapshots["data_snapshot_id"],
        "cohort_version": COHORT, "experiment": "csv_only",
        "comparison": "all-BTS model scored on the CSV subset; not a CSV-only fit",
        "model_version": MODEL_VERSION, "targets": [TARGET],
        "train_airports": source_manifest["train_airports"], "scoring_airports": airports,
        "fit_cutoff_utc": source_manifest["fit_cutoff_utc"],
        "early_stopping_split": source_manifest.get("early_stopping_split"),
        "validation_limitation": "Source all-BTS model selected using H1 2024 validation; validation scores are model-selection diagnostics",
        "source_run": "lgbm_dev", "source_booster_sha256": model_hash,
        "source_manifest_sha256": sha256(source / "manifest.json"),
        "source_prediction_requests_sha256": source_manifest["prediction_requests_sha256"],
        "source_data_snapshot_id": source_manifest["data_snapshot_id"],
        "model_refitted": False,
        "prediction_requests_sha256": sha256(processed / "prediction_requests.parquet"),
        "labels_sha256": sha256(labels_path),
        "feature_sha256": {
            table: sha256(processed / table)
            for table in [registry.WEATHER_TABLE, registry.DEMAND_TABLE]
        },
        "registry_sha256": registry.to_json(registry.build())["content_sha256"],
        "features": names, "categories": levels,
        "rows": len(predictions), "status_counts": predictions.status.value_counts().to_dict(),
        "runtime_s": round(time.perf_counter() - started, 3),
        "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        / (1024 ** 2 if sys.platform == "darwin" else 1024),
    }
    if set(predictions.data_mode) != {manifest["data_mode"]}:
        raise ValueError("CSV inputs and frozen source model data_mode differ")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(output, manifest["status_counts"], flush=True)
    return output


if __name__ == "__main__":
    paired()
