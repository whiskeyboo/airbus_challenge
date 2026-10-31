import pandas as pd
import pytest

from airbus_challenge.operations import request_features, validate_feed


def feed():
    starts = pd.date_range("2023-01-01T08:00Z", periods=4, freq="h")
    return pd.DataFrame(
        {
            "airport_icao": ["KATL"] * 4,
            "source_hour_start_utc": starts,
            "source_hour_end_utc": starts + pd.Timedelta(hours=1),
            "available_at_utc": starts + pd.Timedelta(hours=1, minutes=10),
            "reporting_carrier_touchdowns": [0, 10, None, None],
            "n_unresolved": [0, 0, 1, None],
            "coverage_status": [
                "complete_for_source_scope",
                "complete_for_source_scope",
                "partial",
                "missing",
            ],
            "feed_eligible": [True, True, False, False],
            "availability_basis": ["simulated"] * 4,
            "data_mode": ["fixture"] * 4,
        }
    )


def requests(times, airport="KATL"):
    return pd.DataFrame(
        {
            "prediction_id": [f"p{i}" for i in range(len(times))],
            "airport_icao": [airport] * len(times),
            "as_of_utc": pd.to_datetime(times, utc=True),
            "cohort_version": ["retrospective_schedule_v1"] * len(times),
            "data_mode": ["fixture"] * len(times),
        }
    )


def test_release_boundary_partial_missing_stale_and_zero():
    observations = feed()
    validate_feed(observations, 10)
    req = requests(
        [
            "2023-01-01T10:05Z",
            "2023-01-01T10:10Z",
            "2023-01-01T11:10Z",
            "2023-01-01T12:10Z",
        ]
    )
    out = request_features(req, observations).set_index("prediction_id")
    assert out.loc["p0", "ops_arrivals_last_complete"] == 0
    assert out.loc["p1", "ops_arrivals_last_complete"] == 10
    assert out.loc["p2", "ops_status"] == "partial"
    assert out.loc["p3", "ops_status"] == "missing"
    assert out.loc[["p2", "p3"], "ops_arrivals_last_complete"].isna().all()
    assert out.loc["p1", "source_available_at_utc"] == req.loc[1, "as_of_utc"]
    assert (out.source_hour_end_utc <= out.as_of_utc).all()
    assert (out.source_available_at_utc <= out.as_of_utc).all()
    stale = request_features(requests(["2023-01-01T12:01Z"]), observations.iloc[:1])
    assert stale.ops_status.iloc[0] == "stale" and pd.isna(
        stale.ops_arrivals_last_complete.iloc[0]
    )
    absent = request_features(requests(["2023-01-01T12:01Z"], "KDFW"), observations)
    assert absent.ops_status.iloc[0] == "missing" and pd.isna(
        absent.ops_arrivals_last_complete.iloc[0]
    )


def test_outcomes_after_issue_time_do_not_change_features():
    observations = feed()
    req = requests(["2023-01-01T10:05Z"])
    before = request_features(req, observations)
    changed = observations.copy()
    changed.loc[
        changed.available_at_utc.gt(req.as_of_utc.iloc[0]),
        "reporting_carrier_touchdowns",
    ] = 999
    pd.testing.assert_frame_equal(before, request_features(req, changed))
    with pytest.raises(ValueError, match="latency"):
        validate_feed(observations, 0)
    with pytest.raises(ValueError, match="Duplicate request"):
        request_features(pd.concat([req, req]), observations)


def test_build_writes_hash_bound_optional_feature_table(tmp_path):
    import json

    from airbus_challenge.download import sha256
    from airbus_challenge.operations import build

    req = requests(["2023-01-01T10:05Z", "2023-01-01T11:10Z"])
    obs = feed()
    reqpath = tmp_path / "prediction_requests.parquet"
    feedpath = tmp_path / "operational_feed.parquet"
    req.to_parquet(reqpath, index=False)
    obs.to_parquet(feedpath, index=False)
    base = {"data_mode": "fixture", "source_flights_sha256": "source"}
    reqpath.with_suffix(".manifest.json").write_text(
        json.dumps({**base, "rows": 2, "parquet_sha256": sha256(reqpath)})
    )
    feedpath.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                **base,
                "rows": 4,
                "parquet_sha256": sha256(feedpath),
                "availability_basis": "simulated",
                "latency_min": 10,
            }
        )
    )
    report = build(tmp_path, batch_size=1)
    out = pd.read_parquet(tmp_path / "operations_features.parquet")
    assert report["rows"] == 2 and report["source_requests_sha256"] == sha256(reqpath)
    assert report["source_feed_sha256"] == sha256(feedpath)
    assert report["parquet_sha256"] == sha256(tmp_path / "operations_features.parquet")
    assert report["policy_status"].startswith("provisional")
    assert out.ops_status.tolist() == ["available", "partial"]
    assert out.ops_arrivals_last_complete.iloc[0] == 0
    assert pd.isna(out.ops_arrivals_last_complete.iloc[1])
