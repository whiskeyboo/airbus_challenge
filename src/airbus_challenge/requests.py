import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from airbus_challenge.download import sha256

FLIGHTS = Path("data/processed/flights.parquet")
OUTPUT = Path("data/processed/prediction_requests.parquet")
COHORT_VERSION = "retrospective_schedule_v1"
VERSION = "0.2.0"
SCHEDULE_COLUMNS = [
    "flight_id",
    "origin_icao",
    "scheduled_dep_utc",
    "schedule_snapshot_id",
]
SCHEMA = pa.schema(
    [
        ("prediction_id", pa.string()),
        ("task", pa.string()),
        ("airport_icao", pa.string()),
        ("flight_id", pa.string()),
        ("as_of_utc", pa.timestamp("us", tz="UTC")),
        ("target_start_utc", pa.timestamp("us", tz="UTC")),
        ("target_end_utc", pa.timestamp("us", tz="UTC")),
        ("horizon_h", pa.int32()),
        ("schedule_snapshot_id", pa.string()),
        ("cohort_version", pa.string()),
        ("data_mode", pa.string()),
    ]
)


def bounds(experiment):
    splits = experiment["splits"].values()
    return (
        pd.Timestamp(min(s["start"] for s in splits), tz="UTC"),
        pd.Timestamp(max(s["end"] for s in experiment["splits"].values()), tz="UTC"),
    )


def expand(base, horizons, data_mode, cohort_version=COHORT_VERSION):
    frames = []
    for horizon in horizons:
        df = base.copy()
        df["horizon_h"] = horizon
        df["as_of_utc"] = df.target_start_utc - pd.Timedelta(hours=horizon)
        df["cohort_version"] = cohort_version
        df["data_mode"] = data_mode
        stamp = df.target_start_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        canonical = (
            df.task
            + "|"
            + df.airport_icao
            + "|"
            + df.flight_id.fillna("")
            + "|"
            + stamp
            + "|"
            + str(horizon)
            + "|"
            + cohort_version
        )
        df["prediction_id"] = canonical.map(
            lambda s: hashlib.sha256(s.encode()).hexdigest()
        )
        frames.append(df[SCHEMA.names])
    return pd.concat(frames, ignore_index=True)


def flight_requests(
    schedule,
    icaos,
    horizons,
    start,
    end,
    data_mode="real",
    cohort_version=COHORT_VERSION,
):
    # Whitelist before cohort selection: outcomes cannot remove cancellations or change keys.
    if cohort_version == "csv_only_v1":
        schedule = schedule.loc[schedule.in_provided_csv.eq(True).fillna(False)]
    schedule = schedule[SCHEDULE_COLUMNS]
    selected = (
        schedule.origin_icao.isin(icaos)
        & schedule.scheduled_dep_utc.ge(start)
        & schedule.scheduled_dep_utc.lt(end)
    )
    df = (
        schedule.loc[selected]
        .rename(
            columns={
                "origin_icao": "airport_icao",
                "scheduled_dep_utc": "target_start_utc",
            }
        )
        .copy()
    )
    df["task"] = "severe_delay"
    df["target_end_utc"] = pd.Series(
        pd.NaT, index=df.index, dtype="datetime64[us, UTC]"
    )
    return expand(df, horizons, data_mode, cohort_version)


def airport_requests(
    icaos,
    horizons,
    start,
    end,
    snapshot_id,
    data_mode="real",
    cohort_version=COHORT_VERSION,
):
    if cohort_version == "csv_only_v1":
        raise ValueError("CSV-only has no hourly throughput requests")
    grid = pd.MultiIndex.from_product(
        [icaos, pd.date_range(start, end, freq="h", inclusive="left")],
        names=["airport_icao", "target_start_utc"],
    )
    df = grid.to_frame(index=False)
    df["task"] = "throughput"
    df["flight_id"] = pd.Series(pd.NA, index=df.index, dtype="string")
    df["target_end_utc"] = df.target_start_utc + pd.Timedelta(hours=1)
    df["schedule_snapshot_id"] = snapshot_id
    return expand(df, horizons, data_mode, cohort_version)


def cohort_definitions(icaos):
    if len(icaos) != len(set(icaos)) or len(icaos) < 2:
        raise ValueError(
            "Cohorts need distinct study airports and at least two for holdout"
        )
    primary = {
        "tasks": ["throughput", "severe_delay"],
        "train_airports": list(icaos),
        "score_airports": list(icaos),
        "request_airports": list(icaos),
        "flight_membership": "all study-airport departures",
        "ratio_labels": True,
    }
    result = {
        COHORT_VERSION: primary,
        "csv_only_v1": {
            **primary,
            "tasks": ["severe_delay"],
            "flight_membership": "in_provided_csv=true in every partition",
            "ratio_labels": False,
        },
    }
    for icao in icaos:
        result[f"loao_{icao}_v1"] = {
            **primary,
            "train_airports": [i for i in icaos if i != icao],
            "score_airports": [icao],
            "held_out_airport": icao,
            "request_airports": list(icaos),
            "ratio_labels": False,
        }
    return result


def select_cohorts(icaos, cohorts):
    definitions = cohort_definitions(icaos)
    selected = list(definitions) if list(cohorts) == ["all"] else list(cohorts)
    if (
        not selected
        or len(selected) != len(set(selected))
        or set(selected) - set(definitions)
    ):
        raise ValueError(f"Unknown, empty or duplicate cohorts: {selected}")
    return {name: definitions[name] for name in selected}


def build(output=None, cohorts=(COHORT_VERSION,)):
    output = Path(output) if output is not None else OUTPUT
    config = yaml.safe_load(Path("configs/airports.yaml").read_text())
    experiment = yaml.safe_load(Path("configs/experiment.yaml").read_text())
    start, end = bounds(experiment)
    horizons = experiment["horizons_h"]
    if (
        not horizons
        or len(set(horizons)) != len(horizons)
        or any(h <= 0 or int(h) != h for h in horizons)
    ):
        raise ValueError("Horizons must be distinct positive integer hours")
    source_manifest = json.loads(FLIGHTS.with_suffix(".manifest.json").read_text())
    if sha256(FLIGHTS) != source_manifest["parquet_sha256"]:
        raise ValueError("Flight archive hash disagrees with manifest")
    mode = source_manifest["data_mode"]
    if mode not in {"real", "fixture"}:
        raise ValueError(f"Invalid data_mode: {mode}")
    icaos = list(config["airports"])
    definitions = select_cohorts(icaos, cohorts)
    # Snapshot identifies the final archive used to simulate schedule knowledge, not a live feed.
    snapshot = hashlib.sha256(
        "|".join(s["sha256"] for s in source_manifest["sources"]).encode()
    ).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(".prediction_requests.parquet.tmp")
    report = {
        "schema_version": VERSION,
        "producer": f"airbus_challenge.requests/{VERSION}",
        "data_mode": mode,
        "cohort_versions": list(definitions),
        "cohorts": definitions,
        "primary_prediction_ids_unchanged": True,
        "dependent_artifacts": "new request cohorts require regenerated labels/features and cohort-aware model/baseline manifests",
        "rows": 0,
        "counts": [],
        "schedule_knowledge_basis": "retrospective final archive; schedule assumed known at every issue time; not evidenced live availability",
        "prediction_id_basis": "sha256(task|airport_icao|flight_id-or-empty|target_start_utc RFC3339 Z seconds|horizon_h|cohort_version)",
        "source_flights_sha256": source_manifest["parquet_sha256"],
        "sources": source_manifest["sources"],
        "min_target_utc": start.isoformat(),
        "max_target_exclusive_utc": end.isoformat(),
        "horizons_h": horizons,
        "schedule_rows": 0,
        "study_departures_unresolved_schedule": 0,
    }
    with pq.ParquetWriter(tmp, SCHEMA) as writer:
        batches = pq.ParquetFile(FLIGHTS).iter_batches(
            batch_size=100_000,
            columns=SCHEDULE_COLUMNS
            + (["in_provided_csv"] if "csv_only_v1" in definitions else []),
        )
        for batch in batches:
            schedule = batch.to_pandas()
            study = schedule.origin_icao.isin(icaos)
            report["schedule_rows"] += int(study.sum())
            report["study_departures_unresolved_schedule"] += int(
                (study & schedule.scheduled_dep_utc.isna()).sum()
            )
            for cohort in definitions:
                df = flight_requests(
                    schedule, icaos, horizons, start, end, mode, cohort
                )
                writer.write_table(
                    pa.Table.from_pandas(df, schema=SCHEMA, preserve_index=False)
                )
                report["rows"] += len(df)
                report["counts"].extend(counts(df))
        for cohort, definition in definitions.items():
            if "throughput" not in definition["tasks"]:
                continue
            df = airport_requests(icaos, horizons, start, end, snapshot, mode, cohort)
            writer.write_table(
                pa.Table.from_pandas(df, schema=SCHEMA, preserve_index=False)
            )
            report["rows"] += len(df)
            report["counts"].extend(counts(df))
    missing = set(definitions) - {row["cohort_version"] for row in report["counts"]}
    if missing:
        raise ValueError(f"No eligible requests for cohorts: {sorted(missing)}")
    report["counts"] = (
        pd.DataFrame(report["counts"])
        .groupby(
            ["cohort_version", "task", "airport_icao", "horizon_h"], as_index=False
        )["rows"]
        .sum()
        .to_dict(orient="records")
    )
    report["parquet_sha256"] = sha256(tmp)
    tmp.replace(output)
    mpath = output.with_suffix(".manifest.json")
    temp = mpath.with_name(".prediction_requests.manifest.json.tmp")
    temp.write_text(json.dumps(report, indent=2))
    temp.replace(mpath)
    print(output, report["rows"], "requests", report["counts"])
    return report


def counts(df):
    return (
        df.groupby(["cohort_version", "task", "airport_icao", "horizon_h"])
        .size()
        .rename("rows")
        .reset_index()
        .to_dict(orient="records")
    )


# Approved schedule-only audit: no cancellations, delays, actual movement clocks or weather.
AUDIT_COLUMNS = [
    "flight_id",
    "source_flight_date",
    "origin_icao",
    "dest_icao",
    "carrier_id",
    "raw_Reporting_Airline",
    "scheduled_dep_utc",
    "scheduled_arr_utc",
]


def schedule_counts(schedule, icaos):
    frames = []
    for direction, endpoint, instant in [
        ("departure", "origin_icao", "scheduled_dep_utc"),
        ("arrival", "dest_icao", "scheduled_arr_utc"),
    ]:
        df = schedule.loc[schedule[endpoint].isin(icaos), AUDIT_COLUMNS].copy()
        df["airport_icao"] = df[endpoint]
        df["direction"] = direction
        df["service_month"] = df.source_flight_date.str[:7]
        df["schedule_utc_unresolved"] = df[instant].isna().astype("int32")
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    keys = [
        "airport_icao",
        "direction",
        "service_month",
        "carrier_id",
        "raw_Reporting_Airline",
    ]
    return (
        df.groupby(keys, dropna=False)
        .agg(
            scheduled_flights=("flight_id", "size"),
            unresolved_schedule_utc=("schedule_utc_unresolved", "sum"),
        )
        .reset_index()
    )


def schedule_drift(schedule, icaos):
    carrier = schedule_counts(schedule, icaos)
    keys = ["airport_icao", "direction", "service_month"]
    monthly = carrier.groupby(keys, as_index=False)[
        ["scheduled_flights", "unresolved_schedule_utc"]
    ].sum()
    monthly["calendar_days"] = monthly.service_month.map(
        lambda m: pd.Period(m, freq="M").days_in_month
    )
    monthly["scheduled_per_calendar_day"] = (
        monthly.scheduled_flights / monthly.calendar_days
    )
    years = []
    for year in sorted(monthly.service_month.str[:4].unique()):
        current = monthly[monthly.service_month.str.startswith(year)].copy()
        old = monthly[monthly.service_month.str.startswith(str(int(year) - 1))].copy()
        old["service_month"] = old.service_month.str[4:].radd(year)
        paired = current.merge(
            old, on=keys, suffixes=("", "_prior_year"), validate="one_to_one"
        )
        paired["prior_year"] = str(int(year) - 1)
        paired["per_day_change_fraction"] = (
            paired.scheduled_per_calendar_day
            / paired.scheduled_per_calendar_day_prior_year
            - 1
        )
        years.append(paired)
    comparisons = pd.concat(years, ignore_index=True) if years else pd.DataFrame()
    weekdays = []
    for icao in icaos:
        for direction, endpoint in [
            ("departure", "origin_icao"),
            ("arrival", "dest_icao"),
        ]:
            subset = schedule[schedule[endpoint].eq(icao)]
            dates = pd.to_datetime(subset.source_flight_date)
            daily = (
                pd.DataFrame({"date": dates, "scheduled_flights": 1})
                .groupby("date")
                .scheduled_flights.sum()
            )
            for month in sorted(subset.source_flight_date.str[:7].unique()):
                period = pd.Period(month, freq="M")
                grid = pd.date_range(period.start_time, period.end_time, freq="D")
                values = daily.reindex(grid, fill_value=0)
                for weekday, group in values.groupby(grid.day_of_week):
                    weekdays.append(
                        {
                            "airport_icao": icao,
                            "direction": direction,
                            "service_month": month,
                            "weekday": int(weekday),
                            "calendar_days": len(group),
                            "scheduled_flights": int(group.sum()),
                            "scheduled_per_day": float(group.mean()),
                            "days_with_schedule_rows": int(group.gt(0).sum()),
                        }
                    )
    return {
        "monthly": monthly.to_dict(orient="records"),
        "carrier_monthly": carrier.to_dict(orient="records"),
        "year_over_year": comparisons.to_dict(orient="records"),
        "weekday_daily_rates": weekdays,
    }


def audit_schedules(output=Path("data/processed/schedule_drift.json")):
    config = yaml.safe_load(Path("configs/airports.yaml").read_text())["airports"]
    source = json.loads(FLIGHTS.with_suffix(".manifest.json").read_text())
    if sha256(FLIGHTS) != source["parquet_sha256"]:
        raise ValueError("Flight archive hash disagrees with manifest")
    schedule = pd.read_parquet(FLIGHTS, columns=AUDIT_COLUMNS)
    report = schedule_drift(schedule, list(config))
    raw_counts = []
    national_counts = []
    partitions = []
    raw_columns = [
        "FlightDate",
        "DOT_ID_Reporting_Airline",
        "Reporting_Airline",
        "Origin",
        "Dest",
    ]
    for src in source["sources"]:
        path = Path("data/raw") / src["key"]
        if sha256(path) != src["sha256"]:
            raise ValueError(f"BTS checksum mismatch: {path}")
        with zipfile.ZipFile(path) as z:
            (member,) = [n for n in z.namelist() if n.endswith(".csv")]
            raw = pd.read_csv(z.open(member), usecols=raw_columns, dtype=str)
        raw["FlightDate"] = raw.FlightDate.str[:10]
        national = (
            raw.groupby(["DOT_ID_Reporting_Airline", "Reporting_Airline"])
            .agg(
                scheduled_flights=("FlightDate", "size"),
                source_days=("FlightDate", "nunique"),
            )
            .reset_index()
        )
        national_counts.extend(
            national.assign(source_partition=src["key"]).to_dict(orient="records")
        )
        partitions.append(
            {
                "key": src["key"],
                "sha256": src["sha256"],
                "source_days": int(raw.FlightDate.nunique()),
                "min_service_date": raw.FlightDate.min(),
                "max_service_date": raw.FlightDate.max(),
            }
        )
        for icao, airport in config.items():
            for direction, endpoint in [("departure", "Origin"), ("arrival", "Dest")]:
                selected = raw[raw[endpoint].eq(airport["iata"])].copy()
                selected["service_month"] = selected.FlightDate.str[:7]
                selected["carrier_id"] = (
                    pd.to_numeric(selected.DOT_ID_Reporting_Airline)
                    .astype("Int64")
                    .astype("string")
                )
                selected["raw_Reporting_Airline"] = selected.Reporting_Airline
                counts = (
                    selected.groupby(
                        ["service_month", "carrier_id", "raw_Reporting_Airline"]
                    )
                    .size()
                    .rename("scheduled_flights")
                    .reset_index()
                )
                raw_counts.append(counts.assign(airport_icao=icao, direction=direction))
        print("Schedule-only audit", path.name, flush=True)
    keys = [
        "airport_icao",
        "direction",
        "service_month",
        "carrier_id",
        "raw_Reporting_Airline",
    ]
    raw = (
        pd.concat(raw_counts, ignore_index=True)
        .groupby(keys, as_index=False)
        .scheduled_flights.sum()
    )
    cleaned = pd.DataFrame(report["carrier_monthly"])
    check = cleaned.merge(
        raw, on=keys, how="outer", suffixes=("_processed", "_raw"), indicator=True
    )
    mismatch = check["_merge"].ne("both") | check.scheduled_flights_processed.ne(
        check.scheduled_flights_raw
    )
    if mismatch.any():
        raise ValueError(
            f"Schedule rows differ from BTS source: {check.loc[mismatch].to_dict(orient='records')}"
        )
    report.update(
        schema_version="1.0.0",
        producer="airbus_challenge.requests/schedule-drift/1",
        data_mode=source["data_mode"],
        source_flights_sha256=source["parquet_sha256"],
        rows=len(schedule),
        read_columns=AUDIT_COLUMNS,
        raw_read_columns=raw_columns,
        date_basis="source local departure service month for both directions; not UTC event month",
        policy="scheduled source rows include cancelled/diverted services; no final-outcome fields, weather, predictions or model metrics are loaded; compare same calendar months with per-day and weekday context",
        source_partitions=partitions,
        national_carrier_scope=national_counts,
        raw_reconciliation="passed for every airport/direction/month/carrier",
        interpretation="archive schedule/scope drift only; no inference that actual airport traffic or capacity fell, and no model tuning",
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name("." + output.name + ".tmp")
    tmp.write_text(json.dumps(report, indent=2))
    tmp.replace(output)
    print("Wrote", output)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cohorts",
        nargs="+",
        default=[COHORT_VERSION],
        help="Cohort names, or all; primary IDs stay unchanged",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--audit-schedules", action="store_true")
    parser.add_argument(
        "--audit-output", type=Path, default=Path("data/processed/schedule_drift.json")
    )
    args = parser.parse_args()
    if args.audit_schedules:
        audit_schedules(args.audit_output)
    else:
        build(args.output, args.cohorts)
