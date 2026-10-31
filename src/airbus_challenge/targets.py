import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from airbus_challenge.download import sha256
from airbus_challenge.requests import bounds

FLIGHTS = Path("data/processed/flights.parquet")
REQUESTS = Path("data/processed/prediction_requests.parquet")
HOURLY = Path("data/processed/airport_hourly.parquet")
LABELS = Path("data/labels/labels.parquet")
VERSION = "0.1.0"
METRICS = {
    "scheduled_departures": (
        "origin_icao",
        "scheduled_dep_utc",
        "raw_CRSDepTime",
        "origin_timezone",
    ),
    "scheduled_arrivals": (
        "dest_icao",
        "scheduled_arr_utc",
        "raw_CRSArrTime",
        "dest_timezone",
    ),
    "reporting_carrier_takeoffs": (
        "origin_icao",
        "wheels_off_utc",
        "raw_WheelsOff",
        "origin_timezone",
    ),
    "reporting_carrier_touchdowns": (
        "dest_icao",
        "wheels_on_utc",
        "raw_WheelsOn",
        "dest_timezone",
    ),
}
DEP_REASONS = ("scheduled_dep_", "duplicate_flight_key")
ACTUAL_DEP_REASONS = DEP_REASONS + ("actual_dep_",)
REASONS = {
    "scheduled_departures": DEP_REASONS,
    "scheduled_arrivals": DEP_REASONS + ("scheduled_arr_", "CRSElapsedTime_negative"),
    "reporting_carrier_takeoffs": ACTUAL_DEP_REASONS
    + (
        "wheels_off_",
        "TaxiOut_negative",
        "movement_order_invalid",
        "cancellation_status_unknown",
    ),
    "reporting_carrier_touchdowns": ACTUAL_DEP_REASONS
    + (
        "wheels_on_",
        "actual_arr_",
        "ActualElapsedTime_negative",
        "TaxiIn_negative",
        "movement_order_invalid",
        "cancellation_status_unknown",
        "diversion_status_unknown",
        "arrival_path_unresolved",
    ),
}
LABEL_SCHEMA = pa.schema(
    [
        ("prediction_id", pa.string()),
        ("target_kind", pa.string()),
        ("y_true", pa.float64()),
        ("eligible", pa.bool_()),
        ("exclusion_reason", pa.string()),
        ("outcome_available_at_utc", pa.timestamp("us", tz="UTC")),
        ("availability_basis", pa.string()),
        ("label_source", pa.string()),
        ("label_version", pa.string()),
        ("unit", pa.string()),
    ]
)


def invalid_flags(flags, prefixes):
    return flags.map(lambda fs: any(f.startswith(prefixes) for f in fs))


def uncertain_hours(rows, time, clock, zone, grid):
    from airbus_challenge.clean import clock_minutes

    counts = pd.Series(0, index=grid, dtype="int32")
    for r in rows.to_dict(orient="records"):
        event = r[time]
        affected = set()
        if pd.isna(event):
            # P12 fallback: the full local departure service date, plus any resolved schedule hour.
            day = pd.Timestamp(r["source_flight_date"])
            start = day.tz_localize(r[zone]).tz_convert("UTC")
            end = (day + pd.Timedelta(days=1)).tz_localize(r[zone]).tz_convert("UTC")
            affected.update(
                pd.date_range(start.floor("h"), end, freq="h", inclusive="left")
            )
            if pd.notna(r["scheduled_arr_utc"]):
                affected.add(r["scheduled_arr_utc"].floor("h"))
        else:
            affected.add(event.floor("h"))
            minutes = clock_minutes(pd.Series([r[clock]])).iloc[0]
            local = event.tz_convert(r[zone]).tz_localize(None).normalize()
            candidates = []
            if pd.notna(minutes):
                for day in [-1, 0, 1]:
                    naive = local + pd.Timedelta(days=day, minutes=minutes % 1440)
                    for fold in [True, False]:
                        candidate = naive.tz_localize(
                            r[zone], ambiguous=fold, nonexistent="NaT"
                        )
                        if pd.notna(candidate):
                            candidates.append(candidate.tz_convert("UTC"))
            if candidates:
                nearest = min(candidates, key=lambda t: abs(t - event))
                # Both independently supported clock/duration paths bound the possible hour interval.
                lo, hi = sorted([event.floor("h"), nearest.floor("h")])
                affected.update(pd.date_range(lo, hi, freq="h"))
            else:
                day = event.tz_convert(r[zone]).date()
                affected.update(t for t in grid if t.tz_convert(r[zone]).date() == day)
        ix = counts.index.intersection(pd.DatetimeIndex(list(affected)))
        counts.loc[ix] += 1
    return counts


def airport_hours(flights, icao, start, end, snapshot, complete=True):
    grid = pd.date_range(start, end, freq="h", inclusive="left")
    out = pd.DataFrame({"hour_start_utc": grid})
    out["airport_icao"] = icao
    out["hour_end_utc"] = out.hour_start_utc + pd.Timedelta(hours=1)
    out["source_snapshot_id"] = snapshot
    reached = pd.to_numeric(flights.raw_DivReachedDest, errors="coerce").eq(1)
    for metric, (endpoint, time, clock, zone) in METRICS.items():
        selected = flights[flights[endpoint] == icao]
        if metric.startswith("reporting_carrier"):
            expected = selected.cancelled.ne(True).fillna(True)
            if metric.endswith("touchdowns"):
                expected &= (
                    selected.diverted.ne(True).fillna(True)
                    | reached.loc[selected.index]
                )
            selected = selected[expected]
        invalid = (
            invalid_flags(selected.quality_flags, REASONS[metric])
            | selected[time].isna()
        )
        if metric.endswith("touchdowns"):
            invalid |= selected.timestamp_status.eq("quarantined")
        good = selected[~invalid]
        count = good[time].dt.floor("h").value_counts().reindex(grid, fill_value=0)
        uncertain = uncertain_hours(selected[invalid], time, clock, zone, grid)
        out[metric] = pd.Series(count.to_numpy(), dtype="Int32").mask(
            pd.Series(not complete, index=out.index)
        )
        out[f"{metric}_n_unresolved"] = pd.Series(
            uncertain.to_numpy(), dtype="Int32"
        ).mask(pd.Series(not complete, index=out.index))
        out[f"{metric}_coverage_status"] = (
            pd.Series("complete_for_source_scope", index=out.index)
            .mask(uncertain.to_numpy() > 0, "partial")
            .mask(pd.Series(not complete, index=out.index), "missing")
        )
        if metric.endswith("touchdowns"):
            out["n_resolved"] = out[metric]
            out["n_unresolved"] = out[f"{metric}_n_unresolved"]
            denominator = out.n_resolved + out.n_unresolved
            out["coverage_fraction"] = (
                (out.n_resolved / denominator)
                .astype("float64")
                .where(denominator > 0, 1.0)
                .where(pd.Series(complete, index=out.index))
            )
            out["coverage_status"] = out[f"{metric}_coverage_status"]
            out["throughput_label_eligible"] = out.coverage_status.ne("missing") & (
                out.n_unresolved / denominator
            ).fillna(0).le(0.05)
            out["throughput_exclusion_reason"] = (
                pd.Series(pd.NA, index=out.index, dtype="string")
                .mask(
                    ~out.throughput_label_eligible,
                    "unresolved_arrival_fraction_gt_0.05",
                )
                .mask(out.coverage_status.eq("missing"), "missing_source_month")
            )
            out[metric] = out[metric].where(out.throughput_label_eligible)
            out["exclusion_reason"] = out.throughput_exclusion_reason
            month = selected.source_flight_date.str[:7]
            rates = invalid.groupby(month).mean()
            out["arrival_quarantine_fraction_month"] = (
                out.hour_start_utc.dt.strftime("%Y-%m")
                .map(rates)
                .fillna(0)
                .astype("float64")
            )
            out["month_degraded"] = out.arrival_quarantine_fraction_month.gt(0.01)
    out["official_aar"] = pd.Series(float("nan"), index=out.index, dtype="float64")
    out["aar_source"] = pd.Series(pd.NA, index=out.index, dtype="string")
    out["aar_aggregation_version"] = pd.Series(pd.NA, index=out.index, dtype="string")
    out["schedule_knowledge_basis"] = (
        "retrospective_final_archive; historical schedule availability unknown"
    )
    return out


def label_rows(requests, outcomes, hourly, threshold=45):
    frames = []
    for task, req in requests.groupby("task", sort=False):
        if task == "severe_delay":
            joined = req.merge(
                outcomes,
                on="flight_id",
                how="left",
                validate="many_to_one",
                indicator=True,
            )
            missing = joined["_merge"].eq("left_only")
            for target in ["departure_delay_gt45", "cancellation"]:
                df = pd.DataFrame(
                    {"prediction_id": joined.prediction_id, "target_kind": target}
                )
                reason = pd.Series(pd.NA, index=joined.index, dtype="string")
                if target == "departure_delay_gt45":
                    reason.loc[joined.dep_delay_min.isna()] = "missing_departure_delay"
                    reason.loc[joined.scheduled_dep_utc.isna()] = (
                        "timestamp_quarantined"
                    )
                    reason.loc[joined.cancelled.eq(True).fillna(False)] = "cancelled"
                    reason.loc[joined.cancelled.isna()] = "unknown_cancellation_status"
                    value = joined.dep_delay_min.gt(threshold).astype("float64")
                else:
                    reason.loc[joined.cancelled.isna()] = "unknown_cancellation_status"
                    value = joined.cancelled.astype("Float64").astype("float64")
                reason.loc[missing] = "missing_flight_outcome"
                df["eligible"] = reason.isna()
                df["y_true"] = value.where(df.eligible)
                df["exclusion_reason"] = reason
                df["unit"] = "binary"
                frames.append(df)
        elif task == "throughput":
            joined = req.merge(
                hourly,
                left_on=["airport_icao", "target_start_utc"],
                right_on=["airport_icao", "hour_start_utc"],
                how="left",
                validate="many_to_one",
            )
            df = pd.DataFrame(
                {
                    "prediction_id": joined.prediction_id,
                    "target_kind": "reporting_carrier_touchdowns",
                }
            )
            df["y_true"] = joined.reporting_carrier_touchdowns.astype("Float64").astype(
                "float64"
            )
            df["eligible"] = (
                joined.throughput_label_eligible.fillna(False) & df.y_true.notna()
            )
            df["y_true"] = df.y_true.where(df.eligible)
            df["exclusion_reason"] = joined.throughput_exclusion_reason.fillna(
                "missing_airport_hour"
            ).mask(df.eligible)
            df["unit"] = "touchdowns/hour"
            frames.append(df)
        else:
            raise ValueError(f"Unknown prediction task: {task}")
    labels = pd.concat(frames, ignore_index=True)
    # Final BTS publication times are not evidenced. Event time is not archive availability.
    labels["outcome_available_at_utc"] = pd.Series(
        pd.NaT, index=labels.index, dtype="datetime64[us, UTC]"
    )
    labels["availability_basis"] = "unknown"
    labels["label_source"] = "BTS On-Time Reporting Carrier"
    labels["label_version"] = VERSION
    return labels[LABEL_SCHEMA.names]


def write_manifest(path, rows, sources, extra):
    manifest = {
        "schema_version": VERSION,
        "producer": f"airbus_challenge.targets/{VERSION}",
        "data_mode": sources["data_mode"],
        "rows": rows,
        "parquet_sha256": sha256(path),
        "source_flights_sha256": sources["parquet_sha256"],
        "sources": sources["sources"],
        **extra,
    }
    target = path.with_suffix(".manifest.json")
    tmp = target.with_name("." + target.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, default=str))
    tmp.replace(target)


def split_name(times, experiment):
    result = pd.Series("lookback", index=times.index, dtype="string")
    for name, window in experiment["splits"].items():
        result.loc[
            times.ge(pd.Timestamp(window["start"], tz="UTC"))
            & times.lt(pd.Timestamp(window["end"], tz="UTC"))
        ] = name
    return result


def exclusion_audit(hourly, flights, experiment, weather):
    # Retrospective weather slices only; they never participate in requests or features.
    weather = weather.copy()
    weather["hour_start_utc"] = weather.observed_at_utc.dt.floor("h")
    weather["thunderstorm"] = weather.wx_codes.map(
        lambda codes: any("TS" in code for code in codes)
    )
    weather["ifr"] = weather.ceiling_ft.lt(1000) | weather.visibility_sm.lt(3)
    wx = (
        weather.groupby(["airport_icao", "hour_start_utc"])[["thunderstorm", "ifr"]]
        .any()
        .reset_index()
    )
    wx["weather_condition"] = "other"
    wx.loc[wx.thunderstorm, "weather_condition"] = "thunderstorm"
    wx.loc[wx.ifr, "weather_condition"] = "ifr"
    wx.loc[wx.thunderstorm & wx.ifr, "weather_condition"] = "thunderstorm_and_ifr"
    wx = wx[["airport_icao", "hour_start_utc", "weather_condition"]]
    hours = hourly.merge(
        wx, on=["airport_icao", "hour_start_utc"], how="left", validate="one_to_one"
    )
    hours["weather_condition"] = hours.weather_condition.fillna("missing_weather")
    hours["month"] = hours.hour_start_utc.dt.strftime("%Y-%m")
    hours["split"] = split_name(hours.hour_start_utc, experiment)
    hours["excluded"] = ~hours.throughput_label_eligible
    ratio = hours.n_unresolved / (hours.n_resolved + hours.n_unresolved)
    thresholds = []
    for threshold in [0, 0.05, 0.10]:
        excluded = hours.coverage_status.eq("missing") | ratio.fillna(0).gt(threshold)
        for icao, group in hours.assign(excluded=excluded).groupby("airport_icao"):
            thresholds.append(
                {
                    "airport_icao": icao,
                    "threshold": threshold,
                    "excluded_hours": int(group.excluded.sum()),
                    "hours": len(group),
                }
            )
    group_cols = ["airport_icao", "month", "split", "weather_condition"]
    hour_summary = (
        hours.groupby(group_cols)
        .agg(hours=("excluded", "size"), excluded=("excluded", "sum"))
        .reset_index()
    )
    dep = flights[flights.origin_icao.isin(hourly.airport_icao.unique())].copy()
    dep["airport_icao"] = dep.origin_icao
    dep["timestamp_surrogate"] = dep.scheduled_dep_utc.isna()
    dep["target"] = dep.scheduled_dep_utc.fillna(
        pd.to_datetime(dep.source_flight_date, utc=True)
    )
    dep["hour_start_utc"] = dep.target.dt.floor("h")
    dep["month"] = dep.target.dt.strftime("%Y-%m")
    dep["split"] = split_name(dep.target, experiment)
    dep["exclusion_reason"] = pd.Series(pd.NA, index=dep.index, dtype="string")
    dep.loc[dep.dep_delay_min.isna(), "exclusion_reason"] = "missing_departure_delay"
    dep.loc[dep.scheduled_dep_utc.isna(), "exclusion_reason"] = "timestamp_quarantined"
    dep.loc[dep.cancelled.eq(True).fillna(False), "exclusion_reason"] = "cancelled"
    dep.loc[dep.cancelled.isna(), "exclusion_reason"] = "unknown_cancellation_status"
    dep["excluded"] = dep.exclusion_reason.notna()
    dep = dep.merge(
        wx, on=["airport_icao", "hour_start_utc"], how="left", validate="many_to_one"
    )
    dep["weather_condition"] = dep.weather_condition.fillna("missing_weather").mask(
        dep.timestamp_surrogate, "unresolved_target_time"
    )
    flight_summary = (
        dep.groupby(group_cols)
        .agg(flights=("excluded", "size"), excluded=("excluded", "sum"))
        .reset_index()
    )
    exclusions = (
        dep[dep.excluded]
        .groupby([*group_cols, "exclusion_reason"])
        .size()
        .rename("flights")
        .reset_index()
    )
    rates = (
        hours.groupby("weather_condition").excluded.agg(["size", "mean"]).reset_index()
    )
    bad = hours.weather_condition.isin(["thunderstorm", "ifr", "thunderstorm_and_ifr"])
    bad_rate = float(hours.loc[bad, "excluded"].mean()) if bad.any() else None
    other = hours.weather_condition.eq("other")
    clear_rate = float(hours.loc[other, "excluded"].mean()) if other.any() else None
    return {
        "policy": "P12 PROPOSED; source-date surrogate only for unresolved-flight split counts; weather slices use target-hour METAR regardless of historical availability",
        "excluded_hours": hour_summary.to_dict(orient="records"),
        "excluded_flights": flight_summary.to_dict(orient="records"),
        "flight_exclusion_reasons": exclusions.to_dict(orient="records"),
        "threshold_sensitivity": thresholds,
        "weather_exclusion_rates": rates.to_dict(orient="records"),
        "bad_weather_exclusion_rate": bad_rate,
        "other_weather_exclusion_rate": clear_rate,
        "bad_weather_concentration_flag": bad_rate is not None
        and clear_rate is not None
        and bad_rate > clear_rate,
        "unrequested_timestamp_quarantined_flights": dep.loc[
            dep.timestamp_surrogate,
            ["flight_id", "airport_icao", "month", "split", "exclusion_reason"],
        ].to_dict(orient="records"),
    }


def build():
    config = yaml.safe_load(Path("configs/airports.yaml").read_text())
    experiment = yaml.safe_load(Path("configs/experiment.yaml").read_text())
    manifest = json.loads(FLIGHTS.with_suffix(".manifest.json").read_text())
    request_manifest = json.loads(REQUESTS.with_suffix(".manifest.json").read_text())
    if (
        sha256(FLIGHTS) != manifest["parquet_sha256"]
        or sha256(REQUESTS) != request_manifest["parquet_sha256"]
    ):
        raise ValueError("Input Parquet hash disagrees with manifest")
    if request_manifest["source_flights_sha256"] != manifest["parquet_sha256"]:
        raise ValueError("Requests and targets must use the same flight archive")
    start, end = bounds(experiment)
    # Include the two-day lookback for the first issue-time operational baselines.
    start -= pd.Timedelta(days=2)
    columns = [
        "flight_id",
        "origin_icao",
        "dest_icao",
        "source_flight_date",
        "origin_timezone",
        "dest_timezone",
        "scheduled_dep_utc",
        "scheduled_arr_utc",
        "wheels_off_utc",
        "wheels_on_utc",
        "raw_CRSDepTime",
        "raw_CRSArrTime",
        "raw_WheelsOff",
        "raw_WheelsOn",
        "raw_DivReachedDest",
        "cancelled",
        "diverted",
        "timestamp_status",
        "dep_delay_min",
        "quality_flags",
    ]
    flights = pd.read_parquet(FLIGHTS, columns=columns)
    frames = [
        airport_hours(flights, icao, start, end, manifest["parquet_sha256"])
        for icao in config["airports"]
    ]
    hourly = pd.concat(frames, ignore_index=True)
    HOURLY.parent.mkdir(parents=True, exist_ok=True)
    tmp = HOURLY.with_name(".airport_hourly.parquet.tmp")
    hourly.to_parquet(tmp, index=False)
    tmp.replace(HOURLY)
    write_manifest(
        HOURLY,
        len(hourly),
        manifest,
        {
            "label_name": "arrival throughput (AAR proxy)",
            "coverage_status": hourly.coverage_status.value_counts().to_dict(),
            "coverage_policy": "P12: n_resolved counts resolved arrivals; each unresolved arrival contributes once to every plausible UTC hour; unbounded dates use the full local service date plus resolved scheduled arrival hour; exclude labels only above 5% unresolved; source-month quarantine fraction above 1% flags degraded",
            "coverage_policy_status": "PROPOSED",
            "arrival_month_quality": hourly.assign(
                month=hourly.hour_start_utc.dt.strftime("%Y-%m")
            )
            .groupby(["airport_icao", "month"], as_index=False)
            .agg(
                quarantine_fraction=("arrival_quarantine_fraction_month", "max"),
                degraded=("month_degraded", "any"),
                excluded_hours=("throughput_label_eligible", lambda s: int((~s).sum())),
            )
            .to_dict(orient="records"),
            "source_scope": "BTS reporting-carrier flights with departure service months in the source manifest; excludes cancelled movements; diverted arrivals only when DivReachedDest=1",
            "capacity_ratio_status": "deferred pending P10 approval",
            "min_time_utc": start,
            "max_time_exclusive_utc": end,
            "counts_by_airport": hourly.groupby("airport_icao")[
                [*METRICS, "n_resolved", "n_unresolved"]
            ]
            .sum()
            .to_dict(),
            "null_counts": hourly[list(METRICS)].isna().sum().to_dict(),
        },
    )
    weather = pd.read_parquet(
        "data/processed/weather_observations.parquet",
        columns=[
            "airport_icao",
            "observed_at_utc",
            "wx_codes",
            "ceiling_ft",
            "visibility_sm",
        ],
    )
    bias = exclusion_audit(hourly, flights, experiment, weather)
    outcomes = flights[["flight_id", "dep_delay_min", "cancelled", "scheduled_dep_utc"]]
    del flights
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    tmp = LABELS.with_name(".labels.parquet.tmp")
    summaries = []
    rows = 0
    with pq.ParquetWriter(tmp, LABEL_SCHEMA) as writer:
        for batch in pq.ParquetFile(REQUESTS).iter_batches(
            batch_size=100_000,
            columns=[
                "prediction_id",
                "task",
                "airport_icao",
                "flight_id",
                "target_start_utc",
            ],
        ):
            labels = label_rows(
                batch.to_pandas(),
                outcomes,
                hourly,
                experiment["targets"]["severe_delay_threshold_min"],
            )
            writer.write_table(
                pa.Table.from_pandas(labels, schema=LABEL_SCHEMA, preserve_index=False)
            )
            rows += len(labels)
            summaries.append(
                labels.groupby(["target_kind", "eligible"], dropna=False)
                .size()
                .rename("rows")
                .reset_index()
            )
    tmp.replace(LABELS)
    summary = (
        pd.concat(summaries)
        .groupby(["target_kind", "eligible"], as_index=False)["rows"]
        .sum()
        .to_dict(orient="records")
    )
    write_manifest(
        LABELS,
        rows,
        manifest,
        {
            "source_requests_sha256": request_manifest["parquet_sha256"],
            "summary": summary,
            "exclusion_audit": bias,
            "bias_weather_sha256": sha256(
                Path("data/processed/weather_observations.parquet")
            ),
            "availability_policy": "unknown BTS historical publication time; explicit simulated release policy required before enforcing model-fit availability cutoffs",
            "threshold_min": experiment["targets"]["severe_delay_threshold_min"],
            "threshold_operator": "strictly greater than",
            "min_target_utc": start + pd.Timedelta(days=2),
            "max_target_exclusive_utc": end,
        },
    )
    print(HOURLY, len(hourly), hourly.coverage_status.value_counts().to_dict())
    print(LABELS, rows, summary)
    return hourly, summary


if __name__ == "__main__":
    build()
