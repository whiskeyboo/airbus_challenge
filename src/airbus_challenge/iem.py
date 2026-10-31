import ast
import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import yaml

RAW = Path("data/raw")
PROCESSED = Path("data/processed")
MANIFEST = RAW / "manifest.json"
AIRPORTS = Path("configs/airports.yaml")
SCHEMA_VERSION = "0.1.0"
PRODUCER = "airbus_challenge.iem/0.1.0"

# Historical availability is not evidenced by IEM; these latencies are a documented simulation.
METAR_LATENCY = pd.Timedelta(minutes=10)
TAF_LATENCY = pd.Timedelta(minutes=10)
# US 30-hour TAFs (ATL, DFW): routine cycles at 00/06/12/18Z, each valid 30 h from the cycle.
TAF_CYCLE = pd.Timedelta(hours=6)
TAF_SPAN = pd.Timedelta(hours=30)
TAF_EARLY = pd.Timedelta(
    minutes=40
)  # Routine TAFs are issued up to 40 min before the cycle.
INHG_TO_HPA = 33.8639
IN_TO_MM = 25.4
IEM_TRACE_IN = 0.0001
FORECAST_TYPES = {
    "Observation": "prevailing",
    "Forecast": "FM",
    "Temporary": "TEMPO",
    "Probability 30": "PROB30",
    "Probability 40": "PROB40",
}
WIND = re.compile(r"(?:^|\s)(VRB|\d{3})(\d{2,3})(?:G(\d{2,3}))?KT(?=\s|$)")
SKY = re.compile(r"(?:^|\s)(SKC|NSC|CLR|FEW|SCT|BKN|OVC|VV)(\d{3})?(?:CB|TCU)?(?=\s|$)")
CEILING_COVERS = {"BKN", "OVC", "VV"}


def airports() -> dict:
    return yaml.safe_load(AIRPORTS.read_text())["airports"]


def source(kind: str, icao: str) -> dict:
    manifest = json.loads(MANIFEST.read_text())
    (key,) = [k for k in manifest if k.startswith(f"{kind}/{kind}_{icao}_")]
    return {"key": key, **manifest[key]}


def record_id(*parts) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:32]


def utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True).astype("datetime64[us, UTC]")


def provenance(
    df: pd.DataFrame, name: str, src: dict, available: pd.Series
) -> pd.DataFrame:
    df["source_name"] = name
    df["source_version"] = f"sha256:{src['sha256'][:16]}"
    df["raw_ref"] = src["key"] + "#line=" + (df.index + 2).astype(str)
    df["retrieved_at_utc"] = utc(pd.Series(src["retrieved_at_utc"], index=df.index))
    df["available_at_utc"] = available
    df["availability_basis"] = "simulated"
    return df


def wind_status(
    speed: pd.Series, direction: pd.Series, variable: pd.Series
) -> pd.Series:
    status = pd.Series("missing", index=speed.index, dtype="string")
    status[speed.notna() & direction.notna()] = "directional"
    status[speed.notna() & variable] = "variable"
    status[speed == 0] = "calm"
    return status


def ceiling(covers: list[str], heights: list[float]) -> tuple[float | None, str]:
    if not covers:
        return None, "missing"
    layers = [h for c, h in zip(covers, heights) if c in CEILING_COVERS and pd.notna(h)]
    return (min(layers), "layer") if layers else (None, "none")


def metar_table(raw: pd.DataFrame, icao: str, src: dict) -> pd.DataFrame:
    df = pd.DataFrame(index=raw.index)
    df["airport_icao"] = icao
    df["station_id"] = raw["station"].astype("string")
    df["observed_at_utc"] = utc(raw["valid"])
    df["source_record_id"] = [
        record_id("iem_asos", s, v, m)
        for s, v, m in zip(raw.station, raw.valid, raw.metar)
    ]
    provenance(df, "IEM ASOS METAR", src, df["observed_at_utc"] + METAR_LATENCY)

    speed, direction, gust = (pd.to_numeric(raw[c]) for c in ("sknt", "drct", "gust"))
    variable = raw["metar"].str.contains(r"\sVRB\d", regex=True) & direction.isna()
    df["wind_status"] = wind_status(speed, direction, variable)
    df["wind_from_deg"] = direction.where(df["wind_status"] == "directional")
    df["wind_kt"] = speed
    df["gust_kt"] = gust
    df["wind_variable"] = variable.astype("boolean").mask(speed.isna())

    df["visibility_sm"] = pd.to_numeric(raw["vsby"])
    covers = raw[[f"skyc{i}" for i in range(1, 5)]].apply(lambda c: c.str.strip())
    heights = raw[[f"skyl{i}" for i in range(1, 5)]].apply(pd.to_numeric)
    ceilings = [
        ceiling([x for x in c if pd.notna(x)], list(h))
        for c, h in zip(covers.to_numpy(), heights.to_numpy())
    ]
    df["ceiling_ft"] = pd.Series(
        [c for c, _ in ceilings], index=df.index, dtype="float64"
    )
    df["ceiling_status"] = pd.Series(
        [s for _, s in ceilings], index=df.index, dtype="string"
    )

    df["temp_c"] = (pd.to_numeric(raw["tmpf"]) - 32) * 5 / 9
    df["dewpoint_c"] = (pd.to_numeric(raw["dwpf"]) - 32) * 5 / 9
    precip_in = pd.to_numeric(raw["p01i"])
    df["precip_1h_mm"] = precip_in * IN_TO_MM
    df["pressure_hpa"] = pd.to_numeric(raw["alti"]) * INHG_TO_HPA
    # IEM leaves wxcodes empty when the report has no present weather.
    df["wx_codes"] = raw["wxcodes"].map(
        lambda s: s.split() if isinstance(s, str) else []
    )
    df["raw_metar"] = raw["metar"].astype("string")

    flags = pd.DataFrame(
        {
            "precip_trace": precip_in == IEM_TRACE_IN,
            "sky_clr_below_12000ft": (covers == "CLR").any(axis=1),
            "wind_unparsed": speed.isna(),
            "wind_dir_varying_sector": raw["metar"].str.contains(
                r"KT \d{3}V\d{3}\s", regex=True
            ),
            "duplicate_observed_time": df.duplicated(
                ["station_id", "observed_at_utc"], keep=False
            ),
            "madis_hf": raw["metar"].str.contains("MADISHF"),
            "corrected": raw["metar"].str.contains(r"\sCOR\s", regex=True),
        }
    )
    df["quality_flags"] = flags_list(flags)
    return df.sort_values(["observed_at_utc", "source_record_id"]).reset_index(
        drop=True
    )


def flags_list(flags: pd.DataFrame) -> list[list[str]]:
    flags = flags.fillna(False).astype(bool)
    return [list(flags.columns[row]) for row in flags.to_numpy()]


def parse_wind(text: str) -> tuple[float | None, float | None, float | None, bool]:
    m = WIND.search(text)
    if not m:
        return None, None, None, False
    d, s, g = m.groups()
    return (
        None if d == "VRB" else float(d),
        float(s),
        float(g) if g else None,
        d == "VRB",
    )


def parse_sky(text: str) -> tuple[list[str], list[float]]:
    layers = SKY.findall(text)
    return [c for c, _ in layers], [float(h) * 100 if h else None for _, h in layers]


def bulletin_end(issued: pd.Series) -> pd.Series:
    # Each bulletin belongs to the latest cycle whose routine issuance window (opening
    # TAF_EARLY before the cycle) has started; amendments inherit that cycle's end.
    return (issued + TAF_EARLY).dt.floor(TAF_CYCLE) + TAF_SPAN


def taf_table(raw: pd.DataFrame, icao: str, src: dict) -> pd.DataFrame:
    raw = raw.assign(line=raw.index + 2)
    raw = raw.drop_duplicates(
        ["product_id", "ftype", "fx_valid", "fx_valid_end", "raw"]
    )
    df = pd.DataFrame(index=raw.index)
    df["bulletin_id"] = raw["product_id"].astype("string")
    df["segment_index"] = raw.groupby("product_id").cumcount().astype("int32")
    df["segment_id"] = df["segment_index"].map("{:02d}".format).astype("string")
    df["airport_icao"] = icao
    df["station_id"] = raw["station"].astype("string")
    df["issued_at_utc"] = utc(raw["valid"])
    df["source_record_id"] = [
        record_id("iem_taf", b, s, r)
        for b, s, r in zip(df.bulletin_id, df.segment_id, raw.raw)
    ]
    provenance(df, "IEM TAF", src, df["issued_at_utc"] + TAF_LATENCY)
    df["raw_ref"] = src["key"] + "#line=" + raw["line"].astype(str)

    bbb = (
        raw["product_id"].str.extract(r"^(?:[^-]+-){4}(\w+)$")[0].fillna("")
    )  # WMO BBB
    iem_amd = raw["is_amendment"].map({"True": True, "False": False}).astype("boolean")
    df["is_amendment"] = bbb.str.startswith("AA").astype("boolean")
    # A correction (CCx) may correct either a routine bulletin or an amendment; defer to IEM.
    df.loc[bbb.str.startswith("CC"), "is_amendment"] = iem_amd
    df["is_correction"] = bbb.str.startswith("CC")
    df["forecast_type"] = (
        raw["ftype"].map(FORECAST_TYPES).fillna("unknown").astype("string")
    )
    df["probability"] = (
        df["forecast_type"].str.extract(r"PROB(\d+)")[0].astype("float64") / 100
    )

    df["bulletin_valid_to_utc"] = bulletin_end(df["issued_at_utc"])
    df["valid_from_utc"] = utc(raw["fx_valid"])
    df["valid_to_utc"] = prevailing_ends(df).fillna(utc(raw["fx_valid_end"]))

    winds = pd.DataFrame(
        [parse_wind(t) for t in raw["raw"]],
        index=df.index,
        columns=["d", "s", "g", "v"],
    )
    direction, speed, gust = (winds[c].astype("float64") for c in "dsg")
    variable = winds["v"].astype("boolean")
    df["wind_status"] = wind_status(speed, direction, variable)
    df["wind_from_deg"] = direction.where(df["wind_status"] == "directional")
    df["wind_kt"], df["gust_kt"] = speed, gust
    df["wind_variable"] = variable.mask(speed.isna())

    vis = raw["visibility"].astype("float64")
    df["visibility_sm"] = vis.where(vis != 6.01, 6.0)
    ceilings = [ceiling(*parse_sky(t)) for t in raw["raw"]]
    df["ceiling_ft"] = pd.Series(
        [c for c, _ in ceilings], index=df.index, dtype="float64"
    )
    df["ceiling_status"] = pd.Series(
        [s for _, s in ceilings], index=df.index, dtype="string"
    )
    df["wx_codes"] = raw["presentwx"].map(ast.literal_eval)
    df["llws_height_ft"] = raw["ws_level"].astype("float64")
    df["llws_from_deg"] = raw["ws_drct"].astype("float64")
    df["llws_kt"] = raw["ws_sknt"].astype("float64")
    df["raw_group"] = raw["raw"].astype("string")
    df["raw_bulletin"] = df["bulletin_id"].map(
        df.groupby("bulletin_id")["raw_group"].agg("\n".join)
    )

    duplicated_initial = df[df.forecast_type == "prevailing"].bulletin_id.duplicated(
        keep=False
    )
    conflict = df["bulletin_id"].isin(
        df.loc[duplicated_initial[duplicated_initial].index, "bulletin_id"]
    )
    flags = pd.DataFrame(
        {
            "visibility_p6sm": vis == 6.01,
            "conflicting_bulletin_versions": conflict,
            "valid_to_clipped_to_bulletin_end": df["valid_to_utc"]
            > df["bulletin_valid_to_utc"],
            "segment_starts_after_bulletin_end": df["valid_from_utc"]
            >= df["bulletin_valid_to_utc"],
            "iem_is_amendment_disagrees": iem_amd.ne(df["is_amendment"]),
        }
    )
    df["quality_flags"] = flags_list(flags)
    df["valid_to_utc"] = df[["valid_to_utc", "bulletin_valid_to_utc"]].min(axis=1)
    return df.sort_values(
        ["issued_at_utc", "bulletin_id", "segment_index"]
    ).reset_index(drop=True)


def prevailing_ends(df: pd.DataFrame) -> pd.Series:
    # The initial group and FM groups form one chain; each lasts until the next distinct start.
    chain = df[df["forecast_type"].isin(["prevailing", "FM"])]
    starts = chain[["bulletin_id", "valid_from_utc"]].drop_duplicates()
    starts["next"] = starts.groupby("bulletin_id")["valid_from_utc"].shift(-1)
    ends = chain.merge(starts, on=["bulletin_id", "valid_from_utc"], how="left")["next"]
    ends.index = chain.index
    return ends.fillna(df.loc[chain.index, "bulletin_valid_to_utc"]).reindex(df.index)


def load_metar(icao: str) -> pd.DataFrame:
    src = source("metar", icao)
    raw = pd.read_csv(
        RAW / src["key"], dtype=str, keep_default_na=False, na_values=["null", ""]
    )
    return metar_table(raw, icao, src)


def load_taf(icao: str) -> pd.DataFrame:
    src = source("taf", icao)
    raw = pd.read_csv(
        RAW / src["key"], dtype=str, keep_default_na=False, na_values=[""]
    )
    return taf_table(raw, icao, src)


def gaps(times: pd.Series) -> pd.DataFrame:
    times = times.drop_duplicates().sort_values()
    return pd.DataFrame(
        {"start": times, "gap_h": times.diff().shift(-1) / pd.Timedelta(hours=1)}
    )


def month(s: pd.Series) -> pd.Series:
    return s.dt.tz_convert(None).dt.to_period("M").rename("month")


def coverage(obs: pd.DataFrame, fc: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for icao in obs.airport_icao.unique():
        o = gaps(obs.loc[obs.airport_icao == icao, "observed_at_utc"])
        segs = fc[fc.airport_icao == icao]
        b = segs.drop_duplicates("bulletin_id")
        t = gaps(b.issued_at_utc)
        om, tm = o.groupby(month(o.start)).gap_h, t.groupby(month(t.start)).gap_h
        frame = pd.DataFrame(
            {
                "metar_reports": om.size(),
                "metar_gaps_gt3h": om.apply(lambda g: (g > 3).sum()),
                "metar_max_gap_h": om.max(),
                "taf_bulletins": tm.size(),
                "taf_amendments": b.groupby(month(b.issued_at_utc)).is_amendment.sum(),
                "taf_segments": segs.groupby(month(segs.issued_at_utc)).size(),
                "taf_gaps_gt8h": tm.apply(lambda g: (g > 8).sum()),
                "taf_max_gap_h": tm.max(),
            }
        )
        frames.append(frame.reset_index().assign(airport_icao=icao))
    out = pd.concat(frames, ignore_index=True)
    return out[["airport_icao", *out.columns[:-1]]]


def write(
    df: pd.DataFrame, name: str, time_col: str, sources: list[dict], extra: dict
) -> Path:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    path = PROCESSED / f"{name}.parquet"
    tmp = path.with_name(f".{path.name}.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    manifest = {
        "dataset": name,
        "schema_version": SCHEMA_VERSION,
        "producer": PRODUCER,
        "data_mode": "real",
        "rows": len(df),
        "min_time_utc": df[time_col].min().isoformat(),
        "max_time_utc": df[time_col].max().isoformat(),
        "rows_by_airport": df.airport_icao.value_counts().to_dict(),
        "quality_flag_counts": df.quality_flags.explode().value_counts().to_dict(),
        "availability": {"basis": "simulated", "latency_min": extra.pop("latency_min")},
        "sources": [
            {k: s[k] for k in ("key", "url", "sha256", "retrieved_at_utc")}
            for s in sources
        ],
        **extra,
    }
    mpath = path.with_suffix(".manifest.json")
    tmp = mpath.with_name(f".{mpath.name}.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, default=str))
    tmp.replace(mpath)
    return path


def build() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    icaos = list(airports())
    obs = pd.concat([load_metar(i) for i in icaos], ignore_index=True)
    fc = pd.concat([load_taf(i) for i in icaos], ignore_index=True)
    cov = coverage(obs, fc)
    audit = {
        "coverage": json.loads(cov.astype({"month": str}).to_json(orient="records"))
    }
    write(
        obs,
        "weather_observations",
        "observed_at_utc",
        [source("metar", i) for i in icaos],
        {"latency_min": METAR_LATENCY.total_seconds() / 60, **audit},
    )
    write(
        fc,
        "weather_forecasts",
        "issued_at_utc",
        [source("taf", i) for i in icaos],
        {
            "latency_min": TAF_LATENCY.total_seconds() / 60,
            "bulletin_end_rule": "floor(issued + 40 min, 6 h) + 30 h",
            **audit,
        },
    )
    return obs, fc, cov


if __name__ == "__main__":
    obs, fc, cov = build()
    pd.set_option(
        "display.width", 200, "display.max_columns", 30, "display.max_rows", 100
    )
    print("weather_observations", obs.shape)
    print("weather_forecasts", fc.shape, "bulletins", fc.bulletin_id.nunique())
    print(cov.to_string(index=False))
