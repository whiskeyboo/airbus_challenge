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

CONFIG = {"airports": {"KATL": {"iata": "ATL"}, "KDFW": {"iata": "DFW"}}}
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
