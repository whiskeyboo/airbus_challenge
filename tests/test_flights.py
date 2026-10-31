import pandas as pd
import pytest

from airbus_challenge.clean import (
    CLOCKS,
    DURATIONS,
    TIMES,
    airport_map,
    flight_keys,
    flights,
    mark_sample,
)

CONFIG = {
    "airports": {
        "KATL": {"iata": "ATL", "timezone": "America/New_York"},
        "KDFW": {"iata": "DFW", "timezone": "America/Chicago"},
    }
}
SRC = {
    "key": "bts/fixture.zip",
    "sha256": "fixture",
    "retrieved_at_utc": "2026-10-31T00:00:00Z",
}


def row(**updates):
    result = dict.fromkeys(CLOCKS + DURATIONS)
    result.update(
        FlightDate="2023-01-15",
        DOT_ID_Reporting_Airline="19790",
        Flight_Number_Reporting_Airline="123",
        Origin="ATL",
        Dest="DFW",
        Reporting_Airline="DL",
        CRSDepTime="1000",
        CRSArrTime="1130",
        CRSElapsedTime="150",
        DepTime="0955",
        DepDelay="-5",
        TaxiOut="15",
        WheelsOff="1010",
        WheelsOn="1115",
        TaxiIn="10",
        ArrTime="1125",
        ActualElapsedTime="150",
        AirTime="125",
        ArrDelay="-5",
        Cancelled="0",
        Diverted="0",
    )
    result.update(updates)
    return result


def clean(**updates):
    return flights(pd.DataFrame([row(**updates)]), CONFIG, SRC).iloc[0]


def test_negative_delay_and_cross_timezone():
    r = clean()
    assert r.scheduled_dep_utc == pd.Timestamp("2023-01-15T15:00Z")
    assert r.scheduled_arr_utc == pd.Timestamp("2023-01-15T17:30Z")
    assert r.actual_dep_utc == pd.Timestamp("2023-01-15T14:55Z")
    assert r.wheels_on_utc == pd.Timestamp("2023-01-15T17:15Z")
    assert r.dep_delay_min == -5
    assert r.timestamp_status == "valid"
    r = clean(
        Origin="DFW", Dest="ATL", CRSArrTime="1330", WheelsOn="1315", ArrTime="1325"
    )
    assert r.scheduled_dep_utc == pd.Timestamp("2023-01-15T16:00Z")
    assert r.scheduled_arr_utc == pd.Timestamp("2023-01-15T18:30Z")
    assert r.timestamp_status == "valid"


def test_midnight_2400_and_overnight():
    r = clean(
        CRSDepTime="2400",
        CRSArrTime="0130",
        DepTime="2355",
        WheelsOff="0010",
        WheelsOn="0115",
        ArrTime="0125",
    )
    assert r.scheduled_dep_utc == pd.Timestamp("2023-01-16T05:00Z")
    assert r.actual_dep_utc == pd.Timestamp("2023-01-16T04:55Z")
    assert r.scheduled_arr_utc == pd.Timestamp("2023-01-16T07:30Z")
    assert r.raw_CRSDepTime == "2400"
    assert r.timestamp_status == "valid"
    r = clean(
        CRSDepTime="2330",
        CRSArrTime="0100",
        DepTime="2325",
        WheelsOff="2340",
        WheelsOn="0045",
        ArrTime="0055",
    )
    assert r.scheduled_arr_utc == pd.Timestamp("2023-01-16T07:00Z")
    assert r.timestamp_status == "valid"


@pytest.mark.parametrize(
    ("date", "clock", "flag"),
    [
        ("2023-03-12", "0230", "scheduled_dep_dst_nonexistent"),
        ("2023-11-05", "0130", "scheduled_dep_dst_ambiguous"),
    ],
)
def test_dst_quarantines_instead_of_guessing(date, clock, flag):
    r = clean(FlightDate=date, CRSDepTime=clock)
    assert pd.isna(r.scheduled_dep_utc)
    assert r.timestamp_status == "quarantined"
    assert flag in r.quality_flags


def test_cancelled_has_no_fabricated_movements():
    r = clean(
        Cancelled="1",
        **dict.fromkeys(
            [
                "DepTime",
                "DepDelay",
                "WheelsOff",
                "WheelsOn",
                "ArrTime",
                "ActualElapsedTime",
                "TaxiOut",
                "TaxiIn",
                "AirTime",
                "ArrDelay",
            ]
        ),
    )
    assert all(pd.isna(r[c]) for c in TIMES[2:])
    assert r.timestamp_status == "partial"
    assert pd.notna(r.scheduled_arr_utc)


def test_diverted_preserves_departure_without_destination_landing():
    r = clean(
        Diverted="1",
        ActualElapsedTime=None,
        ArrDelay=None,
        Div1Airport="BNA",
        Div1WheelsOn="1200",
    )
    assert pd.notna(r.actual_dep_utc)
    assert pd.notna(r.wheels_off_utc)
    assert pd.isna(r.wheels_on_utc)
    assert pd.isna(r.actual_arr_utc)
    assert r.raw_Div1Airport == "BNA"
    assert r.timestamp_status == "partial"


def test_long_delay_preserves_date_not_just_clock():
    r = clean(DepDelay="1495", ArrDelay="1495")
    assert r.actual_dep_utc == pd.Timestamp("2023-01-16T15:55Z")
    assert "actual_dep_utc_clock_mismatch" in r.quality_flags
    r = clean(DepDelay="1435", ArrDelay="1435")
    assert r.actual_dep_utc == pd.Timestamp("2023-01-16T14:55Z")
    assert r.timestamp_status == "valid"


def test_clock_tolerance_and_invalid_clock():
    assert clean(DepTime="0957").timestamp_status == "valid"
    assert clean(DepTime="0958").timestamp_status == "quarantined"
    assert "actual_dep_utc_invalid_clock" in clean(DepTime="2460").quality_flags


def test_csv_matching_ignores_weather_and_normalizes_numbers():
    raw = pd.DataFrame([row(), row(Flight_Number_Reporting_Airline="124")])
    sample = pd.DataFrame(
        [row(Flight_Number_Reporting_Airline="123.0", CRSDepTime="1000.0")]
    )
    df = mark_sample(flights(raw, CONFIG, SRC), flight_keys(sample))
    assert df.in_provided_csv.tolist() == [True, False]


def test_duplicate_rows_preserved_with_unique_deterministic_ids():
    raw = pd.DataFrame([row(), row()])
    df = flights(raw, CONFIG, SRC)
    assert df.flight_id.is_unique
    assert df.source_row_hash.nunique() == 1
    assert df.quality_flags.map(lambda f: "duplicate_flight_key" in f).all()
    assert df.flight_id.tolist() == flights(raw, CONFIG, SRC).flight_id.tolist()


def test_override_and_missing_airport_error():
    assert airport_map(
        ["PBI"],
        {
            "timezone_overrides": {
                "PBI": {"icao": "KPBI", "timezone": "America/New_York"}
            }
        },
    )["PBI"] == ("KPBI", "America/New_York")
    with pytest.raises(ValueError, match="ZZZ"):
        airport_map(["ZZZ"], CONFIG)


def test_repeated_local_hour_keeps_distinct_utc_instants():
    # Distinct unambiguous departure anchors reach both instances of 01:30 in New York.
    a = clean(
        FlightDate="2023-11-05",
        Origin="DFW",
        Dest="ATL",
        CRSDepTime="0030",
        CRSElapsedTime="0",
        CRSArrTime="0130",
    )
    b = clean(
        FlightDate="2023-11-05",
        Origin="ATL",
        Dest="ATL",
        CRSDepTime="0030",
        CRSElapsedTime="120",
        CRSArrTime="0130",
    )
    assert a.scheduled_arr_utc == pd.Timestamp("2023-11-05T05:30Z")
    assert b.scheduled_arr_utc == pd.Timestamp("2023-11-05T06:30Z")


def test_cancelled_record_retains_evidenced_departure_path():
    r = clean(Cancelled="1", WheelsOn=None, ArrTime=None, ActualElapsedTime=None)
    assert r.actual_dep_utc == pd.Timestamp("2023-01-15T14:55Z")
    assert r.wheels_off_utc == pd.Timestamp("2023-01-15T15:10Z")
    assert pd.isna(r.actual_arr_utc)
    assert r.timestamp_status == "partial"


def test_diversion_reached_destination_uses_diversion_elapsed_time():
    r = clean(
        Diverted="1",
        ActualElapsedTime=None,
        DivReachedDest="1.00",
        DivActualElapsedTime="210",
        ArrTime="1225",
        WheelsOn="1215",
    )
    assert r.actual_arr_utc == pd.Timestamp("2023-01-15T18:25Z")
    assert r.wheels_on_utc == pd.Timestamp("2023-01-15T18:15Z")
    assert r.timestamp_status == "partial"


def test_operated_missing_movement_is_quarantined():
    assert "operated_departure_missing" in clean(DepTime=None).quality_flags
    assert clean(DepTime=None).timestamp_status == "quarantined"


def test_build_zip_to_parquet_and_match_audit(tmp_path, monkeypatch):
    import json
    import zipfile

    import pyarrow.parquet as pq
    import yaml

    from airbus_challenge import clean as module
    from airbus_challenge import download

    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/airports.yaml").write_text(yaml.safe_dump(CONFIG))
    raw_dir = tmp_path / "data/raw"
    (raw_dir / "bts").mkdir(parents=True)
    manifest = {}
    records = []
    for month in [1, 2]:
        rows = [
            row(FlightDate=f"2023-{month:02d}-15"),
            row(FlightDate=f"2023-{month:02d}-15", Origin="JFK", Dest="SFO"),
        ]
        raw = pd.DataFrame(rows)
        records.extend(rows)
        path = raw_dir / f"bts/bts_2023_{month:02d}.zip"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("flights.csv", raw.to_csv(index=False))
        manifest[str(path.relative_to(raw_dir))] = {
            "sha256": download.sha256(path),
            "url": "fixture",
            "retrieved_at_utc": "2026-10-31T00:00:00Z",
        }
    sample = pd.DataFrame(records).rename(
        columns=dict(zip(module.KEY, module.SAMPLE_KEY))
    )
    sample = sample[module.SAMPLE_KEY]
    path = raw_dir / "Flight_Data_With_Weather_Final.csv"
    sample.to_csv(path, index=False)
    manifest[path.name] = {
        "sha256": download.sha256(path),
        "url": "fixture",
        "retrieved_at_utc": None,
    }
    (raw_dir / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(
        download,
        "study_window",
        lambda: (pd.Timestamp("2023-01-01"), pd.Timestamp("2023-03-01")),
    )
    report = module.build()
    df = pd.read_parquet(module.OUTPUT)
    assert len(df) == 2
    assert df.in_provided_csv.all()
    assert df.flight_id.is_unique
    assert report["provided_csv_match"]["matched_rows"] == 4
    assert report["provided_csv_match"]["study_airport_matched_rows"] == 2
    assert report["provided_csv_match"]["unmatched_rows"] == 0
    assert report["parquet_sha256"] == download.sha256(module.OUTPUT)
    assert pq.read_schema(module.OUTPUT).field("scheduled_dep_utc").type.tz == "UTC"
    assert not module.OUTPUT.with_name(".flights.parquet.tmp").exists()
    assert module.OUTPUT.with_suffix(".manifest.json").exists()


def test_requests_use_schedule_only_and_retain_cancellations():
    from airbus_challenge.requests import flight_requests

    archive = flights(
        pd.DataFrame(
            [row(), row(Flight_Number_Reporting_Airline="124", Cancelled="1")]
        ),
        CONFIG,
        SRC,
    )
    start, end = (
        pd.Timestamp("2023-01-01", tz="UTC"),
        pd.Timestamp("2023-02-01", tz="UTC"),
    )
    before = flight_requests(archive, ["KATL"], [3, 6], start, end, "fixture")
    changed = archive.copy()
    changed["cancelled"] = ~changed.cancelled
    changed["dep_delay_min"] = 5000
    changed["timestamp_status"] = "quarantined"
    changed["actual_dep_utc"] = pd.Timestamp("2025-01-01T00:00Z")
    pd.testing.assert_frame_equal(
        before, flight_requests(changed, ["KATL"], [3, 6], start, end, "fixture")
    )
    assert len(before) == 4
    assert not {"dep_delay_min", "cancelled", "actual_dep_utc"} & set(before.columns)
    assert before.prediction_id.is_unique
    assert (before.target_start_utc - before.as_of_utc).dt.total_seconds().tolist() == [
        10800,
        10800,
        21600,
        21600,
    ]
    assert before.target_end_utc.isna().all()


def test_request_hash_and_airport_grid_across_dst():
    import hashlib

    from airbus_challenge.requests import COHORT_VERSION, airport_requests

    start, end = pd.Timestamp("2023-11-05T04:00Z"), pd.Timestamp("2023-11-05T08:00Z")
    df = airport_requests(["KATL"], [3], start, end, "fixture", "fixture")
    assert len(df) == 4
    assert df.prediction_id.is_unique
    assert df.target_start_utc.dt.tz_convert("America/New_York").dt.hour.tolist() == [
        0,
        1,
        1,
        2,
    ]
    canonical = f"throughput|KATL||2023-11-05T04:00:00Z|3|{COHORT_VERSION}"
    assert df.iloc[0].prediction_id == hashlib.sha256(canonical.encode()).hexdigest()
    assert (df.target_end_utc - df.target_start_utc).eq(pd.Timedelta(hours=1)).all()


def test_flight_requests_half_open_target_window():
    from airbus_challenge.requests import flight_requests

    archive = flights(pd.DataFrame([row()]), CONFIG, SRC)
    target = pd.Timestamp("2023-01-15T15:00Z")
    assert (
        len(
            flight_requests(
                archive, ["KATL"], [3], target, target + pd.Timedelta(hours=1)
            )
        )
        == 1
    )
    assert flight_requests(
        archive, ["KATL"], [3], target - pd.Timedelta(hours=1), target
    ).empty


def outcome_fixture(rows):
    df = flights(pd.DataFrame(rows), CONFIG, SRC)
    if "raw_DivReachedDest" not in df:
        df["raw_DivReachedDest"] = pd.Series(pd.NA, index=df.index, dtype="string")
    return df


def test_hourly_p12_counts_cancellations_and_diversions():
    from airbus_challenge.targets import airport_hours

    rows = [row(Flight_Number_Reporting_Airline=str(i)) for i in range(20)]
    rows += [
        row(Flight_Number_Reporting_Airline="cancel", Cancelled="1"),
        row(Flight_Number_Reporting_Airline="divert", Diverted="1"),
    ]
    rows[-2]["Flight_Number_Reporting_Airline"] = "21"
    rows[-1]["Flight_Number_Reporting_Airline"] = "22"
    df = outcome_fixture(rows)
    # One of the twenty operated arrivals has inconsistent clocks: exactly 5% unresolved.
    df.at[0, "timestamp_status"] = "quarantined"
    grid = airport_hours(
        df,
        "KDFW",
        pd.Timestamp("2023-01-15T17:00Z"),
        pd.Timestamp("2023-01-15T19:00Z"),
        "fixture",
    )
    first = grid.iloc[0]
    assert first.n_resolved == 19
    assert first.n_unresolved == 1
    assert first.coverage_fraction == 0.95
    assert first.coverage_status == "partial"
    assert first.throughput_label_eligible
    assert grid.iloc[1].reporting_carrier_touchdowns == 0
    assert grid.iloc[1].coverage_status == "complete_for_source_scope"
    assert grid.iloc[1].coverage_fraction == 1
    df.at[1, "timestamp_status"] = "quarantined"
    assert (
        not airport_hours(
            df,
            "KDFW",
            pd.Timestamp("2023-01-15T17:00Z"),
            pd.Timestamp("2023-01-15T18:00Z"),
            "fixture",
        )
        .iloc[0]
        .throughput_label_eligible
    )


def test_unbounded_arrival_uses_local_day_not_whole_month():
    from airbus_challenge.targets import airport_hours

    df = outcome_fixture([row()])
    df["wheels_on_utc"] = pd.Series(pd.NaT, index=df.index, dtype="datetime64[us, UTC]")
    df["timestamp_status"] = "quarantined"
    grid = airport_hours(
        df,
        "KDFW",
        pd.Timestamp("2023-01-15T00:00Z"),
        pd.Timestamp("2023-01-17T00:00Z"),
        "fixture",
    )
    assert grid.n_unresolved.sum() == 24
    assert (
        grid.loc[
            grid.hour_start_utc.eq(pd.Timestamp("2023-01-15T05:00Z")), "n_unresolved"
        ].iloc[0]
        == 0
    )
    assert (
        grid.loc[
            grid.hour_start_utc.eq(pd.Timestamp("2023-01-16T05:00Z")), "n_unresolved"
        ].iloc[0]
        == 1
    )
    assert grid.month_degraded.all()


def test_missing_source_has_null_counts():
    from airbus_challenge.targets import airport_hours

    df = outcome_fixture([row()])
    grid = airport_hours(
        df,
        "KDFW",
        pd.Timestamp("2023-01-15T17:00Z"),
        pd.Timestamp("2023-01-15T18:00Z"),
        "fixture",
        complete=False,
    )
    assert grid.reporting_carrier_touchdowns.isna().all()
    assert grid.coverage_status.eq("missing").all()
    assert not grid.throughput_label_eligible.any()


def test_label_45_46_cancelled_and_other_timestamp_quarantine():
    from airbus_challenge.requests import flight_requests
    from airbus_challenge.targets import label_rows

    df = outcome_fixture(
        [
            row(DepDelay="45"),
            row(Flight_Number_Reporting_Airline="124", DepDelay="46"),
            row(Flight_Number_Reporting_Airline="125", Cancelled="1"),
        ]
    )
    # Actual-clock mismatches are intentionally irrelevant to P12's per-flight delay label.
    req = flight_requests(
        df,
        ["KATL"],
        [3],
        pd.Timestamp("2023-01-01T00:00Z"),
        pd.Timestamp("2023-02-01T00:00Z"),
        "fixture",
    )
    labels = label_rows(
        req,
        df[["flight_id", "dep_delay_min", "cancelled", "scheduled_dep_utc"]],
        pd.DataFrame(),
    )
    severe = labels[labels.target_kind.eq("departure_delay_gt45")]
    assert severe.y_true.iloc[:2].tolist() == [0, 1]
    assert pd.isna(severe.y_true.iloc[2])
    assert severe.exclusion_reason.iloc[2] == "cancelled"
    assert labels[labels.target_kind.eq("cancellation")].y_true.tolist() == [0, 0, 1]
    assert labels.loc[labels.eligible, "outcome_available_at_utc"].notna().all()
    assert labels.loc[~labels.eligible, "outcome_available_at_utc"].isna().all()
    assert labels.availability_basis.eq("simulated").all()


@pytest.mark.parametrize("all_cohorts", [False, True])
def test_requests_and_targets_end_to_end_fixture(tmp_path, monkeypatch, all_cohorts):
    import json

    import yaml

    from airbus_challenge import requests, targets
    from airbus_challenge.download import sha256

    monkeypatch.chdir(tmp_path)
    Path = type(tmp_path)
    Path("configs").mkdir()
    Path("configs/airports.yaml").write_text(yaml.safe_dump(CONFIG))
    experiment = {
        "horizons_h": [3, 6],
        "splits": {"train": {"start": "2023-01-15", "end": "2023-01-16"}},
        "targets": {
            "severe_delay_threshold_min": 45,
            "capacity_ratio": "throughput_over_clear_weather_p95",
        },
        "clear_weather": {
            "min_ceiling_ft": 3000,
            "min_visibility_sm": 5,
            "allow_weather_codes": False,
        },
    }
    Path("configs/experiment.yaml").write_text(yaml.safe_dump(experiment))
    df = outcome_fixture(
        [
            row(DepDelay="45"),
            row(Flight_Number_Reporting_Airline="124", DepDelay="46"),
            row(Flight_Number_Reporting_Airline="125", Cancelled="1"),
        ]
    )
    Path("data/processed").mkdir(parents=True)
    df["in_provided_csv"] = [True, False, True]
    df.to_parquet(requests.FLIGHTS, index=False)
    requests.FLIGHTS.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "data_mode": "fixture",
                "parquet_sha256": sha256(requests.FLIGHTS),
                "sources": [{"sha256": "fixture", "key": "bts/fixture.zip"}],
            }
        )
    )
    weather = pd.DataFrame(
        {
            "airport_icao": ["KDFW"],
            "observed_at_utc": [pd.Timestamp("2023-01-15T17:00Z")],
            "wx_codes": [["TSRA"]],
            "ceiling_ft": [900.0],
            "visibility_sm": [2.0],
            "ceiling_status": ["layer"],
            "quality_flags": [[]],
            "source_record_id": ["fixture-weather-1"],
        }
    )
    weather.to_parquet("data/processed/weather_observations.parquet", index=False)
    report = requests.build(
        cohorts=("all",) if all_cohorts else (requests.COHORT_VERSION,)
    )
    req = pd.read_parquet(requests.OUTPUT)
    assert req.data_mode.eq("fixture").all()
    assert req.prediction_id.is_unique
    assert report["rows"] == (310 if all_cohorts else 102)
    hourly, summary = targets.build()
    labels = pd.read_parquet(targets.LABELS)
    assert len(labels) == (428 if all_cohorts else 204)
    import pyarrow.parquet as pq

    feed = targets.build_operational_feed(targets.HOURLY, tmp_path / "feed", 10)
    feed_path = tmp_path / "feed/operational_feed.parquet"
    feed_manifest = json.loads(feed_path.with_suffix(".manifest.json").read_text())
    assert len(feed) == len(hourly)
    assert feed_manifest["source_hourly_sha256"] == sha256(targets.HOURLY)
    assert feed_manifest["parquet_sha256"] == sha256(feed_path)
    assert feed_manifest["availability_basis"] == "simulated"
    assert feed_manifest["data_mode"] == "fixture"
    assert not {"scheduled_arrivals", "throughput_over_clear_weather_p95"} & set(
        feed.columns
    )
    training_path = targets.build_training_labels(
        requests.OUTPUT, targets.LABELS, output_dir=tmp_path / "training"
    )
    training = pd.read_parquet(training_path)
    training_manifest = json.loads(
        training_path.with_suffix(".manifest.json").read_text()
    )
    assert training.outcome_available_at_utc.le(training.fit_cutoff_utc).all()
    assert training.eligible.all()
    assert not training.target_start_utc.ge(pd.Timestamp("2023-01-16T00:00Z")).any()
    assert training_manifest["source_labels_sha256"] == sha256(targets.LABELS)
    assert training_manifest["rows"] == len(training)
    assert training_manifest["data_mode"] == "fixture"
    with pytest.raises(ValueError, match="Capacity reference was fitted after"):
        targets.build_training_labels(
            requests.OUTPUT,
            targets.LABELS,
            fit_cutoff="2023-01-15T18:00Z",
            output_dir=tmp_path / "early-training",
        )
    assert set(hourly.data_mode) == {"fixture"}
    assert set(labels.data_mode) == {"fixture"}
    assert not pq.read_schema(targets.HOURLY).field("data_mode").nullable
    assert not pq.read_schema(targets.LABELS).field("data_mode").nullable
    assert labels.exclusion_reason.isna().eq(labels.eligible).all()
    assert labels.exclusion_detail.isna().eq(labels.eligible).all()
    assert not labels.duplicated(
        ["prediction_id", "target_kind", "label_version"]
    ).any()
    scope = labels.join(
        req.set_index("prediction_id")[["cohort_version"]],
        on="prediction_id",
        validate="many_to_one",
    )
    severe = scope[
        scope.target_kind.eq("departure_delay_gt45")
        & scope.cohort_version.eq(requests.COHORT_VERSION)
    ]
    assert severe.eligible.sum() == 4
    assert severe.y_true.dropna().tolist() == [0, 1, 0, 1]
    assert labels[labels.exclusion_reason.eq("cancelled")].y_true.isna().all()
    manifest = json.loads(targets.LABELS.with_suffix(".manifest.json").read_text())
    assert len(manifest["exclusion_audit"]["threshold_sensitivity"]) == 6
    assert manifest["data_mode"] == "fixture"
    assert sum(r["rows"] for r in manifest["exclusion_counts"]) == len(labels)
    denominator_path = targets.LABELS.with_name("label_denominators.parquet")
    denominators = pd.read_parquet(denominator_path)
    assert denominators.rows.sum() == len(labels)
    assert manifest["label_denominators_sha256"] == sha256(denominator_path)
    denominator_manifest = json.loads(
        denominator_path.with_suffix(".manifest.json").read_text()
    )
    assert denominator_manifest["source_labels_sha256"] == manifest["parquet_sha256"]
    assert denominator_manifest["label_rows"] == len(labels)
    delay_counts = denominators[
        denominators.target_kind.eq("departure_delay_gt45")
        & denominators.cohort_version.eq(requests.COHORT_VERSION)
    ]
    assert delay_counts.loc[delay_counts.eligible, "rows"].sum() == 4
    assert (
        delay_counts.loc[delay_counts.exclusion_reason.eq("cancelled"), "rows"].sum()
        == 2
    )
    assert denominators.data_mode.eq("fixture").all()
    assert {r["task"] for r in manifest["exclusion_counts"]} == {
        "throughput",
        "severe_delay",
    }
    assert any(
        r["exclusion_reason"] is None and r["exclusion_detail"] is None
        for r in manifest["exclusion_counts"]
    )
    assert hourly[["airport_icao", "hour_start_utc"]].duplicated().sum() == 0
    ratios = scope[scope.target_kind.eq("throughput_over_clear_weather_p95")]
    assert set(ratios.cohort_version) == {requests.COHORT_VERSION}
    assert len(ratios) == 96
    assert labels.label_version.eq("0.4.0").all()
    assert summary
    if all_cohorts:
        originals = {
            p: sha256(p) for p in [requests.OUTPUT, targets.HOURLY, targets.LABELS]
        }
        candidate = tmp_path / "candidate"
        candidate_requests = candidate / "prediction_requests.parquet"
        requests.build(candidate_requests, ("all",))
        cached_hourly, _ = targets.build(
            candidate_requests, candidate, reuse_hourly=True
        )
        pd.testing.assert_frame_equal(hourly, cached_hourly)
        assert len(pd.read_parquet(candidate / "labels.parquet")) == 428
        assert all(sha256(p) == value for p, value in originals.items())
        cached_manifest = json.loads(
            (candidate / "airport_hourly.manifest.json").read_text()
        )
        assert cached_manifest["reused_hourly_sha256"] == originals[targets.HOURLY]
        # An empty requested cohort must not replace an existing valid candidate file.
        df["in_provided_csv"] = False
        df.to_parquet(requests.FLIGHTS, index=False)
        source_path = requests.FLIGHTS.with_suffix(".manifest.json")
        source = json.loads(source_path.read_text())
        source["parquet_sha256"] = sha256(requests.FLIGHTS)
        source_path.write_text(json.dumps(source))
        previous = sha256(candidate_requests)
        with pytest.raises(ValueError, match="No eligible requests"):
            requests.build(candidate_requests, ("csv_only_v1",))
        assert sha256(candidate_requests) == previous


def test_overnight_audit_handles_unresolved_dst_with_nullable_strings():
    from airbus_challenge.clean import overnight_rows

    df = outcome_fixture(
        [
            row(FlightDate="2023-11-05", CRSDepTime="0130"),
            row(
                FlightDate="2023-11-05",
                Flight_Number_Reporting_Airline="124",
                CRSDepTime="2330",
                CRSArrTime="0100",
            ),
        ]
    )
    assert overnight_rows(df).tolist() == [False, True]


def test_missing_flight_number_is_identity_exception_not_timestamp_quarantine():
    df = outcome_fixture([row(Flight_Number_Reporting_Airline=None)])
    from airbus_challenge.clean import mark_sample
    from airbus_challenge.targets import airport_hours

    r = mark_sample(df, df.flight_key).iloc[0]
    assert pd.isna(r.flight_number)
    assert not r.in_provided_csv
    assert "missing_flight_number" in r.quality_flags
    assert r.timestamp_status == "valid"
    assert r.flight_id != outcome_fixture([row()]).iloc[0].flight_id
    hourly = airport_hours(
        df,
        "KDFW",
        pd.Timestamp("2023-01-15T17:00Z"),
        pd.Timestamp("2023-01-15T18:00Z"),
        "fixture",
    )
    assert hourly.iloc[0].n_resolved == 1
    assert hourly.iloc[0].n_unresolved == 0


def test_ineligible_hour_retains_resolved_count_but_null_target():
    from airbus_challenge.targets import airport_hours

    df = outcome_fixture([row()])
    df["timestamp_status"] = "quarantined"
    h = airport_hours(
        df,
        "KDFW",
        pd.Timestamp("2023-01-15T17:00Z"),
        pd.Timestamp("2023-01-15T18:00Z"),
        "fixture",
    ).iloc[0]
    assert h.n_resolved == 0
    assert h.n_unresolved == 1
    assert pd.isna(h.reporting_carrier_touchdowns)
    assert h.exclusion_reason == "unresolved_arrival_fraction_gt_0.05"


@pytest.mark.parametrize(
    "field", ["cancelled", "diverted", "wheels_on_utc", "dep_delay_min"]
)
def test_hourly_schedule_counts_ignore_final_outcomes(field):
    from airbus_challenge.targets import airport_hours

    rows = []
    for reverse in [False, True]:
        for i, status in enumerate([{}, {"Cancelled": "1"}, {"Diverted": "1"}]):
            values = {
                "Flight_Number_Reporting_Airline": str(123 + i + 3 * reverse),
                **status,
            }
            if reverse:
                values.update(
                    Origin="DFW",
                    Dest="ATL",
                    CRSArrTime="1330",
                    WheelsOn="1315",
                    ArrTime="1325",
                )
            rows.append(row(**values))
    df = outcome_fixture(rows)
    changed = df.copy()
    if field in {"cancelled", "diverted"}:
        changed[field] = ~changed[field]
    elif field == "wheels_on_utc":
        changed[field] = pd.Timestamp("2025-01-01T00:00Z")
    else:
        changed[field] = 5000.0
    for icao in CONFIG["airports"]:
        args = (
            icao,
            pd.Timestamp("2023-01-15T14:00Z"),
            pd.Timestamp("2023-01-15T20:00Z"),
            "fixture",
        )
        before = airport_hours(df, *args, data_mode="fixture")
        after = airport_hours(changed, *args, data_mode="fixture")
        columns = [
            "airport_icao",
            "hour_start_utc",
            "scheduled_arrivals",
            "scheduled_departures",
        ]
        pd.testing.assert_frame_equal(before[columns], after[columns])
        # All three statuses contribute to schedule demand in each direction.
        assert before.scheduled_arrivals.sum() == 3
        assert before.scheduled_departures.sum() == 3


@pytest.mark.parametrize(
    ("detail", "reason"),
    [
        ("cancelled", "cancelled"),
        ("timestamp_quarantined", "quarantined"),
        ("unresolved_arrival_fraction_gt_0.05", "coverage_incomplete"),
        ("missing_source_month", "coverage_incomplete"),
        ("unknown_cancellation_status", "missing_outcome"),
        ("missing_departure_delay", "missing_outcome"),
    ],
)
def test_label_exclusion_contract_mapping(detail, reason):
    from airbus_challenge.targets import label_exclusions

    labels = label_exclusions(
        pd.DataFrame(
            {
                "prediction_id": ["excluded", "eligible"],
                "eligible": [False, True],
                "exclusion_reason": [detail, None],
            }
        )
    )
    assert labels.exclusion_reason.iloc[0] == reason
    assert labels.exclusion_detail.iloc[0] == detail
    assert labels.exclusion_reason.isna().eq(labels.eligible).all()
    assert labels.exclusion_detail.isna().eq(labels.eligible).all()


@pytest.mark.parametrize(
    ("eligible", "detail", "error"),
    [
        (False, "new_unapproved_detail", "Unknown exclusion_detail"),
        (False, None, "null iff eligible"),
        (True, "cancelled", "null iff eligible"),
    ],
)
def test_label_exclusion_contract_rejects_invalid_values(eligible, detail, error):
    from airbus_challenge.targets import label_exclusions

    with pytest.raises(ValueError, match=error):
        label_exclusions(
            pd.DataFrame(
                {
                    "prediction_id": ["invalid"],
                    "eligible": [eligible],
                    "exclusion_reason": [detail],
                }
            )
        )


def test_required_data_mode_rejects_unknown_values():
    from airbus_challenge.targets import airport_hours, label_rows

    df = outcome_fixture([row()])
    with pytest.raises(ValueError, match="Invalid data_mode"):
        airport_hours(
            df,
            "KATL",
            pd.Timestamp("2023-01-15T00:00Z"),
            pd.Timestamp("2023-01-16T00:00Z"),
            "fixture",
            data_mode="mixed",
        )
    with pytest.raises(ValueError, match="Invalid data_mode"):
        label_rows(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), data_mode=None)


def test_missing_flight_join_is_an_unapproved_exclusion_detail():
    from airbus_challenge.requests import flight_requests
    from airbus_challenge.targets import label_rows

    df = outcome_fixture([row()])
    requests = flight_requests(
        df,
        ["KATL"],
        [3],
        pd.Timestamp("2023-01-15T00:00Z"),
        pd.Timestamp("2023-01-16T00:00Z"),
        "fixture",
    )
    outcomes = df.iloc[:0][
        ["flight_id", "dep_delay_min", "cancelled", "scheduled_dep_utc"]
    ]
    with pytest.raises(ValueError, match="missing_flight_outcome"):
        label_rows(requests, outcomes, pd.DataFrame(), data_mode="fixture")


def test_missing_airport_hour_is_an_unapproved_exclusion_detail():
    from airbus_challenge.requests import airport_requests
    from airbus_challenge.targets import airport_hours, label_rows

    start, end = pd.Timestamp("2023-01-15T00:00Z"), pd.Timestamp("2023-01-16T00:00Z")
    requests = airport_requests(["KATL"], [3], start, end, "fixture", "fixture")
    hourly = airport_hours(
        outcome_fixture([row()]), "KDFW", start, end, "fixture", data_mode="fixture"
    )
    with pytest.raises(ValueError, match="missing_airport_hour"):
        label_rows(requests, pd.DataFrame(), hourly, data_mode="fixture")


CAPACITY_EXPERIMENT = {
    "splits": {"train": {"start": "2023-01-01", "end": "2024-01-01"}},
    "targets": {"capacity_ratio": "throughput_over_clear_weather_p95"},
    "clear_weather": {
        "min_ceiling_ft": 3000,
        "min_visibility_sm": 5,
        "allow_weather_codes": False,
    },
}


def capacity_fixture(events):
    hourly = pd.DataFrame(
        events,
        columns=["airport_icao", "hour_start_utc", "reporting_carrier_touchdowns"],
    )
    hourly["hour_start_utc"] = pd.to_datetime(hourly.hour_start_utc, utc=True)
    hourly["hour_end_utc"] = hourly.hour_start_utc + pd.Timedelta(hours=1)
    hourly["throughput_label_eligible"] = hourly.reporting_carrier_touchdowns.notna()
    hourly["coverage_status"] = "complete_for_source_scope"
    hourly["n_unresolved"] = 0
    hourly["data_mode"] = "fixture"
    weather = (
        hourly[["airport_icao", "hour_start_utc"]]
        .rename(columns={"hour_start_utc": "observed_at_utc"})
        .copy()
    )
    weather["observed_at_utc"] += pd.Timedelta(minutes=30)
    weather["source_record_id"] = [f"weather-{i}" for i in weather.index]
    weather["ceiling_status"] = "layer"
    weather["ceiling_ft"] = 3000.0
    weather["visibility_sm"] = 5.0
    weather["wx_codes"] = [[] for _ in weather.index]
    weather["quality_flags"] = [[] for _ in weather.index]
    return hourly, weather


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, True),
        ({"ceiling_ft": 2999.0}, False),
        ({"visibility_sm": 4.99}, False),
        ({"ceiling_ft": None, "ceiling_status": "none"}, True),
        ({"ceiling_ft": None, "ceiling_status": "missing"}, False),
        ({"visibility_sm": None}, False),
        ({"wx_codes": ["TSRA"]}, False),
        ({"wx_codes": None}, False),
        ({"quality_flags": ["corrected"]}, False),
    ],
)
def test_p10_weather_boundaries_and_missingness(changes, expected):
    from airbus_challenge.targets import clear_weather_hours

    _, weather = capacity_fixture([("KATL", "2023-01-01T15:00Z", 10)])
    for name, value in changes.items():
        weather.at[0, name] = value
    state = clear_weather_hours(weather, CAPACITY_EXPERIMENT["clear_weather"]).iloc[0]
    assert bool(state.benign) == expected


def test_p10_hour_requires_all_reports_to_be_benign():
    from airbus_challenge.targets import clear_weather_hours

    _, weather = capacity_fixture(
        [("KATL", "2023-01-01T15:00Z", 10), ("KATL", "2023-01-01T15:00Z", 10)]
    )
    weather.at[1, "visibility_sm"] = 1.0
    state = clear_weather_hours(weather, CAPACITY_EXPERIMENT["clear_weather"]).iloc[0]
    assert state.metar_reports == 2
    assert not state.benign


def test_capacity_reference_train_only_and_future_weather_invariance():
    from airbus_challenge.targets import add_capacity_ratio

    hourly, weather = capacity_fixture(
        [
            ("KATL", "2023-01-01T15:00Z", 10),
            ("KATL", "2023-01-02T15:00Z", 20),
            ("KATL", "2023-01-03T15:00Z", 1000),
            ("KATL", "2024-01-01T15:00Z", 30),
            ("KATL", "2025-01-01T15:00Z", 40),
        ]
    )
    weather.at[2, "wx_codes"] = ["TSRA"]
    before, report = add_capacity_ratio(
        hourly, weather, CONFIG["airports"], CAPACITY_EXPERIMENT
    )
    assert before.clear_weather_p95_arrivals_per_hour.tolist() == [19.5] * 5
    assert before.clear_weather_fit_hours.tolist() == [2] * 5
    assert before.iloc[3].throughput_over_clear_weather_p95 == 30 / 19.5
    assert (
        before.iloc[3].throughput_over_clear_weather_p95 > 1
    )  # A percentile is not a hard upper bound.
    assert report["fit_hours"] == 2
    hourly.loc[3:, "reporting_carrier_touchdowns"] = 999999
    weather.loc[3:, "ceiling_ft"] = 0
    weather.loc[3:, "source_record_id"] = "changed-future-source"
    weather.loc[3:, "visibility_sm"] = 0
    after, changed_report = add_capacity_ratio(
        hourly, weather, CONFIG["airports"], CAPACITY_EXPERIMENT
    )
    columns = [
        "clear_weather_p95_arrivals_per_hour",
        "clear_weather_fit_hours",
        "clear_weather_reference_id",
    ]
    pd.testing.assert_frame_equal(before[columns], after[columns])
    assert report["reference_id"] == changed_report["reference_id"]
    assert report["reference"] == changed_report["reference"]


def test_capacity_reference_local_hour_dst_and_airport_separation():
    from airbus_challenge.targets import add_capacity_ratio

    hourly, weather = capacity_fixture(
        [
            ("KATL", "2023-01-01T15:00Z", 10),
            ("KATL", "2023-07-01T14:00Z", 20),
            ("KDFW", "2023-01-01T16:00Z", 100),
            ("KDFW", "2023-07-01T15:00Z", 200),
        ]
    )
    out, _ = add_capacity_ratio(
        hourly, weather, CONFIG["airports"], CAPACITY_EXPERIMENT
    )
    assert out.airport_local_hour.tolist() == [10] * 4
    assert out.clear_weather_p95_arrivals_per_hour.tolist() == [
        19.5,
        19.5,
        195.0,
        195.0,
    ]


def test_capacity_reference_unsupported_and_zero_cases():
    from airbus_challenge.targets import add_capacity_ratio

    hourly, weather = capacity_fixture(
        [
            ("KATL", "2023-01-01T15:00Z", 0),
            ("KATL", "2024-01-01T15:00Z", 5),
            ("KATL", "2024-01-01T16:00Z", 5),
        ]
    )
    out, _ = add_capacity_ratio(
        hourly, weather, CONFIG["airports"], CAPACITY_EXPERIMENT
    )
    assert out.capacity_ratio_status.tolist() == [
        "nonpositive_reference",
        "nonpositive_reference",
        "missing_reference",
    ]
    assert out.throughput_over_clear_weather_p95.isna().all()
    assert out.clear_weather_fit_hours.tolist() == [1, 1, 0]


def test_capacity_reference_rejects_partial_training_and_missing_targets():
    from airbus_challenge.targets import add_capacity_ratio

    hourly, weather = capacity_fixture(
        [
            ("KATL", "2023-01-01T15:00Z", 10),
            ("KATL", "2023-01-02T15:00Z", 1000),
            ("KATL", "2024-01-01T15:00Z", None),
            ("KATL", "2025-01-01T15:00Z", 0),
        ]
    )
    hourly.loc[1, "coverage_status"] = "partial"
    hourly.loc[1, "n_unresolved"] = 1
    out, _ = add_capacity_ratio(
        hourly, weather, CONFIG["airports"], CAPACITY_EXPERIMENT
    )
    assert out.clear_weather_p95_arrivals_per_hour.eq(10).all()
    assert out.clear_weather_fit_hours.eq(1).all()
    assert out.capacity_ratio_status.iloc[2] == "throughput_unavailable"
    assert pd.isna(out.throughput_over_clear_weather_p95.iloc[2])
    assert out.capacity_ratio_status.iloc[3] == "available"
    assert out.throughput_over_clear_weather_p95.iloc[3] == 0


def test_cohort_membership_ids_and_holdout_roles():
    from airbus_challenge.requests import (
        COHORT_VERSION,
        airport_requests,
        cohort_definitions,
        flight_requests,
        select_cohorts,
    )

    df = outcome_fixture(
        [
            row(),
            row(Flight_Number_Reporting_Airline="124", Cancelled="1"),
            row(Flight_Number_Reporting_Airline="125", Diverted="1"),
        ]
    )
    df["in_provided_csv"] = [True, True, False]
    start, end = pd.Timestamp("2023-01-15T00:00Z"), pd.Timestamp("2023-01-16T00:00Z")
    definitions = cohort_definitions(list(CONFIG["airports"]))
    frames = [
        flight_requests(df, list(CONFIG["airports"]), [3, 6], start, end, "fixture", c)
        for c in definitions
    ]
    assert [len(f) for f in frames] == [6, 4, 6, 6]
    assert pd.concat(frames).prediction_id.is_unique
    assert frames[0].flight_id.tolist() == frames[2].flight_id.tolist()
    assert set(frames[1].flight_id) == set(df.loc[df.in_provided_csv, "flight_id"])
    for icao in CONFIG["airports"]:
        definition = definitions[f"loao_{icao}_v1"]
        assert icao not in definition["train_airports"]
        assert definition["score_airports"] == [icao]
        assert set(definition["request_airports"]) == set(CONFIG["airports"])
        assert not definition["ratio_labels"]
    altered = df.copy()
    altered["cancelled"] = ~altered.cancelled
    altered["diverted"] = ~altered.diverted
    altered["dep_delay_min"] = 9999
    for i, cohort in enumerate(definitions):
        pd.testing.assert_frame_equal(
            frames[i],
            flight_requests(
                altered, list(CONFIG["airports"]), [3, 6], start, end, "fixture", cohort
            ),
        )
    assert list(select_cohorts(list(CONFIG["airports"]), ["all"])) == list(definitions)
    with pytest.raises(ValueError, match="Unknown, empty or duplicate"):
        select_cohorts(list(CONFIG["airports"]), [COHORT_VERSION, COHORT_VERSION])
    with pytest.raises(ValueError, match="no hourly"):
        airport_requests(
            list(CONFIG["airports"]),
            [3],
            start,
            end,
            "fixture",
            "fixture",
            "csv_only_v1",
        )


@pytest.mark.parametrize(
    ("status", "value", "reason", "detail"),
    [
        ("available", 1.5, None, None),
        ("missing_reference", None, "missing_outcome", "missing_capacity_reference"),
        (
            "nonpositive_reference",
            None,
            "missing_outcome",
            "nonpositive_capacity_reference",
        ),
    ],
)
def test_ratio_labels_and_holdout_normalizer_exclusion(status, value, reason, detail):
    from airbus_challenge.requests import airport_requests
    from airbus_challenge.targets import airport_hours, label_rows

    start, end = pd.Timestamp("2023-01-15T17:00Z"), pd.Timestamp("2023-01-15T18:00Z")
    hourly = airport_hours(
        outcome_fixture([row()]), "KDFW", start, end, "fixture", data_mode="fixture"
    )
    hourly["capacity_ratio_status"] = status
    hourly["throughput_over_clear_weather_p95"] = value
    # Reverse cohort order to catch index misalignment in subset label construction.
    req = pd.concat(
        [
            airport_requests(
                ["KDFW"], [3], start, end, "fixture", "fixture", "loao_KATL_v1"
            ),
            airport_requests(["KDFW"], [3], start, end, "fixture", "fixture"),
        ],
        ignore_index=True,
    )
    labels = label_rows(
        req,
        pd.DataFrame(),
        hourly,
        data_mode="fixture",
        ratio_target="throughput_over_clear_weather_p95",
    )
    assert len(labels) == 3
    ratio = labels[labels.target_kind.eq("throughput_over_clear_weather_p95")].iloc[0]
    assert ratio.prediction_id == req.iloc[1].prediction_id
    assert ratio.unit == "ratio"
    if reason is None:
        assert ratio.eligible and ratio.y_true == value
        assert pd.isna(ratio.exclusion_reason) and pd.isna(ratio.exclusion_detail)
    else:
        assert not ratio.eligible and pd.isna(ratio.y_true)
        assert (ratio.exclusion_reason, ratio.exclusion_detail) == (reason, detail)


def test_ratio_labels_preserve_p12_exclusion_reason():
    from airbus_challenge.requests import airport_requests
    from airbus_challenge.targets import airport_hours, label_rows

    df = outcome_fixture([row()])
    df["timestamp_status"] = "quarantined"
    start, end = pd.Timestamp("2023-01-15T17:00Z"), pd.Timestamp("2023-01-15T18:00Z")
    hourly = airport_hours(df, "KDFW", start, end, "fixture", data_mode="fixture")
    hourly["capacity_ratio_status"] = "missing_reference"
    hourly["throughput_over_clear_weather_p95"] = None
    req = airport_requests(["KDFW"], [3], start, end, "fixture", "fixture")
    labels = label_rows(
        req,
        pd.DataFrame(),
        hourly,
        data_mode="fixture",
        ratio_target="throughput_over_clear_weather_p95",
    )
    assert labels.eligible.eq(False).all()
    assert labels.exclusion_reason.eq("coverage_incomplete").all()
    assert labels.exclusion_detail.eq("unresolved_arrival_fraction_gt_0.05").all()


def test_indexed_outcome_lookup_preserves_labels_and_rejects_duplicates():
    from airbus_challenge.requests import flight_requests
    from airbus_challenge.targets import label_rows

    df = outcome_fixture(
        [row(), row(Flight_Number_Reporting_Airline="124", Cancelled="1")]
    )
    req = flight_requests(
        df,
        ["KATL"],
        [3],
        pd.Timestamp("2023-01-15T00:00Z"),
        pd.Timestamp("2023-01-16T00:00Z"),
        "fixture",
    )
    outcomes = df[["flight_id", "dep_delay_min", "cancelled", "scheduled_dep_utc"]]
    normal = label_rows(req, outcomes, pd.DataFrame(), data_mode="fixture")
    pd.testing.assert_frame_equal(
        normal,
        label_rows(
            req, outcomes.set_index("flight_id"), pd.DataFrame(), data_mode="fixture"
        ),
    )
    with pytest.raises(ValueError, match="Duplicate flight_id"):
        label_rows(req, pd.concat([outcomes, outcomes]), pd.DataFrame())


def test_schedule_drift_ignores_all_outcome_columns():
    from airbus_challenge.requests import schedule_drift

    df = outcome_fixture(
        [
            row(FlightDate="2024-01-15"),
            row(
                FlightDate="2025-01-15",
                Flight_Number_Reporting_Airline="124",
                Cancelled="1",
            ),
            row(
                FlightDate="2025-01-15",
                Flight_Number_Reporting_Airline="125",
                Diverted="1",
            ),
        ]
    )
    before = schedule_drift(df, list(CONFIG["airports"]))
    changed = df.copy()
    changed["cancelled"] = ~changed.cancelled
    changed["diverted"] = ~changed.diverted
    changed["wheels_on_utc"] = pd.Timestamp("2040-01-01T00:00Z")
    changed["dep_delay_min"] = 999999
    assert schedule_drift(changed, list(CONFIG["airports"])) == before
    rows = [
        r
        for r in before["monthly"]
        if r["airport_icao"] == "KATL" and r["direction"] == "departure"
    ]
    assert [r["scheduled_flights"] for r in rows] == [1, 2]
    assert before["year_over_year"][0]["per_day_change_fraction"] == 1


def test_schedule_audit_reads_only_declared_schedule_columns(tmp_path, monkeypatch):
    import json
    import zipfile

    import yaml

    from airbus_challenge import requests
    from airbus_challenge.download import sha256

    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/airports.yaml").write_text(yaml.safe_dump(CONFIG))
    raw_dir = tmp_path / "data/raw/bts"
    raw_dir.mkdir(parents=True)
    raw = pd.DataFrame(
        [row(), row(Flight_Number_Reporting_Airline="124", Cancelled="1")]
    )
    path = raw_dir / "bts_2023_01.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("flights.csv", raw.to_csv(index=False))
    df = outcome_fixture(raw.to_dict(orient="records"))
    (tmp_path / "data/processed").mkdir()
    df.to_parquet(requests.FLIGHTS, index=False)
    requests.FLIGHTS.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "data_mode": "fixture",
                "parquet_sha256": sha256(requests.FLIGHTS),
                "sources": [{"key": "bts/bts_2023_01.zip", "sha256": sha256(path)}],
            }
        )
    )
    read_parquet, read_csv = pd.read_parquet, pd.read_csv
    calls = []

    def schedule_parquet(path, **kwargs):
        assert kwargs["columns"] == requests.AUDIT_COLUMNS
        calls.append("parquet")
        return read_parquet(path, **kwargs)

    def schedule_csv(path, **kwargs):
        assert set(kwargs["usecols"]) == {
            "FlightDate",
            "DOT_ID_Reporting_Airline",
            "Reporting_Airline",
            "Origin",
            "Dest",
        }
        calls.append("csv")
        return read_csv(path, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", schedule_parquet)
    monkeypatch.setattr(pd, "read_csv", schedule_csv)
    report = requests.audit_schedules(tmp_path / "audit.json")
    assert calls == ["parquet", "csv"]
    assert report["data_mode"] == "fixture"
    assert report["raw_reconciliation"].startswith("passed")
    assert report["rows"] == 2
    assert len(report["national_carrier_scope"]) == 1


def test_simulated_flight_label_timing_uses_departure_and_latest_flight_time():
    from airbus_challenge.requests import flight_requests
    from airbus_challenge.targets import label_rows

    df = outcome_fixture(
        [row(), row(Flight_Number_Reporting_Airline="124", Cancelled="1")]
    )
    req = flight_requests(
        df,
        ["KATL"],
        [3],
        pd.Timestamp("2023-01-15T00:00Z"),
        pd.Timestamp("2023-01-16T00:00Z"),
        "fixture",
    )
    fields = ["flight_id", "dep_delay_min", "cancelled", *TIMES]
    labels = label_rows(req, df[fields], pd.DataFrame(), data_mode="fixture")
    delays = labels[labels.target_kind.eq("departure_delay_gt45")]
    cancellations = labels[labels.target_kind.eq("cancellation")]
    assert delays.iloc[0].outcome_available_at_utc == pd.Timestamp("2023-01-15T15:05Z")
    assert pd.isna(delays.iloc[1].outcome_available_at_utc)
    assert cancellations.outcome_available_at_utc.eq(
        pd.Timestamp("2023-01-16T17:30Z")
    ).all()
    assert labels.availability_basis.eq("simulated").all()


def test_simulated_hourly_and_ratio_labels_share_hour_end_timing():
    from airbus_challenge.requests import airport_requests
    from airbus_challenge.targets import airport_hours, label_rows

    start, end = pd.Timestamp("2023-01-15T17:00Z"), pd.Timestamp("2023-01-15T18:00Z")
    hourly = airport_hours(
        outcome_fixture([row()]), "KDFW", start, end, "fixture", data_mode="fixture"
    )
    hourly["capacity_ratio_status"] = "available"
    hourly["throughput_over_clear_weather_p95"] = 0.5
    req = airport_requests(["KDFW"], [3], start, end, "fixture", "fixture")
    labels = label_rows(
        req,
        pd.DataFrame(),
        hourly,
        data_mode="fixture",
        ratio_target="throughput_over_clear_weather_p95",
    )
    assert len(labels) == 2
    assert labels.outcome_available_at_utc.eq(pd.Timestamp("2023-01-15T18:10Z")).all()


@pytest.mark.parametrize(
    ("latency", "fit_hours", "reference"), [(10, 2, 10.0), (0, 3, 95000.5)]
)
def test_reference_fit_respects_simulated_release_cutoff(latency, fit_hours, reference):
    from copy import deepcopy

    from airbus_challenge.targets import LABEL_AVAILABILITY, add_capacity_ratio

    hourly, weather = capacity_fixture(
        [
            ("KATL", "2023-01-01T23:00Z", 10),
            ("KATL", "2023-12-31T22:00Z", 20),
            ("KATL", "2023-12-31T23:00Z", 100000),
        ]
    )
    experiment = deepcopy(CAPACITY_EXPERIMENT)
    experiment["label_availability"] = {
        **LABEL_AVAILABILITY,
        "hourly_latency_min": latency,
    }
    out, report = add_capacity_ratio(hourly, weather, CONFIG["airports"], experiment)
    assert report["fit_hours"] == fit_hours
    assert out.iloc[0].clear_weather_p95_arrivals_per_hour == reference
    assert out.iloc[2].outcome_available_at_utc == pd.Timestamp(
        "2024-01-01T00:00Z"
    ) + pd.Timedelta(minutes=latency)


def test_negative_simulated_label_latency_is_rejected():
    from airbus_challenge.targets import LABEL_AVAILABILITY, label_timing

    with pytest.raises(ValueError, match="Negative"):
        label_timing({**LABEL_AVAILABILITY, "departure_latency_min": -1})


def test_label_denominators_use_target_split_and_preserve_partial_eligibility():
    from airbus_challenge.targets import label_denominators

    requests = pd.DataFrame(
        {
            "prediction_id": ["train", "partial-ok", "partial-excluded"],
            "cohort_version": ["retrospective_schedule_v1"] * 3,
            "task": ["throughput"] * 3,
            "airport_icao": ["KATL"] * 3,
            "target_start_utc": pd.to_datetime(
                [
                    "2023-12-31T23:00Z",
                    "2024-01-01T00:00Z",
                    "2024-01-01T01:00Z",
                ]
            ),
            "horizon_h": [3, 6, 6],
        }
    )
    labels = pd.DataFrame(
        {
            "prediction_id": requests.prediction_id,
            "target_kind": ["reporting_carrier_touchdowns"] * 3,
            "eligible": [True, True, False],
            "exclusion_reason": [None, None, "coverage_incomplete"],
            "exclusion_detail": [None, None, "unresolved_arrival_fraction_gt_0.05"],
            "data_mode": ["fixture"] * 3,
        }
    )
    experiment = {
        "splits": {
            "train": {"start": "2023-01-01", "end": "2024-01-01"},
            "validation": {"start": "2024-01-01", "end": "2024-07-01"},
        }
    }
    counts = label_denominators(requests, labels, experiment)
    assert counts.rows.sum() == 3
    validation = counts[counts.split.eq("validation")]
    assert validation.rows.sum() == 2
    assert validation.loc[validation.eligible, "rows"].sum() == 1
    assert validation.target_month.eq("2024-01").all()
    assert validation.horizon_h.eq(6).all()
    assert counts.loc[counts.eligible, "exclusion_reason"].isna().all()
    with pytest.raises(ValueError, match="unknown prediction_id"):
        label_denominators(requests.iloc[:2], labels, experiment)


def operational_hour_fixture():
    starts = pd.date_range("2023-01-01T00:00Z", periods=4, freq="h")
    return pd.DataFrame(
        {
            "airport_icao": ["KATL"] * 4,
            "hour_start_utc": starts,
            "hour_end_utc": starts + pd.Timedelta(hours=1),
            "reporting_carrier_touchdowns": pd.Series([0, 10, 20, 30], dtype="Int32"),
            "n_unresolved": [0, 0, 0, 0],
            "coverage_status": ["complete_for_source_scope"] * 4,
            "data_mode": ["fixture"] * 4,
        }
    )


def test_operational_feed_release_latency_blocks_latest_finished_hour():
    from airbus_challenge.targets import operational_feed

    feed = operational_feed(operational_hour_fixture(), 10)
    issue = pd.Timestamp("2023-01-01T04:00Z")
    available = feed[feed.feed_eligible & feed.available_at_utc.le(issue)]
    assert available.iloc[-1].source_hour_start_utc == pd.Timestamp("2023-01-01T02:00Z")
    assert available.iloc[-1].reporting_carrier_touchdowns == 20
    assert feed.iloc[-1].available_at_utc == pd.Timestamp("2023-01-01T04:10Z")
    assert feed.iloc[0].reporting_carrier_touchdowns == 0
    assert feed.availability_basis.eq("simulated").all()
    exact = operational_feed(operational_hour_fixture(), 0)
    assert exact.available_at_utc.le(issue).all()


def test_operational_feed_partial_and_missing_counts_stay_null():
    from airbus_challenge.targets import operational_feed

    hourly = operational_hour_fixture()
    hourly.loc[1, ["coverage_status", "n_unresolved"]] = ["partial", 1]
    hourly.loc[2, "coverage_status"] = "missing"
    feed = operational_feed(hourly, 10)
    assert feed.feed_eligible.tolist() == [True, False, False, True]
    assert feed.reporting_carrier_touchdowns.iloc[1:3].isna().all()
    assert feed.coverage_status.tolist() == [
        "complete_for_source_scope",
        "partial",
        "missing",
        "complete_for_source_scope",
    ]
    with pytest.raises(ValueError, match="nonnegative"):
        operational_feed(hourly, -1)
    with pytest.raises(ValueError, match="Duplicate airport-hour"):
        operational_feed(pd.concat([hourly, hourly]), 10)


@pytest.mark.parametrize(
    "cohort",
    ["retrospective_schedule_v1", "csv_only_v1", "loao_KATL_v1", "loao_KDFW_v1"],
)
def test_training_selection_enforces_cohort_airports_targets_and_release(cohort):
    from airbus_challenge.requests import cohort_definitions, flight_requests
    from airbus_challenge.targets import label_rows, select_training_labels

    df = outcome_fixture(
        [
            row(),
            row(Flight_Number_Reporting_Airline="124", Cancelled="1"),
            row(Flight_Number_Reporting_Airline="125", Origin="DFW", Dest="ATL"),
            row(Flight_Number_Reporting_Airline="126", FlightDate="2024-01-01"),
        ]
    )
    df["in_provided_csv"] = True
    definitions = cohort_definitions(list(CONFIG["airports"]))
    req = flight_requests(
        df,
        list(CONFIG["airports"]),
        [3, 6],
        pd.Timestamp("2023-01-01T00:00Z"),
        pd.Timestamp("2024-01-02T00:00Z"),
        "fixture",
        cohort,
    )
    labels = label_rows(
        req,
        df[["flight_id", "dep_delay_min", "cancelled", *TIMES]],
        pd.DataFrame(),
        data_mode="fixture",
    )
    # Exact cutoff is inclusive; a later release cannot enter fitting.
    departed = labels.target_kind.eq("departure_delay_gt45") & labels.eligible
    labels.loc[departed, "outcome_available_at_utc"] = pd.Timestamp("2024-01-01T00:00Z")
    late_id = req.loc[
        req.horizon_h.eq(6) & req.flight_id.eq(df.flight_id.iloc[0]), "prediction_id"
    ].iloc[0]
    labels.loc[
        labels.prediction_id.eq(late_id) & departed, "outcome_available_at_utc"
    ] += pd.Timedelta(seconds=1)
    experiment = {
        "splits": {"train": {"start": "2023-01-01", "end": "2024-01-01"}},
        "targets": {"capacity_ratio": "throughput_over_clear_weather_p95"},
    }
    selected = select_training_labels(
        req, labels, cohort, definitions[cohort], experiment, "2024-01-01T00:00Z"
    )
    assert set(selected.airport_icao) <= set(definitions[cohort]["train_airports"])
    assert selected.target_start_utc.lt(pd.Timestamp("2024-01-01T00:00Z")).all()
    assert selected.outcome_available_at_utc.le(selected.fit_cutoff_utc).all()
    assert selected.eligible.all()
    assert not (
        selected.prediction_id.eq(late_id)
        & selected.target_kind.eq("departure_delay_gt45")
    ).any()
    cancelled_ids = req.loc[req.flight_id.eq(df.flight_id.iloc[1]), "prediction_id"]
    assert not (
        selected.prediction_id.isin(cancelled_ids)
        & selected.target_kind.eq("departure_delay_gt45")
    ).any()
    if "KATL" in definitions[cohort]["train_airports"]:
        assert (
            selected.prediction_id.isin(cancelled_ids)
            & selected.target_kind.eq("cancellation")
        ).sum() == 2
    with pytest.raises(ValueError, match="timezone"):
        select_training_labels(
            req, labels, cohort, definitions[cohort], experiment, "2024-01-01"
        )


def test_training_selection_rejects_unknown_availability_and_holdout_ratio():
    from airbus_challenge.requests import cohort_definitions
    from airbus_challenge.targets import select_training_labels

    req = pd.DataFrame(
        {
            "prediction_id": ["p"],
            "cohort_version": ["loao_KATL_v1"],
            "airport_icao": ["KDFW"],
            "task": ["throughput"],
            "target_start_utc": [pd.Timestamp("2023-01-01T00:00Z")],
            "data_mode": ["fixture"],
        }
    )
    labels = pd.DataFrame(
        {
            "prediction_id": ["p"],
            "target_kind": ["reporting_carrier_touchdowns"],
            "eligible": [True],
            "y_true": [1],
            "outcome_available_at_utc": [pd.Timestamp("2023-01-01T01:10Z")],
            "availability_basis": ["unknown"],
        }
    )
    definition = cohort_definitions(list(CONFIG["airports"]))["loao_KATL_v1"]
    experiment = {
        "splits": {"train": {"start": "2023-01-01", "end": "2024-01-01"}},
        "targets": {"capacity_ratio": "throughput_over_clear_weather_p95"},
    }
    with pytest.raises(ValueError, match="availability basis"):
        select_training_labels(
            req, labels, "loao_KATL_v1", definition, experiment, "2024-01-01T00:00Z"
        )
    labels["availability_basis"] = "simulated"
    labels["target_kind"] = "throughput_over_clear_weather_p95"
    with pytest.raises(ValueError, match="forbidden"):
        select_training_labels(
            req, labels, "loao_KATL_v1", definition, experiment, "2024-01-01T00:00Z"
        )


def replay_fixture():
    from airbus_challenge.requests import flight_requests
    from airbus_challenge.targets import label_rows

    df = outcome_fixture(
        [row(), row(Flight_Number_Reporting_Airline="124", Cancelled="1")]
    )
    req = flight_requests(
        df,
        ["KATL"],
        [3],
        pd.Timestamp("2023-01-15T00:00Z"),
        pd.Timestamp("2023-01-16T00:00Z"),
        "fixture",
    )
    labels = label_rows(
        req,
        df[["flight_id", "dep_delay_min", "cancelled", *TIMES]],
        pd.DataFrame(),
        data_mode="fixture",
    )
    return req, labels


def test_replay_payload_hides_outcomes_and_release_times_until_release():
    from airbus_challenge.targets import replay_outcomes

    req, labels = replay_fixture()
    before = replay_outcomes(req, labels, "2023-01-15T15:04:59Z")
    assert before.outcome_status.eq("not_released").all()
    for column in [
        "y_true",
        "eligible",
        "exclusion_reason",
        "exclusion_detail",
        "outcome_available_at_utc",
    ]:
        assert before[column].isna().all()
    exact = replay_outcomes(req, labels, "2023-01-15T15:05:00Z")
    known = exact[exact.outcome_status.eq("revealed")]
    assert len(known) == 1 and known.y_true.iloc[0] == 0
    assert known.eligible.iloc[0]
    later = replay_outcomes(req, labels, "2023-01-17T00:00Z")
    assert later.outcome_status.eq("revealed").sum() == 3
    cancelled = later[later.target_kind.eq("cancellation")]
    assert sorted(cancelled.y_true.tolist()) == [0, 1]
    assert not {
        "flight_id",
        "scheduled_dep_utc",
        "quality_flags",
        "dep_delay_min",
    } & set(later.columns)
    with pytest.raises(ValueError, match="timezone-aware"):
        replay_outcomes(req, labels, "2023-01-17")
    with pytest.raises(ValueError, match="Duplicate replay outcome"):
        replay_outcomes(req, pd.concat([labels, labels]), "2023-01-17T00:00Z")


def test_replay_loader_projects_only_released_outcome_values(tmp_path, monkeypatch):
    import yaml

    from airbus_challenge import targets

    req, labels = replay_fixture()
    path = tmp_path / "labels.parquet"
    labels.to_parquet(path, index=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/experiment.yaml").write_text(
        yaml.safe_dump({"splits": {"test": {"start": "2025-01-01"}}})
    )
    real_dataset = targets.ds.dataset(path)
    reads = []

    class TrackedDataset:
        def to_table(self, **kwargs):
            table = real_dataset.to_table(**kwargs)
            reads.append((kwargs["columns"], table.num_rows))
            return table

    monkeypatch.setattr(targets.ds, "dataset", lambda path: TrackedDataset())
    out = targets.load_replay_outcomes(req, path, "2023-01-15T15:05Z")
    assert "y_true" not in reads[0][0] and "eligible" not in reads[0][0]
    assert reads[0][1] == 4
    assert "y_true" in reads[1][0] and reads[1][1] == 1
    assert out.outcome_status.eq("revealed").sum() == 1
    pending = out[out.outcome_status.eq("not_released")]
    assert pending.y_true.isna().all() and pending.outcome_available_at_utc.isna().all()


def test_development_replay_rejects_test_targets_before_opening_labels(
    tmp_path, monkeypatch
):
    import yaml

    from airbus_challenge import targets

    req, _ = replay_fixture()
    req["target_start_utc"] = pd.Timestamp("2025-01-01T00:00Z")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/experiment.yaml").write_text(
        yaml.safe_dump({"splits": {"test": {"start": "2025-01-01"}}})
    )

    def forbidden_read(*args, **kwargs):
        raise AssertionError("Test labels must not be opened")

    monkeypatch.setattr(targets.ds, "dataset", forbidden_read)
    with pytest.raises(ValueError, match="test-period"):
        targets.load_replay_outcomes(
            req, tmp_path / "absent.parquet", "2025-01-02T00:00Z"
        )
