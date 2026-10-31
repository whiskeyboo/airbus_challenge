"""Schedule demand features per prediction request, under the retrospective schedule assumption.

Reads only explicit projections: the request columns of prediction_requests, its manifest's
source list, the schedule columns of airport_hourly and configs/. No outcome column or table
(realised movements, ratios, label or flight-archive tables) is read. Lagged operations are out of scope.
"""

import collections
import hashlib
import json
import re
import resource
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import yaml

PROCESSED = Path("data/processed")
REQUESTS = "prediction_requests.parquet"
HOURLY = "airport_hourly.parquet"
OUTPUT = "demand_features.parquet"
DEMAND_VERSION = "schedule-demand/0.1.0"
SCHEDULE_KNOWLEDGE_BASIS = (
    "retrospective final archive; schedule assumed known at every issue time; "
    "not evidenced live availability"
)
HOUR = pd.Timedelta(hours=1)
REQUEST_COLUMNS = [
    "prediction_id",
    "task",
    "airport_icao",
    "flight_id",
    "as_of_utc",
    "target_start_utc",
    "target_end_utc",
    "horizon_h",
    "cohort_version",
    "data_mode",
]
# Verified in targets.airport_hours: these come from scheduled_dep/arr_utc, CRS clocks, schedule
# quality flags (scheduled_dep_*, scheduled_arr_*, CRSElapsedTime_negative, duplicate key of
# date|carrier|number|origin|dest|CRSDepTime) and source coverage. No final-outcome field of
# the flight archive is used for them.
HOURLY_COLUMNS = [
    "airport_icao",
    "hour_start_utc",
    "scheduled_arrivals",
    "scheduled_departures",
    "scheduled_arrivals_n_unresolved",
    "scheduled_departures_n_unresolved",
    "scheduled_arrivals_coverage_status",
    "scheduled_departures_coverage_status",
]
DIRECTIONS = {"arr": "scheduled_arrivals", "dep": "scheduled_departures"}
SOURCE = re.compile(r"bts/bts_(\d{4})_(\d{2})\.zip$")
_basis = "schedule counts, airport_hourly (retrospective schedule)"
FEATURES = {
    # name: (unit, source, transform, missing policy)
    **{
        f"sched_{d}_{w}": (
            "flights/hour",
            _basis,
            f"scheduled {name.split('_')[1]} in the {label} (UTC)",
            "null if the hour's schedule source is missing",
        )
        for d, name in DIRECTIONS.items()
        for w, label in (
            ("h0", "anchor hour"),
            ("hm1", "hour before the anchor"),
            ("hp1", "hour after the anchor"),
        )
    },
    **{
        f"sched_{d}_3h": (
            "flights/3h",
            _basis,
            f"sum of sched_{d}_hm1, h0, hp1",
            "null if any of the three is null",
        )
        for d in DIRECTIONS
    },
    **{
        f"sched_{d}_unresolved_h0": (
            "flights",
            _basis,
            f"schedule rows with unresolved {DIRECTIONS[d]} hour that may fall in h0 (P12)",
            "null if the hour's schedule source is missing",
        )
        for d in DIRECTIONS
    },
    "sched_arr_2023_local_hour_mean": (
        "flights/hour",
        _basis,
        (
            "mean scheduled arrivals per airport and local hour over train-split hours (2023) "
            "with complete schedule coverage; fit on train only"
        ),
        "null if no complete train hour",
    ),
    "sched_arr_vs_2023_local_hour_mean": (
        "ratio",
        _basis,
        "sched_arr_h0 / sched_arr_2023_local_hour_mean",
        "null if either is null or the mean is 0",
    ),
}
REASONS = {
    "schedule_missing_anchor_hour": "Schedule source missing for the anchor hour; counts null",
    "schedule_missing_neighbour_hour": "Schedule source missing for h-1 or h+1",
    "schedule_unresolved_anchor_hour": "Some schedule rows have an unresolved hour (P12)",
    "schedule_normaliser_undefined": "No 2023 mean for this local hour, or it is 0",
}


def utc_scalar(t) -> pa.Scalar:
    return pa.scalar(pd.Timestamp(t), pa.timestamp("us", "UTC"))


def _read(path: Path, columns: list[str], filter=None) -> pd.DataFrame:
    return ds.dataset(path).to_table(columns=columns, filter=filter).to_pandas()


def source_months(manifest: dict) -> set[str]:
    months = {
        f"{m[1]}-{m[2]}" for s in manifest["sources"] if (m := SOURCE.search(s["key"]))
    }
    if not months:
        raise ValueError("request manifest lists no BTS source months")
    return months


def covered(
    hours: pd.DataFrame, airports: dict, months: set[str], direction: str
) -> pd.Series:
    """Departure service month(s) behind an hour's schedule count are all in the source scope.

    Departures need the local date's month; arrivals also the previous local day's month
    (overnight flights). The producer's own 'missing' coverage status also counts as missing.
    """
    zone = hours["airport_icao"].map(lambda a: airports[a]["timezone"])
    ok = pd.Series(True, index=hours.index)
    for icao in hours["airport_icao"].unique():
        rows = hours["airport_icao"] == icao
        local = hours.loc[rows, "hour_start_utc"].dt.tz_convert(zone[rows].iloc[0])
        days = [local] if direction == "dep" else [local, local - pd.Timedelta(days=1)]
        for day in days:
            ok[rows] &= day.dt.strftime("%Y-%m").isin(months).to_numpy()
    status = hours[f"{DIRECTIONS[direction]}_coverage_status"]
    return ok & status.ne("missing")


def hourly_features(
    hourly: pd.DataFrame, airports: dict, months: set[str], train: tuple
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Features per (airport_icao, anchor hour) on a complete grid, plus the train normaliser."""
    grids = []
    for icao, rows in hourly.groupby("airport_icao"):
        span = pd.date_range(
            rows.hour_start_utc.min() - HOUR,
            rows.hour_start_utc.max() + 2 * HOUR,
            freq="h",
        ).astype("datetime64[us, UTC]")
        grid = pd.DataFrame({"airport_icao": icao, "hour_start_utc": span})
        grids.append(
            grid.merge(rows, on=["airport_icao", "hour_start_utc"], how="left")
        )
    h = pd.concat(grids, ignore_index=True)
    for d, name in DIRECTIONS.items():
        h[f"{d}_status"] = h[f"{name}_coverage_status"].fillna("missing")
        h[f"{name}_coverage_status"] = h[f"{d}_status"]
        ok = covered(h, airports, months, d)
        h[f"sched_{d}_h0"] = h[name].astype("Float64").where(ok)
        h[f"sched_{d}_unresolved_h0"] = (
            h[f"{name}_n_unresolved"].astype("Float64").where(ok)
        )
        g = h.groupby("airport_icao")[f"sched_{d}_h0"]
        h[f"sched_{d}_hm1"] = g.shift(1)
        h[f"sched_{d}_hp1"] = g.shift(-1)
        h[f"sched_{d}_3h"] = (
            h[f"sched_{d}_hm1"] + h[f"sched_{d}_h0"] + h[f"sched_{d}_hp1"]
        )

    local_hour = pd.Series(index=h.index, dtype="int64")
    for icao, rows in h.groupby("airport_icao"):
        local_hour[rows.index] = rows.hour_start_utc.dt.tz_convert(
            airports[icao]["timezone"]
        ).dt.hour
    h["local_hour"] = local_hour
    start, end = train
    fit = h[
        h.hour_start_utc.ge(start)
        & h.hour_start_utc.lt(end)
        & h.sched_arr_h0.notna()
        & h.arr_status.eq("complete_for_source_scope")
    ]
    normaliser = (
        fit.groupby(["airport_icao", "local_hour"])["sched_arr_h0"]
        .agg(["mean", "size"])
        .rename(columns={"mean": "sched_arr_2023_local_hour_mean", "size": "fit_hours"})
        .reset_index()
    )
    h = h.merge(
        normaliser[["airport_icao", "local_hour", "sched_arr_2023_local_hour_mean"]],
        on=["airport_icao", "local_hour"],
        how="left",
    )
    mean = h["sched_arr_2023_local_hour_mean"].astype("Float64")
    h["sched_arr_2023_local_hour_mean"] = mean
    h["sched_arr_vs_2023_local_hour_mean"] = h["sched_arr_h0"] / mean.where(mean > 0)

    anchor_missing = h.sched_arr_h0.isna() | h.sched_dep_h0.isna()
    neighbour_missing = (
        h[["sched_arr_hm1", "sched_arr_hp1", "sched_dep_hm1", "sched_dep_hp1"]]
        .isna()
        .any(axis=1)
    )
    unresolved = (h.sched_arr_unresolved_h0.fillna(0) > 0) | (
        h.sched_dep_unresolved_h0.fillna(0) > 0
    )
    norm = h.sched_arr_vs_2023_local_hour_mean.isna() & ~anchor_missing
    flags = pd.DataFrame(
        {
            "schedule_missing_anchor_hour": anchor_missing,
            "schedule_missing_neighbour_hour": neighbour_missing & ~anchor_missing,
            "schedule_unresolved_anchor_hour": unresolved,
            "schedule_normaliser_undefined": norm,
        }
    ).astype(bool)
    h["reason_codes"] = [list(flags.columns[r]) for r in flags.to_numpy()]
    h["status"] = np.select(
        [anchor_missing, flags.any(axis=1)], ["missing", "partial"], "ok"
    )
    cols = ["airport_icao", "hour_start_utc", *FEATURES, "status", "reason_codes"]
    return h[cols].rename(columns={"hour_start_utc": "anchor_hour_utc"}), normaliser


def request_features(requests: pd.DataFrame, per_hour: pd.DataFrame) -> pd.DataFrame:
    """Join each request to its anchor hour: the target hour (throughput) or the scheduled
    departure hour at the departure airport (severe_delay)."""
    req = requests.assign(anchor_hour_utc=requests["target_start_utc"].dt.floor("h"))
    out = req.merge(
        per_hour,
        on=["airport_icao", "anchor_hour_utc"],
        how="left",
        validate="many_to_one",
    )
    lost = out["status"].isna()
    out.loc[lost, "status"] = "missing"
    out.loc[lost, "reason_codes"] = pd.Series(
        [["schedule_missing_anchor_hour"]] * lost.sum(), index=out.index[lost]
    )
    out["schedule_knowledge_basis"] = SCHEDULE_KNOWLEDGE_BASIS
    out["demand_version"] = DEMAND_VERSION
    floats = list(FEATURES)
    out[floats] = out[floats].astype("float64")
    return out


def peak_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / 1e6 if sys.platform == "darwin" else rss / 1e3


def build(root: Path = Path(".")) -> dict:
    t0 = time.time()
    processed = root / PROCESSED
    airports = yaml.safe_load((root / "configs/airports.yaml").read_text())["airports"]
    splits = yaml.safe_load((root / "configs/experiment.yaml").read_text())["splits"]
    train = tuple(pd.Timestamp(splits["train"][k], tz="UTC") for k in ("start", "end"))
    request_manifest = json.loads(
        (processed / REQUESTS).with_suffix(".manifest.json").read_text()
    )
    months = source_months(request_manifest)
    hourly = _read(processed / HOURLY, HOURLY_COLUMNS)
    per_hour, normaliser = hourly_features(hourly, airports, months, train)

    requests = ds.dataset(processed / REQUESTS)
    target = requests.to_table(columns=["target_start_utc"]).column(0).to_pandas()
    first, last = target.min(), target.max()
    out_path = processed / OUTPUT
    tmp = out_path.with_name(f".{OUTPUT}.tmp")
    writer, counts, reasons, status = (
        None,
        collections.Counter(),
        collections.Counter(),
        collections.Counter(),
    )
    nulls = collections.Counter()
    field = ds.field("target_start_utc")
    for m0 in pd.date_range(first.floor("D").replace(day=1), last, freq="MS"):
        m1 = m0 + pd.DateOffset(months=1)
        req = _read(
            processed / REQUESTS,
            REQUEST_COLUMNS,
            (field >= utc_scalar(m0)) & (field < utc_scalar(m1)),
        )
        if req.empty:
            continue
        out = request_features(req, per_hour).sort_values(
            ["task", "horizon_h", "prediction_id"]
        )
        counts.update(out.groupby(["task", "horizon_h"]).size().to_dict())
        status.update(out.groupby(["task", "status"]).size().to_dict())
        reasons.update(
            out[["task", "reason_codes"]]
            .explode("reason_codes")
            .dropna()
            .value_counts()
            .to_dict()
        )
        for task, rows in out.groupby("task"):
            for c in FEATURES:
                nulls[(task, c)] += int(rows[c].isna().sum())
        table = pa.Table.from_pandas(out, preserve_index=False)
        if writer is None:
            schema = table.schema
            schema = schema.set(
                schema.get_field_index("reason_codes"),
                pa.field("reason_codes", pa.list_(pa.string())),
            )
            writer = pq.ParquetWriter(tmp, schema)
        writer.write_table(table.cast(writer.schema))
    written = sum(counts.values())
    assert written == requests.count_rows(), "requests outside the monthly partitions"
    writer.close()
    tmp.replace(out_path)
    rows_by_task = collections.Counter()
    for (task, _), n in counts.items():
        rows_by_task[task] += n
    manifest = {
        "dataset": "demand_features",
        "demand_version": DEMAND_VERSION,
        "data_mode": request_manifest["data_mode"],
        "schedule_knowledge_basis": SCHEDULE_KNOWLEDGE_BASIS,
        "rows": written,
        "rows_by_task_horizon": {
            f"{t}|{h}": int(n) for (t, h), n in sorted(counts.items())
        },
        "status_by_task": {f"{t}|{s}": int(n) for (t, s), n in sorted(status.items())},
        "reason_codes_by_task": {
            f"{t}|{r}": int(n) for (t, r), n in sorted(reasons.items())
        },
        "null_rate_by_task": {
            f"{t}|{c}": round(n / rows_by_task[t], 6)
            for (t, c), n in sorted(nulls.items())
        },
        "features": {
            k: dict(zip(("unit", "source", "transform", "missing"), v))
            for k, v in FEATURES.items()
        },
        "reasons": REASONS,
        "anchor_hour": "floor(target_start_utc): target hour (throughput); scheduled departure "
        "hour at the departure airport (severe_delay)",
        "normaliser": {
            "fit": f"train split [{train[0].isoformat()}, {train[1].isoformat()}), complete coverage",
            "values": normaliser.to_dict(orient="records"),
        },
        "source_months": sorted(months),
        "inputs": {
            "prediction_requests": {
                "columns": REQUEST_COLUMNS,
                "parquet_sha256": request_manifest.get("parquet_sha256"),
            },
            "airport_hourly": {"columns": HOURLY_COLUMNS},
        },
        "output_sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
        "runtime_s": round(time.time() - t0, 1),
        "peak_rss_mb": round(peak_rss_mb(), 1),
    }
    mpath = out_path.with_suffix(".manifest.json")
    mtmp = mpath.with_name(f".{mpath.name}.tmp")
    mtmp.write_text(json.dumps(manifest, indent=2, default=str))
    mtmp.replace(mpath)
    return manifest


if __name__ == "__main__":
    m = build()
    print(
        json.dumps(
            {
                k: m[k]
                for k in (
                    "rows",
                    "rows_by_task_horizon",
                    "status_by_task",
                    "reason_codes_by_task",
                    "runtime_s",
                    "peak_rss_mb",
                )
            },
            indent=2,
        )
    )
