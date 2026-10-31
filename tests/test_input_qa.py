import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from airbus_challenge import input_qa, registry

REPO = Path(__file__).resolve().parents[1]
UTC_US = "datetime64[us, UTC]"
REG = registry.build()
TABLE = {f.name: f.table for f in REG if f.predictor}
DTYPE = {f.name: f.dtype for f in REG if f.predictor}
INPUTS = registry.model_inputs("throughput", REG)


def value(name):
    return {
        "float": np.float32(1.5),
        "double": 1.5,
        "int32": np.int32(3),
        "bool": True,
        "string": "x",
    }[DTYPE[name]]


@pytest.fixture
def root(tmp_path):
    shutil.copytree(REPO / "configs", tmp_path / "configs")
    processed = tmp_path / registry.PROCESSED
    processed.mkdir(parents=True)
    ids = ["p_ok", "p_stale", "p_other_task"]
    base = pd.DataFrame(
        {
            "prediction_id": ids,
            "task": ["throughput", "throughput", "severe_delay"],
            "as_of_utc": pd.Series(
                pd.to_datetime(["2024-03-01 09:00"] * 3, utc=True)
            ).astype(UTC_US),
            "target_start_utc": pd.Series(
                pd.to_datetime(["2024-03-01 12:00"] * 3, utc=True)
            ).astype(UTC_US),
            "data_mode": "fixture",
        }
    )
    weather = base.assign(
        status=["ok", "partial", "ok"],
        reason_codes=[[], ["metar_stale"], []],
        **{n: [value(n)] * 3 for n in INPUTS if TABLE[n] == registry.WEATHER_TABLE},
    )
    weather["airport_icao"] = "KATL"
    weather["horizon_h"] = np.int32(3)
    weather.loc[1, "metar_wind_kt"] = np.nan  # Stale METAR: features null.
    weather.to_parquet(processed / registry.WEATHER_TABLE)
    demand = base.assign(
        airport_icao="KATL",
        status=["ok", "partial", "ok"],
        reason_codes=[[], ["schedule_unresolved_anchor_hour"], []],
        **{n: [value(n)] * 3 for n in INPUTS if TABLE[n] == registry.DEMAND_TABLE},
    )
    demand.to_parquet(processed / registry.DEMAND_TABLE)
    return tmp_path


def test_assemble_returns_metadata_then_exact_registry_columns(root):
    df = input_qa.assemble("throughput", root, split="validation", airports=["KATL"])
    assert list(df.prediction_id) == ["p_ok", "p_stale"]  # Other task filtered out.
    assert list(df.columns) == [*input_qa.META, *input_qa.STATUS, *INPUTS]
    input_qa.validate_inputs(df, "throughput", root)
    assert input_qa.assemble("throughput", root, split="calibration").empty


def test_stale_partial_row_keeps_status_and_reasons(root):
    row = (
        input_qa.assemble("throughput", root).set_index("prediction_id").loc["p_stale"]
    )
    assert row.status == "partial" and row.reason_codes == ["metar_stale"]
    assert row.demand_status == "partial" and row.demand_reason_codes == [
        "schedule_unresolved_anchor_hour"
    ]
    assert pd.isna(row.metar_wind_kt)


def test_reordered_or_wrong_dtype_or_unknown_airport_fail(root):
    df = input_qa.assemble("throughput", root)
    cols = list(df.columns)
    i, j = cols.index(INPUTS[0]), cols.index(INPUTS[1])
    cols[i], cols[j] = cols[j], cols[i]
    with pytest.raises(ValueError, match="order"):
        input_qa.validate_inputs(df[cols], "throughput", root)
    with pytest.raises(ValueError, match="dtype"):
        input_qa.validate_inputs(
            df.astype({"metar_wind_kt": "float64"}), "throughput", root
        )
    with pytest.raises(ValueError, match="order"):
        input_qa.validate_inputs(
            df.assign(reporting_carrier_touchdowns=1), "throughput", root
        )
    with pytest.raises(ValueError, match="unknown airport"):
        input_qa.validate_inputs(df.assign(airport_icao="KXYZ"), "throughput", root)


def test_quality_summary_counts_status_and_reasons(root):
    df = input_qa.assemble("throughput", root)
    (rec,) = input_qa._quality(df, "throughput", "validation", INPUTS)
    assert rec["requests"] == 2 and rec["snapshot_status"] == {"ok": 1, "partial": 1}
    assert rec["snapshot_reasons"] == {"metar_stale": 1}
    assert rec["top_null_rates"]["metar_wind_kt"] == 0.5
