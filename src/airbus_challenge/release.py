"""Freeze development-only fits, then perform one approved 2025 assessment."""

import argparse
import gc
import json
import pickle
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from airbus_challenge import (
    baselines as b,
)
from airbus_challenge import (
    calibrate,
    registry,
    train,
)
from airbus_challenge import (
    experiment_baselines as eb,
)
from airbus_challenge import (
    experiments as ex,
)
from airbus_challenge import (
    flight_baselines as fb,
)
from airbus_challenge.download import sha256
from airbus_challenge.recommend import REFERENCE_COLUMNS, apply_calibrator

FREEZE = Path("reports/phase6_release.json")
BINDING = "phase6_release"
CUTOFF = pd.Timestamp("2025-01-01", tz="UTC")
APPROVAL = "Project lead: explicit chat approval for frozen one-time 2025 assessment, 2026-10-31"
PRIMARY_LABELS = Path("data/processed/candidates/agent1_phase2/labels.parquet")
LABEL_COLUMNS = ["prediction_id", "target_kind", "y_true", "eligible", "label_version"]


def matrix() -> dict:
    out = {}
    for cohort in ex.COHORTS:
        processed, labels, training = ex.paths(cohort)
        source, scoring = ex.memberships(cohort)
        name = (f"leave_out_{scoring[0]}" if cohort.startswith("loao_") else
                "csv_only" if cohort == "csv_only_v1" else "primary")
        targets = ([train.TARGET] if cohort.startswith("loao_") else
                   [fb.SEVERE] if name == "csv_only" else list(ex.TARGETS))
        out[name] = {
            "cohort": cohort, "processed": str(processed),
            "requests": str(processed / "prediction_requests.parquet"),
            "labels": str(PRIMARY_LABELS if name == "primary" else labels),
            "training_labels": str(training), "train_airports": source,
            "scoring_airports": scoring, "targets": targets,
            "run_id": f"frozen_{name}_v1", "held_out": scoring[0] if cohort.startswith("loao_") else None,
        }
    return out


def development_labels(path: Path, ids: list[str], cutoff=CUTOFF) -> pd.DataFrame:
    """Read only requested 2023/2024 outcomes released by the simulated freeze."""
    flt = ds.field("prediction_id").isin(ids) & (ds.field("outcome_available_at_utc") <= pa.scalar(cutoff))
    return ds.dataset(path).to_table(columns=LABEL_COLUMNS, filter=flt).to_pandas()


def request_rows(slot: dict, task: str, split: str, airports=None) -> pd.DataFrame:
    lo, hi = train.bounds(split)
    flt = ((ds.field("task") == task)
           & ds.field("airport_icao").isin(airports or slot["scoring_airports"])
           & (ds.field("cohort_version") == slot["cohort"])
           & (ds.field("target_start_utc") >= pa.scalar(lo))
           & (ds.field("target_start_utc") < pa.scalar(hi)))
    if split == "test":
        flt &= ds.field("as_of_utc") >= pa.scalar(CUTOFF)
    return ds.dataset(slot["requests"]).to_table(columns=b.REQUEST_COLUMNS, filter=flt).to_pandas()


def fit_rows(slot: dict, target: str, split: str) -> pd.DataFrame:
    task, processed = ex.TARGETS[target], Path(slot["processed"])
    if split == "train":
        return ex.training_rows(processed, Path(slot["training_labels"]), task, target,
                                "runway", slot["train_airports"],
                                train.DELAY["train_sample"] if task == fb.TASK else 0)
    frame = ex.read_inputs(processed, task, "validation", "runway", slot["train_airports"])
    labels = development_labels(Path(slot["labels"]), frame.prediction_id.tolist())
    labels = labels[labels.target_kind.eq(target) & labels.eligible & labels.y_true.notna()]
    frame = frame.merge(labels[["prediction_id", "y_true"]], on="prediction_id", validate="one_to_one")
    if task == fb.TASK and len(frame) > train.DELAY["val_sample"]:
        frame = frame.sample(train.DELAY["val_sample"], random_state=train.SEED).sort_index()
    return frame


def candidate_prediction(slot, spec, split, airport):
    req = request_rows(slot, spec["task"], split, [airport])
    frame = ex.read_inputs(Path(slot["processed"]), spec["task"], split, "runway", [airport])
    models = [lgb.Booster(model_file=p) for p in spec["model_paths"]]
    return ex.predict(req, frame, spec["features"], models, spec["categories"],
                      "runway", spec["target"], spec["model_version"])


def clean_status(frame):
    frame = frame.copy()
    bad = frame.status.eq("degraded")
    frame.loc[bad, "status"] = "unavailable"
    frame.loc[bad, ["estimate", "p10", "p90"]] = np.nan
    frame.loc[bad, "reason_codes"] = frame.loc[bad, "reason_codes"].map(
        lambda codes: [*list(codes), "unvalidated_degraded_input"])
    return frame


def apply_policy(frame: pd.DataFrame, policy: dict) -> pd.DataFrame:
    frame = clean_status(frame)
    for (target, model), rows in frame.groupby(["target_kind", "model_version"]):
        cal = policy.get("calibrators", {}).get(target, {}).get(model)
        if cal:
            idx = rows.index[rows.estimate.notna()]
            frame.loc[idx, "estimate"] = apply_calibrator(cal, frame.loc[idx, "estimate"])
        margins = policy.get("throughput_interval", {}).get(model, {})
        if target == train.TARGET and margins:
            margin = rows.airport_icao.map({a: v["margin"] for a, v in margins.items()})
            frame.loc[rows.index, "p10"] = (rows.p10 - margin).clip(lower=0)
            frame.loc[rows.index, "p90"] = rows.p90 + margin
        if cal or margins:
            # Distinct IDs prevent downstream code from applying the raw model's
            # calibrator a second time. Frozen outputs are assessment artifacts.
            frame.loc[rows.index, "model_version"] = model + "_calibrated"
    return frame


def baseline_fits(slot, run: Path) -> dict:
    fits = {}
    tasks = {ex.TARGETS[t] for t in slot["targets"]}
    if fb.TASK in tasks:
        for target in fb.TARGETS:
            columns = ["prediction_id", "flight_id", "airport_icao", "horizon_h", "target_start_utc",
                       "target_kind", "eligible", "y_true", "outcome_available_at_utc"]
            rows = pd.read_parquet(slot["training_labels"], columns=columns,
                filters=[("target_kind", "==", target), ("horizon_h", "==", 3)])
            values = eb.training_rows(rows, target, slot["train_airports"])
            fits[target] = {"rates": fb.fit_rates(values), "logistic": fb.fit_logistic(values)}
    if train.TASK in tasks:
        hourly = pd.read_parquet(b.HOURLY, columns=list(dict.fromkeys([*b.CONTEXT_COLUMNS, *b.OUTCOME_COLUMNS])),
                                 filters=[("hour_start_utc", "<", train.cutoff())])
        training = pd.read_parquet(slot["training_labels"], columns=[
            "airport_icao", "target_start_utc", "target_kind", "eligible", "outcome_available_at_utc"],
            filters=[("target_kind", "==", train.TARGET), ("horizon_h", "==", 3)])
        rows = b.observed(eb.source_hours(hourly, training, slot["train_airports"]))
        fits[train.TARGET] = {"climatology": b.fit_climatology(rows), "schedule": b.fit_schedule(rows)}
        if slot["held_out"]:
            from airbus_challenge.extra_baselines import fit_transfer_schedule
            fits[train.TARGET]["transfer"] = fit_transfer_schedule(rows, slot["held_out"])
    path = run / "baseline_fits.pkl"
    path.write_bytes(pickle.dumps(fits))
    return {"path": str(path), "sha256": sha256(path)}


def prepare() -> dict:
    if FREEZE.exists() or (b.LEDGER / f"{BINDING}.json").exists():
        raise FileExistsError("release already frozen or claimed")
    if b.source_dirty():
        raise ValueError("commit release source before preparing models")
    slots, files = matrix(), {}
    ref = pd.read_parquet(b.HOURLY, columns=REFERENCE_COLUMNS).drop_duplicates(
        ["airport_icao", "airport_local_hour"])
    for name, slot in slots.items():
        print(f"Preparing {name}: development data only", flush=True)
        run = b.ARTIFACTS / slot["run_id"]
        if run.exists():
            raise FileExistsError(f"refusing to overwrite {run}")
        run.mkdir(parents=True)
        slot["candidates"], policy = [], {
            "calibrators": {}, "throughput_interval": {}, "severe_delay_thresholds": {},
            "throughput_alert": {}, "episodes": {}}
        for target in slot["targets"]:
            print(f"  fitting {target} on source-airport development rows", flush=True)
            names = ex.feature_names("runway", ex.TARGETS[target], bool(slot["held_out"]))
            rows, val = fit_rows(slot, target, "train"), fit_rows(slot, target, "validation")
            models, categories, counts = ex.fit_model(rows, names, target != train.TARGET, train.ROUNDS, val)
            del rows, val
            spec = {"task": ex.TARGETS[target], "target": target, "features": names,
                    "categories": categories, "fit_counts": counts,
                    "model_version": f"lgbm_release_{target}_v1", "model_paths": []}
            for i, model in enumerate(models):
                path = run / f"model_{target}_{i}.txt"
                model.save_model(path)
                spec["model_paths"].append(str(path))
                files[str(path)] = sha256(path)
            slot["candidates"].append(spec)
            if not slot["held_out"]:
                parts = [candidate_prediction(slot, spec, "calibration", a)
                         for a in slot["train_airports"]]
                pred = pd.concat(parts, ignore_index=True)
                labels = development_labels(Path(slot["labels"]), pred.prediction_id.unique().tolist())
                fragment = calibrate.calibrate(pred, labels, ref)
                for key, values in policy.items():
                    # Each target has a distinct model ID; calibrator targets remain nested.
                    values.update(fragment[key])
                del parts, pred, labels
            del models
            gc.collect()
        slot["baseline_fits"] = baseline_fits(slot, run)
        files[slot["baseline_fits"]["path"]] = slot["baseline_fits"]["sha256"]
        policy_doc = {"policy_version": "wp-d7-v1", "calibration_fit_utc": [t.isoformat() for t in calibrate.FIT],
                      "threshold_assessment_utc": [t.isoformat() for t in calibrate.ASSESS],
                      "outcome_availability_cutoff_utc": CUTOFF.isoformat(), **policy}
        path = run / "calibration.json"
        path.write_text(json.dumps(policy_doc, indent=2, default=str))
        slot["policy"] = str(path)
        files[str(path)] = sha256(path)
        for path in [slot["requests"], slot["labels"], slot["training_labels"],
                     str(Path(slot["processed"]) / registry.WEATHER_TABLE),
                     str(Path(slot["processed"]) / registry.DEMAND_TABLE)]:
            files.setdefault(path, sha256(Path(path)))
        metadata = json.loads(Path(slot["requests"]).with_suffix(".manifest.json").read_text())
        if metadata["data_mode"] != "real" or metadata["parquet_sha256"] != files[slot["requests"]]:
            raise ValueError("request file or data mode differs from producer manifest")
        slot["data_snapshot_id"] = metadata["source_flights_sha256"]
        slot["request_sha256"] = files[slot["requests"]]
    for path in [b.HOURLY, Path("configs/experiment.yaml"), Path("configs/airports.yaml"), Path("uv.lock")]:
        files[str(path)] = sha256(path)
    frozen = {"release_version": "phase6/1", "approved_by": APPROVAL,
        "approval": "Lead explicitly approved freezing and running the 2025 assessment once, without test-guided changes.",
        "commit": b.git("rev-parse", "HEAD"), "commit_dirty": False,
        "frozen_at_utc": datetime.now(UTC).isoformat(), "data_mode": "real",
        "fit_cutoff_utc": CUTOFF.isoformat(), "training_target_end_utc": train.cutoff().isoformat(),
        "selection_target_end_utc": train.bounds("validation")[1].isoformat(),
        "calibration_target_end_utc": CUTOFF.isoformat(),
        "test_bounds_utc": [t.isoformat() for t in train.bounds("test")],
        "missing_input_policy": "unavailable; no unvalidated degraded fallbacks",
        "probabilities": "primary/CSV calibrated on eligible H2 2024 outcomes; paired CSV reuses primary calibration",
        "intervals": "primary conformal calibration; LOAO raw quantiles with no held-out calibration",
        "feed_basis": "retrospective schedule; persistence uses a declared simulated past-hour feed",
        "registry_sha256": registry.to_json(registry.build())["content_sha256"],
        "recipe": {"params": train.PARAMS, "max_rounds": train.ROUNDS, "early_stopping_rounds": train.EARLY_STOP,
                   "train_binary_cap": train.DELAY["train_sample"], "validation_binary_cap": train.DELAY["val_sample"]},
        "files_sha256": files, "experiments": slots,
        "optional_experiments_omitted": ["operations feed ablation", "capacity ratio models", "severe-delay LOAO"],
        "separate_audits": "omitted under prior lead instruction; implementation tests required"}
    FREEZE.write_text(json.dumps(frozen, indent=2, default=str))
    print(FREEZE, "prepared; no test outcomes read", flush=True)
    return seal()


def seal() -> dict:
    """Bind the exact candidate set before the one-time claim, preserving fit provenance."""
    frozen = json.loads(FREEZE.read_text())
    if frozen.get("sealed") or (b.LEDGER / f"{BINDING}.json").exists():
        raise FileExistsError("release already sealed or claimed")
    if b.source_dirty():
        raise ValueError("commit release source before sealing")
    for path, expected in frozen["files_sha256"].items():
        if sha256(Path(path)) != expected:
            raise ValueError(f"frozen input changed: {path}")
    for name, slot in frozen["experiments"].items():
        policy = json.loads(Path(slot["policy"]).read_text())
        expected = {}
        for spec in slot["candidates"]:
            target, model = spec["target"], spec["model_version"]
            calibrated = (model in policy.get("calibrators", {}).get(target, {})
                          or model in policy.get("throughput_interval", {}))
            expected[target] = [model + "_calibrated" if calibrated else model]
        if name == "csv_only":
            expected[fb.SEVERE].append("lgbm_release_all_bts_on_csv_v1")
            expected[fb.CANCELLATION] = []  # Prespecified cancellation baseline companion.
        slot["expected_candidates"] = expected
    frozen.update(model_fit_commit=frozen["commit"], commit=b.git("rev-parse", "HEAD"),
                  sealed=True, sealed_at_utc=datetime.now(UTC).isoformat())
    FREEZE.write_text(json.dumps(frozen, indent=2))
    return frozen


def verify_frozen(require_claim=False) -> dict:
    frozen = json.loads(FREEZE.read_text())
    if not frozen.get("sealed"):
        raise ValueError("seal the exact candidate matrix before assessment")
    if frozen["commit_dirty"] or frozen["commit"] != b.git("rev-parse", "HEAD") or b.source_dirty():
        raise ValueError("release source differs from the clean frozen commit")
    if pd.Timestamp(frozen["fit_cutoff_utc"]) != CUTOFF:
        raise ValueError("release cutoff changed")
    if require_claim:
        claim = json.loads((b.LEDGER / f"{BINDING}.json").read_text())
        if claim["release_sha256"] != sha256(FREEZE):
            raise ValueError("release changed after the locked claim")
    for path, expected in frozen["files_sha256"].items():
        if sha256(Path(path)) != expected:
            raise ValueError(f"frozen input changed: {path}")
    return frozen


def claim_batch(frozen):
    record = {"run": BINDING, "approved_by": frozen["approved_by"], "commit": frozen["commit"],
              "release_sha256": sha256(FREEZE), "claimed_at_utc": datetime.now(UTC).isoformat(),
              "experiments": list(frozen["experiments"])}
    for directory in [b.LEDGER, b.LEDGER_MIRROR]:
        if any(directory.glob("*.json")):
            raise FileExistsError("locked release already claimed; never start a second assessment")
    b.LEDGER.mkdir(parents=True, exist_ok=True)
    with (b.LEDGER / f"{BINDING}.json").open("x") as file:
        file.write(json.dumps(record, indent=2))
    b.LEDGER_MIRROR.mkdir(parents=True, exist_ok=True)
    (b.LEDGER_MIRROR / f"{BINDING}.json").write_text(json.dumps(record, indent=2))


def baseline_predictions(slot, task, req, fits, hourly):
    if task == train.TASK:
        tp = fits[train.TARGET]
        if slot["held_out"]:
            line = tp["transfer"]
            applied = {"airports": {slot["held_out"]: {k: line[k] for k in ("slope", "intercept")}}}
            schedule = b.schedule_only(req, hourly, applied).assign(
                model_version="baseline_transfer_schedule_v1")
            yield schedule
        else:
            yield b.climatology(req, tp["climatology"])
            yield b.schedule_only(req, hourly, tp["schedule"])
            yield b.seasonal_persistence(req, hourly)
        yield b.persistence(req, hourly)
    else:
        keys = fb.calendar(req)
        for target in fb.TARGETS:
            fit = fits[target]
            yield fb._predictions(req, target, fb.CONDITIONAL_RATE,
                                  *fb.conditional_rate(req, keys, fit["rates"]))
            yield fb._predictions(req, target, fb.LOGISTIC,
                                  *fb.logistic(req, keys, fit["logistic"], set(slot["train_airports"])))


def generate(frozen, name):
    slot = frozen["experiments"][name]
    run = b.ARTIFACTS / slot["run_id"]
    path = run / "predictions.parquet"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite test predictions: {path}")
    # This function is called only after the immutable batch claim.
    if not (b.LEDGER / f"{BINDING}.json").exists():
        raise ValueError("reserve the locked batch before reading test outcomes")
    if verify_frozen(require_claim=True) != frozen:
        raise ValueError("generation differs from the frozen release")
    fits = pickle.loads(Path(slot["baseline_fits"]["path"]).read_bytes())
    policy = json.loads(Path(slot["policy"]).read_text())
    hourly = None
    if train.TARGET in slot["targets"]:
        hourly = pd.read_parquet(b.HOURLY, columns=list(dict.fromkeys([*b.CONTEXT_COLUMNS, *b.OUTCOME_COLUMNS])),
                                 filters=[("hour_start_utc", "<", train.bounds("test")[1])])
    stamp = {"data_snapshot_id": slot["data_snapshot_id"], "generated_at_utc": datetime.now(UTC)}
    counts, rows = {}, 0
    tmp = path.with_suffix(".parquet.part")
    with pq.ParquetWriter(tmp, b.PREDICTION_SCHEMA) as writer:
        def write(frame):
            nonlocal rows
            frame = clean_status(frame).assign(**stamp)
            b.check_predictions(frame)
            writer.write_table(pa.Table.from_pandas(frame, schema=b.PREDICTION_SCHEMA, preserve_index=False))
            rows += len(frame)
            for key, n in frame.groupby(["model_version", "target_kind", "status"]).size().items():
                k = "|".join(key)
                counts[k] = counts.get(k, 0) + int(n)

        for spec in slot["candidates"]:
            for airport in slot["scoring_airports"]:
                frame = candidate_prediction(slot, spec, "test", airport)
                write(apply_policy(frame, policy))
                del frame
                gc.collect()
        if name == "csv_only":
            parent = frozen["experiments"]["primary"]
            spec = next(s for s in parent["candidates"] if s["target"] == fb.SEVERE)
            primary_policy = json.loads(Path(parent["policy"]).read_text())
            for airport in slot["scoring_airports"]:
                pred = candidate_prediction(slot, spec, "test", airport)
                pred = apply_policy(pred, primary_policy).assign(model_version="lgbm_release_all_bts_on_csv_v1")
                write(pred)
        for task in sorted({ex.TARGETS[t] for t in slot["targets"]}):
            for airport in slot["scoring_airports"]:
                req = request_rows(slot, task, "test", [airport])
                for frame in baseline_predictions(slot, task, req, fits, hourly):
                    write(frame)
                gc.collect()
    tmp.replace(path)
    manifest = {"run_id": slot["run_id"], "producer": "airbus_challenge.release",
        "commit": frozen["commit"], "commit_dirty": False, "data_mode": "real",
        "model_fit_commit": frozen["model_fit_commit"],
        "selection_target_end_utc": frozen["selection_target_end_utc"],
        "calibration_target_end_utc": frozen["calibration_target_end_utc"],
        "data_snapshot_id": slot["data_snapshot_id"], "prediction_requests_sha256": slot["request_sha256"],
        "fit_cutoff_utc": frozen["fit_cutoff_utc"], "train_airports": slot["train_airports"],
        "scoring_airports": slot["scoring_airports"], "cohort_version": slot["cohort"], "experiment": name,
        "release_sha256": sha256(FREEZE), "calibration_applied": not bool(slot["held_out"]),
        "calibration_sha256": sha256(Path(slot["policy"])), "rows": rows, "status_counts": counts}
    (run / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(path, rows, flush=True)


def assess():
    frozen = verify_frozen()
    claim_batch(frozen)
    from airbus_challenge import evaluate, failures
    for name, slot in frozen["experiments"].items():
        generate(frozen, name)
        report = evaluate.main([slot["run_id"]], locked_test=True, approved_by=frozen["approved_by"],
                               experiment=name, cohorts=[slot["cohort"]], release=True)
        failures.main(report, Path(slot["processed"]) / "feature_snapshots.parquet",
                      Path(slot["processed"]) / "feature_lineage.parquet")
    return frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "seal", "assess"])
    args = parser.parse_args()
    {"prepare": prepare, "seal": seal, "assess": assess}[args.action]()


if __name__ == "__main__":
    main()
