"""Rule-based failure cases for evaluate's worst misses (EVALUATION_PLAN §7). No LLM."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from airbus_challenge.baselines import git, split_bounds
from airbus_challenge.download import sha256
from airbus_challenge.evaluate import BINARY, REPORTS, is_baseline, write_report
from airbus_challenge.features import FEATURES

SNAPSHOTS = Path("data/processed/feature_snapshots.parquet")
LINEAGE = Path("data/processed/feature_lineage.parquet")
VERSION = "failure-rules/1"
PREDICTION_COLUMNS = [
    "prediction_id",
    "target_kind",
    "model_version",
    "target_start_utc",
    "estimate",
    "p10",
    "p90",
    "unit",
    "status",
    "reason_codes",
]
# Provisional failure-report rules, not validated alert thresholds.
LONG_HORIZON_H = 9
LARGE_RELATIVE_ERROR = 0.25  # |error| / max(y_true, 1), regression
LARGE_PROBABILITY_ERROR = 0.5  # binary
WIDE_INTERVAL = 0.5  # (p90 - p10) / max(estimate, 1)
HIGH_PROBABILITY = 0.5
# IFR as in targets.exclusion_audit; crosswind limits are typical airline guidance.
SIGNALS = {
    "metar_ts_3h": ("is", True),
    "metar_fz_3h": ("is", True),
    "metar_sn_3h": ("is", True),
    "taf_ts_prevailing": ("is", True),
    "taf_ts_conditional": ("is", True),
    "metar_ceiling_min_ft_3h": ("<", 1000),
    "taf_ceiling_min_ft": ("<", 1000),
    "taf_cond_ceiling_min_ft": ("<", 1000),
    "metar_visibility_min_sm_3h": ("<", 3),
    "taf_visibility_min_sm": ("<", 3),
    "taf_cond_visibility_min_sm": ("<", 3),
    "metar_crosswind_kt": (">=", 20),
    "taf_crosswind_max_kt": (">=", 20),
    "metar_gust_crosswind_kt": (">=", 25),
    "taf_gust_crosswind_max_kt": (">=", 25),
    "taf_cond_crosswind_max_kt": (">=", 25),
}
LIMITATIONS = {
    "metar_stale": "METAR older than 3 h at issue time",
    "metar_unavailable": "no METAR in the 6 h before issue time",
    "taf_uncovered": "TAF did not cover the target hour",
    "taf_unavailable": "no TAF available by issue time",
    "source_hour_partial": "source hour partial (P12): the persistence feed count may be low",
    "degraded_input": "unavailable/degraded input",
    "large_error_long_horizon": "large error at long horizon",
    "outside_interval": "outcome outside the p10-p90 interval",
    "no_feature_snapshot": "no feature snapshot for this prediction: insufficient data",
}
HINDSIGHT = (
    "not compared: no evaluation-only target-hour weather table exists, so "
    "'weather changed after issue time' is never claimed"
)


def _utc(moment: pd.Timestamp) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _value(value):
    if not pd.api.types.is_scalar(value):
        return list(value)
    return None if pd.isna(value) else getattr(value, "item", lambda: value)()


def _float(value) -> float | None:
    return None if pd.isna(value) else float(value)


def feature_group(name: str) -> str:
    if name.startswith("taf_"):
        return "taf"
    if name.startswith("metar_"):
        window = name.endswith(("_1h", "_3h", "_6h", "_3h_hpa"))
        return "metar_window" if window else "metar_latest"
    return "calendar"


def predictions_for(paths: list[Path], ids: list[str], dev: bool) -> pd.DataFrame:
    filters = [("prediction_id", "in", ids)]
    if dev:  # Dev never reads a 2025 row, even an outcome-free one.
        filters.append(("target_start_utc", "<", split_bounds("test")[0]))
    frames = [
        pd.read_parquet(p, columns=PREDICTION_COLUMNS, filters=filters) for p in paths
    ]
    return pd.concat(frames, ignore_index=True)


def known_at_issue(
    snapshot: pd.Series, lineage: pd.DataFrame, as_of: pd.Timestamp
) -> dict:
    # Only records available by T; a later row can never enter a case.
    lineage = lineage[lineage["contributing_available_at_utc"].le(as_of)]
    sources = [
        {
            "feature_group": row["feature_group"],
            "source_record_id": row["source_record_id"],
            "source_ref": row["source_ref"],
            "available_at_utc": _utc(row["contributing_available_at_utc"]),
            "age_min": (as_of - row["contributing_available_at_utc"])
            / pd.Timedelta(minutes=1),
        }
        for _, row in lineage.sort_values(["feature_group", "source_ref"]).iterrows()
    ]
    newest = lineage.groupby("feature_group")["contributing_available_at_utc"].max()
    features = {}
    for name in [c for c in FEATURES if c in snapshot.index and c != "airport_icao"]:
        group = feature_group(name)
        seen = newest.get(group)
        features[name] = {
            "value": _value(snapshot[name]),
            "source_group": group,
            "source_available_at_utc": None if seen is None else _utc(seen),
            "source_age_min": None
            if seen is None
            else (as_of - seen) / pd.Timedelta(minutes=1),
        }
    return {
        "snapshot_key": snapshot["snapshot_key"],
        "feature_version": snapshot["feature_version"],
        "feature_status": snapshot["status"],
        "feature_reason_codes": list(snapshot["reason_codes"]),
        "source_ages_min": {
            k: _float(snapshot.get(k)) for k in ("metar_age_min", "taf_age_min")
        },
        "taf_lead_h": _float(snapshot.get("taf_lead_h")),
        "sources": sources,
        "features": features,
    }


def signals(features: dict) -> list[str]:
    found = []
    for name, (op, limit) in SIGNALS.items():
        value = features.get(name, {}).get("value")
        if value is None:
            continue
        hit = {"is": value == limit, "<": value < limit, ">=": value >= limit}[op]
        if hit:
            found.append(
                f"{name}={value}" if op == "is" else f"{name}={value:g} {op} {limit}"
            )
    return found


def limitations(case: dict, known: dict | None, codes: set[str]) -> list[dict]:
    prediction, outcome = case["prediction"], case["outcome"]
    fired = set()
    if known is None:
        fired.add("no_feature_snapshot")
    else:
        fired |= codes & {
            "metar_stale",
            "metar_unavailable",
            "taf_uncovered",
            "taf_unavailable",
        }
        age = known["source_ages_min"]["metar_age_min"]
        if age is not None and age > 180:
            fired.add("metar_stale")
        if known["feature_status"] != "ok":
            fired.add("degraded_input")
    if "source_hour_partial" in codes:
        fired.add("source_hour_partial")
    if prediction["status"] != "available" or "source_hour_incomplete" in codes:
        fired.add("degraded_input")
    if case["target"] in BINARY:
        large = abs(outcome["error"]) >= LARGE_PROBABILITY_ERROR
    else:
        large = (
            abs(outcome["error"]) / max(abs(outcome["y_true"]), 1)
            >= LARGE_RELATIVE_ERROR
        )
        low, high = prediction["p10"], prediction["p90"]
        if (
            low is not None
            and high is not None
            and not low <= outcome["y_true"] <= high
        ):
            fired.add("outside_interval")
    if large and case["horizon"] >= LONG_HORIZON_H:
        fired.add("large_error_long_horizon")
    return [{"code": c, "text": t} for c, t in LIMITATIONS.items() if c in fired]


def advisory(case: dict, known: dict | None) -> tuple[bool | None, str]:
    if known is None:
        return None, "insufficient_data: no feature snapshot at issue time"
    found = signals(known["features"])
    prediction = case["prediction"]
    if case["target"] in BINARY:
        if prediction["estimate"] >= HIGH_PROBABILITY:
            found.append(
                f"probability {prediction['estimate']:.2f} >= {HIGH_PROBABILITY}"
            )
    elif prediction["p10"] is not None and prediction["p90"] is not None:
        width = (prediction["p90"] - prediction["p10"]) / max(prediction["estimate"], 1)
        if width >= WIDE_INTERVAL:
            found.append(f"interval width {width:.2f} x estimate >= {WIDE_INTERVAL}")
    if found:
        return True, "signal at T: " + "; ".join(found)
    if known["feature_status"] == "missing":
        return False, "no weather inputs at T and no wide interval: nothing to act on"
    return False, "no adverse weather feature or wide interval at T: nothing to act on"


def build_case(
    miss: dict, preds: pd.DataFrame, snapshots: pd.DataFrame, lineage: pd.DataFrame
) -> dict:
    as_of = pd.Timestamp(miss["as_of_utc"])
    rows = preds[
        preds["prediction_id"].eq(miss["prediction_id"])
        & preds["target_kind"].eq(miss["target"])
    ]
    own = rows[rows["model_version"].eq(miss["model"])]
    if len(own) != 1 or own["estimate"].iloc[0] != miss["estimate"]:
        raise ValueError(f"{miss['prediction_id']}: metrics and predictions disagree")
    own = own.iloc[0]
    peers = rows[is_baseline(rows["model_version"])].sort_values("model_version")
    case = {
        **{
            k: miss[k]
            for k in (
                "prediction_id",
                "model",
                "target",
                "target_label",
                "cohort",
                "split",
                "airport",
                "horizon",
                "as_of_utc",
                "target_start_utc",
            )
        },
        "prediction": {
            "estimate": float(own["estimate"]),
            "p10": _float(own["p10"]),
            "p90": _float(own["p90"]),
            "unit": own["unit"],
            "status": own["status"],
            "reason_codes": list(own["reason_codes"]),
        },
        "outcome": {
            "y_true": miss["y_true"],
            "error": miss["error"],
            "abs_error": abs(miss["error"]),
        },
        "baselines": {
            row["model_version"]: {
                "estimate": _float(row["estimate"]),
                "status": row["status"],
                "reason_codes": list(row["reason_codes"]),
            }
            for _, row in peers.iterrows()
        },
    }
    snapshot = snapshots[snapshots["prediction_id"].eq(miss["prediction_id"])]
    known = None
    if len(snapshot):
        snapshot = snapshot.iloc[0]
        if snapshot["as_of_utc"] != as_of:
            raise ValueError(
                f"{miss['prediction_id']}: snapshot is not as of {miss['as_of_utc']}"
            )
        known = known_at_issue(
            snapshot,
            lineage[lineage["snapshot_key"].eq(snapshot["snapshot_key"])],
            as_of,
        )
    codes = set(case["prediction"]["reason_codes"])
    codes |= {c for b in case["baselines"].values() for c in b["reason_codes"]}
    if known:
        codes |= set(known["feature_reason_codes"])
    possible, reason = advisory(case, known)
    return {
        **case,
        "explanation_status": "ok" if known else "insufficient_data",
        "known_at_issue": known,
        "flags": sorted(codes),
        "limitations": limitations(case, known, codes),
        "advisory_possible": possible,
        "advisory_reason": reason,
    }


def main(
    metrics_path: Path,
    snapshots_path: Path = SNAPSHOTS,
    lineage_path: Path = LINEAGE,
    reports: Path = REPORTS,
) -> Path:
    metrics = json.loads(metrics_path.read_text())
    dev = metrics["scope"] == "dev"
    misses = metrics["worst_misses"]
    test_start = split_bounds("test")[0]
    if dev and any(
        m["split"] == "test" or pd.Timestamp(m["target_start_utc"]) >= test_start
        for m in misses
    ):
        raise ValueError(
            "dev metrics carry a test-split miss; refusing to read 2025 outcomes"
        )
    # Only the predictions evaluate scored, unchanged since it hashed them.
    recorded = metrics["data_sha256"]
    paths = [p for p in recorded if p.endswith("predictions.parquet")]
    for path in paths:
        if sha256(Path(path)) != recorded[path]:
            raise ValueError(f"{path} changed since {metrics['run_id']}")
    paths = [Path(p) for p in paths]
    ids = sorted({m["prediction_id"] for m in misses})
    preds = predictions_for(paths, ids, dev)
    snapshots = pd.read_parquet(snapshots_path, filters=[("prediction_id", "in", ids)])
    if set(snapshots["data_mode"]) - {metrics["data_mode"]}:
        raise ValueError(f"snapshots are not all data_mode {metrics['data_mode']}")
    keys = snapshots["snapshot_key"].unique().tolist()
    lineage = (
        pd.read_parquet(lineage_path, filters=[("snapshot_key", "in", keys)])
        if keys
        else pq.read_schema(lineage_path).empty_table().to_pandas()
    )
    report = {
        "run_id": metrics["run_id"].replace("evaluate", "failures", 1),
        "rules_version": VERSION,
        "scope": metrics["scope"],
        "experiment": metrics["experiment"],
        "data_mode": metrics["data_mode"],
        "commit": git("rev-parse", "HEAD"),
        "generated_at_utc": _utc(datetime.now(UTC)),
        "source_metrics": {
            "path": str(metrics_path),
            "sha256": sha256(metrics_path),
            "run_id": metrics["run_id"],
        },
        "inputs_sha256": {
            str(p): sha256(p) for p in [*paths, snapshots_path, lineage_path]
        },
        "rules": {
            "limitations": LIMITATIONS,
            "signals": {k: f"{op} {v}" for k, (op, v) in SIGNALS.items()},
            "long_horizon_h": LONG_HORIZON_H,
            "large_relative_error": LARGE_RELATIVE_ERROR,
            "large_probability_error": LARGE_PROBABILITY_ERROR,
            "wide_interval": WIDE_INTERVAL,
            "high_probability": HIGH_PROBABILITY,
            "note": "provisional failure-report rules, not validated alert thresholds; "
            "feature drivers are associations, not causes",
        },
        "hindsight_weather": HINDSIGHT,
        "cases": [build_case(m, preds, snapshots, lineage) for m in misses],
    }
    if metrics["data_mode"] == "fixture":
        reports = reports / "fixture"
    path = reports / metrics_path.name.replace("metrics", "failure_cases", 1)
    write_report(report, path)
    print(path, f"cases={len(report['cases'])}")
    return path


def cli(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--snapshots", type=Path, default=SNAPSHOTS)
    parser.add_argument("--lineage", type=Path, default=LINEAGE)
    parser.add_argument("--reports", type=Path, default=REPORTS)
    args = parser.parse_args(argv)
    return main(args.metrics, args.snapshots, args.lineage, args.reports)


if __name__ == "__main__":
    cli()
