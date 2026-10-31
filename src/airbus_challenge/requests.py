import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from airbus_challenge.download import sha256

FLIGHTS = Path("data/processed/flights.parquet")
OUTPUT = Path("data/processed/prediction_requests.parquet")
COHORT_VERSION = "retrospective_schedule_v1"
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


def expand(base, horizons, data_mode):
    frames = []
    for horizon in horizons:
        df = base.copy()
        df["horizon_h"] = horizon
        df["as_of_utc"] = df.target_start_utc - pd.Timedelta(hours=horizon)
        df["cohort_version"] = COHORT_VERSION
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
            + COHORT_VERSION
        )
        df["prediction_id"] = canonical.map(
            lambda s: hashlib.sha256(s.encode()).hexdigest()
        )
        frames.append(df[SCHEMA.names])
    return pd.concat(frames, ignore_index=True)


def flight_requests(schedule, icaos, horizons, start, end, data_mode="real"):
    # Whitelist before cohort selection: outcomes cannot remove cancellations or change keys.
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
    return expand(df, horizons, data_mode)


def airport_requests(icaos, horizons, start, end, snapshot_id, data_mode="real"):
    grid = pd.MultiIndex.from_product(
        [icaos, pd.date_range(start, end, freq="h", inclusive="left")],
        names=["airport_icao", "target_start_utc"],
    )
    df = grid.to_frame(index=False)
    df["task"] = "throughput"
    df["flight_id"] = pd.Series(pd.NA, index=df.index, dtype="string")
    df["target_end_utc"] = df.target_start_utc + pd.Timedelta(hours=1)
    df["schedule_snapshot_id"] = snapshot_id
    return expand(df, horizons, data_mode)


def build():
    config = yaml.safe_load(Path("configs/airports.yaml").read_text())
    experiment = yaml.safe_load(Path("configs/experiment.yaml").read_text())
    start, end = bounds(experiment)
    horizons = experiment["horizons_h"]
    if len(set(horizons)) != len(horizons) or any(
        h <= 0 or int(h) != h for h in horizons
    ):
        raise ValueError("Horizons must be distinct positive integer hours")
    source_manifest = json.loads(FLIGHTS.with_suffix(".manifest.json").read_text())
    if sha256(FLIGHTS) != source_manifest["parquet_sha256"]:
        raise ValueError("Flight archive hash disagrees with manifest")
    mode = source_manifest["data_mode"]
    icaos = list(config["airports"])
    # Snapshot identifies the final archive used to simulate schedule knowledge, not a live feed.
    snapshot = hashlib.sha256(
        "|".join(s["sha256"] for s in source_manifest["sources"]).encode()
    ).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT.with_name(".prediction_requests.parquet.tmp")
    report = {
        "schema_version": "0.1.0",
        "producer": "airbus_challenge.requests/0.1.0",
        "data_mode": mode,
        "cohort_version": COHORT_VERSION,
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
            batch_size=100_000, columns=SCHEDULE_COLUMNS
        )
        for batch in batches:
            schedule = batch.to_pandas()
            study = schedule.origin_icao.isin(icaos)
            report["schedule_rows"] += int(study.sum())
            report["study_departures_unresolved_schedule"] += int(
                (study & schedule.scheduled_dep_utc.isna()).sum()
            )
            df = flight_requests(schedule, icaos, horizons, start, end, mode)
            writer.write_table(
                pa.Table.from_pandas(df, schema=SCHEMA, preserve_index=False)
            )
            report["rows"] += len(df)
            report["counts"].extend(counts(df))
        df = airport_requests(icaos, horizons, start, end, snapshot, mode)
        writer.write_table(
            pa.Table.from_pandas(df, schema=SCHEMA, preserve_index=False)
        )
        report["rows"] += len(df)
        report["counts"].extend(counts(df))
    report["counts"] = (
        pd.DataFrame(report["counts"])
        .groupby(["task", "airport_icao", "horizon_h"], as_index=False)["rows"]
        .sum()
        .to_dict(orient="records")
    )
    report["parquet_sha256"] = sha256(tmp)
    tmp.replace(OUTPUT)
    mpath = OUTPUT.with_suffix(".manifest.json")
    temp = mpath.with_name(".prediction_requests.manifest.json.tmp")
    temp.write_text(json.dumps(report, indent=2))
    temp.replace(mpath)
    print(OUTPUT, report["rows"], "requests", report["counts"])
    return report


def counts(df):
    return (
        df.groupby(["task", "airport_icao", "horizon_h"])
        .size()
        .rename("rows")
        .reset_index()
        .to_dict(orient="records")
    )


if __name__ == "__main__":
    build()
