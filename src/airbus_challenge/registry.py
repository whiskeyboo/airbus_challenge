"""Frozen model-input registry: the one source of truth for which columns train.py may use.

Built from features.FEATURES (weather + calendar) and demand.FEATURES (schedule demand).
Ages (metar_age_min, taf_age_min, taf_lead_h) are predictors: they are known at T and tell the
model how fresh the weather evidence is. horizon_h and airport_icao are predictors too.
Evaluation slices (slices.py) are never registered.
"""

import dataclasses
import hashlib
import json
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from airbus_challenge import demand, features

PROCESSED = Path("data/processed")
OUTPUT = "feature_registry.json"
REGISTRY_VERSION = "model-inputs/0.1.0"
TASKS = ("throughput", "severe_delay")
WEATHER_TABLE = "feature_snapshots.parquet"
DEMAND_TABLE = "demand_features.parquet"
REQUESTS_TABLE = "prediction_requests.parquet"
CATEGORICAL = {"airport_icao", "metar_wind_status", "metar_best_end", "taf_wind_status"}
INT32 = {
    "horizon_h",
    "target_hour_utc",
    "target_hour_local",
    "target_weekday_local",
    "target_month_local",
    "metar_reports_3h",
}
BOOL = {
    "metar_ceiling_none",
    "taf_is_amendment",
    "taf_ceiling_none",
    "taf_tempo",
    "taf_ts_prevailing",
    "taf_ts_conditional",
    *(f"metar_{k}_3h" for k in features.WX),
}
# Present in the tables but never model inputs.
METADATA = {
    WEATHER_TABLE: [
        "prediction_id", "task", "flight_id", "as_of_utc", "target_start_utc",
        "target_end_utc", "schedule_snapshot_id", "cohort_version", "data_mode",
        "snapshot_key", "window_end_utc", "reason_codes", "status", "feature_version",
        "data_snapshot_id",
    ],
    DEMAND_TABLE: [
        "anchor_hour_utc", "status", "reason_codes", "schedule_knowledge_basis",
        "demand_version",
    ],
}  # fmt: skip
FORBIDDEN = (
    "touchdown", "takeoff", "ratio", "delay", "cancel", "divert", "wheels", "actual_",
    "y_true", "label", "eligible", "exclusion", "prediction_id", "flight_id", "target_kind",
    "estimate", "thunderstorm", "ifr", "low_vis", "strong_crosswind",
)  # fmt: skip


@dataclasses.dataclass(frozen=True)
class Feature:
    name: str
    dtype: str
    unit: str
    table: str
    source: str
    transform: str
    version: str
    missing: str
    serving: str
    predictor: bool


def _dtype(name: str, table: str) -> str:
    if name in CATEGORICAL:
        return "string"
    if name in INT32:
        return "int32"
    if name in BOOL:
        return "bool"
    return "double" if table == DEMAND_TABLE else "float"


def build() -> list[Feature]:
    out = [
        Feature("horizon_h", "int32", "h", WEATHER_TABLE, "prediction_requests.horizon_h",
                "target_start - as_of", "requests", "never null", "live-capable", True)
    ]  # fmt: skip
    for name, (unit, missing, desc) in features.FEATURES.items():
        weather = name.startswith(("metar_", "taf_"))
        out.append(
            Feature(
                name=name,
                dtype=_dtype(name, WEATHER_TABLE),
                unit=unit,
                table=WEATHER_TABLE,
                source="weather_observations/weather_forecasts (IEM METAR/TAF)"
                if weather
                else "prediction_requests",
                transform=desc,
                version=features.FEATURE_VERSION,
                missing=missing,
                # Weather comes from live public feeds; replays use a simulated 10-min latency.
                serving="live-capable",
                predictor=True,
            )
        )
    for name, (unit, source, transform, missing) in demand.FEATURES.items():
        out.append(
            Feature(name, _dtype(name, DEMAND_TABLE), unit, DEMAND_TABLE, source, transform,
                    demand.DEMAND_VERSION, missing, "replay-only (retrospective schedule)", True)
        )  # fmt: skip
    for table, names in METADATA.items():
        for name in names:
            out.append(
                Feature(name, "", "", table, table, "metadata", REGISTRY_VERSION,
                        "", "n/a", False)
            )  # fmt: skip
    return out


def model_inputs(task: str, registry: list[Feature] | None = None) -> list[str]:
    """Ordered predictor names for a task. Same set for both tasks for now."""
    if task not in TASKS:
        raise ValueError(f"unknown task {task}")
    names = [f.name for f in (registry or build()) if f.predictor]
    bad = [n for n in names if any(w in n for w in FORBIDDEN)]
    if bad:
        raise ValueError(f"forbidden predictor names: {bad}")
    return names


def to_json(registry: list[Feature]) -> dict:
    body = [dataclasses.asdict(f) for f in registry]
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return {
        "registry_version": REGISTRY_VERSION,
        "content_sha256": digest,
        "features": body,
    }


def from_json(doc: dict) -> list[Feature]:
    registry = [Feature(**f) for f in doc["features"]]
    if to_json(registry)["content_sha256"] != doc["content_sha256"]:
        raise ValueError("registry content hash mismatch")
    return registry


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate(registry: list[Feature], processed: Path = PROCESSED) -> dict:
    """Every registered column exists with its declared dtype; data_mode agrees across tables."""
    problems, modes = [], {}
    schemas = {t: pq.read_schema(processed / t) for t in (WEATHER_TABLE, DEMAND_TABLE)}
    for f in registry:
        schema = schemas[f.table]
        if f.name not in schema.names:
            problems.append(f"{f.name} missing from {f.table}")
        elif (
            f.dtype and str(schema.field(f.name).type).replace("large_", "") != f.dtype
        ):
            problems.append(f"{f.name}: {schema.field(f.name).type} != {f.dtype}")
    for t in (WEATHER_TABLE, DEMAND_TABLE, REQUESTS_TABLE):
        column = ds.dataset(processed / t).to_table(columns=["data_mode"]).column(0)
        modes[t] = sorted(pc.unique(column).to_pylist())
    if len({m for v in modes.values() for m in v}) != 1:
        problems.append(f"data_mode disagrees: {modes}")
    return {"problems": problems, "data_mode": modes}


def write(processed: Path = PROCESSED) -> dict:
    registry = build()
    check = validate(registry, processed)
    if check["problems"]:
        raise ValueError(check["problems"])
    doc = to_json(registry)
    doc["validation"] = check
    doc["inputs_sha256"] = {
        t: sha256(processed / t) for t in (WEATHER_TABLE, DEMAND_TABLE, REQUESTS_TABLE)
    }
    path = processed / OUTPUT
    tmp = path.with_name(f".{OUTPUT}.tmp")
    tmp.write_text(json.dumps(doc, indent=2))
    tmp.replace(path)
    return doc


if __name__ == "__main__":
    doc = write()
    feats = from_json(doc)
    print(
        {t: len(model_inputs(t, feats)) for t in TASKS},
        "metadata", sum(not f.predictor for f in feats),
        doc["validation"]["data_mode"], doc["content_sha256"][:12],
    )  # fmt: skip
