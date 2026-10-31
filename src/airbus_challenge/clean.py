import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path

import airportsdata
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

RAW = Path("data/raw")
OUTPUT = Path("data/processed/flights.parquet")
TOLERANCE_MIN = 2  # PROPOSED: integrator approval required before production use.
VERSION = "0.1.0"
KEY = [
    "FlightDate",
    "DOT_ID_Reporting_Airline",
    "Flight_Number_Reporting_Airline",
    "Origin",
    "Dest",
    "CRSDepTime",
]
SAMPLE_KEY = [
    "FL_DATE",
    "OP_CARRIER_AIRLINE_ID",
    "OP_CARRIER_FL_NUM",
    "ORIGIN",
    "DEST",
    "CRS_DEP_TIME",
]
CLOCKS = ["CRSDepTime", "CRSArrTime", "DepTime", "WheelsOff", "WheelsOn", "ArrTime"]
DURATIONS = [
    "DepDelay",
    "ArrDelay",
    "CRSElapsedTime",
    "ActualElapsedTime",
    "TaxiOut",
    "TaxiIn",
    "AirTime",
]
TIMES = [
    "scheduled_dep_utc",
    "scheduled_arr_utc",
    "actual_dep_utc",
    "wheels_off_utc",
    "wheels_on_utc",
    "actual_arr_utc",
]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def flight_keys(raw: pd.DataFrame) -> pd.Series:
    fields = raw[KEY].copy()
    fields["FlightDate"] = fields.FlightDate.str[:10]
    for c in [KEY[1], KEY[2], KEY[5]]:
        fields[c] = pd.to_numeric(fields[c]).astype("Int64").astype("string")
    if fields.isna().any().any():
        raise ValueError("Missing required flight key component")
    parts = fields.astype(str)
    result = parts.iloc[:, 0]
    for c in parts.columns[1:]:
        result = result + "|" + parts[c]
    return result


def airport_map(codes, config: dict) -> dict:
    data = airportsdata.load("IATA")
    overrides = config.get("timezone_overrides", {})
    result = {}
    missing = []
    for code in sorted(codes):
        a = data.get(code) or overrides.get(code)
        if not a or not a.get("icao") or not (a.get("tz") or a.get("timezone")):
            missing.append(code)
        else:
            result[code] = (a["icao"], a.get("tz") or a.get("timezone"))
    if missing:
        raise ValueError(f"Airports missing ICAO/timezone mapping: {missing}")
    return result


def clock_minutes(clock: pd.Series) -> pd.Series:
    n = pd.to_numeric(clock, errors="coerce")
    valid = (n == n.round()) & (n >= 0) & (n <= 2400) & (n.mod(100) < 60)
    return ((n // 100) * 60 + n.mod(100)).where(valid)


def local_departure(dates, clocks, zones):
    naive = pd.to_datetime(dates.str[:10]) + pd.to_timedelta(
        clock_minutes(clocks), unit="m"
    )
    utc = pd.Series(pd.NaT, index=dates.index, dtype="datetime64[us, UTC]")
    flags = pd.Series("", index=dates.index, dtype="string")
    for zone in zones.unique():
        ix = zones[zones == zone].index
        t = naive.loc[ix]
        ambiguous = (
            t.dt.tz_localize(zone, ambiguous="NaT", nonexistent="shift_forward").isna()
            & t.notna()
        )
        nonexistent = (
            t.dt.tz_localize(zone, ambiguous=True, nonexistent="NaT").isna() & t.notna()
        )
        flags.loc[ix[ambiguous]] = "scheduled_dep_dst_ambiguous"
        flags.loc[ix[nonexistent]] = "scheduled_dep_dst_nonexistent"
        utc.loc[ix] = t.dt.tz_localize(
            zone, ambiguous="NaT", nonexistent="NaT"
        ).dt.tz_convert("UTC")
    flags.loc[naive.isna()] = "scheduled_dep_invalid_clock"
    return utc, flags


def clock_error(times, clocks, zones):
    expected = clock_minutes(clocks).mod(1440)
    actual = pd.Series(float("nan"), index=times.index)
    for zone in zones.unique():
        ix = zones[zones == zone].index
        local = times.loc[ix].dt.tz_convert(zone)
        actual.loc[ix] = local.dt.hour * 60 + local.dt.minute
    diff = (actual - expected).abs()
    return pd.concat([diff, 1440 - diff], axis=1).min(axis=1)


def flights(raw: pd.DataFrame, config: dict, src: dict) -> pd.DataFrame:
    raw = raw.copy()
    mapping = airport_map(set(raw.Origin) | set(raw.Dest), config)
    df = pd.DataFrame(index=raw.index)
    keys = flight_keys(raw)
    df["flight_key"] = keys
    df["source_row_hash"] = pd.Series(
        [
            digest("|".join(r))
            for r in raw.fillna("").astype(str).itertuples(index=False, name=None)
        ],
        index=raw.index,
    )
    df["source_record_id"] = [digest(f"{src['sha256']}|{i + 2}") for i in raw.index]
    # v1: canonical key for singletons; retain conflicts and distinguish exact repeats.
    duplicates = keys.duplicated(keep=False)
    occurrence = df.groupby(["flight_key", "source_row_hash"], sort=False).cumcount()
    suffix = ("|" + df.source_row_hash + "|" + occurrence.astype(str)).where(
        duplicates, ""
    )
    df["flight_id"] = (keys + "|duplicates-v1" + suffix).map(digest)
    df["carrier_id"] = pd.to_numeric(raw[KEY[1]]).astype("Int64").astype("string")
    df["flight_number"] = pd.to_numeric(raw[KEY[2]]).astype("Int64").astype("string")
    df["source_flight_date"] = raw.FlightDate.str[:10].astype("string")
    for field, col in [("origin", "Origin"), ("dest", "Dest")]:
        df[f"{field}_icao"] = raw[col].map(lambda c: mapping[c][0]).astype("string")
        df[f"{field}_timezone"] = raw[col].map(lambda c: mapping[c][1]).astype("string")
    num = raw[CLOCKS + DURATIONS + ["Cancelled", "Diverted"]].apply(pd.to_numeric)
    flags = {}
    df["scheduled_dep_utc"], dst = local_departure(
        raw.FlightDate, raw.CRSDepTime, df.origin_timezone
    )
    for reason in dst.unique():
        if reason:
            flags[reason] = dst.eq(reason)
    for col in ["Cancelled", "Diverted"]:
        df[col.lower()] = num[col].map({0: False, 1: True}).astype("boolean")
    operated = df.cancelled.eq(False)
    direct = operated & df.diverted.eq(False)

    def duration(base, col, mask):
        return (base + pd.to_timedelta(num[col].where(num[col] >= 0), unit="m")).where(
            mask
        )

    df["scheduled_arr_utc"] = duration(
        df.scheduled_dep_utc, "CRSElapsedTime", num.CRSElapsedTime.notna()
    )
    df["actual_dep_utc"] = (
        df.scheduled_dep_utc + pd.to_timedelta(num.DepDelay, unit="m")
    ).where(raw.DepTime.notna())
    df["wheels_off_utc"] = duration(df.actual_dep_utc, "TaxiOut", raw.WheelsOff.notna())
    reached = pd.to_numeric(
        raw.get("DivReachedDest", pd.Series(index=raw.index, dtype=float))
    ).eq(1) & df.diverted.eq(True)
    div_elapsed = pd.to_numeric(
        raw.get("DivActualElapsedTime", pd.Series(index=raw.index, dtype=float))
    )
    elapsed = num.ActualElapsedTime.where(direct, div_elapsed.where(reached))
    df["actual_arr_utc"] = (
        df.actual_dep_utc + pd.to_timedelta(elapsed.where(elapsed >= 0), unit="m")
    ).where((direct | reached) & raw.ArrTime.notna())
    df["wheels_on_utc"] = (
        df.actual_arr_utc - pd.to_timedelta(num.TaxiIn.where(num.TaxiIn >= 0), unit="m")
    ).where((direct | reached) & raw.WheelsOn.notna())
    flags["diverted_partial_path"] = df.diverted.eq(True)
    flags["cancelled_partial_path"] = df.cancelled.eq(True)
    flags["duplicate_flight_key"] = keys.duplicated(keep=False)
    checks = zip(
        TIMES,
        CLOCKS,
        [
            df.origin_timezone,
            df.dest_timezone,
            df.origin_timezone,
            df.origin_timezone,
            df.dest_timezone,
            df.dest_timezone,
        ],
    )
    for time, clock, zones in checks:
        error = clock_error(df[time], raw[clock], zones)
        df[f"{time}_clock_error_min"] = error
        flags[f"{time}_clock_mismatch"] = error.gt(TOLERANCE_MIN)
        flags[f"{time}_invalid_clock"] = (
            raw[clock].notna() & clock_minutes(raw[clock]).isna()
        )
        flags[f"{time}_missing_clock"] = df[time].notna() & raw[clock].isna()
    flags["scheduled_arr_missing_duration"] = num.CRSElapsedTime.isna()
    flags["actual_dep_unresolved"] = raw.DepTime.notna() & df.actual_dep_utc.isna()
    flags["operated_departure_missing"] = operated & raw.DepTime.isna()
    flags["operated_arrival_missing"] = direct & raw.ArrTime.isna()
    flags["cancellation_status_unknown"] = df.cancelled.isna()
    flags["diversion_status_unknown"] = df.diverted.isna()
    flags["wheels_off_unresolved"] = raw.WheelsOff.notna() & df.wheels_off_utc.isna()
    flags["arrival_path_unresolved"] = (
        (direct | reached) & raw.ArrTime.notna() & df.wheels_on_utc.isna()
    )
    arrival_error = (
        df.actual_arr_utc - df.scheduled_arr_utc
    ).dt.total_seconds() / 60 - num.ArrDelay
    flags["arrival_delay_mismatch"] = direct & arrival_error.abs().gt(TOLERANCE_MIN)
    air_error = (
        df.wheels_on_utc - df.wheels_off_utc
    ).dt.total_seconds() / 60 - num.AirTime
    flags["air_time_mismatch"] = direct & air_error.abs().gt(TOLERANCE_MIN)
    for col in DURATIONS[2:]:
        flags[f"{col}_negative_duration"] = num[col].lt(0)
    flags["movement_order_invalid"] = (df.wheels_on_utc < df.wheels_off_utc) | (
        df.actual_arr_utc < df.actual_dep_utc
    )
    table = pd.DataFrame(flags).fillna(False).astype(bool)
    df["quality_flags"] = [list(table.columns[r]) for r in table.to_numpy()]
    quarantine = table.drop(
        columns=["diverted_partial_path", "cancelled_partial_path"]
    ).any(axis=1)
    df["timestamp_status"] = (
        pd.Series("valid", index=df.index)
        .mask(df.cancelled.fillna(False) | df.diverted.fillna(False), "partial")
        .mask(quarantine, "quarantined")
        .astype("string")
    )
    df["dep_delay_min"], df["arr_delay_min"] = (
        num.DepDelay.astype("float64"),
        num.ArrDelay.astype("float64"),
    )
    for c in (
        CLOCKS
        + DURATIONS
        + ["Cancelled", "Diverted", "Origin", "Dest", "Reporting_Airline"]
    ):
        df[f"raw_{c}"] = raw[c].astype("string")
    # Retain diversion evidence without treating an intermediate landing as the destination.
    for c in raw.columns:
        if c.startswith("Div") and c != "Diverted":
            df[f"raw_{c}"] = raw[c].astype("string")
    df["source_name"] = "BTS On-Time Reporting Carrier"
    df["source_version"] = "sha256:" + src["sha256"]
    df["raw_ref"] = (
        src["key"]
        + "#"
        + src.get("member", "")
        + "#line="
        + (raw.index + 2).astype(str)
    )
    df["retrieved_at_utc"] = pd.to_datetime(src["retrieved_at_utc"], utc=True)
    df["available_at_utc"] = pd.Series(
        pd.NaT, index=df.index, dtype="datetime64[us, UTC]"
    )
    df["availability_basis"] = "unknown"
    df["schedule_snapshot_id"] = src["sha256"]
    df["schedule_knowledge_basis"] = (
        "retrospective_final_archive; historical schedule availability unknown"
    )
    for c in TIMES + ["retrieved_at_utc"]:
        df[c] = df[c].astype("datetime64[us, UTC]")
    return df


def mark_sample(df, sample_keys):
    df["in_provided_csv"] = df.flight_key.isin(sample_keys)
    return df


def audit(df, config):
    rows = []
    for icao in config["airports"]:
        for direction, col in [("departure", "origin_icao"), ("arrival", "dest_icao")]:
            selected = df[df[col] == icao]
            for month, g in selected.groupby(selected.source_flight_date.str[:7]):
                rows.append(
                    {
                        "airport": icao,
                        "direction": direction,
                        "month": month,
                        "rows": len(g),
                        "cancelled": int(g.cancelled.sum()),
                        "cancellation_rate": float(g.cancelled.mean()),
                        "diverted": int(g.diverted.sum()),
                        "diversion_rate": float(g.diverted.mean()),
                        "timestamp_status": g.timestamp_status.value_counts().to_dict(),
                        "quality_flags": dict(
                            Counter(f for fs in g.quality_flags for f in fs)
                        ),
                    }
                )
    return rows


def overnight_rows(df):
    result = pd.Series(False, index=df.index)
    for zone in df.dest_timezone.unique():
        ix = df.dest_timezone[df.dest_timezone == zone].index
        local_date = (
            df.loc[ix, "scheduled_arr_utc"].dt.tz_convert(zone).dt.strftime("%Y-%m-%d")
        )
        result.loc[ix] = (
            (local_date > df.loc[ix, "source_flight_date"])
            .fillna(False)
            .to_numpy(dtype=bool)
        )
    return result


def build():
    from airbus_challenge.download import months, sha256, study_window

    config = yaml.safe_load(Path("configs/airports.yaml").read_text())
    expected = [
        RAW / "bts" / f"bts_{y}_{m:02d}.zip" for y, m in months(*study_window())
    ]
    missing = [str(p) for p in expected if not p.exists()]
    if missing:
        raise ValueError(f"BTS download incomplete; missing {missing}")
    manifest = json.loads((RAW / "manifest.json").read_text())
    sample = pd.read_csv(
        RAW / "Flight_Data_With_Weather_Final.csv", usecols=SAMPLE_KEY, dtype=str
    )
    sample.columns = [KEY[SAMPLE_KEY.index(c)] for c in sample.columns]
    sample_keys = flight_keys(sample)
    csv_src = manifest["Flight_Data_With_Weather_Final.csv"]
    if sha256(RAW / "Flight_Data_With_Weather_Final.csv") != csv_src["sha256"]:
        raise ValueError("Provided CSV checksum mismatch")
    matches = Counter()
    scoped_matches = Counter()
    report = {
        "schema_version": VERSION,
        "producer": f"airbus_challenge.clean/{VERSION}",
        "data_mode": "real",
        "tolerance_min": TOLERANCE_MIN,
        "tolerance_status": "PROPOSED",
        "duplicate_resolution": "v1: sha256(canonical key|duplicates-v1); duplicate keys append |retained-row-sha256|zero-based occurrence in source order",
        "flight_key_components": KEY,
        "sources": [],
        "provided_csv_source": csv_src,
        "config_sha256": sha256(Path("configs/airports.yaml")),
        "coverage": [],
        "rows": 0,
        "null_counts": Counter(),
        "timestamp_status": Counter(),
        "quality_flag_counts": Counter(),
        "timezone_coverage": {},
        "samples": {},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT.with_name(".flights.parquet.tmp")
    writer = None
    tolerance_failures = 0
    cancelled_count, diverted_count = 0, 0
    min_time, max_time = None, None
    try:
        for path in expected:
            key = str(path.relative_to(RAW))
            src = {"key": key, **manifest[key]}
            if sha256(path) != src["sha256"]:
                raise ValueError(f"Source checksum mismatch: {path}")
            with zipfile.ZipFile(path) as z:
                (src["member"],) = [n for n in z.namelist() if n.endswith(".csv")]
                raw = pd.read_csv(
                    z.open(src["member"]),
                    dtype=str,
                    usecols=lambda c: (
                        c
                        in set(
                            KEY
                            + CLOCKS
                            + DURATIONS
                            + ["Cancelled", "Diverted", "Reporting_Airline"]
                        )
                        or c.startswith("Div")
                    ),
                )
            all_keys = flight_keys(raw)
            matches.update(all_keys[all_keys.isin(sample_keys)])
            iatas = [a["iata"] for a in config["airports"].values()]
            raw = raw[raw.Origin.isin(iatas) | raw.Dest.isin(iatas)]
            df = mark_sample(flights(raw, config, src), sample_keys)
            scoped_matches.update(df.flight_key[df.in_provided_csv])
            table = pa.Table.from_pandas(df, preserve_index=False)
            # Empty flag lists must retain a stable list<string> across partitions.
            table = table.set_column(
                table.schema.get_field_index("quality_flags"),
                "quality_flags",
                pa.array(df.quality_flags, type=pa.list_(pa.string())),
            )
            if writer is None:
                writer = pq.ParquetWriter(tmp, table.schema)
                report["columns_and_dtypes"] = {
                    f.name: str(f.type) for f in table.schema
                }
            writer.write_table(table.cast(writer.schema))
            tolerance_failures += int(
                df.quality_flags.map(
                    lambda fs: any(f.endswith("_mismatch") for f in fs)
                ).sum()
            )
            lo, hi = (
                df.scheduled_dep_utc.min().isoformat(),
                df.scheduled_dep_utc.max().isoformat(),
            )
            min_time = min(min_time, lo) if min_time else lo
            max_time = max(max_time, hi) if max_time else hi
            cancelled_count += int(df.cancelled.sum())
            diverted_count += int(df.diverted.sum())
            report["rows"] += len(df)
            report["sources"].append(src)
            report["coverage"].extend(audit(df, config))
            report["null_counts"].update({c: int(df[c].isna().sum()) for c in TIMES})
            report["timestamp_status"].update(df.timestamp_status)
            report["quality_flag_counts"].update(
                f for fs in df.quality_flags for f in fs
            )
            for field in ["origin", "dest"]:
                report["timezone_coverage"].update(
                    dict(zip(df[f"{field}_icao"], df[f"{field}_timezone"]))
                )
            overnight = overnight_rows(df)
            for name, mask in {
                "normal": df.timestamp_status.eq("valid"),
                "cancelled": df.cancelled.fillna(False),
                "overnight": overnight,
            }.items():
                if name not in report["samples"] and mask.any():
                    report["samples"][name] = json.loads(
                        df.loc[
                            mask,
                            [
                                "flight_id",
                                "source_flight_date",
                                "origin_icao",
                                "dest_icao",
                                *TIMES,
                                "cancelled",
                                "diverted",
                                "timestamp_status",
                            ],
                        ]
                        .head(1)
                        .to_json(orient="records", date_format="iso")
                    )[0]
            print(
                path.name,
                len(df),
                df.timestamp_status.value_counts().to_dict(),
                flush=True,
            )
        counts = sample_keys.map(matches).fillna(0).astype(int)
        in_scope = sample.Origin.isin(iatas) | sample.Dest.isin(iatas)
        scope_counts = sample_keys[in_scope].map(scoped_matches).fillna(0).astype(int)
        report["provided_csv_match"] = {
            "study_airport_rows": int(in_scope.sum()),
            "study_airport_matched_rows": int(scope_counts.gt(0).sum()),
            "study_airport_unmatched_rows": int(scope_counts.eq(0).sum()),
            "study_airport_multiply_matched_rows": int(scope_counts.gt(1).sum()),
            "rows": len(sample),
            "matched_rows": int(counts.gt(0).sum()),
            "match_rate": float(counts.gt(0).mean()),
            "unmatched_rows": int(counts.eq(0).sum()),
            "multiply_matched_rows": int(counts.gt(1).sum()),
            "duplicate_sample_key_rows": int(sample_keys.duplicated(keep=False).sum()),
            "multiply_matched_keys": sample_keys[counts.gt(1)].tolist(),
            "unmatched_keys": sample_keys[counts.eq(0)].tolist(),
        }
        report["null_rates"] = {
            c: n / report["rows"] for c, n in report["null_counts"].items()
        }
        report["cancelled_rows"] = cancelled_count
        report["diverted_rows"] = diverted_count
        report["cancellation_rate"] = cancelled_count / report["rows"]
        report["diversion_rate"] = diverted_count / report["rows"]
        report["tolerance_failed_rows"] = tolerance_failures
        report["min_time_utc"] = min_time
        report["max_time_utc"] = max_time
        report["source_row_hash_basis"] = (
            "sha256 of retained raw fields, CSV column order, null as empty, pipe-delimited"
        )
    finally:
        if writer:
            writer.close()
    report["parquet_sha256"] = sha256(tmp)
    tmp.replace(OUTPUT)
    report_path = OUTPUT.with_suffix(".manifest.json")
    temp_report = report_path.with_name(".flights.manifest.json.tmp")
    temp_report.write_text(json.dumps(report, indent=2, default=str))
    temp_report.replace(report_path)
    print(
        "Wrote",
        OUTPUT,
        "rows",
        report["rows"],
        "CSV match",
        report["provided_csv_match"]["match_rate"],
    )
    return report


if __name__ == "__main__":
    build()
