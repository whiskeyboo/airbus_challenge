"""Optional, request-keyed operational replay features from a simulated feed."""

import argparse
import collections
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from airbus_challenge.download import sha256

VERSION = "simulated-operations-features/1"
REQUEST_COLUMNS = [
    "prediction_id",
    "airport_icao",
    "as_of_utc",
    "cohort_version",
    "data_mode",
]
FEED_COLUMNS = [
    "airport_icao",
    "source_hour_start_utc",
    "source_hour_end_utc",
    "available_at_utc",
    "reporting_carrier_touchdowns",
    "n_unresolved",
    "coverage_status",
    "feed_eligible",
    "availability_basis",
    "data_mode",
]
SCHEMA = pa.schema(
    [
        pa.field("prediction_id", pa.string(), nullable=False),
        pa.field("airport_icao", pa.string(), nullable=False),
        pa.field("as_of_utc", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("cohort_version", pa.string(), nullable=False),
        pa.field("data_mode", pa.string(), nullable=False),
        pa.field("ops_arrivals_last_complete", pa.float64()),
        pa.field("ops_source_age_min", pa.float64()),
        pa.field("ops_status", pa.string(), nullable=False),
        pa.field("source_hour_start_utc", pa.timestamp("us", tz="UTC")),
        pa.field("source_hour_end_utc", pa.timestamp("us", tz="UTC")),
        pa.field("source_available_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("availability_basis", pa.string(), nullable=False),
    ]
)


def validate_feed(feed, latency_min):
    if feed.duplicated(["airport_icao", "source_hour_start_utc"]).any():
        raise ValueError("Duplicate feed airport/hour")
    if not feed.availability_basis.eq("simulated").all():
        raise ValueError("Operations feed must have simulated availability")
    if not feed.coverage_status.isin(
        ["complete_for_source_scope", "partial", "missing"]
    ).all():
        raise ValueError("Unknown feed coverage status")
    if (
        not (feed.source_hour_end_utc - feed.source_hour_start_utc)
        .eq(pd.Timedelta(hours=1))
        .all()
    ):
        raise ValueError("Operations feed source interval must be one hour")
    if (
        not (feed.available_at_utc - feed.source_hour_end_utc)
        .eq(pd.Timedelta(minutes=latency_min))
        .all()
    ):
        raise ValueError(
            "Operations feed availability disagrees with its declared latency"
        )
    eligible = feed.feed_eligible.fillna(False).astype(bool)
    if not (
        feed.loc[eligible, "coverage_status"].eq("complete_for_source_scope").all()
        and feed.loc[eligible, "n_unresolved"].eq(0).all()
        and feed.loc[eligible, "reporting_carrier_touchdowns"].notna().all()
        and feed.loc[~eligible, "reporting_carrier_touchdowns"].isna().all()
    ):
        raise ValueError("Operations feed eligibility disagrees with coverage")


def request_features(requests, feed, max_age_min=120):
    if max_age_min < 0:
        raise ValueError("Operations freshness must be nonnegative")
    if requests.prediction_id.duplicated().any():
        raise ValueError("Duplicate request prediction_id")
    outputs = []
    for airport, rows in requests.groupby("airport_icao", sort=False):
        source = feed.loc[feed.airport_icao.eq(airport)].drop(
            columns=["airport_icao", "data_mode", "availability_basis"]
        )
        left = rows.sort_values("as_of_utc")
        if source.empty:
            joined = left.copy()
            for name in source.columns:
                joined[name] = pd.NaT if name.endswith("_utc") else pd.NA
        else:
            joined = pd.merge_asof(
                left,
                source.sort_values("available_at_utc"),
                left_on="as_of_utc",
                right_on="available_at_utc",
                direction="backward",
                allow_exact_matches=True,
            )
        for name in [
            "source_hour_start_utc",
            "source_hour_end_utc",
            "available_at_utc",
        ]:
            joined[name] = pd.to_datetime(joined[name], utc=True)
        age = (joined.as_of_utc - joined.source_hour_end_utc).dt.total_seconds() / 60
        status = pd.Series("available", index=joined.index)
        status.loc[joined.source_hour_end_utc.isna()] = "missing"
        status.loc[joined.coverage_status.eq("partial").fillna(False)] = "partial"
        status.loc[joined.coverage_status.eq("missing").fillna(False)] = "missing"
        status.loc[status.eq("available") & age.gt(max_age_min)] = "stale"
        status.loc[
            status.eq("available") & ~joined.feed_eligible.fillna(False).astype(bool)
        ] = "missing"
        joined["ops_arrivals_last_complete"] = (
            pd.to_numeric(joined.reporting_carrier_touchdowns, errors="coerce")
            .astype("float64")
            .where(status.eq("available"))
        )
        joined["ops_source_age_min"] = age.astype("float64")
        joined["ops_status"] = status
        joined["availability_basis"] = "simulated"
        joined = joined.rename(columns={"available_at_utc": "source_available_at_utc"})
        outputs.append(joined[SCHEMA.names])
    if not outputs:
        return pd.DataFrame(columns=SCHEMA.names)
    return pd.concat(outputs, ignore_index=True)


def build(processed, max_age_min=120, batch_size=100_000):
    processed = Path(processed)
    requests_path = processed / "prediction_requests.parquet"
    feed_path = processed / "operational_feed.parquet"
    manifests = [
        json.loads(p.with_suffix(".manifest.json").read_text())
        for p in [requests_path, feed_path]
    ]
    req_manifest, feed_manifest = manifests
    for path, manifest in zip([requests_path, feed_path], manifests):
        if sha256(path) != manifest["parquet_sha256"]:
            raise ValueError(f"Parquet hash disagrees with manifest: {path}")
    if (
        req_manifest["data_mode"] not in {"real", "fixture"}
        or req_manifest["data_mode"] != feed_manifest["data_mode"]
        or req_manifest["source_flights_sha256"]
        != feed_manifest["source_flights_sha256"]
    ):
        raise ValueError("Requests and feed must use the same source and data mode")
    if (
        feed_manifest["availability_basis"] != "simulated"
        or feed_manifest["latency_min"] != 10
    ):
        raise ValueError(
            "This provisional policy requires the simulated 10-minute feed"
        )
    feed = pq.read_table(feed_path, columns=FEED_COLUMNS).to_pandas()
    if (
        len(feed) != feed_manifest["rows"]
        or not feed.data_mode.eq(req_manifest["data_mode"]).all()
    ):
        raise ValueError("Feed rows or data mode disagree with manifest")
    validate_feed(feed, feed_manifest["latency_min"])
    output = processed / "operations_features.parquet"
    tmp = output.with_name(".operations_features.parquet.tmp")
    rows, counts = 0, collections.Counter()
    with pq.ParquetWriter(tmp, SCHEMA) as writer:
        for batch in pq.ParquetFile(requests_path).iter_batches(
            batch_size=batch_size, columns=REQUEST_COLUMNS
        ):
            requests = batch.to_pandas()
            if not requests.data_mode.eq(req_manifest["data_mode"]).all():
                raise ValueError("Request data mode disagrees with manifest")
            features = request_features(requests, feed, max_age_min)
            writer.write_table(
                pa.Table.from_pandas(features, schema=SCHEMA, preserve_index=False)
            )
            rows += len(features)
            counts.update(features.ops_status.value_counts().to_dict())
    if rows != req_manifest["rows"]:
        raise ValueError("Operations feature row count disagrees with requests")
    tmp.replace(output)
    manifest = {
        "schema_version": "1.0.0",
        "producer": VERSION,
        "data_mode": req_manifest["data_mode"],
        "rows": rows,
        "parquet_sha256": sha256(output),
        "source_requests_sha256": req_manifest["parquet_sha256"],
        "source_feed_sha256": feed_manifest["parquet_sha256"],
        "source_flights_sha256": req_manifest["source_flights_sha256"],
        "policy_status": "provisional; WP-D5 remains pending",
        "availability_basis": "simulated",
        "latency_min": 10,
        "max_source_age_min": max_age_min,
        "status_counts": dict(counts),
        "features": {
            "ops_arrivals_last_complete": {
                "type": "float64",
                "unit": "arrivals/hour",
                "source": "operational_feed",
                "transform": "most recent released source hour",
                "missing": "null for partial, missing or stale source",
            },
            "ops_source_age_min": {
                "type": "float64",
                "unit": "minutes",
                "source": "operational_feed",
                "transform": "as_of minus source hour end",
                "missing": "null if no source",
            },
        },
        "selection": "latest published source hour, including partial or missing rows; do not fall back to an older hour",
        "model_integration": "optional sidecar; join on prediction_id after WP-D5 is accepted",
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_tmp = manifest_path.with_name(".operations_features.manifest.json.tmp")
    manifest_tmp.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_tmp.replace(manifest_path)
    print(
        json.dumps(
            {
                "rows": rows,
                "status_counts": dict(counts),
                "data_mode": manifest["data_mode"],
            }
        )
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument("--max-age-min", type=int, default=120)
    args = parser.parse_args()
    build(args.processed, args.max_age_min)
