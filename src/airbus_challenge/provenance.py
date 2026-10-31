"""Trace one prediction end to end, for docs/FEATURE_PROVENANCE.md.

uv run python -m airbus_challenge.provenance [prediction_id]
The last section reads realised outcomes and is hindsight only.
"""

import sys
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

from airbus_challenge import registry

P = Path("data/processed")
DEFAULT = "cab921e6a2cd0702afe2d4e9270f7a4496f4e3a0737271d479acad694c9ab82f"
SHOW = ["metar_crosswind_kt", "taf_ts_prevailing", "taf_age_min", "sched_arr_h0"]


def row(path, flt, columns=None) -> pd.DataFrame:
    return ds.dataset(path).to_table(columns=columns, filter=flt).to_pandas()


def trace(pid: str) -> None:
    snap = row(P / "feature_snapshots.parquet", ds.field("prediction_id") == pid).iloc[
        0
    ]
    print(f"prediction_id {pid}\n  task={snap.task} airport={snap.airport_icao} as_of={snap.as_of_utc} "
          f"target={snap.target_start_utc} h={snap.horizon_h}")  # fmt: skip
    print(
        f"  snapshot_key={snap.snapshot_key} status={snap.status} reasons={list(snap.reason_codes)}"
    )
    lin = row(
        P / "feature_lineage.parquet", ds.field("snapshot_key") == snap.snapshot_key
    )
    for _, r in lin.iterrows():
        print(
            f"  lineage {r.feature_group}: {r.source_ref} available {r.contributing_available_at_utc}"
        )
    mid = lin.loc[lin.feature_group == "metar_latest", "source_record_id"].iloc[0]
    m = row(
        P / "weather_observations.parquet", ds.field("source_record_id") == mid
    ).iloc[0]
    print(
        f"  METAR observed {m.observed_at_utc} available {m.available_at_utc} age {snap.metar_age_min:.0f} min"
    )
    print(f"    {m.raw_metar}")
    bid = lin.loc[lin.feature_group == "taf", "source_ref"].iloc[0].split("#")[0]
    segs = row(P / "weather_forecasts.parquet", ds.field("bulletin_id") == bid)
    print(f"  TAF {bid} issued {segs.issued_at_utc.iloc[0]} available {segs.available_at_utc.iloc[0]} "
          f"age {snap.taf_age_min:.0f} min")  # fmt: skip
    used = set(lin.loc[lin.feature_group == "taf", "source_ref"].str.split("#").str[1])
    for _, s in segs.iterrows():
        mark = "*" if s.segment_id in used else " "
        print(
            f"   {mark} {s.segment_id} {s.forecast_type:<10} {s.valid_from_utc:%d %H:%MZ}-{s.valid_to_utc:%d %H:%MZ} {s.raw_group}"
        )
    dem = row(P / "demand_features.parquet", ds.field("prediction_id") == pid).iloc[0]
    print("  features and registry entries:")
    reg = {f.name: f for f in registry.build()}
    for name in SHOW:
        f = reg[name]
        value = dem[name] if f.table == registry.DEMAND_TABLE else snap[name]
        print(
            f"    {name} = {value} [{f.unit}; {f.dtype}; {f.table}; missing: {f.missing}; {f.serving}]"
        )
    pred = row(
        Path("artifacts/lgbm_throughput_dev/predictions.parquet"),
        ds.field("prediction_id") == pid,
    )
    for _, p in pred.iterrows():
        print(
            f"  prediction {p.model_version}: {p.estimate:.1f} {p.unit} (p10 {p.p10:.1f}, p90 {p.p90:.1f}) status {p.status}"
        )
    hourly = row(P / "airport_hourly.parquet",
                 (ds.field("airport_icao") == snap.airport_icao) & (ds.field("hour_start_utc") == snap.target_start_utc),
                 ["scheduled_arrivals", "reporting_carrier_touchdowns"]).iloc[0]  # fmt: skip
    print(f"  HINDSIGHT (not known at T): realised touchdowns {hourly.reporting_carrier_touchdowns}, "
          f"scheduled {hourly.scheduled_arrivals}")  # fmt: skip


if __name__ == "__main__":
    trace(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
