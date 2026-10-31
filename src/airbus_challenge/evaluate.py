import argparse
import json
from datetime import UTC, datetime
from itertools import cycle, product
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.metrics import average_precision_score, precision_recall_curve

from airbus_challenge.baselines import (
    AIRPORTS,
    ARTIFACTS,
    DATA_MODES,
    EXPERIMENT,
    PREDICTION_SCHEMA,
    REQUESTS,
    RETROSPECTIVE_SCHEDULE,
    SIMULATED_FEED,
    SOURCE_PATHS,
    TARGET,
    TARGET_LABEL,
    check_predictions,
    claim_locked_run,
    git,
    source_dirty,
    split_bounds,
)
from airbus_challenge.download import sha256

LABELS = Path("data/labels/labels.parquet")
REPORTS = Path("reports")
CONFIGS = [Path("configs/airports.yaml"), Path("configs/experiment.yaml")]

SEVERE = EXPERIMENT["targets"]["severe_delay"]
CAPACITY_RATIO = EXPERIMENT["targets"]["capacity_ratio"]
BINARY = {SEVERE, "cancellation"}
TARGET_LABELS = {
    TARGET: TARGET_LABEL,
    CAPACITY_RATIO: f"{TARGET_LABEL} over clear-weather ceiling",
    SEVERE: "severe departure delay (>45 min, operated flights)",
}
PERSISTENCE = "baseline_persistence_v1"
CLIMATOLOGY = "baseline_climatology_v1"
REQUIRED_BASELINES = (PERSISTENCE, CLIMATOLOGY)
ASSUMPTIONS = {SIMULATED_FEED, RETROSPECTIVE_SCHEDULE}
EXCLUSION_REASONS = {
    "cancelled",
    "coverage_incomplete",
    "missing_outcome",
    "quarantined",
}
REQUEST_KEYS = [
    "prediction_id",
    "task",
    "airport_icao",
    "as_of_utc",
    "target_start_utc",
    "horizon_h",
    "cohort_version",
    "data_mode",
]
LABEL_KEYS = ["prediction_id", "target_kind", "unit", "label_version"]
# Each has one locked run. Anything else on the test split is exploratory.
LOCKED_EXPERIMENTS = ["primary", "csv_only", *(f"leave_out_{i}" for i in AIRPORTS)]
METRIC_DEFINITIONS = {
    "average_precision": "sklearn.metrics.average_precision_score, step-wise",
    "recall_at_precision": (
        "best recall on the scored rows' own curve, a summary and not an operating "
        "point: its threshold is not frozen in advance"
    ),
    "pooled": "rows weighted equally: by flight for flight tasks, by airport-hour "
    "for airport tasks, so airport tasks are not volume-weighted. At horizon all, "
    "each target counts once per horizon",
    "macro": "unweighted mean over every configured airport, null unless all are "
    "defined",
    "common_support": "rows where every model active in the cell gave an estimate",
    "baseline_support": "rows the model and both required baselines all scored; "
    "skill is measured only here",
    "operational_day": "24 h from 08:00 UTC, near the overnight traffic trough",
}

SPLITS = ("validation", "calibration", "test")
SCOPE = ["split", "cohort_version", "target_kind"]
CELL = [*SCOPE, "airport_icao", "horizon_h"]
POOLED = "pooled"
MACRO = "macro"
ALL_HORIZONS = "all"
RESAMPLES = 1000
MIN_CI_DAYS = 20
CI_METHOD = f"operational_day_block_bootstrap_{RESAMPLES}_percentile_95"
NO_CI = {"ci_low": None, "ci_high": None, "ci_method": None, "ci_reason": None}
# 00Z is evening at KATL and KDFW, so a UTC day would cut through peak storm hours.
DAY_OFFSET = pd.Timedelta(hours=8)
# Curve summaries, not validated alert thresholds.
RECALL_PRECISIONS = (0.25, 0.5)
RECALL_NAMES = [f"recall_at_precision_{p:g}" for p in RECALL_PRECISIONS]
RELIABILITY_BINS = 10
WORST_N = 3

# Colour follows the model, so a filtered chart never repaints a series.
BASELINE_COLOURS = {
    PERSISTENCE: "#eb6834",
    CLIMATOLOGY: "#1baf7a",
    "baseline_seasonal_persistence_v1": "#eda100",
    "baseline_schedule_v1": "#e87ba4",
}
CANDIDATE_COLOURS = ["#2a78d6", "#008300", "#6250d6"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED_INK = "#52514e"
GRID = "#e6e5e1"


def is_baseline(models: pd.Series) -> pd.Series:
    return models.isin(BASELINE_COLOURS)


def split_of(targets: pd.Series) -> pd.Series:
    names = pd.Series(pd.NA, index=targets.index, dtype="string")
    for name in SPLITS:
        start, end = split_bounds(name)
        names[targets.ge(start) & targets.lt(end)] = name
    return names


def load_predictions(
    artifacts: Path,
    runs: list[str],
    locked_test: bool,
    cohorts: list[str] | None = None,
) -> pd.DataFrame:
    predictions = pd.concat(
        [pd.read_parquet(artifacts / r / "predictions.parquet") for r in runs],
        ignore_index=True,
    )
    # A stray y_true or eligible column would otherwise override the labels.
    extra = set(predictions) - set(PREDICTION_SCHEMA.names)
    if extra:
        raise ValueError(f"predictions must not carry {sorted(extra)}")
    if cohorts:
        predictions = predictions[predictions["cohort_version"].isin(cohorts)]
        if predictions.empty:
            raise ValueError(f"no predictions for cohorts {cohorts}")
    check_predictions(predictions)
    predictions["split"] = split_of(predictions["target_start_utc"])
    if predictions["split"].isna().any():
        raise ValueError("prediction outside validation, calibration and test")
    # Dev runs never touch the test split (docs/WORK_PLAN.md test-set rule).
    if predictions["split"].eq("test").ne(locked_test).any():
        raise ValueError(f"expected only {'test' if locked_test else 'dev'} rows")
    return predictions


def check_contract(predictions: pd.DataFrame) -> None:
    if np.isinf(predictions["estimate"]).any():
        raise ValueError("estimate must be finite")
    if predictions["reason_codes"].isna().any():
        raise ValueError("reason_codes must not be null")
    binary = predictions["target_kind"].isin(BINARY)
    if not predictions.loc[binary, "estimate"].dropna().between(0, 1).all():
        raise ValueError("probability outside [0, 1]")
    if predictions["p10"].gt(predictions["p90"]).any():
        raise ValueError("p10 above p90")
    if not predictions["horizon_h"].isin(EXPERIMENT["horizons_h"]).all():
        raise ValueError(f"horizon_h outside {EXPERIMENT['horizons_h']}")


def check_requests(predictions: pd.DataFrame, requests: pd.DataFrame) -> None:
    if requests["prediction_id"].duplicated().any():
        raise ValueError("duplicate prediction_id in requests")
    # Labels carry no time, so requests vouch for each id's target and split.
    rows = predictions[REQUEST_KEYS].drop_duplicates()
    matched = rows.merge(requests[REQUEST_KEYS], how="left", indicator=True)
    stray = matched[matched["_merge"].ne("both")]
    if len(stray):
        raise ValueError(f"no matching request for {stray['prediction_id'].iloc[0]}")
    fit_cutoff = split_bounds("train")[1]
    expected = requests[requests["as_of_utc"].ge(fit_cutoff)]
    expected = expected.assign(split=split_of(expected["target_start_utc"]))
    keys = ["split", "task", "cohort_version", "target_kind", "model_version"]
    for (split, task, cohort, target, model), frame in predictions.groupby(keys):
        scope = (
            expected["split"].eq(split)
            & expected["task"].eq(task)
            & expected["cohort_version"].eq(cohort)
        )
        wanted = expected.loc[scope.fillna(False), "prediction_id"]
        absent = wanted[~wanted.isin(frame["prediction_id"])]
        if len(absent):
            raise ValueError(
                f"{model} has no {target} row for {absent.iloc[0]}; "
                "a request it cannot score must be marked unavailable"
            )


def check_baselines(predictions: pd.DataFrame) -> None:
    usable = predictions[predictions["estimate"].notna()]
    for cell, frame in usable.groupby(CELL):
        ids = frame.groupby("model_version")["prediction_id"].agg(set)
        candidates = ids[~is_baseline(ids.index.to_series())]
        if candidates.empty:
            continue
        missing = set(REQUIRED_BASELINES) - set(ids.index)
        if missing:
            raise ValueError(f"{cell}: a model needs baselines {sorted(missing)}")
        shared = ids[PERSISTENCE] & ids[CLIMATOLOGY]
        for model, rows in candidates.items():
            if not rows & shared:
                raise ValueError(f"{cell}: {model} shares no row with both baselines")


def check_locked_candidates(predictions: pd.DataFrame) -> None:
    candidates = predictions[~is_baseline(predictions["model_version"])]
    scope = ["cohort_version", "target_kind"]
    per_target = candidates.groupby(scope)["model_version"].nunique()
    targets = set(predictions[scope].itertuples(index=False, name=None))
    if set(per_target.index) != targets or per_target.ne(1).any():
        raise ValueError(f"locked test needs one frozen model for each of {targets}")
    # A candidate that scores nothing would spend the run on an all-null report.
    cells = predictions[CELL].drop_duplicates()
    usable = candidates[candidates["estimate"].notna()][CELL].drop_duplicates()
    empty = cells.merge(usable, how="left", indicator=True)
    empty = empty[empty["_merge"].ne("both")]
    if len(empty):
        raise ValueError(f"no usable estimate in {empty[CELL].iloc[0].to_dict()}")


def check_run_manifests(artifacts: Path, runs: list[str]) -> None:
    for run in runs:
        manifest = json.loads((artifacts / run / "manifest.json").read_text())
        if manifest["run_id"] != run:
            raise ValueError(f"{run}: manifest belongs to {manifest['run_id']}")
        if manifest["data_mode"] != "real":
            raise ValueError(f"{run}: locked test needs real data")
        if manifest["commit_dirty"] is not False:
            raise ValueError(f"{run}: built from uncommitted code")


def labels_data_mode(path: Path) -> str:
    if "data_mode" not in pq.read_schema(path).names:
        raise ValueError("labels need a data_mode column of real or fixture")
    modes = pd.read_parquet(path, columns=["data_mode"])["data_mode"].unique()
    if len(modes) != 1:
        raise ValueError(f"mixed labels data_mode {sorted(modes)}")
    return modes[0]


def check_label_keys(path: Path, predictions: pd.DataFrame) -> None:
    # Outcome-free columns only, so broken labels are refused before a locked claim.
    ids = predictions["prediction_id"].unique().tolist()
    keys = pd.read_parquet(
        path, columns=LABEL_KEYS, filters=[("prediction_id", "in", ids)]
    )
    if keys["label_version"].nunique() > 1:
        raise ValueError("labels must hold one label_version")
    key = ["prediction_id", "target_kind"]
    if keys.duplicated(key).any():
        raise ValueError("more than one label for a prediction and target")
    joined = predictions[[*key, "unit"]].merge(
        keys, on=key, how="left", suffixes=("", "_label"), indicator=True
    )
    unlabelled = joined[joined["_merge"].ne("both")]
    if len(unlabelled):
        raise ValueError(f"no label for {unlabelled['prediction_id'].iloc[0]}")
    mismatch = joined[joined["unit"].ne(joined["unit_label"])]
    if len(mismatch):
        row = mismatch.iloc[0]
        raise ValueError(
            f"{row['target_kind']}: prediction unit {row['unit']} "
            f"!= label unit {row['unit_label']}"
        )


def load_labels(path: Path, prediction_ids: list[str]) -> pd.DataFrame:
    # Filtered at read, so a dev run never loads labels for test rows.
    labels = pd.read_parquet(path, filters=[("prediction_id", "in", prediction_ids)])
    if labels["eligible"].eq(labels["exclusion_reason"].notna()).any():
        raise ValueError("exclusion_reason must be null exactly when eligible")
    unknown = set(labels["exclusion_reason"].dropna()) - EXCLUSION_REASONS
    if unknown:
        raise ValueError(f"unknown exclusion_reason {sorted(unknown)}")
    if labels.loc[labels["eligible"], "y_true"].isna().any():
        raise ValueError("eligible label without an outcome")
    binary = labels["target_kind"].isin(BINARY) & labels["eligible"]
    if not labels.loc[binary, "y_true"].isin([0, 1]).all():
        raise ValueError("binary labels must be exactly 0 or 1")
    return labels


def join_labels(predictions: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    key = ["prediction_id", "target_kind"]
    columns = [*key, "y_true", "eligible", "exclusion_reason"]
    joined = predictions.merge(labels[columns], on=key, how="inner", validate="m:1")
    shifted = joined["target_start_utc"] - DAY_OFFSET
    return joined.assign(
        eligible=lambda d: d["eligible"].astype(bool),
        day=shifted.dt.tz_convert(None).dt.floor("D"),
    )


def mark_common(joined: pd.DataFrame) -> pd.DataFrame:
    scored = joined["eligible"] & joined["estimate"].notna()
    rows = joined[scored]
    n_active = rows.groupby(CELL)["model_version"].transform("nunique")
    n_models = rows.groupby(["prediction_id", "target_kind"])["model_version"]
    common = n_models.transform("nunique").eq(n_active)
    return joined.assign(
        scored=scored, common=common.reindex(joined.index, fill_value=False)
    )


def _mean(n: np.ndarray, total: np.ndarray) -> np.ndarray:
    return total / n


def _root_mean(n: np.ndarray, total: np.ndarray) -> np.ndarray:
    return np.sqrt(total / n)


def _rmse_skill(n: np.ndarray, model: np.ndarray, base: np.ndarray) -> np.ndarray:
    return 1 - np.sqrt(model / base)


def _brier_skill(n: np.ndarray, model: np.ndarray, base: np.ndarray) -> np.ndarray:
    return 1 - model / base


def _ci(days: pd.Series, stat, *columns: np.ndarray) -> dict:
    # Hours, horizons and airports within a day are correlated: resample whole days.
    index, unique = pd.factorize(days)
    n_days = len(unique)
    if n_days < MIN_CI_DAYS:
        return {**NO_CI, "ci_reason": "too_few_days"}
    rng = np.random.default_rng(EXPERIMENT["seed"])
    draws = rng.multinomial(n_days, np.full(n_days, 1 / n_days), size=RESAMPLES)
    totals = [draws @ np.bincount(index, column) for column in columns]
    with np.errstate(divide="ignore", invalid="ignore"):
        values = stat(draws @ np.bincount(index), *totals)
    if not np.isfinite(values).all():
        return {**NO_CI, "ci_reason": "nonfinite_resample"}
    low, high = np.percentile(values, [2.5, 97.5])
    return {
        "ci_low": float(low),
        "ci_high": float(high),
        "ci_method": CI_METHOD,
        "ci_reason": None,
    }


def _metric(
    name: str,
    value: float | None,
    unit: str,
    ci: dict | None = None,
    reason: str | None = None,
) -> dict:
    return {
        "metric": name,
        "value": None if value is None else float(value),
        "unit": unit,
        **(ci or NO_CI),
        "reason": reason,
    }


def metric_units(binary: bool, unit: str) -> dict[str, str]:
    if binary:
        recall = {name: "share" for name in RECALL_NAMES}
        return {"brier": "probability^2", "average_precision": "share", **recall}
    return {
        "rmse": unit,
        "mae": unit,
        "bias": unit,
        "p10_p90_coverage": "share",
        "p10_p90_width": unit,
        "pinball_loss": unit,
    }


def null_metrics(names: dict[str, str], reason: str) -> list[dict]:
    return [_metric(name, None, unit, reason=reason) for name, unit in names.items()]


def _pinball(y: pd.Series, quantile: pd.Series, q: float) -> pd.Series:
    gap = y - quantile
    return np.maximum(q * gap, (q - 1) * gap)


def interval_metrics(rows: pd.DataFrame) -> list[dict]:
    unit = rows["unit"].iloc[0]
    if rows[["p10", "p90"]].isna().any(axis=None):
        units = metric_units(False, unit)
        names = ["p10_p90_coverage", "p10_p90_width", "pinball_loss"]
        return null_metrics({k: units[k] for k in names}, "no_complete_intervals")
    y, p10, p90 = rows["y_true"], rows["p10"], rows["p90"]
    days = rows["day"]
    inside = y.between(p10, p90).to_numpy(float)
    width = (p90 - p10).to_numpy()
    pinball = ((_pinball(y, p10, 0.1) + _pinball(y, p90, 0.9)) / 2).to_numpy()
    return [
        _metric("p10_p90_coverage", inside.mean(), "share", _ci(days, _mean, inside)),
        _metric("p10_p90_width", width.mean(), unit, _ci(days, _mean, width)),
        _metric("pinball_loss", pinball.mean(), unit, _ci(days, _mean, pinball)),
    ]


def regression_metrics(rows: pd.DataFrame) -> list[dict]:
    unit = rows["unit"].iloc[0]
    days = rows["day"]
    error = (rows["estimate"] - rows["y_true"]).to_numpy()
    squared, absolute = error**2, np.abs(error)
    return [
        _metric("rmse", np.sqrt(squared.mean()), unit, _ci(days, _root_mean, squared)),
        _metric("mae", absolute.mean(), unit, _ci(days, _mean, absolute)),
        _metric("bias", error.mean(), unit, _ci(days, _mean, error)),
        *interval_metrics(rows),
    ]


def classification_metrics(rows: pd.DataFrame) -> list[dict]:
    y, p = rows["y_true"].to_numpy(), rows["estimate"].to_numpy()
    squared = (p - y) ** 2
    units = metric_units(True, "")
    metrics = [
        _metric(
            "brier", squared.mean(), units["brier"], _ci(rows["day"], _mean, squared)
        )
    ]
    if len(np.unique(y)) < 2:
        names = {k: "share" for k in ["average_precision", *RECALL_NAMES]}
        return metrics + null_metrics(names, "single_class")
    metrics.append(_metric("average_precision", average_precision_score(y, p), "share"))
    precision, recall, _ = precision_recall_curve(y, p)
    # The curve's last point is a fixed (1, 0) sentinel, not a real threshold.
    precision, recall = precision[:-1], recall[:-1]
    for name, floor in zip(RECALL_NAMES, RECALL_PRECISIONS):
        reached = recall[precision >= floor]
        metrics.append(
            _metric(name, reached.max(), "share")
            if reached.size
            else _metric(name, None, "share", reason="precision_not_reached")
        )
    return metrics


def squared_errors(scored: pd.DataFrame) -> pd.DataFrame:
    return scored.assign(se=(scored["estimate"] - scored["y_true"]) ** 2).pivot(
        index="prediction_id", columns="model_version", values="se"
    )


def baseline_support(squared: pd.DataFrame, model: str) -> pd.DataFrame:
    if model not in squared:
        return squared.iloc[:0]
    columns = dict.fromkeys([model, *REQUIRED_BASELINES])
    return squared[[c for c in columns if c in squared]].dropna()


def skill_metrics(
    support: pd.DataFrame, days: pd.Series, model: str, binary: bool
) -> list[dict]:
    baselines = [b for b in REQUIRED_BASELINES if b != model]
    if support.empty:
        names = {f"skill_vs_{b}": "share" for b in baselines}
        return null_metrics(names, "no_predicted_rows")
    days = days.reindex(support.index)
    stat = _brier_skill if binary else _rmse_skill
    metrics = []
    for baseline in baselines:
        name = f"skill_vs_{baseline}"
        if baseline not in support:
            metrics.append(_metric(name, None, "share", reason="baseline_absent"))
            continue
        model_se, base_se = support[model].to_numpy(), support[baseline].to_numpy()
        if base_se.sum() == 0:
            metrics.append(_metric(name, None, "share", reason="baseline_error_zero"))
            continue
        value = stat(1, model_se.sum(), base_se.sum())
        metrics.append(
            _metric(name, value, "share", _ci(days, stat, model_se, base_se))
        )
    return metrics


def _cell_counts(cell: pd.DataFrame, rows: pd.DataFrame, binary: bool) -> dict:
    excluded = cell[~cell["eligible"]]
    return {
        "n_eligible": int(cell["eligible"].sum()),
        "n_predicted": len(rows),
        "n_excluded": len(excluded),
        "n_degraded": int(rows["status"].eq("degraded").sum()),
        "n_days": int(rows["day"].nunique()),
        "n_targets": int(rows["target_start_utc"].nunique()),
        "exclusions": {
            str(reason): int(n)
            for reason, n in excluded["exclusion_reason"].value_counts().items()
        },
        "prevalence": float(rows["y_true"].mean()) if binary and len(rows) else None,
    }


def cancellation_rate(counts: dict) -> dict:
    cancelled = counts["exclusions"].get("cancelled", 0)
    scheduled = counts["n_eligible"] + cancelled
    if not scheduled:
        return _metric("cancellation_rate", None, "share", reason="no_flights")
    return _metric("cancellation_rate", cancelled / scheduled, "share")


def _rows(
    identity: dict,
    place: dict,
    model: str,
    basis: dict[str, list[str]],
    slice_name: str,
    metrics: list[dict],
    counts: dict,
) -> list[dict]:
    return [
        {
            **identity,
            "model": model,
            "availability_basis": basis.get(model, []),
            **place,
            "slice": slice_name,
            **metric,
            **counts,
        }
        for metric in metrics
    ]


def evaluate_target(frame: pd.DataFrame, basis: dict[str, list[str]]) -> list[dict]:
    split, target = frame["split"].iloc[0], frame["target_kind"].iloc[0]
    binary = target in BINARY
    models = sorted(frame["model_version"].unique())
    airports = [*sorted(frame["airport_icao"].unique()), POOLED]
    horizons = [*sorted(frame["horizon_h"].unique()), ALL_HORIZONS]
    empty = null_metrics(
        metric_units(binary, frame["unit"].iloc[0]), "no_predicted_rows"
    )
    identity = {
        "split": split,
        "cohort": frame["cohort_version"].iloc[0],
        "task": frame["task"].iloc[0],
        "target": target,
        "target_label": TARGET_LABELS.get(target, target),
    }
    records = []
    for airport, horizon in product(airports, horizons):
        cell = frame
        if airport != POOLED:
            cell = cell[cell["airport_icao"].eq(airport)]
        if horizon != ALL_HORIZONS:
            cell = cell[cell["horizon_h"].eq(horizon)]
        if cell.empty:
            continue
        common = cell[cell["common"]]
        scored = cell[cell["scored"]]
        squared = squared_errors(scored)
        days = scored.drop_duplicates("prediction_id").set_index("prediction_id")["day"]
        place = {
            "airport": airport,
            "horizon": int(horizon) if horizon != ALL_HORIZONS else horizon,
        }

        for model, slice_name in product(models, ["own_support", "common_support"]):
            own = cell[cell["model_version"].eq(model)]
            in_common = slice_name == "common_support"
            rows = common if in_common else own[own["scored"]]
            rows = rows[rows["model_version"].eq(model)]
            if rows.empty:
                metrics = list(empty)
            elif binary:
                metrics = classification_metrics(rows)
            else:
                metrics = regression_metrics(rows)
            counts = _cell_counts(own, rows, binary)
            if target == SEVERE and not in_common:
                metrics.append(cancellation_rate(counts))
            records += _rows(identity, place, model, basis, slice_name, metrics, counts)
        for model in models:
            own = cell[cell["model_version"].eq(model)]
            support = baseline_support(squared, model)
            rows = own[own["prediction_id"].isin(support.index)]
            counts = _cell_counts(own, rows, binary)
            skill = skill_metrics(support, days, model, binary)
            records += _rows(
                identity, place, model, basis, "baseline_support", skill, counts
            )
    return records


def macro_records(records: list[dict]) -> list[dict]:
    table = pd.DataFrame(records)
    table = table[table["airport"].ne(POOLED)]
    keys = [
        "split",
        "cohort",
        "task",
        "target",
        "target_label",
        "model",
        "horizon",
        "slice",
        "metric",
    ]
    macro = []
    for values, group in table.groupby(keys, sort=False):
        complete = group["value"].notna().all() and len(group) == len(AIRPORTS)
        exclusions: dict[str, int] = {}
        for counts in group["exclusions"]:
            for reason, n in counts.items():
                exclusions[reason] = exclusions.get(reason, 0) + n
        macro.append(
            {
                **dict(zip(keys, values)),
                "availability_basis": group["availability_basis"].iloc[0],
                "airport": MACRO,
                "unit": group["unit"].iloc[0],
                "value": float(group["value"].mean()) if complete else None,
                **NO_CI,
                "ci_reason": "not_resampled",
                "reason": None if complete else "undefined_for_an_airport",
                "n_eligible": int(group["n_eligible"].sum()),
                "n_predicted": int(group["n_predicted"].sum()),
                "n_excluded": int(group["n_excluded"].sum()),
                "n_degraded": int(group["n_degraded"].sum()),
                "n_days": int(group["n_days"].max()),
                "n_targets": int(group["n_targets"].max()),
                "exclusions": exclusions,
                "prevalence": None,
            }
        )
    return macro


def reliability(joined: pd.DataFrame) -> list[dict]:
    rows = joined[joined["target_kind"].isin(BINARY) & joined["common"]]
    bins = []
    keys = [*SCOPE, "model_version"]
    for (split, cohort, target, model), group in rows.groupby(keys):
        for airport in [*sorted(group["airport_icao"].unique()), POOLED]:
            cell = group
            if airport != POOLED:
                cell = group[group["airport_icao"].eq(airport)]
            cuts = np.linspace(0, 1, RELIABILITY_BINS + 1)[1:-1]
            # Tied probabilities stay in one bin.
            edges = np.unique(np.quantile(cell["estimate"], cuts))
            index = np.searchsorted(edges, cell["estimate"], side="left")
            table = cell.groupby(index).agg(
                mean_predicted=("estimate", "mean"),
                observed_rate=("y_true", "mean"),
                n=("y_true", "size"),
            )
            bins += [
                {
                    "split": split,
                    "cohort": cohort,
                    "target": target,
                    "model": model,
                    "airport": airport,
                    **row,
                }
                for row in table.to_dict("records")
            ]
    return bins


def _utc(moment: pd.Timestamp) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def worst_misses(joined: pd.DataFrame) -> list[dict]:
    rows = joined[joined["scored"] & ~is_baseline(joined["model_version"])]
    rows = rows.assign(error=rows["estimate"] - rows["y_true"])
    rows = rows.assign(abs_error=rows["error"].abs()).sort_values(
        ["abs_error", "prediction_id"], ascending=[False, True]
    )
    group = [*SCOPE, "model_version"]
    # One event fills every horizon, so each airport-day appears once.
    rows = rows.drop_duplicates([*group, "airport_icao", "day"])
    baselines = joined[is_baseline(joined["model_version"])]
    by_id = baselines.groupby(["prediction_id", "target_kind"])
    misses = []
    for _, row in rows.groupby(group, sort=False).head(WORST_N).iterrows():
        key = (row["prediction_id"], row["target_kind"])
        peers = by_id.get_group(key) if key in by_id.groups else baselines.iloc[:0]
        misses.append(
            {
                "split": row["split"],
                "cohort": row["cohort_version"],
                "target": row["target_kind"],
                "target_label": TARGET_LABELS.get(
                    row["target_kind"], row["target_kind"]
                ),
                "model": row["model_version"],
                "prediction_id": row["prediction_id"],
                "airport": row["airport_icao"],
                "horizon": int(row["horizon_h"]),
                "as_of_utc": _utc(row["as_of_utc"]),
                "target_start_utc": _utc(row["target_start_utc"]),
                "estimate": float(row["estimate"]),
                "p10": None if pd.isna(row["p10"]) else float(row["p10"]),
                "p90": None if pd.isna(row["p90"]) else float(row["p90"]),
                "y_true": float(row["y_true"]),
                "error": float(row["error"]),
                "unit": row["unit"],
                "status": row["status"],
                "reason_codes": list(row["reason_codes"]),
                "baseline_estimates": {
                    model: None if pd.isna(value) else float(value)
                    for model, value in zip(peers["model_version"], peers["estimate"])
                },
                # Needs the inputs known at T, which live in the feature snapshots.
                "explanation": None,
                "explanation_reason": "needs_feature_snapshots",
            }
        )
    return misses


def availability_basis(predictions: pd.DataFrame) -> dict[str, list[str]]:
    codes = predictions[["model_version", "reason_codes"]].explode("reason_codes")
    marked = codes[codes["reason_codes"].isin(ASSUMPTIONS)].drop_duplicates()
    grouped = marked.groupby("model_version")["reason_codes"]
    return {model: sorted(values) for model, values in grouped}


def _colours(models: list[str]) -> dict[str, str]:
    # Candidates first, so the legend leads with what is being judged.
    ordered = sorted(models, key=lambda m: (m in BASELINE_COLOURS, m))
    candidates = cycle(CANDIDATE_COLOURS)
    return {m: BASELINE_COLOURS.get(m) or next(candidates) for m in ordered}


def _label(model: str, basis: dict[str, list[str]]) -> str:
    name = model.removesuffix("_v1").removeprefix("baseline_")
    notes = [code.replace("_", " ") for code in basis.get(model, [])]
    return f"{name} ({', '.join(notes)})" if notes else name


def _style(ax: plt.Axes) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED_INK, length=0)


def _legend(fig: plt.Figure, axes: list[plt.Axes], ncol: int) -> None:
    # A model can be absent from one airport, so every panel adds to the legend.
    entries = {}
    for ax in axes:
        handles, labels = ax.get_legend_handles_labels()
        entries |= dict(zip(labels, handles))
    fig.legend(
        list(entries.values()),
        list(entries),
        loc="lower center",
        ncol=ncol,
        frameon=False,
        labelcolor=MUTED_INK,
        fontsize=8,
    )


def rmse_figure(
    records: list[dict],
    basis: dict[str, list[str]],
    split: str,
    cohort: str,
    target: str,
    path: Path,
) -> None:
    table = pd.DataFrame(records)
    table = table[
        table["split"].eq(split)
        & table["cohort"].eq(cohort)
        & table["target"].eq(target)
        & table["metric"].eq("rmse")
        & table["slice"].eq("common_support")
        & table["horizon"].ne(ALL_HORIZONS)
        & ~table["airport"].isin([POOLED, MACRO])
        & table["value"].notna()
    ]
    if table.empty:
        return
    airports = sorted(table["airport"].unique())
    colours = _colours(sorted(table["model"].unique()))
    fig, axes = plt.subplots(
        1,
        len(airports),
        figsize=(4.4 * len(airports), 3.9),
        sharey=True,
        facecolor=SURFACE,
        squeeze=False,
    )
    for ax, airport in zip(axes[0], airports):
        for model, colour in colours.items():
            rows = table[table["airport"].eq(airport) & table["model"].eq(model)]
            rows = rows.sort_values("horizon", key=lambda s: s.astype(int))
            ax.plot(
                rows["horizon"].astype(int),
                rows["value"],
                color=colour,
                lw=2,
                marker="o",
                ms=6,
                label=_label(model, basis),
            )
        ax.set_title(airport, color=INK, fontsize=11, loc="left")
        ax.set_xticks(EXPERIMENT["horizons_h"])
        ax.set_xlabel("horizon (h)", color=MUTED_INK)
        ax.set_ylim(bottom=0)
        _style(ax)
    unit = table["unit"].iloc[0]
    axes[0][0].set_ylabel(f"RMSE ({unit})", color=MUTED_INK)
    fig.suptitle(
        f"{TARGET_LABELS.get(target, target)}: RMSE by horizon, {split}, {cohort}",
        color=INK,
        fontsize=12,
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0.14, 1, 0.97))
    _legend(fig, list(axes[0]), ncol=3)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def reliability_figure(
    bins: list[dict],
    basis: dict[str, list[str]],
    split: str,
    cohort: str,
    target: str,
    path: Path,
) -> None:
    table = pd.DataFrame(bins)
    if table.empty:
        return
    table = table[
        table["split"].eq(split)
        & table["cohort"].eq(cohort)
        & table["target"].eq(target)
        & table["airport"].eq(POOLED)
    ]
    if table.empty:
        return
    fig, ax = plt.subplots(figsize=(5.4, 5.2), facecolor=SURFACE)
    top = float(table[["mean_predicted", "observed_rate"]].max(axis=None))
    ax.plot([0, top], [0, top], color=MUTED_INK, lw=1, ls="--", label="perfect")
    for model, colour in _colours(sorted(table["model"].unique())).items():
        rows = table[table["model"].eq(model)]
        ax.plot(
            rows["mean_predicted"],
            rows["observed_rate"],
            color=colour,
            lw=2,
            marker="o",
            ms=6,
            label=_label(model, basis),
        )
    ax.set_xlabel("mean predicted probability", color=MUTED_INK)
    ax.set_ylabel("observed rate", color=MUTED_INK)
    title = f"{TARGET_LABELS.get(target, target)}\nreliability, {split}, {cohort}"
    ax.set_title(title, color=INK, fontsize=10, loc="left")
    _style(ax)
    fig.tight_layout(rect=(0, 0.14, 1, 1))
    _legend(fig, [ax], ncol=2)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".json.part")
    part.write_text(json.dumps(report, indent=2, allow_nan=False))
    part.replace(path)


def main(
    runs: list[str],
    labels_path: Path = LABELS,
    requests_path: Path = REQUESTS,
    artifacts: Path = ARTIFACTS,
    reports: Path = REPORTS,
    locked_test: bool = False,
    approved_by: str | None = None,
    experiment: str = "primary",
    cohorts: list[str] | None = None,
) -> Path:
    if experiment not in LOCKED_EXPERIMENTS:
        raise ValueError(f"experiment outside {LOCKED_EXPERIMENTS}")
    # Hashed before the read, because worktrees share data/.
    sources = [artifacts / r / "predictions.parquet" for r in runs]
    data_sha256 = {str(p): sha256(p) for p in [*sources, labels_path, requests_path]}
    predictions = load_predictions(artifacts, runs, locked_test, cohorts)
    check_contract(predictions)
    requests = pd.read_parquet(requests_path, columns=REQUEST_KEYS)
    if cohorts:
        requests = requests[requests["cohort_version"].isin(cohorts)]
    check_requests(predictions, requests)
    check_baselines(predictions)
    check_label_keys(labels_path, predictions)
    modes = (
        set(predictions["data_mode"])
        | set(requests["data_mode"])
        | {labels_data_mode(labels_path)}
    )
    if len(modes) != 1:
        raise ValueError(f"mixed data_mode {sorted(modes)}")
    data_mode = modes.pop()
    if data_mode not in DATA_MODES:
        raise ValueError(f"data_mode {data_mode} outside {DATA_MODES}")
    ledger = reports / "locked_runs"
    if data_mode == "fixture":
        reports = reports / "fixture"
    suffix = "" if experiment == "primary" else f"_{experiment}"
    name = f"metrics{suffix}.json" if locked_test else f"metrics_dev{suffix}.json"
    path = reports / name
    figures = reports / "figures" / experiment.replace("primary", "")
    run_id = f"evaluate_{experiment}" if locked_test else f"evaluate_dev{suffix}"
    commit, commit_dirty = git("rev-parse", "HEAD"), source_dirty()
    if locked_test:
        if not approved_by:
            raise ValueError("locked test needs approved_by, after the model is frozen")
        if data_mode != "real":
            raise ValueError(f"locked test needs real data, got {data_mode}")
        if commit_dirty:
            raise ValueError(f"locked test needs {SOURCE_PATHS} committed")
        if predictions["data_snapshot_id"].nunique() != 1:
            raise ValueError("locked test needs one data snapshot across runs")
        check_locked_candidates(predictions)
        check_run_manifests(artifacts, runs)
        claim_locked_run(run_id, approved_by, commit, ledger)
    ids = predictions["prediction_id"].unique().tolist()
    labels = load_labels(labels_path, ids)
    joined = mark_common(join_labels(predictions, labels))
    basis = availability_basis(predictions)
    records = []
    for _, frame in joined.groupby(SCOPE):
        records += evaluate_target(frame, basis)
    records += macro_records(records)
    bins = reliability(joined)
    splits = sorted(joined["split"].unique())
    report = {
        "run_id": run_id,
        "scope": "locked_test" if locked_test else "dev",
        "experiment": experiment,
        "cohorts": sorted(joined["cohort_version"].unique()),
        "data_mode": data_mode,
        "commit": commit,
        "commit_dirty": commit_dirty,
        "approved_by": approved_by,
        "seed": EXPERIMENT["seed"],
        "config_sha256": {str(c): sha256(c) for c in CONFIGS},
        "uv_lock_sha256": sha256(Path("uv.lock")),
        "data_sha256": data_sha256,
        "data_snapshot_ids": sorted(predictions["data_snapshot_id"].unique()),
        "label_versions": sorted(labels["label_version"].unique()),
        "split_bounds": {s: [_utc(t) for t in split_bounds(s)] for s in splits},
        "targets": EXPERIMENT["targets"],
        "target_labels": TARGET_LABELS,
        "model_ids": sorted(predictions["model_version"].unique()),
        "availability_basis": basis,
        "metric_definitions": METRIC_DEFINITIONS,
        "generated_at_utc": _utc(datetime.now(UTC)),
        "metrics": records,
        "reliability": bins,
        "worst_misses": worst_misses(joined),
    }
    figures.mkdir(parents=True, exist_ok=True)
    for split, cohort, target in joined[SCOPE].drop_duplicates().to_numpy():
        stem = f"{target}_{split}_{cohort}.png"
        if target in BINARY:
            reliability_figure(
                bins, basis, split, cohort, target, figures / f"reliability_{stem}"
            )
        else:
            rmse_figure(records, basis, split, cohort, target, figures / f"rmse_{stem}")
    # Written last, so a report on disk always has its figures.
    write_report(report, path)
    print(path, f"data_mode={data_mode}", f"records={len(records)}")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--locked-test", action="store_true")
    parser.add_argument("--approved-by")
    parser.add_argument("--runs", nargs="+")
    parser.add_argument("--experiment", default="primary", choices=LOCKED_EXPERIMENTS)
    parser.add_argument("--cohorts", nargs="+")
    parser.add_argument("--requests", type=Path, default=REQUESTS)
    parser.add_argument("--reports", type=Path, default=REPORTS)
    args = parser.parse_args()
    default = "baselines_locked_test" if args.locked_test else "baselines_dev"
    main(
        args.runs or [default],
        requests_path=args.requests,
        reports=args.reports,
        locked_test=args.locked_test,
        approved_by=args.approved_by,
        experiment=args.experiment,
        cohorts=args.cohorts,
    )
