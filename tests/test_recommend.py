import json

import pandas as pd
import pytest

from airbus_challenge.baselines import TARGET
from airbus_challenge.recommend import (
    SEVERE,
    THRESHOLD_LABEL,
    THRESHOLDS,
    advisories,
    load_policy,
    recommend,
)

AS_OF = pd.Timestamp("2024-03-05 12:00", tz="UTC")
TARGET_T = AS_OF + pd.Timedelta(hours=3)  # 10:00 local at KATL


def reference(p95=100.0, fit_hours=50):
    return pd.DataFrame({
        "airport_icao": ["KATL"], "airport_local_hour": [10],
        "clear_weather_p95_arrivals_per_hour": [p95], "clear_weather_fit_hours": [fit_hours],
        "clear_weather_reference_id": ["ref-1"],
        "clear_weather_fit_end_utc": [pd.Timestamp("2024-01-01", tz="UTC")],
    })  # fmt: skip


def row(kind, estimate, p10=None, status="available", flight_id=None, reasons=()):
    return {
        "airport_icao": "KATL", "as_of_utc": AS_OF, "target_start_utc": TARGET_T, "horizon_h": 3,
        "flight_id": flight_id, "target_kind": kind, "estimate": estimate, "p10": p10,
        "p90": None, "unit": "touchdowns/hour" if kind == TARGET else "probability",
        "status": status, "reason_codes": list(reasons), "model_version": f"m-{kind}",
        "generated_at_utc": AS_OF,
    }  # fmt: skip


def preds(tp=95.0, p10=90.0, delay=(0.05, 0.10), canc=(0.02,), tp_status="available"):
    rows = [
        row(
            TARGET,
            tp,
            p10,
            status=tp_status,
            reasons=["x"] if tp_status == "unavailable" else (),
        )
    ]
    rows += [row(SEVERE, p, flight_id=f"F{i}") for i, p in enumerate(delay)]
    rows += [row("cancellation", p, flight_id=f"F{i}") for i, p in enumerate(canc)]
    return pd.DataFrame(rows)


def by_kind(rec):
    return {c["kind"]: c for c in rec["components"]}


def test_normal():
    rec = recommend(preds(), reference())
    assert rec["level"] == "normal"
    tp = by_kind(rec)["throughput"]
    assert tp["numbers"]["ratio_estimate"] == pytest.approx(0.95)
    assert tp["timestamps"]["as_of_utc"] == AS_OF.isoformat()
    assert tp["reference"]["clear_weather_reference_id"] == "ref-1"
    assert "arrival throughput (AAR proxy)" in tp["message"]


@pytest.mark.parametrize(
    "tp,p10,level", [(80.0, 75.0, "watch"), (95.0, 60.0, "watch"), (60.0, 50.0, "act")]
)
def test_throughput_levels(tp, p10, level):
    rec = recommend(preds(tp=tp, p10=p10), reference())
    assert by_kind(rec)["throughput"]["level"] == level
    assert rec["level"] == level


@pytest.mark.parametrize(
    "delay,level", [((0.1, 0.25), "watch"), ((0.1, 0.5), "act"), ((0.2,), "normal")]
)
def test_severe_delay_levels(delay, level):
    sd = by_kind(recommend(preds(delay=delay), reference()))["severe_delay"]
    assert sd["level"] == level  # 0.20 is not strictly above the watch threshold
    assert sd["numbers"]["max_probability"] == max(delay)
    assert "conditional on the flight operating" in sd["label"]


def test_unavailable_abstains_with_reasons():
    rec = recommend(preds(tp=None, p10=None, tp_status="unavailable"), reference())
    tp = by_kind(rec)["throughput"]
    assert tp["level"] == "abstain" and tp["reasons"] == ["x"]
    assert rec["level"] == "abstain"  # no all-clear while an input is missing


def test_missing_or_thin_reference_abstains():
    for ref in (None, reference(fit_hours=3), reference(p95=0.0)):
        tp = by_kind(recommend(preds(), ref))["throughput"]
        assert tp["level"] == "abstain"
        assert "no_usable_clear_weather_reference" in tp["reasons"]


def test_no_delay_rows_or_all_unavailable_abstains():
    rec = recommend(preds(delay=()), reference())
    assert by_kind(rec)["severe_delay"]["reasons"] == ["no_prediction_rows"]
    df = preds()
    df.loc[df.target_kind.eq(SEVERE), ["estimate", "status"]] = [None, "unavailable"]
    assert by_kind(recommend(df, reference()))["severe_delay"]["level"] == "abstain"


def test_cancellation_separate():
    low = recommend(preds(canc=(0.01,)), reference())
    high = recommend(preds(canc=(0.99,)), reference())
    assert high["cancellation"]["numbers"]["max_probability"] == 0.99
    assert high["cancellation"]["reported_separately"] is True
    assert by_kind(high)["severe_delay"] == by_kind(low)["severe_delay"]
    assert high["level"] == low["level"] == "normal"


def test_provisional_label_everywhere():
    assert THRESHOLDS["label"] == THRESHOLD_LABEL == "provisional_until_WP-D7"
    rec = recommend(preds(), reference())
    assert rec["threshold_label"] == THRESHOLD_LABEL
    assert set(advisories([rec]).threshold_label) == {THRESHOLD_LABEL}


def test_contract_violations_fail_loudly():
    with pytest.raises(ValueError, match="probability"):
        recommend(preds(delay=(1.5,)), reference())
    two = pd.concat([preds(), preds().assign(as_of_utc=AS_OF + pd.Timedelta(hours=1))])
    with pytest.raises(ValueError, match="one airport"):
        recommend(two, reference())


def calibration_json(tmp_path, act=0.5, watch=0.3, act_ratio=0.70, margin=5.0):
    th = lambda t: {
        "pooled": {"threshold": t},
        "KATL": {"threshold": t, "pooled": False},
    }
    cal = {
        "policy_version": "wp-d7-v1",
        "calibrators": {SEVERE: {f"m-{SEVERE}": {"x": [0.0, 0.1, 1.0], "y": [0.0, 0.6, 0.9]}}},
        "severe_delay_thresholds": {f"m-{SEVERE}": {"act": th(act), "watch": th(watch)}},
        "throughput_interval": {f"m-{TARGET}": {"KATL": {"margin": margin}}},
        "throughput_alert": {f"m-{TARGET}": {"act_ratio": act_ratio, "watch_ratio": 0.85}},
    }  # fmt: skip
    (tmp_path / "calibration.json").write_text(json.dumps(cal))
    return load_policy(tmp_path)


def test_policy_from_calibration_json(tmp_path):
    assert load_policy(tmp_path) is THRESHOLDS  # no file -> provisional
    policy = calibration_json(tmp_path)
    assert policy["label"] == "wp-d7-v1"
    assert policy["source"] == str(tmp_path / "calibration.json")
    rec = recommend(preds(tp=95.0, p10=72.0, delay=(0.1,)), reference(), policy)
    assert rec["threshold_label"] == "wp-d7-v1" and "provisional" not in rec["message"]
    assert set(advisories([rec]).threshold_label) == {"wp-d7-v1"}
    sd, tp = by_kind(rec)["severe_delay"], by_kind(rec)["throughput"]
    assert sd["level"] == "act"
    assert sd["numbers"]["max_probability"] == pytest.approx(0.6)  # calibrated
    assert tp["level"] == "act" and tp["numbers"]["p10_widened"] == 67.0  # 72-5 < 70
    old = recommend(preds(tp=95.0, p10=72.0, delay=(0.1,)), reference())
    assert by_kind(old)["severe_delay"]["level"] == "normal"
    assert by_kind(old)["throughput"]["level"] == "normal"


def test_null_threshold_never_alerts(tmp_path):
    policy = calibration_json(tmp_path, act=None, watch=None, act_ratio=None)
    rec = recommend(preds(tp=95.0, p10=10.0, delay=(0.99,)), reference(), policy)
    sd, tp = by_kind(rec)["severe_delay"], by_kind(rec)["throughput"]
    assert sd["level"] == "abstain" and "no_threshold_meets_precision" in sd["reasons"]
    assert sd["numbers"]["n_above_act"] == 0
    assert tp["level"] == "normal"  # p10 far below the ceiling, but act ratio is null
    only_watch = calibration_json(tmp_path, act=None, watch=0.3)
    sd = by_kind(recommend(preds(delay=(0.99,)), reference(), only_watch))[
        "severe_delay"
    ]
    assert sd["level"] == "watch"
