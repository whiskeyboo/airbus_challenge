from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from airbus_challenge import demand, features, registry, slices

REPO = Path(__file__).resolve().parents[1]
PROCESSED = REPO / registry.PROCESSED
REAL = all(
    (PROCESSED / t).exists()
    for t in (registry.WEATHER_TABLE, registry.DEMAND_TABLE, registry.REQUESTS_TABLE)
)


def test_registry_round_trips_through_json_and_hash():
    reg = registry.build()
    doc = registry.to_json(reg)
    assert registry.from_json(doc) == reg
    doc["features"][0]["unit"] = "changed"
    with pytest.raises(ValueError, match="hash"):
        registry.from_json(doc)


def test_model_inputs_are_ordered_predictors_without_keys_outcomes_or_slices():
    inputs = registry.model_inputs("throughput")
    assert inputs == registry.model_inputs("severe_delay")  # Same set for now.
    assert len(inputs) == len(set(inputs))
    meta = {n for names in registry.METADATA.values() for n in names}
    assert not set(inputs) & meta
    assert not set(inputs) & set(slices.SLICE_COLUMNS)
    assert not [n for n in inputs if any(w in n for w in registry.FORBIDDEN)]
    assert set(inputs) == {"horizon_h", *features.FEATURES, *demand.FEATURES}
    assert {"metar_age_min", "taf_age_min", "airport_icao"} <= set(inputs)
    with pytest.raises(ValueError):
        registry.model_inputs("cancellation")


def test_model_inputs_refuse_a_forbidden_predictor():
    reg = registry.build()
    bad = registry.Feature(
        "reporting_carrier_touchdowns", "double", "", "x", "", "", "", "", "", True
    )
    with pytest.raises(ValueError, match="forbidden"):
        registry.model_inputs("throughput", [*reg, bad])
    slice_col = registry.Feature(
        "thunderstorm", "bool", "", "x", "", "", "", "", "", True
    )
    with pytest.raises(ValueError, match="forbidden"):
        registry.model_inputs("throughput", [*reg, slice_col])


@pytest.mark.skipif(not REAL, reason="needs the processed data folder")
def test_registry_matches_real_tables_and_data_mode_agrees():
    check = registry.validate(registry.build(), PROCESSED)
    assert check["problems"] == []
    assert {m for v in check["data_mode"].values() for m in v} == {"real"}


def test_validate_reports_wrong_dtype(tmp_path):
    reg = registry.build()
    weather = {f.name: np.float32(1) for f in reg if f.table == registry.WEATHER_TABLE}
    for f in reg:
        if f.table == registry.WEATHER_TABLE and f.dtype == "int32":
            weather[f.name] = np.int32(1)
        elif f.table == registry.WEATHER_TABLE and f.dtype == "bool":
            weather[f.name] = True
        elif f.table == registry.WEATHER_TABLE and f.dtype in ("string", ""):
            weather[f.name] = "x"
    weather["metar_wind_kt"] = 1.0  # double, registry says float
    weather["data_mode"] = "fixture"
    pd.DataFrame([weather]).to_parquet(tmp_path / registry.WEATHER_TABLE)
    dem = {
        f.name: (1.0 if f.dtype == "double" else "x")
        for f in reg
        if f.table == registry.DEMAND_TABLE
    }
    pd.DataFrame([{**dem, "data_mode": "real"}]).to_parquet(
        tmp_path / registry.DEMAND_TABLE
    )
    pd.DataFrame([{"data_mode": "fixture"}]).to_parquet(
        tmp_path / registry.REQUESTS_TABLE
    )
    problems = registry.validate(reg, tmp_path)["problems"]
    assert any("metar_wind_kt" in p for p in problems)
    assert any("data_mode disagrees" in p for p in problems)


def test_slices_flag_ts_ifr_crosswind_and_missing_hours():
    t = pd.Timestamp("2024-05-28 00:00", tz="UTC")
    obs = pd.DataFrame(
        {
            "airport_icao": "KDFW",
            "observed_at_utc": pd.Series(
                [t + pd.Timedelta(minutes=m) for m in (10, 53, 113)]
            ).astype("datetime64[us, UTC]"),
            "source_record_id": ["a", "b", "c"],
            "wind_from_deg": [90.0, 180.0, np.nan],
            "wind_kt": [22.0, 10.0, 8.0],
            "gust_kt": np.nan,
            "wind_status": ["directional", "directional", "variable"],
            "visibility_sm": [10.0, 2.5, 10.0],
            "ceiling_ft": [5000.0, np.nan, np.nan],
            "wx_codes": [["VCTS"], ["BR"], []],
        }
    )
    out = slices.slice_table(obs, ["KDFW"], t, t + pd.Timedelta(hours=3)).set_index(
        "hour_start_utc"
    )
    h0, h1, h2 = (out.loc[t + pd.Timedelta(hours=i)] for i in range(3))
    # Runway 180: wind from 090 at 22 kt is a 22 kt crosswind (>= 20 kt).
    assert (h0.thunderstorm, h0.ifr, h0.low_vis, h0.strong_crosswind, h0.n_metars) == (
        True,
        True,
        False,
        True,
        2,
    )
    assert h0.source_record_ids == ["a", "b"]
    assert (h1.thunderstorm, h1.strong_crosswind, h1.coverage) == (
        False,
        False,
        "observed",
    )
    assert h2.n_metars == 0 and h2.coverage == "missing" and pd.isna(h2.thunderstorm)


def test_feature_producers_never_reference_the_slice_table():
    for module in (features, demand, registry):
        source = Path(module.__file__).read_text()
        assert slices.OUTPUT not in source and "eval_weather_slices" not in source
        assert "slices" not in source or module is registry
