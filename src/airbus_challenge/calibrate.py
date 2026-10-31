"""WP-D7: calibrators, interval margins, alert thresholds and episodes from H2 2024 only."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from airbus_challenge.baselines import AIRPORTS, ARTIFACTS, HOURLY, TARGET, split_bounds
from airbus_challenge.download import sha256
from airbus_challenge.evaluate import (
    BINARY,
    CAPACITY_RATIO,
    LABELS,
    SEVERE,
    load_labels,
    split_of,
)
from airbus_challenge.recommend import (
    POLICY_VERSION,
    REFERENCE_COLUMNS,
    THRESHOLDS,
    apply_calibrator,
)

FIT = (pd.Timestamp("2024-07-01", tz="UTC"), pd.Timestamp("2024-10-01", tz="UTC"))
ASSESS = (pd.Timestamp("2024-10-01", tz="UTC"), pd.Timestamp("2025-01-01", tz="UTC"))
assert (
    FIT[0] == split_bounds("calibration")[0]
    and ASSESS[1] == split_bounds("calibration")[1]
)
COVERAGE = 0.80
PRECISION = {"act": 0.5, "watch": 0.3}
MIN_POSITIVES = 50
RATIO_ACT, RATIO_FLOOR, RATIO_STEP, RATIO_WATCH = 0.70, 0.50, 0.05, 0.85
EVENT_RATIO = 0.70
MERGE_GAP_H, MATCH_WINDOW_H = 1, 1
MIN_VALIDATION_N = 30
HOUR = pd.Timedelta(hours=1)


def in_window(rows: pd.DataFrame, window) -> pd.DataFrame:
    t = rows["target_start_utc"]
    return rows[t.ge(window[0]) & t.lt(window[1])]


def window_days(window) -> int:
    return (window[1] - window[0]).days


def fit_isotonic(p, y) -> dict:
    iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(p, y)
    return {
        "method": "isotonic_breakpoints_linear_interp_clip",
        "x": iso.X_thresholds_.tolist(),
        "y": iso.y_thresholds_.tolist(),
        "n": len(y),
        "positives": int(np.sum(y)),
    }


def conformal_margins(rows: pd.DataFrame) -> dict:
    """rows: eligible throughput fit rows with p10, p90, y_true. Additive margin per airport."""
    out = {}
    for icao, g in rows.groupby("airport_icao"):
        g = g.dropna(subset=["p10", "p90"])
        if g.empty:
            out[icao] = {"margin": None, "reason": "p10_p90_absent"}
            continue
        y = g["y_true"].to_numpy()
        score = np.maximum(g["p10"] - y, y - g["p90"]).to_numpy()
        level = min(1.0, np.ceil((len(y) + 1) * COVERAGE) / len(y))
        m = max(0.0, float(np.quantile(score, level, method="higher")))
        lo, hi = g["p10"].to_numpy(), g["p90"].to_numpy()
        out[icao] = {"margin": m, "n": len(y), "coverage_before": _inside(y, lo, hi, 0.0),
                     "coverage_after": _inside(y, lo, hi, m), "target_coverage": COVERAGE}  # fmt: skip
    return out


def _inside(y, lo, hi, m) -> float:
    return float(np.mean((y >= lo - m) & (y <= hi + m)))


def _stats(p, y, t, airport_days) -> dict:
    alert = p >= t
    tp = int((alert & (y == 1)).sum())
    return {
        "precision": tp / int(alert.sum()) if alert.any() else None,
        "recall": tp / int(y.sum()) if y.sum() else None,
        "n": len(y),
        "positives": int(y.sum()),
        "alerts": int(alert.sum()),
        "alerts_per_airport_day": int(alert.sum()) / airport_days,
    }


def pick_threshold(p, y, target: float, airport_days: int) -> dict:
    """Lowest threshold (alert = p >= threshold) whose precision is >= target."""
    p, y = np.asarray(p), np.asarray(y)
    for t in np.unique(p):
        alert = p >= t
        if (y[alert] == 1).mean() >= target:
            return {"threshold": float(t)} | _stats(p, y, t, airport_days)
    return {"threshold": None, "reason": "precision_target_not_reached",
            "n": len(y), "positives": int(y.sum())}  # fmt: skip


def severe_thresholds(rows: pd.DataFrame) -> dict:
    """rows: eligible assessment rows with calibrated p_cal and y_true."""
    days = window_days(ASSESS)
    out = {}
    for level, target in PRECISION.items():
        n_airports = rows["airport_icao"].nunique()
        pooled = pick_threshold(
            rows["p_cal"], rows["y_true"], target, days * n_airports
        )
        per = {"pooled": pooled | {"precision_target": target}}
        for icao, g in rows.groupby("airport_icao"):
            p, y = g["p_cal"].to_numpy(), g["y_true"].to_numpy()
            if y.sum() >= MIN_POSITIVES:
                per[icao] = pick_threshold(p, y, target, days) | {"pooled": False}
            elif pooled["threshold"] is None:
                per[icao] = {
                    "threshold": None,
                    "reason": pooled["reason"],
                    "pooled": True,
                }
            else:
                t = pooled["threshold"]
                per[icao] = {"threshold": t, "pooled": True,
                             "pooled_reason": f"fewer_than_{MIN_POSITIVES}_positives"} | _stats(p, y, t, days)  # fmt: skip
        out[level] = per
    return out


def episodes(alert_hours, event_hours, days: int) -> dict:
    """Merge alert hours with gaps <= MERGE_GAP_H missing hours; hit = event within ±MATCH_WINDOW_H."""
    alert = pd.DatetimeIndex(sorted(set(alert_hours)))
    events = pd.DatetimeIndex(sorted(set(event_hours)))
    spans = []
    for t in alert:
        if spans and t - spans[-1][1] <= (MERGE_GAP_H + 1) * HOUR:
            spans[-1][1] = t
        else:
            spans.append([t, t])
    w = MATCH_WINDOW_H * HOUR
    near = lambda e, s: s[0] - w <= e <= s[1] + w
    hits = sum(any(near(e, s) for e in events) for s in spans)
    missed = sum(not any(near(e, s) for s in spans) for e in events)
    return {"episodes": len(spans), "hits": hits, "false_episodes": len(spans) - hits,
            "events": len(events), "missed_events": missed,
            "episodes_per_day": len(spans) / days}  # fmt: skip


def _by_cell(rows, alert_col, event_col, days) -> dict:
    out = {}
    for (icao, h), g in rows.groupby(["airport_icao", "horizon_h"]):
        hour = g["target_start_utc"].dt.floor("h")
        out[f"{icao}|h{h}"] = episodes(hour[g[alert_col]], hour[g[event_col]], days)
    return out


def ceiling(rows: pd.DataFrame, reference: pd.DataFrame) -> pd.Series:
    hour = pd.Series(np.nan, index=rows.index)
    for icao, g in rows.groupby("airport_icao"):
        hour[g.index] = (
            g["target_start_utc"].dt.tz_convert(AIRPORTS[icao]["timezone"]).dt.hour
        )
    keyed = rows[["airport_icao"]].assign(airport_local_hour=hour.astype(int))
    ref = reference[
        reference["clear_weather_fit_hours"].ge(THRESHOLDS["min_reference_fit_hours"])
    ]
    merged = keyed.merge(ref, on=["airport_icao", "airport_local_hour"], how="left")
    return pd.Series(
        merged["clear_weather_p95_arrivals_per_hour"].to_numpy(), index=rows.index
    )


def throughput_alerts(rows: pd.DataFrame) -> dict:
    """rows: assessment rows with p10_widened, p95, actual_ratio (eligible, non-null)."""
    steps, ratio = [], RATIO_ACT
    if rows["p10_widened"].isna().all():
        return {"act_ratio": None, "reason": "p10_absent", "watch_ratio": RATIO_WATCH}
    while True:
        act = rows["p10_widened"] < ratio * rows["p95"]
        share = (
            float(rows.loc[act, "actual_ratio"].lt(EVENT_RATIO).mean())
            if act.any()
            else None
        )
        steps.append(
            {
                "act_ratio": round(ratio, 2),
                "act_hours": int(act.sum()),
                "share_actual_below_0.70": share,
            }
        )
        if (
            (share is not None and share >= 0.5)
            or ratio <= RATIO_FLOOR + 1e-9
            or share is None
        ):
            break
        ratio -= RATIO_STEP
    reached = share is not None and share >= 0.5
    # Like a delay threshold that misses its precision target, an unmet share
    # leaves no act ratio, so recommend never acts on it.
    return {"act_ratio": round(ratio, 2) if reached else None, "watch_ratio": RATIO_WATCH,
            "target_share": 0.5, "reached": reached, "steps": steps,
            "reason": None if reached else "act_share_target_not_reached"}  # fmt: skip


def validate_fallback(
    rows: pd.DataFrame, fallback_model: str, reference_model: str
) -> dict:
    """Degraded only if the fallback's RMSE/Brier on shared validation rows is no worse."""
    kinds = rows["target_kind"].unique()
    if len(kinds) != 1:
        raise ValueError(f"validate_fallback takes one target_kind, got {list(kinds)}")
    metric = "brier" if kinds[0] in BINARY else "rmse"
    lo, hi = split_bounds("validation")
    v = rows[rows["target_start_utc"].ge(lo) & rows["target_start_utc"].lt(hi)]
    v = v[v["eligible"].astype(bool) & v["estimate"].notna()]
    ref = v.loc[v["model_version"].eq(reference_model), ["prediction_id", "estimate"]]
    both = v[v["model_version"].eq(fallback_model)].merge(
        ref, on="prediction_id", suffixes=("", "_ref")
    )
    out = {"fallback_model": fallback_model, "reference_model": reference_model,
           "target_kind": kinds[0], "metric": metric, "n": len(both)}  # fmt: skip
    if len(both) < MIN_VALIDATION_N:
        return out | {
            "verdict": "unavailable",
            "reason": f"fewer_than_{MIN_VALIDATION_N}_rows",
        }
    f, r = (
        float(np.mean((both[c] - both["y_true"]) ** 2))
        for c in ("estimate", "estimate_ref")
    )
    if metric == "rmse":
        f, r = f**0.5, r**0.5
    return out | {"fallback_score": f, "reference_score": r,
                  "verdict": "degraded" if f <= r else "unavailable",
                  "reason": None if f <= r else "worse_than_reference"}  # fmt: skip


def calibrate(
    predictions: pd.DataFrame, labels: pd.DataFrame, reference: pd.DataFrame | None
) -> dict:
    key = ["prediction_id", "target_kind"]
    rows = predictions.merge(labels[[*key, "y_true", "eligible"]], on=key, how="inner")
    rows = rows[rows["eligible"].astype(bool) & rows["estimate"].notna()]
    ratio = labels.loc[labels["target_kind"].eq(CAPACITY_RATIO) & labels["eligible"].astype(bool),
                       ["prediction_id", "y_true"]].rename(columns={"y_true": "actual_ratio"})  # fmt: skip
    fit, assess = in_window(rows, FIT), in_window(rows, ASSESS)
    days = window_days(ASSESS)
    out = {"calibrators": {}, "throughput_interval": {}, "severe_delay_thresholds": {},
           "throughput_alert": {}, "episodes": {}}  # fmt: skip
    for kind in sorted(BINARY):
        for model, g in fit[fit["target_kind"].eq(kind)].groupby("model_version"):
            cal = fit_isotonic(g["estimate"], g["y_true"])
            out["calibrators"].setdefault(kind, {})[model] = cal
            if kind != SEVERE:
                continue
            a = assess[
                assess["target_kind"].eq(kind) & assess["model_version"].eq(model)
            ]
            a = a.assign(p_cal=apply_calibrator(cal, a["estimate"]))
            th = out["severe_delay_thresholds"][model] = severe_thresholds(a)
            act_by_airport = {
                i: v["threshold"] for i, v in th["act"].items() if i != "pooled"
            }
            act = a["airport_icao"].map(act_by_airport).astype(float)
            flight_hour = a["target_start_utc"].dt.floor("h")
            share = a.groupby(["airport_icao", "horizon_h", flight_hour])[
                "y_true"
            ].transform("mean")
            a = a.assign(
                alert=a["p_cal"].ge(act) & act.notna(),
                event=share.ge(act) & act.notna(),
            )
            out["episodes"][model] = {
                "true_event": "an hour whose observed severe-delay share among operated flights "
                "(same airport and horizon) is >= the airport's act threshold; null act -> no events",
                "cells": _by_cell(a, "alert", "event", days)}  # fmt: skip
    for model, g in fit[fit["target_kind"].eq(TARGET)].groupby("model_version"):
        margins = out["throughput_interval"][model] = conformal_margins(g)
        a = assess[assess["target_kind"].eq(TARGET) & assess["model_version"].eq(model)]
        if reference is None:
            out["throughput_alert"][model] = {
                "act_ratio": None,
                "reason": "no_reference",
                "watch_ratio": RATIO_WATCH,
            }
            continue
        margin = {i: v.get("margin") for i, v in margins.items()}
        a = a.merge(ratio, on="prediction_id", how="inner")
        a = a.assign(p10_widened=a["p10"] - a["airport_icao"].map(margin).astype(float),
                     p95=ceiling(a, reference))  # fmt: skip
        a = a[a["p95"].gt(0)]
        rule = out["throughput_alert"][model] = throughput_alerts(a)
        if rule["act_ratio"] is None:
            continue
        a = a.assign(
            alert=a["p10_widened"] < rule["act_ratio"] * a["p95"],
            event=a["actual_ratio"].lt(EVENT_RATIO),
        )
        out["episodes"][model] = {"true_event": f"actual ratio below {EVENT_RATIO}",
                                  "cells": _by_cell(a, "alert", "event", days)}  # fmt: skip
    return out


def load(
    runs: list[str], labels_path: Path, artifacts: Path = ARTIFACTS
) -> tuple[pd.DataFrame, pd.DataFrame]:
    preds = pd.concat(
        [pd.read_parquet(artifacts / r / "predictions.parquet") for r in runs],
        ignore_index=True,
    )
    preds = preds[split_of(preds["target_start_utc"]).eq("calibration")]
    # Filtered to calibration-split ids at read, so outcomes outside H2 2024 are never loaded.
    return preds, load_labels(labels_path, preds["prediction_id"].unique().tolist())


def run(
    run_id: str,
    extra: list[str],
    labels_path=LABELS,
    reference_path=HOURLY,
    artifacts=ARTIFACTS,
) -> dict:
    runs = [run_id, *extra]
    preds, labels = load(runs, Path(labels_path), Path(artifacts))
    ref_path = Path(reference_path)
    reference = (pd.read_parquet(ref_path, columns=REFERENCE_COLUMNS).drop_duplicates(["airport_icao", "airport_local_hour"])
                 if ref_path.exists() else None)  # fmt: skip
    hashes = {
        f"predictions:{r}": sha256(Path(artifacts) / r / "predictions.parquet")
        for r in runs
    }
    hashes["labels"] = sha256(Path(labels_path))
    hashes["reference"] = sha256(ref_path) if ref_path.exists() else None
    result = {
        "policy_version": POLICY_VERSION,
        "decision": "docs/DECISIONS.md WP-D7",
        "runs": runs,
        "calibration_fit_utc": [t.isoformat() for t in FIT],
        "threshold_assessment_utc": [t.isoformat() for t in ASSESS],
        "alert_rule": "alert when calibrated probability >= threshold; null threshold never alerts",
        "input_hashes": hashes,
    } | calibrate(preds, labels, reference)
    path = Path(artifacts) / run_id / "calibration.json"
    path.write_text(json.dumps(result, indent=2, default=str))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--runs", nargs="*", default=[])
    args = parser.parse_args()
    out = run(args.run, args.runs)
    print(
        json.dumps(
            {k: out[k] for k in ("severe_delay_thresholds", "throughput_alert")},
            indent=1,
            default=str,
        )[:4000]
    )


if __name__ == "__main__":
    main()
