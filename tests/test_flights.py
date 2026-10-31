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
    assert labels.outcome_available_at_utc.isna().all()
    assert labels.availability_basis.eq("unknown").all()


def test_requests_and_targets_end_to_end_fixture(tmp_path, monkeypatch):
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
    report = requests.build()
    req = pd.read_parquet(requests.OUTPUT)
    assert req.data_mode.eq("fixture").all()
    assert req.prediction_id.is_unique
    assert report["rows"] == 102
    hourly, summary = targets.build()
    labels = pd.read_parquet(targets.LABELS)
    assert len(labels) == 108
    import pyarrow.parquet as pq

    assert set(hourly.data_mode) == {"fixture"}
    assert set(labels.data_mode) == {"fixture"}
    assert not pq.read_schema(targets.HOURLY).field("data_mode").nullable
    assert not pq.read_schema(targets.LABELS).field("data_mode").nullable
    assert labels.exclusion_reason.isna().eq(labels.eligible).all()
    assert labels.exclusion_detail.isna().eq(labels.eligible).all()
    assert not labels.duplicated(
        ["prediction_id", "target_kind", "label_version"]
    ).any()
    severe = labels[labels.target_kind.eq("departure_delay_gt45")]
    assert severe.eligible.sum() == 4
    assert severe.y_true.dropna().tolist() == [0, 1, 0, 1]
    assert labels[labels.exclusion_reason.eq("cancelled")].y_true.isna().all()
    manifest = json.loads(targets.LABELS.with_suffix(".manifest.json").read_text())
    assert len(manifest["exclusion_audit"]["threshold_sensitivity"]) == 6
    assert manifest["data_mode"] == "fixture"
    assert sum(r["rows"] for r in manifest["exclusion_counts"]) == len(labels)
    assert {r["task"] for r in manifest["exclusion_counts"]} == {
        "throughput",
        "severe_delay",
    }
    assert any(
        r["exclusion_reason"] is None and r["exclusion_detail"] is None
        for r in manifest["exclusion_counts"]
    )
    assert hourly[["airport_icao", "hour_start_utc"]].duplicated().sum() == 0
    assert summary


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
