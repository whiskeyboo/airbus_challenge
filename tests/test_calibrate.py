import json

import numpy as np
import pandas as pd
import pytest

from airbus_challenge import calibrate
from airbus_challenge.baselines import TARGET
from airbus_challenge.calibrate import (
    ASSESS,
    FIT,
    MIN_POSITIVES,
    episodes,
    fit_isotonic,
    pick_threshold,
    run,
    severe_thresholds,
    validate_fallback,
)
from airbus_challenge.evaluate import CAPACITY_RATIO, SEVERE
from airbus_challenge.recommend import apply_calibrator

H = pd.Timedelta(hours=1)


def fixture_tables(seed=0):
    rng = np.random.default_rng(seed)
    hours = pd.date_range(
        "2024-06-25", "2025-01-08", freq="h", tz="UTC", inclusive="left"
    )
    preds, labels = [], []
    for icao in ("KATL", "KDFW"):
        risk = rng.beta(1, 6, len(hours))
        ids = [f"{icao}|{t}|6" for t in hours]
        common = {"airport_icao": icao, "target_start_utc": hours, "horizon_h": 6}
        preds.append(pd.DataFrame(common | {"prediction_id": ids, "target_kind": SEVERE,
                     "estimate": np.clip(risk * 0.6 + rng.normal(0, 0.02, len(hours)), 0, 1),
                     "p10": np.nan, "p90": np.nan, "model_version": "m-delay"}))  # fmt: skip
        labels.append(pd.DataFrame({"prediction_id": ids, "target_kind": SEVERE,
                      "y_true": rng.binomial(1, risk).astype(float)}))  # fmt: skip
        arrivals = rng.poisson(80 * (1 - risk))
        est = 80 * (1 - risk) + rng.normal(0, 5, len(hours))
        tids = [f"{icao}|{t}|6|tp" for t in hours]
        preds.append(pd.DataFrame(common | {"prediction_id": tids, "target_kind": TARGET,
                     "estimate": est, "p10": est - 5, "p90": est + 5, "model_version": "m-tp"}))  # fmt: skip
        labels += [
            pd.DataFrame({"prediction_id": tids, "target_kind": TARGET, "y_true": arrivals.astype(float)}),
            pd.DataFrame({"prediction_id": tids, "target_kind": CAPACITY_RATIO, "y_true": arrivals / 100}),
        ]  # fmt: skip
    labels = pd.concat(labels, ignore_index=True).assign(
        eligible=True, exclusion_reason=None, exclusion_detail=None
    )
    reference = pd.DataFrame([
        {"airport_icao": i, "airport_local_hour": h, "clear_weather_p95_arrivals_per_hour": 100.0,
         "clear_weather_fit_hours": 50, "clear_weather_reference_id": "ref",
         "clear_weather_fit_end_utc": pd.Timestamp("2024-01-01", tz="UTC")}
        for i in ("KATL", "KDFW") for h in range(24)
    ])  # fmt: skip
    return pd.concat(preds, ignore_index=True), labels, reference


def write_and_run(tmp_path, preds, labels, reference):
    (tmp_path / "artifacts" / "r1").mkdir(parents=True, exist_ok=True)
    preds.to_parquet(tmp_path / "artifacts" / "r1" / "predictions.parquet", index=False)
    labels.to_parquet(tmp_path / "labels.parquet", index=False)
    reference.to_parquet(tmp_path / "ref.parquet", index=False)
    out = run(
        "r1",
        [],
        tmp_path / "labels.parquet",
        tmp_path / "ref.parquet",
        tmp_path / "artifacts",
    )
    assert (
        json.loads((tmp_path / "artifacts" / "r1" / "calibration.json").read_text())[
            "policy_version"
        ]
        == "wp-d7-v1"
    )
    return out | {"input_hashes": None}


def times_of(preds, labels, start, end):
    t = preds.set_index("prediction_id")["target_start_utc"]
    when = labels["prediction_id"].map(t)
    return when.ge(start) & when.lt(end)


@pytest.fixture(scope="module")
def tables():
    return fixture_tables()


def test_isotonic_monotone_in_unit_interval():
    rng = np.random.default_rng(1)
    p = rng.uniform(0, 1, 500)
    cal = fit_isotonic(p, rng.binomial(1, p))
    assert np.all(np.diff(cal["y"]) >= 0) and min(cal["y"]) >= 0 and max(cal["y"]) <= 1
    out = apply_calibrator(cal, np.linspace(-0.5, 1.5, 201))
    assert np.all(np.diff(out) >= 0) and out.min() >= 0 and out.max() <= 1


def test_run_outputs_and_windows(tmp_path, tables):
    preds, labels, reference = tables
    out = write_and_run(tmp_path, preds, labels, reference)
    assert out["calibration_fit_utc"] == [t.isoformat() for t in FIT]
    assert out["threshold_assessment_utc"] == [t.isoformat() for t in ASSESS]
    sev = labels["target_kind"].eq(SEVERE)
    oct_dec = sev & times_of(preds, labels, *ASSESS)
    pooled = out["severe_delay_thresholds"]["m-delay"]["act"]["pooled"]
    assert (
        pooled["n"] == oct_dec.sum()
        and pooled["positives"] == labels.loc[oct_dec, "y_true"].sum()
    )
    assert (
        out["calibrators"][SEVERE]["m-delay"]["n"]
        == (sev & times_of(preds, labels, *FIT)).sum()
    )
    for v in out["throughput_interval"]["m-tp"].values():
        assert v["margin"] >= 0 and v["coverage_after"] >= 0.8
    assert out["throughput_alert"]["m-tp"]["act_ratio"] >= 0.5
    assert "KATL|h6" in out["episodes"]["m-tp"]["cells"]

    # Jul-Sep labels move the calibrator, not which rows are assessed.
    flipped = labels.copy()
    jul_sep = sev & times_of(preds, labels, *FIT)
    flipped.loc[jul_sep, "y_true"] = 1 - flipped.loc[jul_sep, "y_true"]
    moved = write_and_run(tmp_path, preds, flipped, reference)
    assert moved["calibrators"][SEVERE] != out["calibrators"][SEVERE]
    new = moved["severe_delay_thresholds"]["m-delay"]["act"]["pooled"]
    assert (new["n"], new["positives"]) == (pooled["n"], pooled["positives"])

    # 2025 rows (predictions and labels) are never read.
    late = labels.copy()
    y2025 = times_of(
        preds,
        labels,
        pd.Timestamp("2025-01-01", tz="UTC"),
        pd.Timestamp("2026-01-01", tz="UTC"),
    )
    assert y2025.any()
    late.loc[y2025, "y_true"] = 0.0
    late_preds = preds.copy()
    late_preds.loc[late_preds["target_start_utc"].ge(ASSESS[1]), "estimate"] = 0.99
    assert write_and_run(tmp_path, late_preds, late, reference) == out


def test_pooled_fallback_below_min_positives():
    rng = np.random.default_rng(2)
    n = 4000
    p = rng.uniform(0, 1, n)
    rows = pd.DataFrame(
        {"airport_icao": "KATL", "p_cal": p, "y_true": rng.binomial(1, p)}
    )
    sparse = pd.DataFrame({"airport_icao": "KDFW", "p_cal": rng.uniform(0, 1, 200),
                           "y_true": np.r_[np.ones(MIN_POSITIVES - 1), np.zeros(200 - MIN_POSITIVES + 1)]})  # fmt: skip
    th = severe_thresholds(pd.concat([rows, sparse], ignore_index=True))
    for level in ("act", "watch"):
        assert th[level]["KATL"]["pooled"] is False
        assert th[level]["KDFW"]["pooled"] is True
        assert th[level]["KDFW"]["threshold"] == th[level]["pooled"]["threshold"]


def test_unreachable_precision_gives_null():
    out = pick_threshold([0.1, 0.5, 0.9], [0, 0, 0], 0.5, 1)
    assert out["threshold"] is None and out["reason"] == "precision_target_not_reached"
    hit = pick_threshold([0.1, 0.5, 0.9, 0.95], [0, 0, 1, 0], 0.5, 2)
    assert (
        hit["threshold"] == 0.9
        and hit["precision"] == 0.5
        and hit["alerts_per_airport_day"] == 1.0
    )


def test_episode_merge_and_hits():
    t0 = pd.Timestamp("2024-10-02", tz="UTC")
    alerts = [t0 + k * H for k in (0, 1, 3, 6, 10)]  # 0-3 merge over a 1 h gap
    events = [t0 + k * H for k in (4, 12, 20)]  # 4 is within 1 h of episode 0-3
    assert episodes(alerts, events, days=1) == {
        "episodes": 3, "hits": 1, "false_episodes": 2, "events": 3,
        "missed_events": 2, "episodes_per_day": 3.0,
    }  # fmt: skip
    assert episodes([t0, t0 + 3 * H], [], days=1)["episodes"] == 2  # 2 h gap splits


def fallback_rows(n, fallback_err, kind=TARGET):
    rng = np.random.default_rng(3)
    t = pd.Timestamp("2024-02-01", tz="UTC") + pd.to_timedelta(np.arange(n), unit="h")
    y = (
        rng.binomial(1, 0.3, n).astype(float)
        if kind == SEVERE
        else rng.normal(50, 5, n)
    )
    ref = np.full(n, 0.3) if kind == SEVERE else y + rng.normal(0, 3, n)
    fb = (
        np.clip(y + rng.normal(0, fallback_err, n), 0, 1)
        if kind == SEVERE
        else y + rng.normal(0, fallback_err, n)
    )
    base = {"prediction_id": [f"p{i}" for i in range(n)], "target_start_utc": t, "target_kind": kind,
            "y_true": y, "eligible": True}  # fmt: skip
    return pd.concat([pd.DataFrame(base | {"model_version": "fb", "estimate": fb}),
                      pd.DataFrame(base | {"model_version": "clim", "estimate": ref})])  # fmt: skip


def test_validate_fallback_verdicts():
    good = validate_fallback(fallback_rows(100, 1.0), "fb", "clim")
    assert (
        good["verdict"] == "degraded" and good["metric"] == "rmse" and good["n"] == 100
    )
    bad = validate_fallback(fallback_rows(100, 10.0), "fb", "clim")
    assert bad["verdict"] == "unavailable" and bad["reason"] == "worse_than_reference"
    thin = validate_fallback(fallback_rows(29, 1.0), "fb", "clim")
    assert thin["verdict"] == "unavailable" and thin["reason"] == "fewer_than_30_rows"
    binary = validate_fallback(fallback_rows(100, 0.05, SEVERE), "fb", "clim")
    assert binary["metric"] == "brier" and binary["verdict"] == "degraded"
    calib = fallback_rows(100, 1.0).assign(
        target_start_utc=pd.Timestamp("2024-08-01", tz="UTC")
    )
    assert validate_fallback(calib, "fb", "clim")["n"] == 0  # validation rows only


def test_an_unmet_act_share_leaves_no_act_ratio():
    # Every act-hour came in well above 0.70 of the ceiling, at every ratio tried.
    rows = pd.DataFrame(
        {"p10_widened": [10.0] * 4, "p95": [100.0] * 4, "actual_ratio": [0.95] * 4}
    )
    out = calibrate.throughput_alerts(rows)
    assert out["act_ratio"] is None and out["reached"] is False
    assert out["reason"] == "act_share_target_not_reached"
    assert out["steps"][-1]["act_ratio"] == calibrate.RATIO_FLOOR
