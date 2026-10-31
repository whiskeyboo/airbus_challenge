import json

import pandas as pd
import pytest

from airbus_challenge.download import sha256
from airbus_challenge.failures import SIGNALS, main
from airbus_challenge.features import FEATURES

CANDIDATE = "candidate_v1"
PERSISTENCE = "baseline_persistence_v1"
CLIMATOLOGY = "baseline_climatology_v1"
TARGET = "reporting_carrier_touchdowns"
T = pd.Timestamp("2024-03-05 12:00", tz="UTC")


def miss(pid="p1", horizon=3, estimate=50.0, y_true=40.0, **extra) -> dict:
    as_of = pd.Timestamp("2024-03-05 15:00", tz="UTC") - pd.Timedelta(hours=horizon)
    return {
        "split": "validation",
        "cohort": "fixture-v0",
        "target": TARGET,
        "target_label": "arrival throughput (AAR proxy)",
        "model": CANDIDATE,
        "prediction_id": pid,
        "airport": "KATL",
        "horizon": horizon,
        "as_of_utc": as_of.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target_start_utc": "2024-03-05T15:00:00Z",
        "estimate": estimate,
        "y_true": y_true,
        "error": estimate - y_true,
        **extra,
    }


def prediction(
    m: dict,
    model=CANDIDATE,
    estimate=None,
    p10=None,
    p90=None,
    status="available",
    codes=(),
):
    return {
        "prediction_id": m["prediction_id"],
        "target_kind": m["target"],
        "model_version": model,
        "target_start_utc": pd.Timestamp(m["target_start_utc"]),
        "estimate": m["estimate"] if estimate is None else estimate,
        "p10": p10,
        "p90": p90,
        "unit": "touchdowns/hour",
        "status": status,
        "reason_codes": list(codes),
    }


def snapshot(m: dict, status="ok", codes=(), **features) -> dict:
    base = {
        "metar_age_min": 20.0,
        "taf_age_min": 120.0,
        "taf_lead_h": 5.0,
        "metar_wind_kt": 8.0,
    }
    return {
        "prediction_id": m["prediction_id"],
        "snapshot_key": f"key-{m['prediction_id']}",
        "as_of_utc": pd.Timestamp(m["as_of_utc"]),
        "data_mode": "fixture",
        "status": status,
        "reason_codes": list(codes),
        "feature_version": "fixture",
        "target_hour_utc": 15,
        **base,
        **features,
    }


def lineage(m: dict, available_at=None, group="metar_latest", record="r1") -> dict:
    return {
        "snapshot_key": f"key-{m['prediction_id']}",
        "feature_group": group,
        "source_record_id": record,
        "source_ref": f"ref-{record}",
        "contributing_available_at_utc": available_at
        or pd.Timestamp(m["as_of_utc"]) - pd.Timedelta(minutes=20),
        "availability_basis": "simulated",
        "transform_version": "fixture",
    }


def run(tmp_path, misses, preds, snaps, lins, data_mode="fixture", scope="dev"):
    pred_path = tmp_path / "artifacts" / "run" / "predictions.parquet"
    pred_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(preds).astype({"p10": "float64", "p90": "float64"}).to_parquet(
        pred_path
    )
    snap_path, lin_path = tmp_path / "snapshots.parquet", tmp_path / "lineage.parquet"
    pd.DataFrame(snaps).to_parquet(snap_path)
    pd.DataFrame(lins).to_parquet(lin_path)
    metrics = tmp_path / "metrics_dev.json"
    metrics.write_text(
        json.dumps(
            {
                "run_id": "evaluate_dev",
                "scope": scope,
                "experiment": "primary",
                "data_mode": data_mode,
                "data_sha256": {str(pred_path): sha256(pred_path)},
                "worst_misses": misses,
            }
        )
    )
    path = main(metrics, snap_path, lin_path, tmp_path / "reports")
    return path, json.loads(path.read_text())["cases"]


def single(tmp_path, m, pred=None, peers=(), snap=None, lins=None):
    preds = [pred or prediction(m), *peers]
    snaps = [snap or snapshot(m)]
    return run(tmp_path, [m], preds, snaps, lins or [lineage(m)])[1][0]


def codes(case) -> set[str]:
    return {item["code"] for item in case["limitations"]}


def test_fixture_writes_under_reports_fixture(tmp_path):
    m = miss()
    path, cases = run(tmp_path, [m], [prediction(m)], [snapshot(m)], [lineage(m)])
    assert path == tmp_path / "reports" / "fixture" / "failure_cases_dev.json"
    assert cases[0]["explanation_status"] == "ok"


def test_case_carries_prediction_outcome_baselines_and_sources(tmp_path):
    m = miss()
    peers = [
        prediction(m, PERSISTENCE, 30.0, codes=["simulated_feed"]),
        prediction(m, CLIMATOLOGY, 35.0),
    ]
    case = single(tmp_path, m, prediction(m, p10=45.0, p90=55.0), peers)
    assert case["prediction"]["p10"] == 45.0
    assert case["outcome"] == {"y_true": 40.0, "error": 10.0, "abs_error": 10.0}
    assert case["baselines"][PERSISTENCE]["estimate"] == 30.0
    assert case["baselines"][CLIMATOLOGY]["estimate"] == 35.0
    known = case["known_at_issue"]
    assert known["features"]["metar_wind_kt"]["value"] == 8.0
    assert known["features"]["metar_wind_kt"]["source_age_min"] == 20.0
    assert known["sources"][0]["source_record_id"] == "r1"
    assert known["source_ages_min"]["metar_age_min"] == 20.0


def test_rows_after_issue_time_do_not_change_the_case(tmp_path):
    m = miss()
    later = pd.Timestamp(m["as_of_utc"]) + pd.Timedelta(minutes=30)
    later_request = miss("p2", horizon=1)  # same target, issued 2 h later
    calm = snapshot(later_request, metar_ts_3h=False)
    base = run(tmp_path / "a", [m], [prediction(m)], [snapshot(m), calm], [lineage(m)])[
        1
    ]
    changed = run(
        tmp_path / "b",
        [m],
        [prediction(m)],
        [snapshot(m), snapshot(later_request, metar_wind_kt=40.0, metar_ts_3h=True)],
        [
            lineage(m),
            lineage(m, available_at=later, record="hindsight"),
            lineage(m, available_at=later, group="taf", record="late-taf"),
            lineage(later_request),
        ],
    )[1]
    assert changed == base


def test_missing_snapshot_is_insufficient_data(tmp_path):
    m, other = miss(), miss("p2")
    case = run(tmp_path, [m], [prediction(m)], [snapshot(other)], [lineage(other)])[1][
        0
    ]
    assert case["explanation_status"] == "insufficient_data"
    assert case["known_at_issue"] is None
    assert case["advisory_possible"] is None
    assert case["advisory_reason"].startswith("insufficient_data")
    assert "no_feature_snapshot" in codes(case)


@pytest.mark.parametrize(
    ("snap_kwargs", "code"),
    [
        (
            {"status": "partial", "codes": ["metar_stale"], "metar_age_min": 240.0},
            "metar_stale",
        ),
        (
            {
                "status": "partial",
                "codes": ["metar_unavailable"],
                "metar_age_min": None,
            },
            "metar_unavailable",
        ),
        ({"status": "partial", "codes": ["taf_uncovered"]}, "taf_uncovered"),
        ({"status": "partial", "codes": ["taf_unavailable"]}, "taf_unavailable"),
        ({"status": "missing"}, "degraded_input"),
    ],
)
def test_snapshot_limitations_fire(tmp_path, snap_kwargs, code):
    m = miss()
    case = single(tmp_path, m, snap=snapshot(m, **snap_kwargs))
    assert code in codes(case)
    assert "metar_stale" in codes(
        single(tmp_path, m, snap=snapshot(m, metar_age_min=200.0))
    )


def test_clean_case_has_no_limitations(tmp_path):
    assert codes(single(tmp_path, miss())) == set()


def test_partial_source_hour_fires_from_the_baseline_feed(tmp_path):
    m = miss()
    peer = prediction(
        m, PERSISTENCE, 20.0, codes=["simulated_feed", "source_hour_partial"]
    )
    assert "source_hour_partial" in codes(single(tmp_path, m, peers=[peer]))


def test_degraded_prediction_fires(tmp_path):
    m = miss()
    assert "degraded_input" in codes(
        single(tmp_path, m, prediction(m, status="degraded"))
    )


def test_large_error_fires_only_at_long_horizon(tmp_path):
    long, short = miss(horizon=12, estimate=60.0), miss(horizon=3, estimate=60.0)
    assert "large_error_long_horizon" in codes(single(tmp_path, long))
    assert "large_error_long_horizon" not in codes(single(tmp_path, short))
    small = miss(horizon=12, estimate=42.0)
    assert "large_error_long_horizon" not in codes(single(tmp_path, small))


def test_outcome_outside_interval_fires(tmp_path):
    m = miss()
    assert "outside_interval" in codes(
        single(tmp_path, m, prediction(m, p10=45.0, p90=55.0))
    )
    assert "outside_interval" not in codes(
        single(tmp_path, m, prediction(m, p10=35.0, p90=55.0))
    )


def test_advisory_needs_a_signal_at_issue_time(tmp_path):
    m = miss()
    calm = single(tmp_path, m)
    assert calm["advisory_possible"] is False
    storm = single(
        tmp_path, m, snap=snapshot(m, taf_ts_conditional=True, taf_ceiling_min_ft=600.0)
    )
    assert storm["advisory_possible"] is True
    assert "taf_ts_conditional=True" in storm["advisory_reason"]
    assert "taf_ceiling_min_ft=600 < 1000" in storm["advisory_reason"]
    wide = single(tmp_path, m, prediction(m, p10=20.0, p90=60.0))
    assert wide["advisory_possible"] is True
    assert "interval width" in wide["advisory_reason"]


def test_signals_name_registered_features():
    assert set(SIGNALS) <= set(FEATURES)


def test_dev_refuses_a_test_split_miss(tmp_path):
    m = miss(split="test")
    with pytest.raises(ValueError, match="2025"):
        run(tmp_path, [m], [prediction(m)], [snapshot(m)], [lineage(m)])


def test_predictions_that_disagree_with_metrics_are_refused(tmp_path):
    m = miss()
    with pytest.raises(ValueError, match="disagree"):
        run(tmp_path, [m], [prediction(m, estimate=99.0)], [snapshot(m)], [lineage(m)])
