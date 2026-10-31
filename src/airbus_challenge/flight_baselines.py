import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

from airbus_challenge.baselines import (
    AIRPORTS,
    ARTIFACTS,
    DATA_MODES,
    EXPERIMENT,
    REQUEST_COLUMNS,
    REQUESTS,
    RETROSPECTIVE_SCHEDULE,
    git,
    in_split,
    source_dirty,
    split_bounds,
    write_predictions,
)
from airbus_challenge.download import sha256
from airbus_challenge.evaluate import CONDITIONAL_RATE, LABELS, LOGISTIC, SEVERE

TASK = "severe_delay"
CANCELLATION = "cancellation"
TARGETS = (SEVERE, CANCELLATION)
UNIT = "binary"
RUN_ID = "baselines_flight_dev"
VERSION = "flight-baseline-v1"
# Pseudo-flights pulling a group toward its airport rate, and an airport toward the pooled rate.
PRIOR_STRENGTH = 50
# A thinner airport x local-hour group uses the airport rate.
MIN_GROUP_N = 30
GROUP = ["airport_icao", "local_hour"]
FEATURES = ["airport_icao", "local_hour", "local_weekday", "month"]
LOGISTIC_C = 1.0
DEV_SPLITS = ("validation", "calibration")


def calendar(requests: pd.DataFrame) -> pd.DataFrame:
    # Scheduled departure in airport local time; known at issue under the retrospective schedule.
    out = pd.DataFrame(np.nan, index=requests.index, columns=FEATURES[1:])
    for icao, rows in requests.groupby("airport_icao"):
        if icao not in AIRPORTS:
            continue
        local = rows["target_start_utc"].dt.tz_convert(AIRPORTS[icao]["timezone"])
        out.loc[rows.index, "local_hour"] = local.dt.hour
        out.loc[rows.index, "local_weekday"] = local.dt.day_of_week
        out.loc[rows.index, "month"] = local.dt.month
    return out.assign(airport_icao=requests["airport_icao"])


def training_rows(
    requests: pd.DataFrame, labels: pd.DataFrame, target: str
) -> pd.DataFrame:
    # One row per train flight: every horizon of a flight shares its outcome.
    train = in_split(requests[requests["task"].eq(TASK)], "train", "target_start_utc")
    train = train.sort_values("horizon_h").drop_duplicates("flight_id")
    # Ineligible labels (cancelled for severe delay, unknown status) leave the denominator.
    eligible = labels[labels["target_kind"].eq(target) & labels["eligible"]]
    rows = train.merge(eligible[["prediction_id", "y_true"]], on="prediction_id")
    return pd.concat([calendar(rows), rows["y_true"].rename("y")], axis=1).dropna()


def fit_rates(rows: pd.DataFrame) -> dict:
    pooled = rows["y"].mean()
    by_airport = rows.groupby("airport_icao")["y"].agg(["sum", "size"])
    airport = (by_airport["sum"] + PRIOR_STRENGTH * pooled) / (
        by_airport["size"] + PRIOR_STRENGTH
    )
    group = rows.groupby(GROUP)["y"].agg(["sum", "size"])
    prior = airport.reindex(group.index.get_level_values(0)).to_numpy()
    group["rate"] = (group["sum"] + PRIOR_STRENGTH * prior) / (
        group["size"] + PRIOR_STRENGTH
    )
    return {"pooled": float(pooled), "airport": airport, "group": group}


def conditional_rate(
    scored: pd.DataFrame, keys: pd.DataFrame, fit: dict
) -> tuple[np.ndarray, list[list[str]]]:
    index = pd.MultiIndex.from_arrays([keys["airport_icao"], keys["local_hour"]])
    group = fit["group"].reindex(index)
    n = group["size"].fillna(0).to_numpy()
    airport = fit["airport"].reindex(scored["airport_icao"]).to_numpy()
    configured = keys["local_hour"].notna().to_numpy()
    seen = ~np.isnan(airport)
    estimate = np.where(n >= MIN_GROUP_N, group["rate"].to_numpy(), airport)
    estimate = np.where(seen, estimate, fit["pooled"])
    estimate = np.where(configured, estimate, np.nan)
    reasons = [
        ["airport_not_configured"]
        if not c
        else ["airport_not_in_train_pooled_rate"]
        if not s
        else ["unseen_group_airport_rate"]
        if k == 0
        else ["rare_group_airport_rate"]
        if k < MIN_GROUP_N
        else []
        for c, s, k in zip(configured, seen, n)
    ]
    return estimate, reasons


def encode(keys: pd.DataFrame) -> pd.DataFrame:
    return keys[FEATURES].astype({c: int for c in FEATURES[1:]}).astype(str)


def fit_logistic(rows: pd.DataFrame):
    model = make_pipeline(
        OneHotEncoder(handle_unknown="ignore"),
        LogisticRegression(C=LOGISTIC_C, max_iter=1000),
    )
    return model.fit(encode(rows), rows["y"].astype(int))


def logistic(
    scored: pd.DataFrame, keys: pd.DataFrame, model, train_airports: set[str]
) -> tuple[np.ndarray, list[list[str]]]:
    configured = keys["local_hour"].notna().to_numpy()
    estimate = np.full(len(keys), np.nan)
    if configured.any():
        estimate[configured] = model.predict_proba(encode(keys[configured]))[:, 1]
    seen = scored["airport_icao"].isin(train_airports).to_numpy()
    reasons = [
        ["airport_not_configured"]
        if not c
        else []
        if s
        else ["airport_not_in_train_no_airport_term"]
        for c, s in zip(configured, seen)
    ]
    return estimate, reasons


def _predictions(scored, target, model, estimate, reasons) -> pd.DataFrame:
    reasons = [[RETROSPECTIVE_SCHEDULE, *r] for r in reasons]
    status = np.where(
        np.isnan(estimate),
        "unavailable",
        np.where([len(r) > 1 for r in reasons], "degraded", "available"),
    )
    return scored[REQUEST_COLUMNS].assign(
        target_kind=target,
        estimate=estimate,
        p10=np.nan,
        p90=np.nan,
        unit=UNIT,
        status=status,
        reason_codes=reasons,
        model_version=model,
        feature_version=VERSION,
    )


def scored_requests(requests: pd.DataFrame) -> pd.DataFrame:
    flights = requests[requests["task"].eq(TASK)]
    scored = pd.concat([in_split(flights, s, "target_start_utc") for s in DEV_SPLITS])
    # At the start of validation, T can precede the fit cutoff the fits rely on.
    return scored[scored["as_of_utc"].ge(split_bounds("train")[1])]


def flight_baselines(
    requests: pd.DataFrame, labels: pd.DataFrame
) -> tuple[pd.DataFrame, dict]:
    scored = scored_requests(requests)
    keys = calendar(scored)
    frames, summary = [], {}
    for target in TARGETS:
        rows = training_rows(requests, labels, target)
        rates = fit_rates(rows)
        frames.append(
            _predictions(
                scored, target, CONDITIONAL_RATE, *conditional_rate(scored, keys, rates)
            )
        )
        train_airports = set(rows["airport_icao"])
        model = fit_logistic(rows)
        frames.append(
            _predictions(
                scored, target, LOGISTIC, *logistic(scored, keys, model, train_airports)
            )
        )
        summary[target] = {
            "train_flights": len(rows),
            "train_positives": int(rows["y"].sum()),
            "pooled_rate": rates["pooled"],
            "airport_rate": rates["airport"].to_dict(),
            "airport_train_flights": rows["airport_icao"].value_counts().to_dict(),
            "groups": len(rates["group"]),
            "groups_below_min_n": int(rates["group"]["size"].lt(MIN_GROUP_N).sum()),
        }
    return pd.concat(frames, ignore_index=True), summary


def main(
    requests_path: Path = REQUESTS, labels_path: Path = LABELS, artifacts=ARTIFACTS
) -> Path:
    path = artifacts / RUN_ID / "predictions.parquet"
    commit, commit_dirty = git("rev-parse", "HEAD"), source_dirty()
    requests_sha256, labels_sha256 = sha256(requests_path), sha256(labels_path)
    source = json.loads(requests_path.with_suffix(".manifest.json").read_text())
    train_start, fit_cutoff = split_bounds("train")
    test_start, _ = split_bounds("test")
    requests = pd.read_parquet(
        requests_path,
        columns=REQUEST_COLUMNS,
        filters=[("task", "==", TASK), ("target_start_utc", "<", test_start)],
    )
    # Only train outcomes are read: validation, calibration and 2025 labels never load.
    train_ids = in_split(requests, "train", "target_start_utc")["prediction_id"]
    labels = pd.read_parquet(
        labels_path,
        columns=["prediction_id", "target_kind", "y_true", "eligible", "data_mode"],
        filters=[
            ("prediction_id", "in", train_ids.tolist()),
            ("target_kind", "in", list(TARGETS)),
        ],
    )
    modes = set(requests["data_mode"]) | set(labels["data_mode"])
    if len(modes) != 1 or not modes <= DATA_MODES:
        raise ValueError(f"expected one data_mode of {DATA_MODES}, got {modes}")
    data_mode = modes.pop()
    predictions, summary = flight_baselines(requests, labels)
    snapshot = source["source_flights_sha256"]
    predictions = predictions.assign(
        data_snapshot_id=snapshot, generated_at_utc=datetime.now(UTC)
    )
    counts = predictions.groupby(["model_version", "target_kind", "status"]).size()
    manifest = {
        "run_id": RUN_ID,
        "producer": "airbus_challenge.flight_baselines",
        "producer_version": VERSION,
        "commit": commit,
        "commit_dirty": commit_dirty,
        "data_mode": data_mode,
        "data_snapshot_id": snapshot,
        "prediction_requests_sha256": requests_sha256,
        "labels_sha256": labels_sha256,
        "targets": list(TARGETS),
        "fit_split": EXPERIMENT["splits"]["train"],
        "fit_bounds_utc": [train_start.isoformat(), fit_cutoff.isoformat()],
        "fit_cutoff_utc": fit_cutoff.isoformat(),
        "fit_availability": "simulated: train outcomes are treated as known at the "
        "cutoff, though BTS publishes months later",
        "schedule_knowledge_basis": RETROSPECTIVE_SCHEDULE,
        "conditional_rate": {
            "group": GROUP,
            "smoothing": "additive: (k + m * airport_rate) / (n + m); airport rate "
            "smoothed the same way toward the pooled train rate",
            "prior_strength_m": PRIOR_STRENGTH,
            "min_group_n": MIN_GROUP_N,
        },
        "logistic": {"features": FEATURES, "encoding": "one-hot", "C": LOGISTIC_C},
        "train_counts": summary,
        "rows": len(predictions),
        "status_counts": {"|".join(k): int(v) for k, v in counts.items()},
    }
    write_predictions(predictions, path)
    part = path.with_name("manifest.json.part")
    part.write_text(json.dumps(manifest, indent=2, default=int))
    part.replace(path.with_name("manifest.json"))
    print(path, f"data_mode={data_mode}")
    print(counts)
    return path


if __name__ == "__main__":
    main()
