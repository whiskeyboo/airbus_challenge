"""Reproducible development ablations and strict CSV/airport-transfer experiments."""

import argparse
import gc
import json
import resource
import time
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds

from airbus_challenge import baselines, input_qa, registry, train
from airbus_challenge.download import sha256

PRIMARY = "retrospective_schedule_v1"
VARIANTS = ("schedule", "observations", "forecasts", "runway", "operations")
COHORTS = (PRIMARY, "csv_only_v1", *(f"loao_{a}_v1" for a in baselines.AIRPORTS))
SELECTION_START = pd.Timestamp("2024-01-01", tz="UTC")
OPS_INPUTS = ["ops_arrivals_last_complete", "ops_source_age_min"]
TARGETS = {train.TARGET: "throughput", "departure_delay_gt45": "severe_delay",
           "cancellation": "severe_delay"}


def feature_names(variant: str, task: str, transfer=False) -> list[str]:
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant}")
    names = registry.model_inputs(task)
    # Wind intensity is never an independent predictor: the runway stage introduces
    # intensity together with its direction-relative components.
    wind = ("wind", "gust", "crosswind", "tailwind", "headwind", "best_end")
    out = []
    for name in names:
        metar, taf = name.startswith("metar_"), name.startswith("taf_")
        if metar and variant == "schedule":
            continue
        if taf and variant in ("schedule", "observations"):
            continue
        if ((metar or taf) and any(w in name for w in wind)
                and variant not in ("runway", "operations")):
            continue
        out.append(name)
    if transfer:
        out = [n for n in out if n != "airport_icao" and "2023" not in n]
    return out + (OPS_INPUTS if variant == "operations" else [])


def paths(cohort: str) -> tuple[Path, Path, Path]:
    if cohort not in COHORTS:
        raise ValueError(f"unknown cohort {cohort}")
    processed = Path("data/processed")
    if cohort != PRIMARY:
        processed /= f"cohorts/{cohort}"
    labels = Path("data/labels/labels.parquet") if cohort == PRIMARY else Path(
        f"data/labels/cohorts/{cohort}/labels.parquet"
    )
    training = Path(f"data/processed/candidates/agent1_training/{cohort}/training_labels.parquet")
    return processed, labels, training


def memberships(cohort: str) -> tuple[list[str], list[str]]:
    airports = sorted(baselines.AIRPORTS)
    if cohort.startswith("loao_"):
        held_out = cohort.removeprefix("loao_").removesuffix("_v1")
        return [a for a in airports if a != held_out], [held_out]
    return airports, airports


def categorical_levels(frame: pd.DataFrame) -> dict:
    types = {f.name: f.dtype for f in registry.build() if f.predictor}
    return {c: sorted(frame[c].dropna().astype(str).unique().tolist())
            for c in frame if types.get(c) == "string"}


def encode(frame: pd.DataFrame, levels: dict) -> pd.DataFrame:
    out = frame.copy()
    for c in out:
        if c in levels:
            out[c] = pd.Categorical(out[c].where(out[c].isin(levels[c])), categories=levels[c])
        else:
            out[c] = pd.to_numeric(out[c], errors="raise").astype("float32")
    return out


def read_inputs(processed: Path, task: str, split: str, variant: str,
                airports: list[str]) -> pd.DataFrame:
    names = feature_names(variant, task)
    base_names = [n for n in names if n not in OPS_INPUTS]
    lo, hi = train.bounds(split)
    flt = ((ds.field("task") == task) & ds.field("airport_icao").isin(airports)
           & (ds.field("target_start_utc") >= pa.scalar(lo))
           & (ds.field("target_start_utc") < pa.scalar(hi)))
    tables = {f.name: f.table for f in registry.build() if f.predictor}
    weather_names = [n for n in base_names if tables[n] == registry.WEATHER_TABLE
                     and n not in input_qa.KEYS]
    weather = ds.dataset(processed / registry.WEATHER_TABLE).to_table(
        columns=[*input_qa.META, *input_qa.KEYS, "status", "reason_codes", *weather_names],
        filter=flt).to_pandas()
    demand_names = [n for n in base_names if tables[n] == registry.DEMAND_TABLE]
    demand = ds.dataset(processed / registry.DEMAND_TABLE).to_table(
        columns=["prediction_id", "status", "reason_codes", *demand_names], filter=flt
    ).to_pandas().rename(columns={"status": "demand_status", "reason_codes": "demand_reason_codes"})
    frame = weather.merge(demand, on="prediction_id", how="left", validate="one_to_one")
    frame["demand_status"] = frame.demand_status.fillna("missing")
    for c in ["reason_codes", "demand_reason_codes"]:
        frame[c] = frame[c].map(lambda r: list(r) if isinstance(r, (list, tuple, np.ndarray)) else ["snapshot_missing"])
    if variant == "operations":
        # The optional simulated feed has its own availability contract and is never
        # read by the ordinary weather/schedule input loader.
        ops = ds.dataset("data/processed/candidates/agent1_phase2/operations_features.parquet")
        cols = ["prediction_id", *OPS_INPUTS, "ops_status", "source_hour_end_utc",
                "source_available_at_utc", "availability_basis"]
        table = ops.to_table(columns=cols, filter=ds.field("prediction_id").isin(
            frame.prediction_id.tolist())).to_pandas()
        frame = frame.merge(table, on="prediction_id", how="left", validate="one_to_one")
        known = frame.source_available_at_utc.notna()
        if (frame.loc[known, "source_available_at_utc"] > frame.loc[known, "as_of_utc"]).any():
            raise ValueError("operations feature published after issue time")
        if (frame.loc[known, "source_hour_end_utc"] > frame.loc[known, "as_of_utc"]).any():
            raise ValueError("operations source hour ends after issue time")
        if not frame.loc[known, "availability_basis"].eq("simulated").all():
            raise ValueError("operations availability must be explicitly simulated")
    return frame


def training_rows(processed: Path, training_path: Path, task: str, target: str,
                  variant: str, airports: list[str], max_rows: int) -> pd.DataFrame:
    # Dedicated exports enforce source-airport membership and simulated label release.
    flt = (ds.field("target_kind") == target) & ds.field("airport_icao").isin(airports)
    labels = ds.dataset(training_path).to_table(
        columns=["prediction_id", "y_true", "eligible", "target_start_utc",
                 "outcome_available_at_utc"], filter=flt).to_pandas()
    if labels.prediction_id.duplicated().any():
        raise ValueError("duplicate training prediction_id")
    start, end = train.bounds("train")
    allowed = (labels.eligible.fillna(False) & labels.y_true.notna()
               & labels.target_start_utc.ge(start) & labels.target_start_utc.lt(end)
               & labels.outcome_available_at_utc.le(end))
    if not allowed.all():
        raise ValueError("training export contains ineligible or unavailable labels")
    frame = read_inputs(processed, task, "train", variant, airports)
    frame = frame.merge(labels[["prediction_id", "y_true"]], on="prediction_id",
                        how="inner", validate="one_to_one")
    if max_rows and len(frame) > max_rows:
        # Fixed ID-based sample, identical across feature variants. Splits remain temporal.
        hashes = pd.util.hash_pandas_object(frame.prediction_id, index=False)
        frame = frame.loc[hashes.nsmallest(max_rows).index].sort_values("prediction_id")
    if frame.empty:
        raise ValueError(f"no eligible training rows for {target}")
    return frame


def fit_model(frame: pd.DataFrame, names: list[str], binary: bool,
              rounds: int, validation: pd.DataFrame) -> tuple[list, dict, dict]:
    if frame.empty or validation.empty:
        raise ValueError("training and source validation rows are required")
    levels = categorical_levels(frame[names])
    X, valid = encode(frame[names], levels), encode(validation[names], levels)
    objectives = [{"objective": "binary" if binary else "regression"}]
    if not binary:
        objectives += [{"objective": "quantile", "alpha": q} for q in (0.1, 0.9)]
    models, iterations = [], []
    for objective in objectives:
        params = {**train.PARAMS, **objective}
        model = lgb.train(params, lgb.Dataset(X, frame.y_true),
            num_boost_round=rounds,
            valid_sets=[lgb.Dataset(valid, validation.y_true)],
            callbacks=[lgb.early_stopping(train.EARLY_STOP, verbose=False)])
        models.append(model)
        iterations.append(model.best_iteration)
    return models, levels, {"selected_rounds": iterations, "fit_rows": len(frame),
                            "selection_rows": len(validation), "refit_rows": 0}


def validation_rows(processed, labels_path, task, target, variant, airports, max_rows):
    frame = read_inputs(processed, task, "validation", variant, airports)
    lab = train.training_labels(labels_path, frame.prediction_id.tolist(), target)
    frame = frame.merge(lab, on="prediction_id", how="inner", validate="one_to_one")
    if max_rows and len(frame) > max_rows:
        frame = frame.sample(max_rows, random_state=train.SEED).sort_index()
    return frame


def requests(processed: Path, task: str, airports: list[str]) -> pd.DataFrame:
    lo, hi = train.bounds("validation")[0], train.bounds("calibration")[1]
    flt = ((ds.field("task") == task) & ds.field("airport_icao").isin(airports)
           & (ds.field("target_start_utc") >= pa.scalar(lo))
           & (ds.field("target_start_utc") < pa.scalar(hi))
           & (ds.field("as_of_utc") >= pa.scalar(train.cutoff())))
    return ds.dataset(processed / "prediction_requests.parquet").to_table(
        columns=baselines.REQUEST_COLUMNS, filter=flt).to_pandas()


def predict(req: pd.DataFrame, frame: pd.DataFrame, names: list[str], models: list,
            levels: dict, variant: str, target: str, model_version: str) -> pd.DataFrame:
    frame = req[["prediction_id"]].merge(frame, on="prediction_id", how="left",
                                         validate="one_to_one")
    ok = frame.demand_status.eq("ok")
    if variant == "observations":
        # A missing forecast cannot disqualify a variant that never reads forecasts.
        irrelevant = frame.reason_codes.map(lambda codes: bool(codes) and all(
            str(c).startswith("taf_") for c in codes))
        ok &= frame.status.eq("ok") | irrelevant
    elif variant != "schedule":
        ok &= frame.status.eq("ok")
    if variant == "operations":
        ok &= frame.ops_status.eq("available")
    values = encode(frame[names], levels)
    point = models[0].predict(values)
    low, high = np.full(len(req), np.nan), np.full(len(req), np.nan)
    if len(models) == 3:
        low, high = np.sort(np.stack([m.predict(values) for m in models[1:]]), axis=0)
        low, high, point = np.maximum(low, 0), np.maximum(high, 0), np.maximum(point, 0)
    reasons = []
    ops_status = frame.ops_status if variant == "operations" else [None] * len(frame)
    for demand, weather, ops in zip(frame.demand_reason_codes, frame.reason_codes, ops_status):
        codes = list(demand) if isinstance(demand, list) else ["snapshot_missing"]
        if variant != "schedule" and isinstance(weather, list):
            codes += weather
        if variant == "operations" and ops != "available":
            codes.append("simulated_operations_unavailable")
        if variant == "operations":
            codes.append("simulated_feed")
        reasons.append(sorted({"retrospective_schedule", *codes}))
    return req[baselines.REQUEST_COLUMNS].assign(target_kind=target,
        estimate=np.where(ok, point, np.nan), p10=np.where(ok, low, np.nan),
        p90=np.where(ok, high, np.nan), unit="binary" if target != train.TARGET else train.UNIT,
        status=np.where(ok, "available", "unavailable"), reason_codes=reasons,
        model_version=model_version, feature_version=registry.REGISTRY_VERSION)


def run(cohort: str, variant: str, artifacts=Path("artifacts"),
        targets: list[str] | None = None, rounds=600, max_train_rows=1_500_000) -> Path:
    started = time.monotonic()
    processed, labels_path, training_path = paths(cohort)
    fitting, scoring = memberships(cohort)
    targets = targets or [train.TARGET]
    if cohort == "csv_only_v1":
        targets = [t for t in targets if TARGETS[t] == "severe_delay"]
    if cohort.startswith("loao_"):
        run_id = f"lgbm_throughput_dev_leave_out_{scoring[0]}"
        targets = [train.TARGET]
    elif cohort == "csv_only_v1":
        run_id = "lgbm_delay_csv_only_dev"
        targets = ["departure_delay_gt45"]
    else:
        run_id = f"ablation_{targets[0] if len(targets) == 1 else 'all'}_{variant}_dev"
    output = artifacts / run_id
    output.mkdir(parents=True, exist_ok=True)
    source = json.loads((processed / "feature_snapshots.manifest.json").read_text())
    frames, source_frames, fits = [], [], {}
    for target in targets:
        task = TARGETS[target]
        names = feature_names(variant, task, cohort.startswith("loao_"))
        print(f"{run_id}: fitting {target}", flush=True)
        rows = training_rows(processed, training_path, task, target, variant, fitting,
                             max_train_rows if task == "severe_delay" else 0)
        val = validation_rows(processed, labels_path, task, target, variant, fitting,
                              train.DELAY["val_sample"] if task == "severe_delay" else 0)
        models, levels, counts = fit_model(rows, names, task == "severe_delay", rounds, val)
        del val
        del rows
        model_version = ("lgbm_throughput_loao_v1" if cohort.startswith("loao_") else
                         "lgbm_delay_csv_only_v1" if cohort == "csv_only_v1" else
                         f"lgbm_{target}_{variant}_v1")
        for head, model in zip(("point", "p10", "p90"), models):
            model.save_model(output / f"model_{target}_{head}.txt")
        fits[target] = {**counts, "features": names, "categories": levels}
        for split in train.DEV_SPLITS:
            for airport in sorted(set(fitting + scoring)):
                req = requests(processed, task, [airport])
                lo, hi = train.bounds(split)
                req = req[req.target_start_utc.ge(lo) & req.target_start_utc.lt(hi)]
                X = read_inputs(processed, task, split, variant, [airport])
                pred = predict(req, X, names, models, levels, variant, target, model_version)
                (frames if airport in scoring else source_frames).append(pred)
                del X, pred
                gc.collect()
    stamp = {"data_snapshot_id": source["data_snapshot_id"], "generated_at_utc": datetime.now(UTC)}
    preds = pd.concat(frames, ignore_index=True).assign(**stamp)
    baselines.write_predictions(preds, output / "predictions.parquet")
    if source_frames:
        baselines.write_predictions(pd.concat(source_frames, ignore_index=True).assign(**stamp),
                                    output / "source_calibration_predictions.parquet")
    experiment = f"leave_out_{scoring[0]}" if cohort.startswith("loao_") else (
        "csv_only" if cohort == "csv_only_v1" else "primary")
    manifest = {"run_id": run_id, "producer": "airbus_challenge.experiments",
        "commit": baselines.git("rev-parse", "HEAD"), "commit_dirty": baselines.source_dirty(),
        "data_mode": str(preds.data_mode.iloc[0]), "data_snapshot_id": stamp["data_snapshot_id"],
        "cohort_version": cohort, "experiment": experiment, "variant": variant,
        "fit_split": "train", "fit_cutoff_utc": train.cutoff().isoformat(),
        "early_stopping_split": "validation", "early_stopping_start_utc": SELECTION_START.isoformat(),
        "selection_policy": "2023 parameter fitting; source-airport H1 2024 validation early stopping",
        "selection_data_end_utc": train.bounds("validation")[1].isoformat(),
        "validation_limitation": "Validation used for early stopping; validation metrics are retrospective model-selection diagnostics, not prospective performance",
        "predictor_difference": "LOAO drops airport category and airport-specific 2023 schedule normalizers" if cohort.startswith("loao_") else None,
        "source_calibration_predictions": "source_calibration_predictions.parquet" if source_frames else None,
        "train_airports": fitting, "scoring_airports": scoring,
        "calibration_airports": fitting, "held_out_calibration": False,
        "prediction_requests_sha256": sha256(processed / "prediction_requests.parquet"),
        "labels_sha256": sha256(labels_path), "training_labels_sha256": sha256(training_path),
        "operations_sha256": sha256(Path("data/processed/candidates/agent1_phase2/operations_features.parquet")) if variant == "operations" else None,
        "operations_basis": "simulated operations feed, 10-minute latency; maximum age 120 minutes" if variant == "operations" else None,
        "feature_sha256": {p: sha256(processed / p) for p in
                           [registry.WEATHER_TABLE, registry.DEMAND_TABLE]},
        "registry_sha256": registry.to_json(registry.build())["content_sha256"],
        "params": train.PARAMS, "max_rounds": rounds, "max_binary_training_rows": max_train_rows,
        "fits": fits, "model_versions": sorted(preds.model_version.unique()),
        "targets": targets, "rows": len(preds), "status_counts": preds.status.value_counts().to_dict(),
        "availability": "simulated label release; retrospective schedule; optional operations explicitly simulated",
        "runtime_s": round(time.monotonic() - started, 3),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2, 1)}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(output, manifest["status_counts"], flush=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", choices=COHORTS, default=PRIMARY)
    parser.add_argument("--variants", nargs="+", choices=VARIANTS)
    parser.add_argument("--targets", nargs="+", choices=TARGETS)
    parser.add_argument("--rounds", type=int, default=train.ROUNDS)
    parser.add_argument("--max-train-rows", type=int, default=1_500_000)
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    variants = args.variants or (list(VARIANTS) if args.cohort == PRIMARY else ["runway"])
    if args.cohort != PRIMARY and len(variants) != 1:
        parser.error("CSV/LOAO use a single variant and one named artifact directory")
    for variant in variants:
        run(args.cohort, variant, args.artifacts, args.targets, args.rounds, args.max_train_rows)


if __name__ == "__main__":
    main()
