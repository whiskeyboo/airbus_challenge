import io

import pandas as pd

from airbus_challenge import iem

SRC = {
    "key": "x/fixture.csv",
    "sha256": "0" * 64,
    "retrieved_at_utc": "2026-10-31T04:00:00+00:00",
}
METAR_HEADER = (
    "station,valid,tmpf,dwpf,relh,drct,sknt,p01i,alti,mslp,vsby,gust,skyc1,skyc2,skyc3,skyc4,"
    "skyl1,skyl2,skyl3,skyl4,wxcodes,ice_accretion_1hr,ice_accretion_3hr,ice_accretion_6hr,"
    "peak_wind_gust,peak_wind_drct,peak_wind_time,feel,metar,snowdepth"
)
TAF_HEADER = (
    "station,valid,fx_valid,raw,is_tempo,fx_valid_end,sknt,drct,gust,visibility,presentwx,"
    "skyc,skyl,ws_level,ws_drct,ws_sknt,product_id,ftype,is_amendment"
)


def metar(*rows: str) -> pd.DataFrame:
    raw = pd.read_csv(
        io.StringIO("\n".join([METAR_HEADER, *rows])),
        dtype=str,
        keep_default_na=False,
        na_values=["null", ""],
    )
    return iem.metar_table(raw, "KATL", SRC)


def metar_row(valid, drct, sknt, gust, skyc, skyl, text, wx="null", p01i="0.00"):
    skyc = (skyc + ["null"] * 4)[:4]
    skyl = (skyl + ["null"] * 4)[:4]
    return ",".join(
        [
            "ATL",
            valid,
            "60.00",
            "50.00",
            "70",
            drct,
            sknt,
            p01i,
            "30.00",
            "null",
            "10.00",
            gust,
        ]
        + skyc
        + skyl
        + [wx, *["null"] * 7, text, "null"]
    )


def taf(*rows: str) -> pd.DataFrame:
    raw = pd.read_csv(
        io.StringIO("\n".join([TAF_HEADER, *rows])),
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )
    return iem.taf_table(raw, "KATL", SRC)


def taf_row(pid, valid, fx_valid, text, ftype, fx_end="", amd="False"):
    return f"KATL,{valid},{fx_valid},{text},False,{fx_end},,,,6.01,[],[],[],,,,{pid},{ftype},{amd}"


def by_status(df):
    return df.set_index("wind_status")


def test_metar_keeps_variable_calm_missing_and_directional_wind_distinct():
    df = metar(
        metar_row(
            "2023-01-01 00:52",
            "null",
            "6.00",
            "null",
            ["FEW"],
            ["5000"],
            "KATL 010052Z VRB06KT 10SM FEW050",
        ),
        metar_row(
            "2023-01-01 01:52",
            "0.00",
            "0.00",
            "null",
            ["FEW"],
            ["5000"],
            "KATL 010152Z 00000KT 10SM FEW050",
        ),
        metar_row(
            "2023-01-01 02:52",
            "null",
            "null",
            "null",
            ["FEW"],
            ["5000"],
            "KATL 010252Z 180/03KT 10SM FEW050",
        ),
        metar_row(
            "2023-01-01 03:52",
            "250.00",
            "12.00",
            "22.00",
            ["FEW"],
            ["5000"],
            "KATL 010352Z 25012G22KT 10SM FEW050",
        ),
    )
    s = by_status(df)
    assert list(df.wind_status) == ["variable", "calm", "missing", "directional"]
    assert (
        pd.isna(s.loc["variable", "wind_from_deg"])
        and s.loc["variable", "wind_kt"] == 6
    )
    assert s.loc["variable", "wind_variable"]
    assert pd.isna(s.loc["calm", "wind_from_deg"]) and s.loc["calm", "wind_kt"] == 0
    assert not s.loc["calm", "wind_variable"]
    assert pd.isna(s.loc["missing", "wind_kt"]) and pd.isna(
        s.loc["missing", "wind_variable"]
    )
    assert "wind_unparsed" in s.loc["missing", "quality_flags"]
    assert (
        s.loc["directional", "wind_from_deg"] == 250
        and s.loc["directional", "gust_kt"] == 22
    )
    assert df.gust_kt.isna().sum() == 3  # No gust group is not a measured zero gust.


def test_metar_ceiling_is_lowest_bkn_ovc_vv_and_clear_is_not_zero():
    df = metar(
        metar_row(
            "2023-01-01 00:52",
            "90",
            "5",
            "null",
            ["SCT", "BKN", "OVC"],
            ["800", "2500", "4000"],
            "KATL A",
        ),
        metar_row("2023-01-01 01:52", "90", "5", "null", ["CLR"], ["null"], "KATL B"),
        metar_row(
            "2023-01-01 02:52",
            "90",
            "5",
            "null",
            ["FEW", "SCT"],
            ["3000", "9000"],
            "KATL C",
        ),
        metar_row(
            "2023-01-01 03:52", "90", "5", "null", ["VV "], ["100"], "KATL D", wx="FG"
        ),
        metar_row("2023-01-01 04:52", "90", "5", "null", [], [], "KATL E"),
    )
    assert df.ceiling_ft.tolist()[0] == 2500
    assert list(df.ceiling_status) == ["layer", "none", "none", "layer", "missing"]
    assert df.ceiling_ft.isna().tolist() == [False, True, True, False, True]
    assert df.ceiling_ft[3] == 100 and df.wx_codes[3] == ["FG"]
    assert "sky_clr_below_12000ft" in df.quality_flags[1]


def test_metar_timestamps_are_utc_and_availability_is_after_observation():
    df = metar(
        metar_row(
            "2023-03-12 06:52",
            "90",
            "5",
            "null",
            ["FEW"],
            ["5000"],
            "KATL x",
            p01i="0.0001",
        )
    )
    assert str(df.observed_at_utc.dtype) == "datetime64[us, UTC]"
    assert df.observed_at_utc[0] == pd.Timestamp("2023-03-12 06:52", tz="UTC")
    assert df.available_at_utc[0] == df.observed_at_utc[0] + iem.METAR_LATENCY
    assert df.availability_basis[0] == "simulated"
    assert df.precip_1h_mm[0] > 0 and "precip_trace" in df.quality_flags[0]


ROUTINE = "202301011140-KFFC-FTUS42-TAFATL"


def test_taf_segment_windows_follow_fm_chain_and_30h_cycle():
    df = taf(
        taf_row(
            ROUTINE,
            "2023-01-01 11:40",
            "2023-01-01 11:40",
            "18010KT P6SM SCT050",
            "Observation",
        ),
        taf_row(
            ROUTINE,
            "2023-01-01 11:40",
            "2023-01-01 16:00",
            "FM011600 VRB15G25KT 3SM TSRA OVC021CB",
            "Forecast",
        ),
        taf_row(
            ROUTINE,
            "2023-01-01 11:40",
            "2023-01-01 18:00",
            "TEMPO 0118/0120 1SM +TSRA BKN008",
            "Temporary",
            "2023-01-01 20:00",
        ),
        taf_row(
            ROUTINE,
            "2023-01-01 11:40",
            "2023-01-02 03:00",
            "FM020300 00000KT P6SM SKC",
            "Forecast",
        ),
        taf_row(
            ROUTINE,
            "2023-01-01 11:40",
            "2023-01-02 12:00",
            "PROB30 0212/0218 2SM BR",
            "Probability 30",
            "2023-01-02 18:00",
        ),
    )
    end = pd.Timestamp("2023-01-02 18:00", tz="UTC")  # 12Z cycle + 30 h.
    assert (df.bulletin_valid_to_utc == end).all()
    assert list(df.forecast_type) == ["prevailing", "FM", "TEMPO", "FM", "PROB30"]
    assert df.valid_to_utc.tolist() == [
        pd.Timestamp("2023-01-01 16:00", tz="UTC"),
        pd.Timestamp("2023-01-02 03:00", tz="UTC"),
        pd.Timestamp("2023-01-01 20:00", tz="UTC"),
        end,
        end,
    ]
    assert df.probability.tolist()[4] == 0.3 and df.probability.isna().sum() == 4
    fm, tempo, calm = df.iloc[1], df.iloc[2], df.iloc[3]
    assert fm.wind_status == "variable" and pd.isna(fm.wind_from_deg)
    assert fm.wind_kt == 15 and fm.gust_kt == 25 and fm.ceiling_ft == 2100
    assert tempo.wind_status == "missing" and tempo.ceiling_ft == 800
    assert (
        calm.wind_status == "calm"
        and calm.ceiling_status == "none"
        and pd.isna(calm.ceiling_ft)
    )
    assert df.iloc[4].ceiling_status == "missing"
    assert (
        df.issued_at_utc.dt.tz is not None
        and str(df.valid_from_utc.dtype) == "datetime64[us, UTC]"
    )
    assert df.raw_bulletin[0].splitlines()[1] == "FM011600 VRB15G25KT 3SM TSRA OVC021CB"


def test_taf_bulletin_end_assigns_amendments_to_their_cycle():
    issued = pd.Series(
        pd.to_datetime(
            ["2023-01-01 21:00", "2023-01-01 23:25", "2023-01-02 00:10"], utc=True
        )
    )
    assert iem.bulletin_end(issued).tolist() == [
        pd.Timestamp("2023-01-03 00:00", tz="UTC"),  # Amends the 18Z TAF.
        pd.Timestamp(
            "2023-01-03 06:00", tz="UTC"
        ),  # After the 00Z routine window opens.
        pd.Timestamp("2023-01-03 06:00", tz="UTC"),
    ]


def test_taf_amendment_is_kept_as_a_separate_bulletin():
    amd = "202301011500-KFFC-FTUS42-TAFATL-AAA"
    df = taf(
        taf_row(
            ROUTINE,
            "2023-01-01 11:40",
            "2023-01-01 11:40",
            "18010KT P6SM SCT050",
            "Observation",
        ),
        taf_row(
            amd,
            "2023-01-01 15:00",
            "2023-01-01 15:00",
            "20012KT 3SM BR BKN009",
            "Observation",
            amd="True",
        ),
    )
    assert df.bulletin_id.tolist() == [ROUTINE, amd]
    assert df.is_amendment.tolist() == [False, True]
    assert df.valid_from_utc[1] == pd.Timestamp("2023-01-01 15:00", tz="UTC")
    assert df.available_at_utc.tolist() == [
        t + iem.TAF_LATENCY for t in df.issued_at_utc
    ]


def ts(s):
    return pd.Timestamp(s, tz="UTC")


def test_hour_24_at_end_of_may_is_midnight_on_june_1():
    pid = "202305301737-KFFC-FTUS42-TAFATL"
    df = taf(
        taf_row(
            pid,
            "2023-05-30 17:37",
            "2023-05-30 17:37",
            "18010KT P6SM SCT050",
            "Observation",
        ),
        # IEM's own fx_valid_end for this group is wrong (2023-05-18 00:00); the raw text wins.
        taf_row(
            pid,
            "2023-05-30 17:37",
            "2023-05-31 19:00",
            "PROB30 3119/3124 4SM TSRA BR BKN040CB",
            "Probability 30",
            "2023-05-18 00:00",
        ),
    )
    prob = df.iloc[1]
    assert (prob.valid_from_utc, prob.valid_to_utc) == (
        ts("2023-05-31 19:00"),
        ts("2023-06-01 00:00"),
    )
    assert "iem_validity_disagrees" in prob.quality_flags
    assert (df.valid_to_utc > df.valid_from_utc).all()


def test_group_times_roll_over_december_to_january():
    issued = ts("2023-12-31 23:20")
    assert iem.group_window("TEMPO 3122/3124 BKN008", issued) == (
        ts("2023-12-31 22:00"),
        ts("2024-01-01 00:00"),
    )
    assert iem.group_window("PROB30 0102/0106 2SM BR", issued) == (
        ts("2024-01-01 02:00"),
        ts("2024-01-01 06:00"),
    )
    assert iem.group_window("FM010300 00000KT P6SM SKC", issued) == (
        ts("2024-01-01 03:00"),
        None,
    )
    assert iem.group_window("18010KT P6SM SCT050", issued) == (None, None)


def test_bulletin_issued_early_is_moved_to_the_cycle_its_groups_reach():
    issued = pd.Series([ts("2025-01-08 20:56")])
    assert iem.bulletin_end(issued)[0] == ts("2025-01-10 00:00")
    assert iem.bulletin_end(issued, pd.Series([ts("2025-01-10 02:00")]))[0] == ts(
        "2025-01-10 06:00"
    )
