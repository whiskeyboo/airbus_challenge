"""LightGBM model for arrival throughput (AAR proxy), fit on train (2023) only.

Early stopping uses the validation split (H1 2024), so validation scores are mildly optimistic;
calibration (H2 2024) is untouched by fitting. Predicts every in-scope validation and calibration
request (as_of >= fit cutoff) and never the test split. Labels are read only for train and
validation prediction ids; 2025 labels are never read.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import yaml

from airbus_challenge import baselines, input_qa, registry
from airbus_challenge.download import sha256

ARTIFACTS = Path("artifacts")
LABELS = Path("data/labels/labels.parquet")
REQUESTS = Path("data/processed/prediction_requests.parquet")
TASK = "throughput"
TARGET = "reporting_carrier_touchdowns"
MODEL_VERSION = "lgbm_throughput_v1"
RUN_ID = "lgbm_throughput_dev"
UNIT = "touchdowns/hour"
SEED = 42
PARAMS = {
    "objective": "regression",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 50,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "seed": SEED,
    "deterministic": True,
    "num_threads": 4,
    "verbose": -1,
}
ROUNDS, EARLY_STOP = 2000, 100
DEV_SPLITS = ("validation", "calibration")


def bounds(split: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    return baselines.split_bounds(split)


def cutoff() -> pd.Timestamp:
    return bounds("train")[1]


def in_scope(requests: pd.DataFrame) -> pd.DataFrame:
    """Validation + calibration requests issued at or after the fit cutoff."""
    lo, hi = bounds(DEV_SPLITS[0])[0], bounds(DEV_SPLITS[-1])[1]
    t = requests["target_start_utc"]
    return requests[t.ge(lo) & t.lt(hi) & requests["as_of_utc"].ge(cutoff())]


def model_frame(X: pd.DataFrame, airports: list[str]) -> pd.DataFrame:
    """Registry columns as LightGBM inputs: categoricals as category, booleans as 0/1/NaN."""
    reg = {f.name: f.dtype for f in registry.build() if f.predictor}
    out = X.copy()
    for c in out.columns:
        if c == "airport_icao":
            out[c] = pd.Categorical(out[c], categories=airports)
        elif reg[c] == "string":
            out[c] = out[c].astype("category")
        elif reg[c] == "bool":
            out[c] = out[c].map({True: 1.0, False: 0.0}).astype("float64")
    return out


def training_labels(path: Path, ids: list[str], target: str = TARGET) -> pd.DataFrame:
    """Eligible throughput labels for the given prediction ids only."""
    labels = (
        ds.dataset(path)
        .to_table(
            columns=["prediction_id", "y_true", "eligible"],
            filter=(ds.field("target_kind") == target)
            & ds.field("prediction_id").isin(ids),
        )
        .to_pandas()
    )
    return labels[labels["eligible"].fillna(False).astype(bool)][
        ["prediction_id", "y_true"]
    ]


def labelled(split, root, airports, labels_path, task=TASK, target=TARGET, sample=None):
    X = input_qa.assemble(task, root, split)
    lab = training_labels(labels_path, X["prediction_id"].tolist(), target)
    df = X.merge(lab, on="prediction_id", how="inner")
    if sample and len(df) > sample:
        df = df.sample(sample, random_state=SEED).sort_index()
    inputs = registry.model_inputs(task)
    return model_frame(df[inputs], airports), df["y_true"].to_numpy()


def fit(train, y_train, val, y_val, objective: dict | None = None):
    params = {**PARAMS, **(objective or {})}
    data = lgb.Dataset(train, y_train, categorical_feature="auto", free_raw_data=False)
    valid = lgb.Dataset(val, y_val, reference=data)
    return lgb.train(
        params, data, ROUNDS, valid_sets=[valid],
        callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False)],
    )  # fmt: skip


def predictions_frame(requests, X, models, airports) -> pd.DataFrame:
    df = requests.merge(
        X, on="prediction_id", how="left", suffixes=("", "_x"), validate="one_to_one"
    )
    inputs = registry.model_inputs(TASK)
    feats = model_frame(df[inputs], airports)
    point, lo, hi = (m.predict(feats, num_iteration=m.best_iteration) for m in models)
    q = np.sort(np.stack([lo, hi]), axis=0)  # Fix quantile crossing by sorting.
    reasons = [
        sorted(set(a) | set(b)) if isinstance(a, list) else ["snapshot_missing"]
        for a, b in zip(df["reason_codes"], df["demand_reason_codes"])
    ]
    ok = df["status"].eq("ok") & df["demand_status"].eq("ok")
    status = np.where(ok, "available", "degraded")
    return requests[baselines.REQUEST_COLUMNS].assign(
        target_kind=TARGET,
        estimate=np.clip(point, 0, None),
        p10=np.clip(q[0], 0, None),
        p90=np.clip(q[1], 0, None),
        unit=UNIT,
        status=status,
        reason_codes=reasons,
        model_version=MODEL_VERSION,
        feature_version=f"{registry.REGISTRY_VERSION}",
    )


def main(
    root: Path = Path("."), artifacts: Path = ARTIFACTS, labels_path: Path = LABELS
) -> Path:
    airports = list(
        yaml.safe_load((root / "configs/airports.yaml").read_text())["airports"]
    )
    train_X, train_y = labelled("train", root, airports, labels_path)
    val_X, val_y = labelled("validation", root, airports, labels_path)
    models = [
        fit(train_X, train_y, val_X, val_y),
        fit(train_X, train_y, val_X, val_y, {"objective": "quantile", "alpha": 0.1}),
        fit(train_X, train_y, val_X, val_y, {"objective": "quantile", "alpha": 0.9}),
    ]
    lo, hi = bounds(DEV_SPLITS[0])[0], bounds(DEV_SPLITS[-1])[1]
    requests = (
        ds.dataset(root / REQUESTS)
        .to_table(
            columns=baselines.REQUEST_COLUMNS,
            filter=(ds.field("task") == TASK)
            & (ds.field("target_start_utc") >= pa.scalar(lo, pa.timestamp("us", "UTC")))
            & (ds.field("target_start_utc") < pa.scalar(hi, pa.timestamp("us", "UTC"))),
        )
        .to_pandas()
    )
    requests = in_scope(requests)
    X = pd.concat(
        [input_qa.assemble(TASK, root, s) for s in DEV_SPLITS], ignore_index=True
    )
    input_qa.validate_inputs(X, TASK, root)
    snapshot_ids = ds.dataset(
        root / registry.PROCESSED / registry.WEATHER_TABLE
    ).to_table(columns=["data_snapshot_id"], filter=ds.field("task") == TASK)
    snapshot_id = sorted(set(snapshot_ids.column(0).to_pylist()))
    preds = predictions_frame(requests, X, models, airports).assign(
        data_snapshot_id=snapshot_id[0], generated_at_utc=datetime.now(UTC)
    )
    run = artifacts / RUN_ID
    baselines.write_predictions(preds, run / "predictions.parquet")
    gain = models[0].feature_importance("gain")
    imp = pd.DataFrame({"feature": models[0].feature_name(), "gain": gain}).nlargest(
        15, "gain"
    )
    imp.to_csv(run / "feature_importance.csv", index=False)
    manifest = {
        "run_id": RUN_ID,
        "producer": "airbus_challenge.train",
        "model_version": MODEL_VERSION,
        "commit": baselines.git("rev-parse", "HEAD"),
        "commit_dirty": baselines.source_dirty(),
        "data_mode": str(preds["data_mode"].iloc[0]),
        "data_snapshot_id": snapshot_id[0],
        "target": TARGET,
        "fit_split": "train",
        "early_stopping_split": "validation",
        "fit_cutoff_utc": cutoff().isoformat(),
        "prediction_requests_sha256": sha256(root / REQUESTS),
        "train_airports": airports,
        "registry_sha256": registry.to_json(registry.build())["content_sha256"],
        "params": PARAMS,
        "best_iteration": {
            "point": models[0].best_iteration,
            "p10": models[1].best_iteration,
            "p90": models[2].best_iteration,
        },
        "train_rows": len(train_y),
        "rows": len(preds),
        "status_counts": preds["status"].value_counts().to_dict(),
    }
    (run / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(run, manifest["best_iteration"], manifest["status_counts"])
    print(imp.to_string(index=False))
    return run


DELAY = {
    "task": "severe_delay",
    "target": "departure_delay_gt45",
    "model_version": "lgbm_delay_v1",
    "run_id": "lgbm_delay_dev",
    "unit": "binary",
    "train_sample": 1_500_000,
    "val_sample": 500_000,
}


def delay_main(
    root: Path = Path("."), artifacts: Path = ARTIFACTS, labels_path: Path = LABELS
):
    """Severe departure delay (> 45 min) among operated flights; ineligible (cancelled) excluded."""
    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        precision_recall_curve,
    )

    d = DELAY
    airports = list(
        yaml.safe_load((root / "configs/airports.yaml").read_text())["airports"]
    )
    args = (root, airports, labels_path, d["task"], d["target"])
    train_X, train_y = labelled("train", *args, sample=d["train_sample"])
    val_X, val_y = labelled("validation", *args, sample=d["val_sample"])
    model = fit(train_X, train_y, val_X, val_y, {"objective": "binary"})
    lo, hi = bounds(DEV_SPLITS[0])[0], bounds(DEV_SPLITS[-1])[1]
    requests = in_scope(
        ds.dataset(root / REQUESTS)
        .to_table(
            columns=baselines.REQUEST_COLUMNS,
            filter=(ds.field("task") == d["task"])
            & (ds.field("target_start_utc") >= pa.scalar(lo, pa.timestamp("us", "UTC")))
            & (ds.field("target_start_utc") < pa.scalar(hi, pa.timestamp("us", "UTC"))),
        )
        .to_pandas()
    )
    X = pd.concat(
        [input_qa.assemble(d["task"], root, s) for s in DEV_SPLITS], ignore_index=True
    )
    input_qa.validate_inputs(X, d["task"], root)
    df = requests.merge(
        X, on="prediction_id", how="left", suffixes=("", "_x"), validate="one_to_one"
    )
    inputs = registry.model_inputs(d["task"])
    proba = model.predict(
        model_frame(df[inputs], airports), num_iteration=model.best_iteration
    )
    ok = df["status"].eq("ok") & df["demand_status"].eq("ok")
    reasons = [
        sorted(set(a) | set(b))
        for a, b in zip(df["reason_codes"], df["demand_reason_codes"])
    ]
    weather = ds.dataset(root / registry.PROCESSED / registry.WEATHER_TABLE)
    snapshot_id = min(
        set(
            weather.to_table(
                columns=["data_snapshot_id"], filter=ds.field("task") == d["task"]
            )
            .column(0)
            .to_pylist()
        )
    )
    preds = requests[baselines.REQUEST_COLUMNS].assign(
        target_kind=d["target"], estimate=proba, p10=np.nan, p90=np.nan, unit=d["unit"],
        status=np.where(ok, "available", "degraded"), reason_codes=reasons,
        model_version=d["model_version"], feature_version=registry.REGISTRY_VERSION,
        data_snapshot_id=snapshot_id, generated_at_utc=datetime.now(UTC),
    )  # fmt: skip
    run = artifacts / d["run_id"]
    baselines.write_predictions(preds, run / "predictions.parquet")
    imp = pd.DataFrame(
        {"feature": model.feature_name(), "gain": model.feature_importance("gain")}
    )
    imp.nlargest(15, "gain").to_csv(run / "feature_importance.csv", index=False)
    # Dev metrics, not via the evaluator (it requires severe-delay baselines that don't exist yet).
    lab = training_labels(labels_path, preds["prediction_id"].tolist(), d["target"])
    scored = preds.merge(lab, on="prediction_id")
    scored["split"] = np.where(
        scored.target_start_utc < bounds("calibration")[0], "validation", "calibration"
    )
    metrics = []
    for (split, airport), g in scored.groupby(["split", "airport_icao"]):
        prec, rec, _ = precision_recall_curve(g.y_true, g.estimate)
        metrics.append({
            "split": split, "airport": airport, "n_eligible": len(g),
            "prevalence": float(g.y_true.mean()),
            "pr_auc": float(average_precision_score(g.y_true, g.estimate)),
            "brier": float(brier_score_loss(g.y_true, g.estimate)),
            "recall_at_precision_0.5": float(rec[prec >= 0.5].max()) if (prec >= 0.5).any() else 0.0,
        })  # fmt: skip
    manifest = {
        "run_id": d["run_id"], "producer": "airbus_challenge.train", "model_version": d["model_version"],
        "commit": baselines.git("rev-parse", "HEAD"), "commit_dirty": baselines.source_dirty(),
        "data_mode": str(preds["data_mode"].iloc[0]), "data_snapshot_id": snapshot_id,
        "target": d["target"], "fit_split": "train", "early_stopping_split": "validation",
        "train_subsample_rows": len(train_y), "val_subsample_rows": len(val_y),
        "fit_cutoff_utc": cutoff().isoformat(), "train_airports": airports,
        "prediction_requests_sha256": sha256(root / REQUESTS),
        "registry_sha256": registry.to_json(registry.build())["content_sha256"],
        "params": {**PARAMS, "objective": "binary"}, "best_iteration": model.best_iteration,
        "rows": len(preds), "status_counts": preds["status"].value_counts().to_dict(),
        "dev_metrics_not_via_evaluator": metrics,
    }  # fmt: skip
    (run / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(pd.DataFrame(metrics).round(4).to_string(index=False))
    print(imp.nlargest(10, "gain").to_string(index=False))
    return run


CANCEL = {**DELAY, "target": "cancellation", "model_version": "lgbm_cancellation_v1"}
ALL_RUN_ID = "lgbm_dev"
TOP_K = 5
SHAP_CHUNK = 200_000


def dev_requests(root: Path, task: str) -> pd.DataFrame:
    lo, hi = bounds(DEV_SPLITS[0])[0], bounds(DEV_SPLITS[-1])[1]
    t = ds.field("target_start_utc")
    return in_scope(
        ds.dataset(root / REQUESTS)
        .to_table(
            columns=baselines.REQUEST_COLUMNS,
            filter=(ds.field("task") == task)
            & (t >= pa.scalar(lo, pa.timestamp("us", "UTC")))
            & (t < pa.scalar(hi, pa.timestamp("us", "UTC"))),
        )
        .to_pandas()
    ).reset_index(drop=True)


def dev_inputs(root: Path, task: str, airports: list[str]):
    """In-scope dev requests, their assembled rows and LightGBM input frame."""
    requests = dev_requests(root, task)
    X = pd.concat(
        [input_qa.assemble(task, root, s) for s in DEV_SPLITS], ignore_index=True
    )
    input_qa.validate_inputs(X, task, root)
    df = requests.merge(
        X, on="prediction_id", how="left", suffixes=("", "_x"), validate="one_to_one"
    )
    return requests, df, model_frame(df[registry.model_inputs(task)], airports)


def shap_drivers(
    model, feats: pd.DataFrame, ids: pd.Series, target: str, scale: str
) -> pd.DataFrame:
    """Top TOP_K features by |SHAP| per row (LightGBM pred_contrib), computed in chunks."""
    names = np.array(feats.columns)
    parts = []
    for start in range(0, len(feats), SHAP_CHUNK):
        chunk = feats.iloc[start : start + SHAP_CHUNK]
        contrib = model.predict(
            chunk, num_iteration=model.best_iteration, pred_contrib=True
        )[:, :-1]
        top = np.argsort(-np.abs(contrib), axis=1)[:, :TOP_K]
        rows = np.repeat(np.arange(len(chunk)), TOP_K)
        cols = top.ravel()
        values = chunk.to_numpy(dtype=object)[rows, cols]
        parts.append(
            pd.DataFrame(
                {
                    "prediction_id": ids.iloc[start : start + SHAP_CHUNK].to_numpy()[
                        rows
                    ],
                    "target_kind": target,
                    "feature": names[cols],
                    "value": [None if pd.isna(v) else str(v) for v in values],
                    "contribution": contrib[rows, cols].astype("float64"),
                    "contribution_scale": scale,
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


def binary_metrics(preds: pd.DataFrame, labels_path: Path, target: str) -> list[dict]:
    from sklearn.metrics import average_precision_score, brier_score_loss

    lab = training_labels(labels_path, preds["prediction_id"].tolist(), target)
    scored = preds.merge(lab, on="prediction_id")
    scored["split"] = np.where(
        scored.target_start_utc < bounds("calibration")[0], "validation", "calibration"
    )
    return [
        {"split": sp, "airport": a, "n_eligible": len(g), "prevalence": float(g.y_true.mean()),
         "pr_auc": float(average_precision_score(g.y_true, g.estimate)),
         "brier": float(brier_score_loss(g.y_true, g.estimate))}
        for (sp, a), g in scored.groupby(["split", "airport_icao"])
    ]  # fmt: skip


def all_main(
    root: Path = Path("."), artifacts: Path = ARTIFACTS, labels_path: Path = LABELS
) -> Path:
    """One run with throughput (point + p10/p90), severe delay and cancellation, plus boosters
    and per-prediction SHAP drivers. Same params, seeds and subsamples as the separate runs."""
    airports = list(
        yaml.safe_load((root / "configs/airports.yaml").read_text())["airports"]
    )
    run = artifacts / ALL_RUN_ID
    run.mkdir(parents=True, exist_ok=True)
    snapshot_id = min(
        set(
            ds.dataset(root / registry.PROCESSED / registry.WEATHER_TABLE)
            .to_table(columns=["data_snapshot_id"]).column(0).to_pylist()
        )
    )  # fmt: skip
    now = datetime.now(UTC)
    # Throughput.
    tX, ty = labelled("train", root, airports, labels_path)
    vX, vy = labelled("validation", root, airports, labels_path)
    tp_models = [
        fit(tX, ty, vX, vy),
        fit(tX, ty, vX, vy, {"objective": "quantile", "alpha": 0.1}),
        fit(tX, ty, vX, vy, {"objective": "quantile", "alpha": 0.9}),
    ]
    tp_req, tp_df, tp_feats = dev_inputs(root, TASK, airports)
    tp_x = tp_df[["prediction_id", *registry.model_inputs(TASK), *input_qa.STATUS]]
    frames = [predictions_frame(tp_req, tp_x, tp_models, airports)]
    drivers = [
        shap_drivers(
            tp_models[0], tp_feats, tp_req["prediction_id"], TARGET, "touchdowns/h"
        )
    ]
    best = {"throughput": [m.best_iteration for m in tp_models]}
    tp_models[0].save_model(run / f"model_{TARGET}.txt")
    del tX, vX
    # Severe delay and cancellation share the flight requests and inputs.
    req, df, feats = dev_inputs(root, DELAY["task"], airports)
    ok = df["status"].eq("ok") & df["demand_status"].eq("ok")
    reasons = [
        sorted(set(a) | set(b))
        for a, b in zip(df["reason_codes"], df["demand_reason_codes"])
    ]
    metrics, sizes = {}, {}
    for spec in (DELAY, CANCEL):
        args = (root, airports, labels_path, spec["task"], spec["target"])
        trX, trY = labelled("train", *args, sample=spec["train_sample"])
        vaX, vaY = labelled("validation", *args, sample=spec["val_sample"])
        model = fit(trX, trY, vaX, vaY, {"objective": "binary"})
        del trX, vaX
        model.save_model(run / f"model_{spec['target']}.txt")
        best[spec["target"]] = model.best_iteration
        sizes[spec["target"]] = {"train": len(trY), "validation": len(vaY)}
        frames.append(
            req[baselines.REQUEST_COLUMNS].assign(
                target_kind=spec["target"],
                estimate=model.predict(feats, num_iteration=model.best_iteration),
                p10=np.nan,
                p90=np.nan,
                unit=spec["unit"],
                status=np.where(ok, "available", "degraded"),
                reason_codes=reasons,
                model_version=spec["model_version"],
                feature_version=registry.REGISTRY_VERSION,
            )
        )
        drivers.append(
            shap_drivers(model, feats, req["prediction_id"], spec["target"], "log-odds")
        )
        metrics[spec["target"]] = binary_metrics(
            frames[-1], labels_path, spec["target"]
        )
    preds = pd.concat(frames, ignore_index=True).assign(
        data_snapshot_id=snapshot_id, generated_at_utc=now
    )
    baselines.write_predictions(preds, run / "predictions.parquet")
    pd.concat(drivers, ignore_index=True).to_parquet(
        run / "shap_drivers.parquet", index=False
    )
    manifest = {
        "run_id": ALL_RUN_ID,
        "producer": "airbus_challenge.train",
        "model_versions": sorted(preds["model_version"].unique()),
        "targets": sorted(preds["target_kind"].unique()),
        "commit": baselines.git("rev-parse", "HEAD"),
        "commit_dirty": baselines.source_dirty(),
        "data_mode": str(preds["data_mode"].iloc[0]),
        "data_snapshot_id": snapshot_id,
        "fit_split": "train",
        "early_stopping_split": "validation",
        "fit_cutoff_utc": cutoff().isoformat(),
        "prediction_requests_sha256": sha256(root / REQUESTS),
        "train_airports": airports,
        "registry_sha256": registry.to_json(registry.build())["content_sha256"],
        "params": PARAMS,
        "binary_objective": "binary",
        "best_iteration": best,
        "subsample_rows": sizes,
        "shap": {
            "method": "lightgbm pred_contrib",
            "top_k": TOP_K,
            "scales": {"throughput": "touchdowns/h", "binary": "log-odds"},
            "note": "associations, not causes",
        },
        "rows_by_target": preds["target_kind"].value_counts().to_dict(),
        "status_counts": preds.groupby("target_kind")["status"]
        .value_counts()
        .unstack(fill_value=0)
        .to_dict("index"),
        "dev_metrics_not_via_evaluator": metrics,
    }
    (run / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(run, manifest["rows_by_target"], best)
    for t, m in metrics.items():
        print(t)
        print(pd.DataFrame(m).round(4).to_string(index=False))
    return run


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--task", choices=["throughput", "severe_delay", "all"], default="throughput"
    )
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    args = parser.parse_args()
    run = {"throughput": main, "severe_delay": delay_main, "all": all_main}[args.task]
    run(artifacts=args.artifacts)
