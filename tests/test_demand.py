import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from test_flights import outcome_fixture, row

from airbus_challenge import demand
from airbus_challenge.targets import airport_hours

REPO = Path(__file__).resolve().parents[1]
UTC_US = "datetime64[us, UTC]"
MONTHS = ["2022-12", "2023-01", "2023-12", "2024-01"]


def utc(s):
    return pd.Timestamp(s, tz="UTC")


def hourly_fixture() -> pd.DataFrame:
    """Two airports, 2023-01-01..03 (train) and 2024-01-01..03; arrivals = local hour + 10."""
    frames = []
    for icao, zone in (("KATL", "America/New_York"), ("KDFW", "America/Chicago")):
        for start in ("2023-01-01", "2024-01-01"):
            hours = pd.date_range(start, periods=72, freq="h", tz="UTC")
            local = hours.tz_convert(zone).hour
            frames.append(
                pd.DataFrame(
                    {
                        "airport_icao": icao,
                        "hour_start_utc": hours.astype(UTC_US),
                        "scheduled_arrivals": pd.array(local + 10, dtype="Int32"),
                        "scheduled_departures": pd.array(np.full(72, 7), dtype="Int32"),
                        "scheduled_arrivals_n_unresolved": pd.array(
                            np.zeros(72), dtype="Int32"
                        ),
                        "scheduled_departures_n_unresolved": pd.array(
                            np.zeros(72), dtype="Int32"
                        ),
                        "scheduled_arrivals_coverage_status": "complete_for_source_scope",
                        "scheduled_departures_coverage_status": "complete_for_source_scope",
                        # Outcome columns the demand build must never read.
                        "reporting_carrier_touchdowns": pd.array(
                            np.full(72, 3), dtype="Int32"
                        ),
                        "reporting_carrier_takeoffs": pd.array(
                            np.full(72, 4), dtype="Int32"
                        ),
                        "coverage_status": "complete_for_source_scope",
                        "throughput_over_clear_weather_p95": 0.5,
                        "exclusion_reason": None,
                    }
                )
            )
    return pd.concat(frames, ignore_index=True)


def requests_fixture() -> pd.DataFrame:
    rows = []
    for icao in ("KATL", "KDFW"):
        for target in ("2023-01-02 15:00", "2024-01-02 15:00"):
            for h in (3, 6):
                rows.append(("throughput", icao, None, target, h))
        rows.append(("severe_delay", icao, f"f-{icao}", "2024-01-02 15:47", 3))
    df = pd.DataFrame(
        rows, columns=["task", "airport_icao", "flight_id", "target", "horizon_h"]
    )
    df["target_start_utc"] = pd.to_datetime(df.target, utc=True).astype(UTC_US)
    df["as_of_utc"] = df.target_start_utc - pd.to_timedelta(df.horizon_h, unit="h")
    end = df.target_start_utc + pd.Timedelta(hours=1)
    df["target_end_utc"] = end.where(df.task == "throughput")
    df["prediction_id"] = [f"p{i}" for i in range(len(df))]
    df["horizon_h"] = df.horizon_h.astype("int32")
    return df.assign(
        cohort_version="v1", data_mode="fixture", schedule_snapshot_id="s"
    )[[*demand.REQUEST_COLUMNS, "schedule_snapshot_id"]]


def make_root(path: Path, hourly=None, requests=None, months=MONTHS) -> Path:
    shutil.copytree(REPO / "configs", path / "configs", dirs_exist_ok=True)
    processed = path / "data/processed"
    processed.mkdir(parents=True, exist_ok=True)
    (hourly_fixture() if hourly is None else hourly).to_parquet(
        processed / demand.HOURLY
    )
    (requests_fixture() if requests is None else requests).to_parquet(
        processed / demand.REQUESTS
    )
    manifest = {
        "data_mode": "fixture",
        "parquet_sha256": "fixture",
        "sources": [{"key": f"bts/bts_{m.replace('-', '_')}.zip"} for m in months],
    }
    (processed / "prediction_requests.manifest.json").write_text(json.dumps(manifest))
    return path


def build(root: Path) -> pd.DataFrame:
    demand.build(root)
    return pd.read_parquet(root / demand.PROCESSED / demand.OUTPUT).set_index(
        "prediction_id"
    )


def output_bytes(root: Path) -> bytes:
    demand.build(root)
    return (root / demand.PROCESSED / demand.OUTPUT).read_bytes()


# Values, joins and the anchor hour ------------------------------------------------------------


def test_features_have_expected_values_and_one_row_per_request(tmp_path):
    out = build(make_root(tmp_path))
    req = requests_fixture()
    assert len(out) == len(req) and out.index.is_unique
    counts = out.groupby(["task", "horizon_h"]).size().to_dict()
    assert counts == req.groupby(["task", "horizon_h"]).size().to_dict()
    # KATL 2024-01-02 15Z = 10 local: arrivals 20, neighbours 19 and 21.
    katl = out[
        (out.airport_icao == "KATL")
        & (out.task == "throughput")
        & (out.target_start_utc == utc("2024-01-02 15:00"))
    ]
    first = katl.iloc[0]
    assert (
        first.sched_arr_h0,
        first.sched_arr_hm1,
        first.sched_arr_hp1,
        first.sched_arr_3h,
    ) == (20, 19, 21, 60)
    assert (first.sched_dep_h0, first.sched_dep_3h) == (7, 21)
    assert (
        first.sched_arr_2023_local_hour_mean == 20
        and first.sched_arr_vs_2023_local_hour_mean == 1.0
    )
    assert first.status == "ok" and list(first.reason_codes) == []
    assert (
        katl.drop(columns=["horizon_h", "as_of_utc", "reason_codes"]).nunique().max()
        == 1
    )  # Same for h=3/6.
    # Flight departing 15:47Z at KDFW anchors on its 15Z departure hour (09 local): 19 arrivals.
    flight = out[(out.task == "severe_delay") & (out.airport_icao == "KDFW")].iloc[0]
    assert (
        flight.sched_arr_h0 == 19
        and flight.sched_dep_h0 == 7
        and pd.isna(flight.target_end_utc)
    )
    assert flight.schedule_knowledge_basis == demand.SCHEDULE_KNOWLEDGE_BASIS
    manifest = json.loads(
        (tmp_path / "data/processed/demand_features.manifest.json").read_text()
    )
    assert manifest["schedule_knowledge_basis"] == demand.SCHEDULE_KNOWLEDGE_BASIS


# Coverage: missing schedule source gives null with a reason, never 0 --------------------------


def test_missing_source_month_gives_null_with_reason_not_zero(tmp_path):
    out = build(
        make_root(tmp_path, months=["2022-12", "2023-01", "2023-12"])
    )  # 2024-01 absent.
    rows = out[out.target_start_utc == utc("2024-01-02 15:00")]
    assert rows.sched_arr_h0.isna().all() and rows.sched_dep_3h.isna().all()
    assert rows.status.eq("missing").all()
    assert rows.reason_codes.map(lambda r: "schedule_missing_anchor_hour" in r).all()
    kept = out[out.target_start_utc == utc("2023-01-02 15:00")]
    assert kept.sched_arr_h0.notna().all()


def test_producer_missing_coverage_and_neighbour_gaps(tmp_path):
    hourly = hourly_fixture()
    gap = (hourly.airport_icao == "KATL") & (
        hourly.hour_start_utc == utc("2024-01-02 14:00")
    )
    hourly.loc[gap, "scheduled_arrivals_coverage_status"] = "missing"
    hourly.loc[gap, "scheduled_arrivals"] = (
        0  # A fabricated zero must not reach the features.
    )
    out = build(make_root(tmp_path, hourly=hourly))
    row = out[
        (out.airport_icao == "KATL") & (out.target_start_utc == utc("2024-01-02 15:00"))
    ].iloc[0]
    assert (
        pd.isna(row.sched_arr_hm1)
        and pd.isna(row.sched_arr_3h)
        and row.sched_arr_h0 == 20
    )
    assert (
        list(row.reason_codes) == ["schedule_missing_neighbour_hour"]
        and row.status == "partial"
    )


# Outcome invariance (TEMPORAL_RULES §7 test 9 for demand) -------------------------------------


def schedule_rows(**outcomes):
    """Four flights in each direction around 15Z on 2023-01-15; outcome fields vary."""
    rows = []
    for i in range(4):
        rows.append(row(Flight_Number_Reporting_Airline=str(100 + i), **outcomes))
        rows.append(
            row(**{"Flight_Number_Reporting_Airline": str(200 + i), "Origin": "DFW",
                   "Dest": "ATL", "CRSArrTime": "1330", "WheelsOn": "1315",
                   "ArrTime": "1325", **outcomes})
        )  # fmt: skip
    return rows


def hourly_from_flights(rows) -> pd.DataFrame:
    df = outcome_fixture(rows)
    frames = [
        airport_hours(
            df,
            icao,
            utc("2023-01-15 00:00"),
            utc("2023-01-16 00:00"),
            "fixture",
            data_mode="fixture",
        )
        for icao in ("KATL", "KDFW")
    ]
    return pd.concat(frames, ignore_index=True)


OUTCOME_CHANGES = {
    "cancelled": {
        "Cancelled": "1",
        "DepTime": None,
        "WheelsOff": None,
        "WheelsOn": None,
        "ArrTime": None,
    },
    "diverted": {"Diverted": "1"},
    "actual_times": {
        "DepTime": "1240",
        "WheelsOff": "1255",
        "WheelsOn": "1405",
        "ArrTime": "1415",
        "DepDelay": "160",
    },
    "delays": {"DepDelay": "300", "ArrDelay": "290"},
}


@pytest.mark.parametrize("change", OUTCOME_CHANGES)
def test_flight_outcomes_do_not_change_demand_features(tmp_path, change):
    req = (
        requests_fixture()
        .iloc[:2]
        .assign(
            target_start_utc=pd.Series([utc("2023-01-15 16:00")] * 2).astype(UTC_US),
            airport_icao="KDFW",
        )
    )
    req["as_of_utc"] = req.target_start_utc - pd.to_timedelta(req.horizon_h, unit="h")
    req["target_end_utc"] = req.target_start_utc + pd.Timedelta(hours=1)
    base_hourly = hourly_from_flights(schedule_rows())
    changed_hourly = hourly_from_flights(schedule_rows(**OUTCOME_CHANGES[change]))
    # The change is real: realised movements differ.
    assert (
        not base_hourly.reporting_carrier_touchdowns.equals(
            changed_hourly.reporting_carrier_touchdowns
        )
        or change == "delays"
    )
    a = output_bytes(
        make_root(tmp_path / "a", hourly=base_hourly, requests=req, months=["2023-01"])
    )
    b = output_bytes(
        make_root(
            tmp_path / "b", hourly=changed_hourly, requests=req, months=["2023-01"]
        )
    )
    assert a == b
    out = pd.read_parquet(tmp_path / "a/data/processed/demand_features.parquet").iloc[0]
    # DFW departures leave 10:00 CST = 16Z; ATL departures arrive at DFW 11:30 CST = 17:30Z.
    assert (out.sched_dep_h0, out.sched_arr_h0, out.sched_arr_hp1) == (4, 0, 4)


def test_outcome_columns_in_hourly_do_not_change_demand_features(tmp_path):
    a = output_bytes(make_root(tmp_path / "a"))
    hourly = hourly_fixture()
    hourly["reporting_carrier_touchdowns"] = pd.array(
        np.zeros(len(hourly)), dtype="Int32"
    )
    hourly["reporting_carrier_takeoffs"] = pd.array(
        np.full(len(hourly), 99), dtype="Int32"
    )
    hourly["coverage_status"] = "missing"
    hourly["throughput_over_clear_weather_p95"] = 9.0
    hourly["exclusion_reason"] = "missing_source_month"
    b = output_bytes(make_root(tmp_path / "b", hourly=hourly))
    assert a == b


# Train-only normaliser -------------------------------------------------------------------------


def test_normaliser_ignores_2024_and_2025_schedule(tmp_path):
    build(make_root(tmp_path / "a"))
    hourly = hourly_fixture()
    later = hourly.hour_start_utc >= utc("2024-01-01")
    hourly.loc[later, "scheduled_arrivals"] = 500
    out = build(make_root(tmp_path / "b", hourly=hourly))
    m = [
        json.loads(
            (tmp_path / x / "data/processed/demand_features.manifest.json").read_text()
        )
        for x in "ab"
    ]
    assert m[0]["normaliser"] == m[1]["normaliser"]
    row = out[
        (out.airport_icao == "KATL") & (out.target_start_utc == utc("2024-01-02 15:00"))
    ].iloc[0]
    assert (
        row.sched_arr_2023_local_hour_mean == 20
        and row.sched_arr_vs_2023_local_hour_mean == 25.0
    )


# Read boundary ---------------------------------------------------------------------------------


def test_build_reads_only_the_named_projections(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    reads = []
    real = demand._read

    def spy(path, columns, filter=None):
        reads.append((Path(path).name, list(columns)))
        return real(path, columns, filter)

    monkeypatch.setattr(demand, "_read", spy)
    demand.build(root)
    assert {name for name, _ in reads} == {demand.HOURLY, demand.REQUESTS}
    for name, cols in reads:
        assert cols == (
            demand.HOURLY_COLUMNS if name == demand.HOURLY else demand.REQUEST_COLUMNS
        )


OUTCOME_WORDS = (
    "touchdown", "takeoff", "y_true", "wheels", "dep_delay", "cancelled", "diverted",
    "actual_", "throughput_over", "official_aar", "labels.parquet", "flights.parquet",
)  # fmt: skip


def test_demand_source_names_no_outcome_field_or_table():
    source = Path(demand.__file__).read_text()
    assert not [w for w in OUTCOME_WORDS if w in source]
    assert source.count("ds.dataset(") == 2  # _read and the request row count only.
    assert not set(demand.HOURLY_COLUMNS) & {
        "reporting_carrier_touchdowns",
        "coverage_status",
    }


AUDIT_SCRIPT = """
import json, os, sys
from pathlib import Path
import airbus_challenge.demand as D
import pandas, pyarrow, pyarrow.dataset, pyarrow.parquet  # noqa: F401
opened = []
def hook(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        opened.append(str(Path(os.fsdecode(args[0])).resolve()))
sys.addaudithook(hook)
D.build()
print(json.dumps({"module": D.__file__, "opened": opened}))
"""
DECOYS = [
    "data/processed/flights.parquet",
    "data/processed/labels.parquet",
    "data/labels/labels.parquet",
    "data/raw/Flight_Data_With_Weather_Final.csv",
]


def test_build_opens_only_allowed_files_in_a_fresh_process(tmp_path):
    root = make_root(tmp_path)
    for rel in DECOYS:
        decoy = root / rel
        decoy.parent.mkdir(parents=True, exist_ok=True)
        decoy.write_bytes(b"outcomes")
        decoy.chmod(0)  # Unreadable, so native pyarrow opens fail too.
    cmd = [sys.executable, "-c", AUDIT_SCRIPT]
    if shutil.which("sandbox-exec"):
        names = r"/(flights|labels)[^/]*\.parquet$|Flight_Data_With_Weather"
        cmd = [
            "sandbox-exec",
            "-p",
            f'(version 1)(allow default)(deny file-read* (regex #"{names}"))',
            *cmd,
        ]
    run = subprocess.run(cmd, check=False, cwd=root, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout.strip().splitlines()[-1])
    assert report["module"] == demand.__file__
    base = root.resolve()
    allowed = {
        base / "configs/airports.yaml",
        base / "configs/experiment.yaml",
        base / "data/processed/prediction_requests.manifest.json",
        base / "data/processed/.demand_features.manifest.json.tmp",
        base / "data/processed/demand_features.parquet",
    }
    bad = [
        p for p in map(Path, report["opened"])
        if (p.is_relative_to(base) and p not in allowed)
        or (not p.is_relative_to(base) and ("/data/" in str(p) or "label" in p.name))
    ]  # fmt: skip
    assert not bad, bad
