import collections
import functools
import hashlib
import json
import resource
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import yaml

from airbus_challenge import iem

INTERIM = Path("data/interim")
EXPERIMENT = Path("configs/experiment.yaml")
FEATURE_VERSION = "weather-features/0.2.0"
# TAF selection policy: latest bulletin with available_at <= T, ordered by (available_at,
# issued_at, bulletin_id). Amendments and corrections supersede earlier bulletins. A bulletin
# flagged conflicting_bulletin_versions is skipped: the previous eligible bulletin is used (even
# if older) and the row gets reason code taf_conflict_fallback. If the chosen bulletin does not
# cover the target window, TAF features are null (taf_uncovered); no other bulletin is used.
TAF_POLICY = "taf-select/1"
# METAR policy: reports without an available_at (corrections, COR) are never used; when a COR
# would have been the latest report under the simulated latency, the row gets metar_cor_skipped.
# Ties on observed_at prefer the official report over MADIS high-frequency rows.
METAR_POLICY = "metar-select/1"
KEY = ["airport_icao", "as_of_utc", "target_start_utc", "horizon_h"]
SNAPSHOT_KEY = ["airport_icao", "as_of_utc", "target_start_utc", "window_end_utc"]
# Read from prediction_requests; it holds schedule fields only, never outcomes.
REQUEST_COLUMNS = [
    "prediction_id",
    "task",
    "airport_icao",
    "flight_id",
    "as_of_utc",
    "target_start_utc",
    "target_end_utc",
    "horizon_h",
    "schedule_snapshot_id",
    "cohort_version",
    "data_mode",
]
# Trailing windows (1/3/6 h) are on available_at_utc; nothing older than 6 h is read.
METAR_WINDOW = pd.Timedelta(hours=6)
METAR_MAX_AGE = pd.Timedelta(hours=3)  # Older latest report: METAR features are null.
WX = {"ts": "TS", "fz": "FZ", "sn": "SN", "fg": "FG", "ra": "RA"}
TAF_CHAIN = ["prevailing", "FM"]
METAR_COLUMNS = [
    "airport_icao", "observed_at_utc", "available_at_utc", "source_record_id", "raw_ref",
    "wind_from_deg", "wind_kt", "gust_kt", "wind_status", "visibility_sm", "ceiling_ft",
    "ceiling_status", "temp_c", "dewpoint_c", "pressure_hpa", "precip_1h_mm", "wx_codes",
    "_official",
]  # fmt: skip
TAF_COLUMNS = [
    "bulletin_id", "segment_id", "issued_at_utc", "available_at_utc", "forecast_type",
    "valid_from_utc", "valid_to_utc", "wind_from_deg", "wind_kt", "gust_kt", "wind_status",
    "visibility_sm", "ceiling_ft", "ceiling_status", "probability", "wx_codes", "raw_group",
    "source_record_id", "airport_icao",
]  # fmt: skip
METAR_COMPONENTS = [
    "metar_headwind_kt_hdg",
    "metar_tailwind_kt_hdg",
    "metar_tailwind_kt_rec",
    "metar_crosswind_kt",
    "metar_headwind_kt_best",
    "metar_best_end",
    "metar_gust_crosswind_kt",
    "metar_gust_tailwind_kt_hdg",
    "metar_gust_tailwind_kt_rec",
]

# name: (unit, missing policy, description). Wind components follow CLAUDE.md rule 2 with
# headings from configs/airports.yaml used as given (true vs magnetic unspecified, DECISIONS O03).
# hdg = configured heading, rec = heading + 180. Calm: components 0. Variable: head/tailwind null,
# crosswind = full speed (worst case). Missing wind: all null. Gust components use the gust where
# reported, otherwise the sustained speed.
FEATURES = {
    "airport_icao": ("category", "never null", "Airport"),
    "target_hour_utc": ("hour", "never null", "UTC hour of target start"),
    "target_hour_local": ("hour", "never null", "Local hour of target start"),
    "target_weekday_local": ("0=Mon", "never null", "Local weekday of target start"),
    "target_month_local": ("month", "never null", "Local month of target start"),
    "metar_age_min": (
        "min",
        "null if no report in 6 h",
        "T minus latest eligible observation",
    ),
    "metar_wind_status": (
        "category",
        "null if stale",
        "directional/calm/variable/missing",
    ),
    "metar_wind_kt": ("kt", "null if stale or missing", "Latest sustained wind"),
    "metar_gust_kt": ("kt", "null if no gust reported", "Latest gust"),
    "metar_headwind_kt_hdg": (
        "kt",
        "null if variable/missing/stale",
        "Headwind on hdg end",
    ),
    "metar_tailwind_kt_hdg": (
        "kt",
        "null if variable/missing/stale",
        "Tailwind on hdg end",
    ),
    "metar_tailwind_kt_rec": (
        "kt",
        "null if variable/missing/stale",
        "Tailwind on rec end",
    ),
    "metar_crosswind_kt": (
        "kt",
        "null if missing/stale",
        "Crosswind (same on both ends)",
    ),
    "metar_headwind_kt_best": (
        "kt",
        "null if variable/missing/stale",
        "Headwind on favourable end",
    ),
    "metar_best_end": ("category", "null if no direction", "hdg or rec, max headwind"),
    "metar_gust_crosswind_kt": ("kt", "null if missing/stale", "Gust crosswind"),
    "metar_gust_tailwind_kt_hdg": (
        "kt",
        "null if variable/missing/stale",
        "Gust tailwind hdg end",
    ),
    "metar_gust_tailwind_kt_rec": (
        "kt",
        "null if variable/missing/stale",
        "Gust tailwind rec end",
    ),
    "metar_visibility_sm": ("sm", "null if stale or missing", "Latest visibility"),
    "metar_ceiling_ft": (
        "ft",
        "null if no ceiling, stale or missing",
        "Latest ceiling",
    ),
    "metar_ceiling_none": (
        "bool",
        "null if sky missing or stale",
        "No BKN/OVC/VV layer",
    ),
    "metar_temp_dewpoint_spread_c": ("C", "null if stale or missing", "Latest T - Td"),
    "metar_pressure_tendency_3h_hpa": (
        "hPa",
        "null if 3 h span < 2 h",
        "Latest minus oldest, 3 h",
    ),
    "metar_reports_3h": (
        "count",
        "0 if none",
        "Reports with available_at in (T-3h, T]",
    ),
    "metar_wind_max_kt_3h": ("kt", "null if none", "Max sustained wind, 3 h"),
    "metar_gust_max_kt_3h": ("kt", "null if no gusts", "Max gust, 3 h"),
    "metar_visibility_min_sm_1h": ("sm", "null if none", "Min visibility, 1 h"),
    "metar_visibility_min_sm_3h": ("sm", "null if none", "Min visibility, 3 h"),
    "metar_ceiling_min_ft_3h": ("ft", "null if no ceiling", "Lowest ceiling, 3 h"),
    "metar_precip_max_mm_1h": (
        "mm",
        "null if none",
        "Max 1-h precip report, 1 h (not summed)",
    ),
    "metar_precip_max_mm_6h": (
        "mm",
        "null if none",
        "Max 1-h precip report, 6 h (not summed)",
    ),
    **{
        f"metar_{k}_3h": ("bool", "null if no reports", f"Any {v} weather code, 3 h")
        for k, v in WX.items()
    },
    "taf_age_min": ("min", "null if no eligible TAF", "T minus bulletin issuance"),
    "taf_lead_h": ("h", "null if no eligible TAF", "Target start minus issuance"),
    "taf_is_amendment": ("bool", "null if unknown", "Bulletin used is an amendment"),
    "taf_wind_status": (
        "category",
        "null if uncovered",
        "Worst prevailing wind status",
    ),
    "taf_wind_max_kt": (
        "kt",
        "null if uncovered/unspecified",
        "Max prevailing wind in window",
    ),
    "taf_gust_max_kt": (
        "kt",
        "null if no gust forecast",
        "Max prevailing gust in window",
    ),
    "taf_crosswind_max_kt": (
        "kt",
        "null if uncovered/unspecified",
        "Max prevailing crosswind",
    ),
    "taf_tailwind_max_kt_hdg": (
        "kt",
        "null if uncovered/unspecified",
        "Max prevailing tailwind hdg; variable wind counts as full speed",
    ),
    "taf_tailwind_max_kt_rec": (
        "kt",
        "null if uncovered/unspecified",
        "Max prevailing tailwind rec; variable wind counts as full speed",
    ),
    "taf_gust_crosswind_max_kt": (
        "kt",
        "null if uncovered/unspecified",
        "Max gust crosswind",
    ),
    "taf_visibility_min_sm": ("sm", "null if uncovered", "Min prevailing visibility"),
    "taf_ceiling_min_ft": ("ft", "null if no ceiling", "Lowest prevailing ceiling"),
    "taf_ceiling_none": (
        "bool",
        "null if uncovered/unspecified",
        "No prevailing ceiling",
    ),
    "taf_tempo": ("bool", "null if uncovered", "TEMPO group overlaps window"),
    "taf_prob_max": (
        "prob",
        "0 if none; null if uncovered",
        "Max PROB overlapping window",
    ),
    "taf_cond_visibility_min_sm": ("sm", "null if none", "Min TEMPO/PROB visibility"),
    "taf_cond_ceiling_min_ft": ("ft", "null if none", "Lowest TEMPO/PROB ceiling"),
    "taf_cond_gust_max_kt": ("kt", "null if none", "Max TEMPO/PROB gust or wind"),
    "taf_cond_crosswind_max_kt": (
        "kt",
        "null if none",
        "Max TEMPO/PROB gust crosswind",
    ),
    "taf_ts_prevailing": (
        "bool",
        "null if uncovered",
        "TS code or CB in prevailing groups",
    ),
    "taf_ts_conditional": (
        "bool",
        "null if uncovered",
        "TS code or CB in TEMPO/PROB groups",
    ),
}


@functools.cache
def airports() -> dict:
    return iem.airports()


def utc_np(s: pd.Series) -> np.ndarray:
    return s.dt.tz_convert(None).astype("datetime64[us]").to_numpy()


def wind_components(
    direction: pd.Series, speed: pd.Series, status: pd.Series, heading: float
) -> tuple[pd.Series, pd.Series, pd.Series]:
    theta = np.radians(direction - heading)
    head = speed * np.cos(theta)
    cross = (speed * np.sin(theta)).abs()
    calm, variable = status == "calm", status == "variable"
    head = head.mask(calm, 0.0)
    cross = cross.mask(calm, 0.0).mask(variable, speed)
    tail = (-head).clip(lower=0)
    return head, tail, cross


def add_components(
    df: pd.DataFrame, prefix: str, speed: str, gust: str
) -> pd.DataFrame:
    heading = (
        df["airport_icao"]
        .map(lambda a: airports()[a]["runway_heading_deg"])
        .astype(float)
    )
    peak = df[gust].fillna(df[speed])
    out = {}
    for name, ws in (("", df[speed]), ("gust_", peak)):
        head, tail, cross = wind_components(
            df["wind_from_deg"], ws, df["wind_status"], heading
        )
        head_rec, tail_rec, _ = wind_components(
            df["wind_from_deg"], ws, df["wind_status"], heading + 180
        )
        out[f"{prefix}{name}headwind_kt_hdg"] = head
        out[f"{prefix}{name}tailwind_kt_hdg"] = tail
        out[f"{prefix}{name}tailwind_kt_rec"] = tail_rec
        out[f"{prefix}{name}crosswind_kt"] = cross
        out[f"{prefix}{name}headwind_kt_best"] = np.fmax(head, head_rec).where(
            head.notna()
        )
        if not name:
            out[f"{prefix}best_end"] = (
                pd.Series(np.where(head >= head_rec, "hdg", "rec"), index=df.index)
                .where(df["wind_status"] == "directional")
                .astype("string")
            )
    return df.assign(**out)


def expand_windows(obs: pd.DataFrame, keys: pd.DataFrame) -> pd.DataFrame:
    """One row per (key, report) with available_at in (T - METAR_WINDOW, T] and observed_at <= T.

    Windows are on availability: at an on-the-hour T they hold whole hourly cycles of reports.
    """
    parts = []
    for icao, k in keys.groupby("airport_icao"):
        o = obs[obs["airport_icao"] == icao].sort_values(
            ["available_at_utc", "observed_at_utc", "source_record_id"]
        )
        t, T = utc_np(o["available_at_utc"]), utc_np(k["as_of_utc"])
        lo = np.searchsorted(t, T - METAR_WINDOW.to_timedelta64(), "right")
        hi = np.searchsorted(t, T, "right")
        n = hi - lo
        rows = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n) + np.repeat(lo, n)
        part = o.iloc[rows].reset_index(drop=True)
        part["key_row"] = np.repeat(k.index.to_numpy(), n)
        part["as_of_utc"] = np.repeat(k["as_of_utc"].to_numpy(), n)
        parts.append(part)
    ex = pd.concat(parts, ignore_index=True)
    ex = ex[ex["observed_at_utc"] <= ex["as_of_utc"]]
    assert (ex["available_at_utc"] <= ex["as_of_utc"]).all()
    return ex


def cor_skipped(
    cor: pd.DataFrame, keys: pd.DataFrame, latest_obs: pd.Series
) -> pd.Series:
    """True where a COR observed before T - latency is newer than the latest report used."""
    k = keys.reset_index(names="key_row").sort_values("as_of_utc")
    k["cutoff"] = k["as_of_utc"] - iem.METAR_LATENCY
    c = cor[["airport_icao", "observed_at_utc"]].sort_values("observed_at_utc")
    m = pd.merge_asof(
        k, c, left_on="cutoff", right_on="observed_at_utc", by="airport_icao"
    ).set_index("key_row")
    newest = m["observed_at_utc"].reindex(keys.index)
    recent = newest > keys["as_of_utc"] - METAR_WINDOW
    return (recent & ~(newest <= latest_obs)).fillna(False).astype(bool)


def metar_features(
    obs: pd.DataFrame, keys: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """keys: unique (airport_icao, as_of_utc) with a RangeIndex.

    Returns features, lineage and a metar_cor_skipped flag per key.
    """
    usable = obs["available_at_utc"].notna()
    obs = obs.assign(_official=~obs["quality_flags"].map(lambda f: "madis_hf" in f))
    ex = expand_windows(obs.loc[usable, METAR_COLUMNS], keys)
    ex = ex.sort_values(["key_row", "observed_at_utc", "_official", "source_record_id"])
    age = ex["as_of_utc"] - ex["available_at_utc"]
    g = ex.groupby("key_row")
    latest = ex.groupby("key_row").tail(1).set_index("key_row")
    latest = add_components(latest, "metar_", "wind_kt", "gust_kt")
    f = pd.DataFrame(index=keys.index)
    f["metar_age_min"] = (keys["as_of_utc"] - latest["observed_at_utc"]) / pd.Timedelta(
        minutes=1
    )
    fresh = f["metar_age_min"] <= METAR_MAX_AGE / pd.Timedelta(minutes=1)
    f["metar_wind_status"] = latest["wind_status"]
    f["metar_wind_kt"] = latest["wind_kt"]
    f["metar_gust_kt"] = latest["gust_kt"]
    for c in METAR_COMPONENTS:
        f[c] = latest[c]
    f["metar_visibility_sm"] = latest["visibility_sm"]
    f["metar_ceiling_ft"] = latest["ceiling_ft"]
    f["metar_ceiling_none"] = (
        (latest["ceiling_status"] == "none")
        .astype("boolean")
        .mask(latest["ceiling_status"] == "missing")
    )
    f["metar_temp_dewpoint_spread_c"] = latest["temp_c"] - latest["dewpoint_c"]

    in3 = age < pd.Timedelta(hours=3)
    in1 = age < pd.Timedelta(hours=1)
    w3, w1 = ex[in3], ex[in1]
    g3, g1 = w3.groupby("key_row"), w1.groupby("key_row")
    first3 = (
        w3.sort_values(
            ["key_row", "observed_at_utc", "_official"], ascending=[True, True, False]
        )
        .groupby("key_row")
        .head(1)
        .set_index("key_row")
    )
    span = latest["observed_at_utc"] - first3["observed_at_utc"]
    f["metar_pressure_tendency_3h_hpa"] = (
        latest["pressure_hpa"] - first3["pressure_hpa"]
    ).where(span >= pd.Timedelta(hours=2))
    f["metar_reports_3h"] = g3.size().reindex(keys.index, fill_value=0).astype("int32")
    f["metar_wind_max_kt_3h"] = g3["wind_kt"].max()
    f["metar_gust_max_kt_3h"] = g3["gust_kt"].max()
    f["metar_visibility_min_sm_1h"] = g1["visibility_sm"].min()
    f["metar_visibility_min_sm_3h"] = g3["visibility_sm"].min()
    f["metar_ceiling_min_ft_3h"] = g3["ceiling_ft"].min()
    f["metar_precip_max_mm_1h"] = g1["precip_1h_mm"].max()
    f["metar_precip_max_mm_6h"] = g["precip_1h_mm"].max()
    codes = w3["wx_codes"].map(" ".join)
    for k, v in WX.items():
        f[f"metar_{k}_3h"] = (
            codes.str.contains(v).groupby(w3["key_row"]).any().astype("boolean")
        )

    metar_cols = [
        c for c in f.columns if c not in ("metar_age_min", "metar_reports_3h")
    ]
    f[metar_cols] = f[metar_cols].where(fresh, None)
    f.loc[~fresh, "metar_reports_3h"] = 0
    f["metar_reports_3h"] = f["metar_reports_3h"].astype("int32")

    window_ids = g["source_record_id"].agg(
        lambda s: hashlib.sha256("|".join(sorted(s)).encode()).hexdigest()[:32]
    )
    lineage = pd.concat(
        [
            pd.DataFrame(
                {
                    "key_row": latest.index,
                    "feature_group": "metar_latest",
                    "source_record_id": latest["source_record_id"].to_numpy(),
                    "source_ref": latest["raw_ref"].to_numpy(),
                    "contributing_available_at_utc": latest[
                        "available_at_utc"
                    ].to_numpy(),
                }
            ),
            pd.DataFrame(
                {
                    "key_row": window_ids.index,
                    "feature_group": "metar_window",
                    "source_record_id": "window:" + window_ids.to_numpy(),
                    "source_ref": "weather_observations: airport_icao, available_at_utc in "
                    "(as_of - 6h, as_of], observed_at_utc <= as_of",
                    "contributing_available_at_utc": g["available_at_utc"]
                    .max()
                    .to_numpy(),
                }
            ),
        ],
        ignore_index=True,
    )
    latest_obs = latest["observed_at_utc"].reindex(keys.index)
    return f, lineage, cor_skipped(obs[~usable], keys, latest_obs)


def select_bulletins(fc: pd.DataFrame, keys: pd.DataFrame) -> pd.DataFrame:
    """Latest eligible bulletin per (airport_icao, as_of_utc); keys has a RangeIndex."""
    b = fc.drop_duplicates("bulletin_id")[
        [
            "airport_icao",
            "bulletin_id",
            "issued_at_utc",
            "available_at_utc",
            "bulletin_valid_to_utc",
            "is_amendment",
            "quality_flags",
        ]
    ].copy()
    b["conflict"] = b["quality_flags"].map(
        lambda f: "conflicting_bulletin_versions" in f
    )
    b = b.drop(columns="quality_flags").sort_values(
        ["available_at_utc", "issued_at_utc", "bulletin_id"]
    )
    k = keys.reset_index(names="key_row").sort_values("as_of_utc")
    pick = lambda bs: (
        pd.merge_asof(
            k,
            bs,
            left_on="as_of_utc",
            right_on="available_at_utc",
            by="airport_icao",
            direction="backward",
            allow_exact_matches=True,
        )
        .set_index("key_row")
        .sort_index()
    )
    sel = pick(b[~b["conflict"]])
    newest = pick(b)
    sel["taf_conflict_fallback"] = newest["conflict"].fillna(False).astype(bool)
    assert (
        sel["issued_at_utc"].dropna()
        <= sel.loc[sel["issued_at_utc"].notna(), "as_of_utc"]
    ).all()
    return sel.drop(columns=["conflict"])


def taf_features(
    fc: pd.DataFrame, req: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """req: airport_icao, as_of_utc, target_start_utc, target_end_utc with a RangeIndex."""
    keys = req[["airport_icao", "as_of_utc"]].drop_duplicates().reset_index(drop=True)
    sel = select_bulletins(fc, keys)
    r = (
        req.reset_index(names="row")
        .merge(
            keys.reset_index(names="key_row"),
            on=["airport_icao", "as_of_utc"],
            how="left",
        )
        .set_index("row")
        .sort_index()
    )
    s = sel.loc[r["key_row"]].set_index(r.index)
    covered = s["bulletin_id"].notna() & (
        r["target_end_utc"] <= s["bulletin_valid_to_utc"]
    )
    f = pd.DataFrame(index=req.index)
    f["taf_age_min"] = (r["as_of_utc"] - s["issued_at_utc"]) / pd.Timedelta(minutes=1)
    f["taf_lead_h"] = (r["target_start_utc"] - s["issued_at_utc"]) / pd.Timedelta(
        hours=1
    )
    f["taf_is_amendment"] = s["is_amendment"].astype("boolean")

    segs = fc[TAF_COLUMNS].merge(
        pd.DataFrame(
            {"row": r.index[covered], "bulletin_id": s.loc[covered, "bulletin_id"]}
        ),
        on="bulletin_id",
    )
    segs = segs.merge(
        r[["target_start_utc", "target_end_utc", "as_of_utc"]]
        .rename_axis("row")
        .reset_index(),
        on="row",
    )
    segs = segs[
        (segs["valid_from_utc"] < segs["target_end_utc"])
        & (segs["valid_to_utc"] > segs["target_start_utc"])
    ]
    assert (segs["available_at_utc"] <= segs["as_of_utc"]).all()
    assert (segs["issued_at_utc"] <= segs["as_of_utc"]).all()
    segs = add_components(segs, "", "wind_kt", "gust_kt")
    # Worst case for a variable forecast wind: all of it may blow along the runway from behind.
    variable = segs["wind_status"] == "variable"
    for end in ("hdg", "rec"):
        segs[f"tailwind_kt_{end}"] = segs[f"tailwind_kt_{end}"].mask(
            variable, segs["wind_kt"]
        )
    segs["ts"] = segs["wx_codes"].map(lambda c: any("TS" in x for x in c)) | segs[
        "raw_group"
    ].str.contains(r"\d{3}CB\b", regex=True)
    chain = segs[segs["forecast_type"].isin(TAF_CHAIN)]
    cond = segs[~segs["forecast_type"].isin(TAF_CHAIN)]
    gp, gc = chain.groupby("row"), cond.groupby("row")
    rank = chain["wind_status"].map(
        {"calm": 0, "directional": 1, "variable": 2, "missing": 3}
    )
    worst = (
        rank.groupby(chain["row"])
        .max()
        .map({0: "calm", 1: "directional", 2: "variable", 3: "missing"})
    )
    f["taf_wind_status"] = worst.astype("string")
    f["taf_wind_max_kt"] = gp["wind_kt"].max()
    f["taf_gust_max_kt"] = gp["gust_kt"].max()
    f["taf_crosswind_max_kt"] = gp["crosswind_kt"].max()
    f["taf_tailwind_max_kt_hdg"] = gp["tailwind_kt_hdg"].max()
    f["taf_tailwind_max_kt_rec"] = gp["tailwind_kt_rec"].max()
    f["taf_gust_crosswind_max_kt"] = gp["gust_crosswind_kt"].max()
    f["taf_visibility_min_sm"] = gp["visibility_sm"].min()
    f["taf_ceiling_min_ft"] = gp["ceiling_ft"].min()
    sky = pd.get_dummies(chain["ceiling_status"]).groupby(chain["row"]).any()
    sky = sky.reindex(columns=["layer", "none", "missing"], fill_value=False)
    f["taf_ceiling_none"] = (
        (~sky["layer"]).astype("boolean").mask(~sky["layer"] & sky["missing"])
    )
    f["taf_tempo"] = (
        (cond["forecast_type"] == "TEMPO")
        .groupby(cond["row"])
        .any()
        .reindex(req.index, fill_value=False)
    )
    f["taf_prob_max"] = gc["probability"].max().reindex(req.index).fillna(0.0)
    f["taf_cond_visibility_min_sm"] = gc["visibility_sm"].min()
    f["taf_cond_ceiling_min_ft"] = gc["ceiling_ft"].min()
    f["taf_cond_gust_max_kt"] = (
        gc["gust_kt"].max().combine(gc["wind_kt"].max(), np.fmax)
    )
    f["taf_cond_crosswind_max_kt"] = gc["gust_crosswind_kt"].max()
    f["taf_ts_prevailing"] = gp["ts"].any()
    f["taf_ts_conditional"] = gc["ts"].any().reindex(req.index, fill_value=False)
    for c in ("taf_tempo", "taf_ts_prevailing", "taf_ts_conditional"):
        f[c] = f[c].astype("boolean")
    taf_cols = [
        c
        for c in f.columns
        if c not in ("taf_age_min", "taf_lead_h", "taf_is_amendment")
    ]
    f[taf_cols] = f[taf_cols].where(covered, None)

    lineage = pd.DataFrame(
        {
            "row": segs["row"].to_numpy(),
            "feature_group": "taf",
            "source_record_id": segs["source_record_id"].to_numpy(),
            "source_ref": (segs["bulletin_id"] + "#" + segs["segment_id"]).to_numpy(),
            "contributing_available_at_utc": segs["available_at_utc"].to_numpy(),
        }
    )
    reasons = pd.Series(
        [
            (
                ["taf_unavailable"]
                if b is None or pd.isna(b)
                else []
                if c
                else ["taf_uncovered"]
            )
            + (["taf_conflict_fallback"] if fb else [])
            for b, c, fb in zip(s["bulletin_id"], covered, s["taf_conflict_fallback"])
        ],
        index=req.index,
    )
    return f, lineage, reasons


def calendar(req: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=req.index)
    f["target_hour_utc"] = req["target_start_utc"].dt.hour.astype("int32")
    for icao, rows in req.groupby("airport_icao"):
        local = rows["target_start_utc"].dt.tz_convert(airports()[icao]["timezone"])
        f.loc[rows.index, "target_hour_local"] = local.dt.hour
        f.loc[rows.index, "target_weekday_local"] = local.dt.day_of_week
        f.loc[rows.index, "target_month_local"] = local.dt.month
    return f.astype("int32")


def snapshot(
    obs: pd.DataFrame, fc: pd.DataFrame, req: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Weather features at as_of_utc for each request row.

    req needs airport_icao, as_of_utc, target_start_utc and target_end_utc (null = start + 1 h);
    other columns (e.g. prediction_id, horizon_h) are carried through. Only records with
    available_at_utc <= as_of_utc are read.
    """
    req = req.reset_index(drop=True).copy()
    req["target_end_utc"] = req["target_end_utc"].fillna(
        req["target_start_utc"] + pd.Timedelta(hours=1)
    )
    keys = req[["airport_icao", "as_of_utc"]].drop_duplicates().reset_index(drop=True)
    mf, mlin, cor = metar_features(obs, keys)
    key_row = req.merge(
        keys.reset_index(names="key_row"), on=["airport_icao", "as_of_utc"], how="left"
    )["key_row"]
    met = mf.loc[key_row].set_index(req.index)
    cor_rows = cor.loc[key_row].to_numpy()
    taf, tlin, reasons = taf_features(fc, req)

    out = pd.concat([req, calendar(req), met, taf], axis=1)
    out["airport_icao"] = out["airport_icao"].astype("string")
    metar_ok = out["metar_age_min"] <= METAR_MAX_AGE / pd.Timedelta(minutes=1)
    taf_ok = out["taf_tempo"].notna()  # Null exactly when the window is not covered.
    metar_reason = np.where(
        out["metar_age_min"].isna(), "metar_unavailable", "metar_stale"
    )
    out["reason_codes"] = [
        ([] if m else [mr]) + (["metar_cor_skipped"] if c else []) + t
        for m, mr, c, t in zip(metar_ok, metar_reason, cor_rows, reasons)
    ]
    out["status"] = np.select(
        [metar_ok & taf_ok, metar_ok | taf_ok], ["ok", "partial"], "missing"
    )
    out["feature_version"] = FEATURE_VERSION

    mlin = mlin.merge(key_row.rename_axis("row").reset_index(), on="key_row").drop(
        columns="key_row"
    )
    lineage = pd.concat([mlin, tlin], ignore_index=True)
    lineage = lineage.merge(req.rename_axis("row").reset_index(), on="row").drop(
        columns="row"
    )
    lineage["availability_basis"] = "simulated"
    lineage["transform_version"] = f"{FEATURE_VERSION}+{METAR_POLICY}+{TAF_POLICY}"
    assert (lineage["contributing_available_at_utc"] <= lineage["as_of_utc"]).all()
    cols = [c for c in req.columns]
    lineage = lineage[cols + [c for c in lineage.columns if c not in cols]]
    return out, lineage.sort_values(cols + ["feature_group", "source_ref"]).reset_index(
        drop=True
    )


def airport_hour_requests(
    icaos: list[str], start, end, horizons: list[int]
) -> pd.DataFrame:
    hours = pd.date_range(start, end, freq="h", inclusive="left").astype(
        "datetime64[us, UTC]"
    )
    req = pd.MultiIndex.from_product(
        [icaos, horizons, hours],
        names=["airport_icao", "horizon_h", "target_start_utc"],
    ).to_frame(index=False)
    req["horizon_h"] = req["horizon_h"].astype("int32")
    req["target_end_utc"] = req["target_start_utc"] + pd.Timedelta(hours=1)
    req["as_of_utc"] = req["target_start_utc"] - pd.to_timedelta(
        req["horizon_h"], unit="h"
    )
    return req[KEY[:3] + ["target_end_utc", "horizon_h"]]


def write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def data_snapshot_id(processed: Path = iem.PROCESSED) -> str:
    manifests = [
        json.loads((processed / f"{n}.manifest.json").read_text())
        for n in ("weather_observations", "weather_forecasts")
    ]
    parts = sorted(s["sha256"] for m in manifests for s in m["sources"])
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def load_weather(processed: Path = iem.PROCESSED) -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_parquet(processed / "weather_observations.parquet"),
        pd.read_parquet(processed / "weather_forecasts.parquet"),
    )


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    exp = yaml.safe_load(EXPERIMENT.read_text())
    start = datetime.fromisoformat(exp["splits"]["train"]["start"]).replace(tzinfo=UTC)
    end = datetime.fromisoformat(exp["splits"]["test"]["end"]).replace(tzinfo=UTC)
    req = airport_hour_requests(list(airports()), start, end, exp["horizons_h"])
    obs, fc = load_weather()
    feats, lineage = snapshot(obs, fc, req)
    feats["data_snapshot_id"] = data_snapshot_id()
    feats = feats.sort_values(KEY).reset_index(drop=True)
    write(feats, INTERIM / "weather_features_airport_hour.parquet")
    write(lineage, INTERIM / "weather_features_lineage_airport_hour.parquet")
    return feats, lineage


def snapshot_key(df: pd.DataFrame) -> pd.Series:
    """sha256 of airport|as_of|target_start|window_end (RFC 3339 seconds), first 32 hex chars."""
    iso = {c: df[c].dt.strftime("%Y-%m-%dT%H:%M:%SZ") for c in SNAPSHOT_KEY[1:]}
    text = df[SNAPSHOT_KEY[0]].astype(str) + "|" + iso[SNAPSHOT_KEY[1]]
    for c in SNAPSHOT_KEY[2:]:
        text = text + "|" + iso[c]
    return text.map(lambda t: hashlib.sha256(t.encode()).hexdigest()[:32]).astype(
        "string"
    )


def request_snapshots(
    obs: pd.DataFrame, fc: pd.DataFrame, req: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Features per prediction request, computed once per unique snapshot key.

    The snapshot key is (airport_icao, as_of_utc, target_start_utc, window_end_utc), where
    window_end_utc = target_end_utc, or target_start_utc + 1 h when null (flight tasks).
    Lineage is returned per snapshot_key; requests map to it through their snapshot_key column.
    """
    req = req.reset_index(drop=True)
    window = req[["airport_icao", "as_of_utc", "target_start_utc"]].assign(
        window_end_utc=req["target_end_utc"].fillna(
            req["target_start_utc"] + pd.Timedelta(hours=1)
        )
    )
    req = req.assign(
        snapshot_key=snapshot_key(window), window_end_utc=window["window_end_utc"]
    )
    keys = req.drop_duplicates("snapshot_key")[[*SNAPSHOT_KEY, "snapshot_key"]]
    feats, lineage = snapshot(
        obs, fc, keys.rename(columns={"window_end_utc": "target_end_utc"})
    )
    feats = feats.drop(
        columns=["airport_icao", "as_of_utc", "target_start_utc", "target_end_utc"]
    )
    out = req.merge(feats, on="snapshot_key", how="left", validate="many_to_one")
    lineage = lineage.drop(
        columns=["airport_icao", "as_of_utc", "target_start_utc", "target_end_utc"]
    )
    return out, lineage


def compact(df: pd.DataFrame) -> pd.DataFrame:
    floats = [c for c in df.columns if df[c].dtype == "float64"]
    return df.astype(dict.fromkeys(floats, "float32"))


def months_of(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    return list(pd.date_range(start.floor("D").replace(day=1), end, freq="MS"))


def build_requests(processed: Path = iem.PROCESSED) -> dict:
    """feature_snapshots / feature_lineage for every prediction request, one month at a time.

    Reads only the weather tables, their manifests and prediction_requests (request columns).
    """
    t0 = time.time()
    obs, fc = load_weather(processed)
    snapshot_id = data_snapshot_id(processed)
    requests = ds.dataset(processed / "prediction_requests.parquet")
    bounds = requests.to_table(columns=["target_start_utc"]).column(0)
    lo, hi = pc.min_max(bounds).values()
    start = pd.Timestamp(lo.as_py()).tz_convert("UTC")
    stop = pd.Timestamp(hi.as_py()).tz_convert("UTC")
    paths = {
        n: processed / f"{n}.parquet" for n in ("feature_snapshots", "feature_lineage")
    }
    tmps = {n: p.with_name(f".{p.name}.tmp") for n, p in paths.items()}
    writers, counts, keys, status = {}, collections.Counter(), 0, collections.Counter()
    for m0 in months_of(start, stop):
        m1 = m0 + pd.DateOffset(months=1)
        field = ds.field("target_start_utc")
        req = requests.to_table(
            columns=REQUEST_COLUMNS,
            filter=(field >= pa.scalar(m0, pa.timestamp("us", "UTC")))
            & (field < pa.scalar(m1, pa.timestamp("us", "UTC"))),
        ).to_pandas()
        if req.empty:
            continue
        out, lineage = request_snapshots(obs, fc, req)
        out["data_snapshot_id"] = snapshot_id
        out = compact(out.sort_values(["task", "horizon_h", "prediction_id"]))
        keys += out["snapshot_key"].nunique()
        counts.update(out.groupby(["task", "horizon_h"]).size().to_dict())
        status.update(out.groupby(["task", "status"]).size().to_dict())
        for name, df in (("feature_snapshots", out), ("feature_lineage", lineage)):
            table = pa.Table.from_pandas(df, preserve_index=False)
            if name not in writers:
                schema = table.schema
                if "reason_codes" in schema.names:
                    i = schema.get_field_index("reason_codes")
                    schema = schema.set(
                        i, pa.field("reason_codes", pa.list_(pa.string()))
                    )
                writers[name] = pq.ParquetWriter(tmps[name], schema)
            writers[name].write_table(table.cast(writers[name].schema))
    for name, w in writers.items():
        w.close()
        tmps[name].replace(paths[name])
    summary = {
        "feature_version": FEATURE_VERSION,
        "data_snapshot_id": snapshot_id,
        "rows_by_task_horizon": {
            f"{t}|{h}": int(n) for (t, h), n in sorted(counts.items())
        },
        "unique_snapshot_keys": int(keys),
        "status_by_task": {f"{t}|{s}": int(n) for (t, s), n in sorted(status.items())},
        "lineage_key": "snapshot_key (join via feature_snapshots.snapshot_key)",
        "runtime_s": round(time.time() - t0, 1),
        "peak_rss_mb": round(peak_rss_mb(), 1),
        "bytes": {n: p.stat().st_size for n, p in paths.items()},
    }
    manifest = processed / "feature_snapshots.manifest.json"
    tmp = manifest.with_name(f".{manifest.name}.tmp")
    tmp.write_text(json.dumps(summary, indent=2))
    tmp.replace(manifest)
    return summary


def peak_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / 1e6 if sys.platform == "darwin" else rss / 1e3


if __name__ == "__main__":
    feats, lineage = build()
    print("airport-hour features", feats.shape, "lineage", lineage.shape)
    print(json.dumps(build_requests(), indent=2))
