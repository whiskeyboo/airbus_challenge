"""Target-hour weather slices for EVALUATION only. Never a model input.

Built from realised METAR in each target hour, in hindsight: every report observed in
[hour, hour + 1 h) counts, including corrected (COR) reports, regardless of availability.
- thunderstorm: any weather code containing TS (includes VCTS, vicinity thunderstorm).
- ifr: any report with ceiling < 1000 ft or visibility < 3 sm.
- low_vis: any report with visibility < 1 sm.
- strong_crosswind: max crosswind >= 20 kt (crosswind is the same on both runway ends, so this is
  also the favourable end); variable wind counts at full speed, as in features.py.
- n_metars: reports in the hour; with 0 reports every slice flag is null (missing).
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from airbus_challenge import features

PROCESSED = Path("data/processed")
OUTPUT = "eval_weather_slices.parquet"
SLICE_VERSION = "eval-weather-slices/0.1.0"
IFR_CEILING_FT = 1000
IFR_VISIBILITY_SM = 3
LOW_VIS_SM = 1
CROSSWIND_KT = 20
SLICE_COLUMNS = [
    "thunderstorm",
    "ifr",
    "low_vis",
    "strong_crosswind",
    "n_metars",
    "source_record_ids",
]


def slice_table(obs: pd.DataFrame, airports: list[str], start, end) -> pd.DataFrame:
    hours = pd.date_range(start, end, freq="h", inclusive="left").astype(
        "datetime64[us, UTC]"
    )
    grid = pd.MultiIndex.from_product(
        [airports, hours], names=["airport_icao", "hour_start_utc"]
    ).to_frame(index=False)
    o = features.add_components(obs.copy(), "", "wind_kt", "gust_kt")
    o["hour_start_utc"] = o["observed_at_utc"].dt.floor("h")
    o["ts"] = o["wx_codes"].map(lambda c: any("TS" in x for x in c))
    o["ifr"] = (o["ceiling_ft"] < IFR_CEILING_FT) | (
        o["visibility_sm"] < IFR_VISIBILITY_SM
    )
    o["low_vis"] = o["visibility_sm"] < LOW_VIS_SM
    o["xw"] = o["crosswind_kt"] >= CROSSWIND_KT
    g = o.sort_values("observed_at_utc").groupby(["airport_icao", "hour_start_utc"])
    agg = pd.DataFrame(
        {
            "thunderstorm": g["ts"].any(),
            "ifr": g["ifr"].any(),
            "low_vis": g["low_vis"].any(),
            "strong_crosswind": g["xw"].any(),
            "n_metars": g.size(),
            "source_record_ids": g["source_record_id"].agg(list),
        }
    ).reset_index()
    out = grid.merge(agg, on=["airport_icao", "hour_start_utc"], how="left")
    out["n_metars"] = out["n_metars"].fillna(0).astype("int32")
    for c in ("thunderstorm", "ifr", "low_vis", "strong_crosswind"):
        out[c] = out[c].astype("boolean").mask(out["n_metars"] == 0)
    out["source_record_ids"] = out["source_record_ids"].map(
        lambda v: v if isinstance(v, list) else []
    )
    out["coverage"] = np.where(out["n_metars"] > 0, "observed", "missing")
    out["slice_version"] = SLICE_VERSION
    return out


def build(root: Path = Path(".")) -> pd.DataFrame:
    splits = yaml.safe_load((root / "configs/experiment.yaml").read_text())["splits"]
    airports = list(
        yaml.safe_load((root / "configs/airports.yaml").read_text())["airports"]
    )
    obs = pd.read_parquet(
        root / PROCESSED / "weather_observations.parquet",
        columns=["airport_icao", "observed_at_utc", "source_record_id", "wind_from_deg", "wind_kt",
                 "gust_kt", "wind_status", "visibility_sm", "ceiling_ft", "wx_codes"],
    )  # fmt: skip
    out = slice_table(obs, airports, pd.Timestamp(splits["train"]["start"], tz="UTC"),
                      pd.Timestamp(splits["test"]["end"], tz="UTC"))  # fmt: skip
    path = root / PROCESSED / OUTPUT
    tmp = path.with_name(f".{OUTPUT}.tmp")
    out.to_parquet(tmp, index=False)
    tmp.replace(path)
    prevalence = out.groupby("airport_icao")[
        ["thunderstorm", "ifr", "low_vis", "strong_crosswind"]
    ].mean()
    manifest = {
        "dataset": "eval_weather_slices",
        "slice_version": SLICE_VERSION,
        "use": "evaluation only; never a model input; hindsight (all reports in the hour, incl. COR)",
        "rows": len(out),
        "missing_hours": int((out.coverage == "missing").sum()),
        "prevalence": prevalence.round(4).to_dict(orient="index"),
        "definitions": __doc__,
    }
    mpath = path.with_suffix(".manifest.json")
    mtmp = mpath.with_name(f".{mpath.name}.tmp")
    mtmp.write_text(json.dumps(manifest, indent=2, default=str))
    mtmp.replace(mpath)
    return out


if __name__ == "__main__":
    out = build()
    print(len(out), (out.coverage == "missing").sum())
    print(
        out.groupby("airport_icao")[
            ["thunderstorm", "ifr", "low_vis", "strong_crosswind"]
        ]
        .mean()
        .round(4)
    )
