"""Model-input assembly, inference compatibility checks and input-quality summaries.

assemble() is the one helper train.py should use: it joins feature_snapshots and
demand_features on prediction_id and returns metadata plus exactly registry.model_inputs(task),
in order. validate_inputs() checks a frame against the frozen registry; an unknown airport is a
hard error (ValueError), never a silently dropped or imputed row. Reads only the two feature
tables (column projections) and the registry; no outcome table.
"""

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import yaml

from airbus_challenge import registry

REPORT = Path("reports/input_quality.json")
META = ["prediction_id", "task", "as_of_utc", "target_start_utc"]
KEYS = [
    "airport_icao",
    "horizon_h",
]  # Also predictors; read once and placed in registry order.
STATUS = ["status", "reason_codes", "demand_status", "demand_reason_codes"]
DTYPES = {
    "float": {"float32"},
    "double": {"float64"},
    "int32": {"int32"},
    "bool": {"bool", "boolean", "object"},  # arrow bool with nulls arrives as object
    "string": {"str", "string", "object"},
}


def _bounds(root: Path, split: str):
    s = yaml.safe_load((root / "configs/experiment.yaml").read_text())["splits"][split]
    return pd.Timestamp(s["start"], tz="UTC"), pd.Timestamp(s["end"], tz="UTC")


def _ts(t) -> pa.Scalar:
    return pa.scalar(t, pa.timestamp("us", "UTC"))


def assemble(
    task: str,
    root: Path = Path("."),
    split: str | None = None,
    airports: list[str] | None = None,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Metadata, status columns and model_inputs(task) for one task, optionally filtered."""
    reg = registry.build()
    inputs = registry.model_inputs(task, reg)
    wanted = inputs if columns is None else [c for c in inputs if c in columns]
    tables = {f.name: f.table for f in reg if f.predictor}
    flt = ds.field("task") == task
    if split:
        lo, hi = _bounds(root, split)
        flt &= (ds.field("target_start_utc") >= _ts(lo)) & (
            ds.field("target_start_utc") < _ts(hi)
        )
    if airports:
        flt &= ds.field("airport_icao").isin(airports)
    processed = root / registry.PROCESSED
    weather_cols = [
        c for c in wanted if tables[c] == registry.WEATHER_TABLE and c not in KEYS
    ]
    weather = (
        ds.dataset(processed / registry.WEATHER_TABLE)
        .to_table(
            columns=[*META, *KEYS, "status", "reason_codes", *weather_cols], filter=flt
        )
        .to_pandas()
    )
    demand_cols = [c for c in wanted if tables[c] == registry.DEMAND_TABLE]
    demand = (
        ds.dataset(processed / registry.DEMAND_TABLE)
        .to_table(
            columns=["prediction_id", "status", "reason_codes", *demand_cols],
            filter=flt,
        )
        .to_pandas()
        .rename(
            columns={"status": "demand_status", "reason_codes": "demand_reason_codes"}
        )
    )
    out = weather.merge(demand, on="prediction_id", how="left", validate="one_to_one")
    missing = out["demand_status"].isna()
    out.loc[missing, "demand_status"] = "missing"
    out["demand_reason_codes"] = out["demand_reason_codes"].map(
        lambda r: (
            list(r)
            if isinstance(r, (list, tuple)) or hasattr(r, "tolist")
            else ["demand_row_missing"]
        )
    )
    out["reason_codes"] = out["reason_codes"].map(list)
    order = (
        [c for c in wanted]
        if columns is None
        else [*KEYS, *[c for c in wanted if c not in KEYS]]
    )
    return out[[*META, *STATUS, *order]]


def validate_inputs(df: pd.DataFrame, task: str, root: Path = Path(".")) -> None:
    """Raise ValueError unless df's predictor columns match the frozen registry exactly."""
    reg = registry.build()
    inputs = registry.model_inputs(task, reg)
    predictors = [c for c in df.columns if c not in META + STATUS]
    if predictors != inputs:
        raise ValueError(
            f"predictor columns differ from model_inputs({task}) or are out of order"
        )
    declared = {f.name: f.dtype for f in reg if f.predictor}
    bad = [c for c in inputs if str(df[c].dtype) not in DTYPES[declared[c]]]
    if bad:
        raise ValueError(
            f"dtype mismatch: {[(c, str(df[c].dtype), declared[c]) for c in bad]}"
        )
    known = set(
        yaml.safe_load((root / "configs/airports.yaml").read_text())["airports"]
    )
    unknown = set(df["airport_icao"].dropna()) - known
    if unknown:
        raise ValueError(
            f"unknown airport(s) {sorted(unknown)}; add them to configs/airports.yaml"
        )


def _quality(df: pd.DataFrame, task: str, split: str, inputs: list[str]) -> list[dict]:
    rows = []
    for (airport, horizon), g in df.groupby(["airport_icao", "horizon_h"]):
        nulls = g[inputs].isna().mean().sort_values(ascending=False).head(10)
        ages = {
            c: {"median": float(g[c].median()), "p95": float(g[c].quantile(0.95))}
            for c in ("metar_age_min", "taf_age_min", "taf_lead_h")
        }
        rows.append(
            {
                "split": split,
                "task": task,
                "airport": airport,
                "horizon_h": int(horizon),
                "requests": len(g),
                "snapshot_status": g["status"].value_counts().to_dict(),
                "snapshot_reasons": g["reason_codes"]
                .explode()
                .dropna()
                .value_counts()
                .to_dict(),
                "demand_status": g["demand_status"].value_counts().to_dict(),
                "demand_reasons": g["demand_reason_codes"]
                .explode()
                .dropna()
                .value_counts()
                .to_dict(),
                "ages": ages,
                "top_null_rates": nulls.round(5).to_dict(),
            }
        )
    return rows


def build(root: Path = Path(".")) -> dict:
    reg = registry.build()
    records = []
    for split in ("train", "validation", "calibration", "test"):
        for task in registry.TASKS:
            df = assemble(task, root, split)
            records += _quality(df, task, split, registry.model_inputs(task, reg))
    processed = root / registry.PROCESSED
    doc = {
        "registry_sha256": registry.to_json(reg)["content_sha256"],
        "inputs_sha256": {
            t: registry.sha256(processed / t)
            for t in (registry.WEATHER_TABLE, registry.DEMAND_TABLE)
        },
        "note": "Feature inputs only; no outcome columns are read, including for test.",
        "records": records,
    }
    path = root / REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(doc, indent=2, default=str))
    tmp.replace(path)
    return doc


if __name__ == "__main__":
    doc = build()
    for r in doc["records"]:
        n = r["requests"]
        partial = 1 - r["snapshot_status"].get("ok", 0) / n
        a = r["ages"]
        print(
            f"{r['split']:<11} {r['task']:<12} {r['airport']} h{r['horizon_h']:<2} n={n:<8} "
            f"partial={partial:.3%} metar_age={a['metar_age_min']['median']:.0f}min "
            f"taf_age={a['taf_age_min']['median']:.0f}min lead={a['taf_lead_h']['median']:.1f}h"
        )
