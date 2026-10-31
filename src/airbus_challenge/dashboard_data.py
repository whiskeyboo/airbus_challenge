"""Data loading and shaping for app/dashboard.py, kept free of Streamlit so it can be tested.

Forecast and evidence loaders never read outcome columns or files; only the replay-outcomes
loader does. Every parquet read goes through _read, so a test can check what each loader reads.
Nothing here computes evaluation metrics; the evaluation panel only displays metrics files.
"""

from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import yaml

HOUR = pd.Timedelta(hours=1)
HORIZONS = (3, 6, 9, 12)
WINDOW = pd.Timedelta(hours=13)  # T to the end of the T+12 target hour.
THROUGHPUT_LABEL = "arrival throughput (AAR proxy)"
SNAPSHOTS = "data/processed/feature_snapshots.parquet"
LINEAGE = "data/processed/feature_lineage.parquet"
OBSERVATIONS = "data/processed/weather_observations.parquet"
FORECASTS = "data/processed/weather_forecasts.parquet"
HOURLY = "data/processed/airport_hourly.parquet"
REQUESTS = "data/processed/prediction_requests.parquet"
LABELS = "data/labels/labels.parquet"
ARTIFACTS = "artifacts"
REPORTS = "reports"
# Outcome data: only load_replay_outcomes may read these.
OUTCOME_FILES = {LABELS, "data/processed/flights.parquet"}
OUTCOME_COLUMNS = {
    "reporting_carrier_touchdowns",
    "reporting_carrier_takeoffs",
    "throughput_over_clear_weather_p95",
    "official_aar",
    "y_true",
    "eligible",
    "exclusion_reason",
    "exclusion_detail",
    "throughput_label_eligible",
    "throughput_exclusion_reason",
}
SCHEDULE_COLUMNS = [
    "airport_icao",
    "hour_start_utc",
    "scheduled_arrivals",
    "scheduled_arrivals_coverage_status",
    "schedule_knowledge_basis",
]
REASONS = {
    "metar_stale": "Latest METAR available at T is over 3 h old; METAR features are blank.",
    "metar_unavailable": "No METAR was available in the 6 h before T.",
    "metar_cor_skipped": "A corrected METAR would have been latest, but its send time is "
    "unknown, so the previous report was used.",
    "taf_unavailable": "No TAF was available by T.",
    "taf_uncovered": "The TAF in force at T ends before this target hour.",
    "taf_conflict_fallback": "The newest TAF exists in two conflicting versions; the "
    "previous one was used.",
    "simulated_feed": "Uses realised arrivals from a past hour as if a live feed existed "
    "(BTS publishes months later).",
    "retrospective_schedule": "Uses the schedule as flown (BTS), which was only partly "
    "known at T.",
    "source_hour_incomplete": "The past hour this baseline copies has no complete count.",
}
STATUS = {
    "ok": "All weather sources available.",
    "partial": "Some weather sources missing; see reasons.",
    "missing": "No weather available at T.",
}


def _ts(t: pd.Timestamp) -> pa.Scalar:
    return pa.scalar(t, pa.timestamp("us", "UTC"))


def _read(path: Path, columns: list[str] | None = None, filter=None) -> pd.DataFrame:
    return ds.dataset(path).to_table(columns=columns, filter=filter).to_pandas()


def airports(root: Path) -> dict:
    return yaml.safe_load((root / "configs/airports.yaml").read_text())["airports"]


def local_time(root: Path, icao: str, t: pd.Timestamp) -> pd.Timestamp:
    return t.tz_convert(ZoneInfo(airports(root)[icao]["timezone"]))


def reason_text(codes) -> list[str]:
    return [
        f"{c}: {REASONS.get(c, 'see docs')}"
        for c in (codes if codes is not None else [])
    ]


# Known at T ------------------------------------------------------------------------------


def load_evidence(root: Path, icao: str, t: pd.Timestamp) -> dict:
    """Weather evidence for the throughput snapshots at airport icao and as_of t."""
    snaps = _read(
        root / SNAPSHOTS,
        filter=(ds.field("task") == "throughput")
        & (ds.field("airport_icao") == icao)
        & (ds.field("as_of_utc") == _ts(t)),
    ).sort_values("horizon_h", ignore_index=True)
    snaps = snaps.drop(columns=[c for c in snaps if c in OUTCOME_COLUMNS])
    if snaps.empty:
        return {
            "snapshots": snaps,
            "lineage": pd.DataFrame(),
            "metar": None,
            "taf": None,
        }
    lineage = _read(
        root / LINEAGE, filter=ds.field("snapshot_key").isin(list(snaps.snapshot_key))
    )
    assert (lineage["contributing_available_at_utc"] <= t).all()
    metar_ids = lineage.loc[lineage.feature_group == "metar_latest", "source_record_id"]
    metar = None
    if len(metar_ids):
        rows = _read(
            root / OBSERVATIONS,
            columns=[
                "source_record_id",
                "observed_at_utc",
                "available_at_utc",
                "raw_metar",
                "availability_basis",
                "wind_status",
                "wind_from_deg",
                "wind_kt",
                "gust_kt",
            ],
            filter=ds.field("source_record_id").isin(list(metar_ids.unique())),
        )
        metar = rows.iloc[0].to_dict() if len(rows) else None
    taf = None
    refs = lineage.loc[lineage.feature_group == "taf", "source_ref"]
    if len(refs):
        bulletin = refs.str.split("#").str[0].iloc[0]
        segs = _read(
            root / FORECASTS,
            columns=[
                "bulletin_id",
                "segment_id",
                "issued_at_utc",
                "available_at_utc",
                "availability_basis",
                "is_amendment",
                "is_correction",
                "forecast_type",
                "probability",
                "valid_from_utc",
                "valid_to_utc",
                "bulletin_valid_to_utc",
                "raw_group",
            ],
            filter=ds.field("bulletin_id") == bulletin,
        ).sort_values("segment_id", ignore_index=True)
        assert (segs["available_at_utc"] <= t).all()
        covering = segs[(segs.valid_to_utc > t) & (segs.valid_from_utc < t + WINDOW)]
        taf = {
            "bulletin": segs.iloc[0].to_dict(),
            "segments": covering.reset_index(drop=True),
        }
    return {"snapshots": snaps, "lineage": lineage, "metar": metar, "taf": taf}


def runway_winds(root: Path, icao: str, snap: pd.Series) -> pd.DataFrame:
    """Runway-relative METAR wind at T, per runway end, from the snapshot's features."""
    heading = airports(root)[icao]["runway_heading_deg"]
    status = snap.get("metar_wind_status")
    head = snap.get("metar_headwind_kt_hdg")
    ends = [(f"{heading:03.0f}", head, snap.get("metar_tailwind_kt_hdg")),
            (f"{(heading + 180) % 360:03.0f}", None if pd.isna(head) else -head,
             snap.get("metar_tailwind_kt_rec"))]  # fmt: skip
    best = snap.get("metar_best_end")
    rows = []
    for i, (name, h, tail) in enumerate(ends):
        rows.append(
            {
                "runway end (heading °)": name,
                "headwind (kt)": h,
                "tailwind (kt)": tail,
                "crosswind (kt)": snap.get("metar_crosswind_kt"),
                "favourable end": (best == ("hdg", "rec")[i])
                if isinstance(best, str)
                else None,
            }
        )
    note = {
        "calm": "Calm wind: all components 0 kt.",
        "variable": "Variable wind: head/tailwind unknown; crosswind shown as full speed "
        "(worst case).",
        "missing": "Wind missing in the latest METAR.",
    }.get(status, "")
    return pd.DataFrame(rows).assign(wind_status=status, note=note)


# Forecast for the next 12 h --------------------------------------------------------------


def list_runs(root: Path) -> list[str]:
    base = root / ARTIFACTS
    return (
        sorted(p.parent.name for p in base.glob("*/predictions.parquet"))
        if base.exists()
        else []
    )


def load_predictions(root: Path, run: str, icao: str, t: pd.Timestamp) -> pd.DataFrame:
    df = _read(
        root / ARTIFACTS / run / "predictions.parquet",
        columns=[
            "prediction_id",
            "airport_icao",
            "as_of_utc",
            "target_start_utc",
            "horizon_h",
            "target_kind",
            "estimate",
            "p10",
            "p90",
            "unit",
            "status",
            "reason_codes",
            "model_version",
            "feature_version",
            "generated_at_utc",
        ],
        filter=(ds.field("task") == "throughput")
        & (ds.field("airport_icao") == icao)
        & (ds.field("as_of_utc") == _ts(t)),
    )
    return df.sort_values(["model_version", "horizon_h"], ignore_index=True)


def load_schedule(root: Path, icao: str, t: pd.Timestamp) -> pd.DataFrame:
    return _read(
        root / HOURLY,
        columns=SCHEDULE_COLUMNS,
        filter=(ds.field("airport_icao") == icao)
        & (ds.field("hour_start_utc") >= _ts(t))
        & (ds.field("hour_start_utc") < _ts(t + WINDOW)),
    ).sort_values("hour_start_utc", ignore_index=True)


def forecast_table(predictions: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """One row per model and target hour; unavailable rows say so instead of showing a number."""
    if predictions.empty:
        return pd.DataFrame()
    df = predictions.merge(
        schedule[["hour_start_utc", "scheduled_arrivals"]],
        left_on="target_start_utc", right_on="hour_start_utc", how="left",
    )  # fmt: skip
    df["kind"] = df["model_version"].map(
        lambda m: "baseline" if m.startswith("baseline") else "model"
    )
    df["shown"] = df["estimate"].where(df["status"] != "unavailable")
    df["note"] = df["status"].map({"unavailable": "insufficient data"}).fillna("")
    return df[["model_version", "kind", "horizon_h", "target_start_utc", "shown", "p10", "p90",
               "unit", "status", "note", "reason_codes", "scheduled_arrivals"]]  # fmt: skip


def load_advisories(
    root: Path, run: str, icao: str, t: pd.Timestamp
) -> pd.DataFrame | None:
    path = root / ARTIFACTS / run / "advisories.parquet"
    if not path.exists():
        return None
    return _read(
        path,
        filter=(ds.field("airport_icao") == icao) & (ds.field("as_of_utc") == _ts(t)),
    )


# What actually happened (hindsight only) ----------------------------------------------------


def load_replay_outcomes(root: Path, icao: str, t: pd.Timestamp) -> dict:
    """Realised outcomes for the hours after T. Only the hindsight panel calls this."""
    hourly = _read(
        root / HOURLY,
        columns=[
            "hour_start_utc",
            "scheduled_arrivals",
            "reporting_carrier_touchdowns",
            "coverage_status",
            "scheduled_departures",
        ],
        filter=(ds.field("airport_icao") == icao)
        & (ds.field("hour_start_utc") >= _ts(t))
        & (ds.field("hour_start_utc") < _ts(t + WINDOW)),
    ).sort_values("hour_start_utc", ignore_index=True)
    flights = _read(
        root / REQUESTS,
        columns=["prediction_id", "target_start_utc"],
        filter=(ds.field("task") == "severe_delay")
        & (ds.field("airport_icao") == icao)
        & (
            ds.field("horizon_h") == 3
        )  # One request per flight; labels repeat per horizon.
        & (ds.field("target_start_utc") >= _ts(t))
        & (ds.field("target_start_utc") < _ts(t + WINDOW)),
    )
    labels = _read(
        root / LABELS,
        columns=["prediction_id", "y_true", "eligible", "exclusion_reason"],
        filter=(ds.field("target_kind") == "departure_delay_gt45")
        & ds.field("prediction_id").isin(list(flights.prediction_id)),
    )
    return {"hourly": hourly, "departures": departure_outcomes(flights, labels)}


def departure_outcomes(flights: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Per scheduled-departure hour: flights, operated, delayed > 45 min, and the share among
    operated flights (cancelled flights are excluded, not counted as on time)."""
    df = flights.merge(labels, on="prediction_id", how="left")
    operated = df["eligible"].fillna(False).astype(bool)
    df = df.assign(
        hour_start_utc=df["target_start_utc"].dt.floor("h"),
        operated_with_outcome=operated,
        delayed_gt45=df["y_true"].where(operated, 0).fillna(0).astype(int),
        cancelled=df["exclusion_reason"].eq("cancelled"),
    )
    out = df.groupby("hour_start_utc").agg(
        scheduled_departures=("prediction_id", "size"),
        operated_with_outcome=("operated_with_outcome", "sum"),
        delayed_gt45=("delayed_gt45", "sum"),
        cancelled=("cancelled", "sum"),
    )
    out["severe_delay_share"] = out["delayed_gt45"] / out[
        "operated_with_outcome"
    ].where(out["operated_with_outcome"] > 0)
    return out.reset_index()


# Evaluation and cases -------------------------------------------------------------------------


def list_metric_files(root: Path) -> list[Path]:
    base = root / REPORTS
    return sorted(base.rglob("metrics*.json")) if base.exists() else []


def metric_records(report: dict) -> pd.DataFrame:
    """The report's own metric records, unchanged, as a table (no recomputation)."""
    cols = ["split", "airport", "horizon", "target_label", "model", "metric", "value", "unit",
            "ci_low", "ci_high", "ci_method", "n_eligible", "n_predicted", "n_excluded",
            "slice", "reason"]  # fmt: skip
    df = pd.DataFrame(report.get("metrics", []))
    df = df[[c for c in cols if c in df]]
    return (
        df.astype({"horizon": "string"}) if "horizon" in df else df
    )  # "all" for macro rows


def load_cases(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())["cases"]
