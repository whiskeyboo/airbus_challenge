"""TEMPORAL_RULES.md §7 tests 1, 2, 3, 5 and 9 for weather features, plus wind components.

Test 4 (future flight statuses) is out of scope here: weather features read no flight data.
"""

import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from airbus_challenge import features, iem

LATENCY = pd.Timedelta(minutes=10)


def ts(s):
    return pd.Timestamp(s, tz="UTC")


def metar(
    observed,
    wind_from=90.0,
    wind=5.0,
    status="directional",
    gust=None,
    vis=10.0,
    ceiling=None,
    wx=(),
    pressure=1015.0,
    available=None,
    flags=(),
    rid=None,
):
    corrected = "corrected" in flags
    return {
        "airport_icao": "KATL",
        "observed_at_utc": ts(observed),
        "available_at_utc": pd.NaT
        if corrected
        else ts(observed) + LATENCY
        if available is None
        else ts(available),
        "source_record_id": rid or f"m-{observed}",
        "raw_ref": f"fixture#{observed}",
        "wind_from_deg": wind_from,
        "wind_kt": wind,
        "gust_kt": gust,
        "wind_status": status,
        "visibility_sm": vis,
        "ceiling_ft": ceiling,
        "ceiling_status": "none" if ceiling is None else "layer",
        "temp_c": 20.0,
        "dewpoint_c": 15.0,
        "pressure_hpa": pressure,
        "precip_1h_mm": 0.0,
        "wx_codes": list(wx),
        "quality_flags": list(flags),
    }


def obs_table(*rows):
    df = pd.DataFrame(rows)
    for c in ("observed_at_utc", "available_at_utc"):
        df[c] = df[c].astype("datetime64[us, UTC]")
    df["gust_kt"] = df["gust_kt"].astype("float64")
    df["ceiling_ft"] = df["ceiling_ft"].astype("float64")
    return df


def bulletin(bid, issued, end, segments, amendment=False, flags=()):
    """segments: (forecast_type, valid_from, valid_to, visibility, ceiling, wx, probability)."""
    rows = []
    for i, (kind, start, stop, vis, ceiling, wx, prob) in enumerate(segments):
        rows.append(
            {
                "airport_icao": "KATL",
                "bulletin_id": bid,
                "segment_id": f"{i:02d}",
                "issued_at_utc": ts(issued),
                "available_at_utc": ts(issued) + LATENCY,
                "bulletin_valid_to_utc": ts(end),
                "is_amendment": amendment,
                "quality_flags": list(flags),
                "forecast_type": kind,
                "valid_from_utc": ts(start),
                "valid_to_utc": ts(stop),
                "wind_from_deg": 170.0,
                "wind_kt": 10.0,
                "gust_kt": None,
                "wind_status": "directional",
                "visibility_sm": vis,
                "ceiling_ft": ceiling,
                "ceiling_status": "none" if ceiling is None else "layer",
                "probability": prob,
                "wx_codes": list(wx),
                "raw_group": " ".join(wx),
                "source_record_id": f"{bid}-{i}",
            }
        )
    return rows


def fc_table(*bulletins):
    df = pd.DataFrame([r for b in bulletins for r in b])
    for c in (
        "issued_at_utc",
        "available_at_utc",
        "bulletin_valid_to_utc",
        "valid_from_utc",
        "valid_to_utc",
    ):
        df[c] = df[c].astype("datetime64[us, UTC]")
    for c in ("gust_kt", "ceiling_ft", "probability", "visibility_sm"):
        df[c] = df[c].astype("float64")
    return df


ROUTINE = bulletin(
    "R1130",
    "2023-06-01 11:20",
    "2023-06-02 18:00",
    [
        ("prevailing", "2023-06-01 11:20", "2023-06-01 16:00", 6.0, None, (), None),
        ("FM", "2023-06-01 16:00", "2023-06-02 18:00", 6.0, 2500.0, (), None),
        ("TEMPO", "2023-06-01 17:00", "2023-06-01 20:00", 2.0, 800.0, ("TSRA",), None),
    ],
)
AMEND_1140 = bulletin(
    "A1140",
    "2023-06-01 11:40",
    "2023-06-02 18:00",
    [
        (
            "prevailing",
            "2023-06-01 11:40",
            "2023-06-02 18:00",
            3.0,
            1200.0,
            ("BR",),
            None,
        )
    ],
    amendment=True,
)
AMEND_1210 = bulletin(
    "A1210",
    "2023-06-01 12:10",
    "2023-06-02 18:00",
    [("prevailing", "2023-06-01 12:10", "2023-06-02 18:00", 0.5, 200.0, ("FG",), None)],
    amendment=True,
)
OBS = [
    metar("2023-06-01 08:52", wind=3.0, pressure=1017.0),
    metar("2023-06-01 09:52", wind=4.0, pressure=1016.0),
    metar("2023-06-01 10:52", wind=7.0, pressure=1014.0),
    metar("2023-06-01 11:52", wind=30.0, vis=1.0, wx=("TSRA",), pressure=1009.0),
]


def request(as_of, start, end=None):
    return pd.DataFrame(
        {
            "airport_icao": ["KATL"],
            "as_of_utc": pd.Series([ts(as_of)]).astype("datetime64[us, UTC]"),
            "target_start_utc": pd.Series([ts(start)]).astype("datetime64[us, UTC]"),
            "target_end_utc": pd.Series([None if end is None else ts(end)]).astype(
                "datetime64[us, UTC]"
            ),
        }
    )


def snap(obs, fc, req):
    out, lineage = features.snapshot(obs, fc, req)
    return out.iloc[0], lineage


def parquet_bytes(df):
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    return buf.getvalue()


# §7 test 1 and 5: METAR observed before T but available after T (11:52, available 12:02) and
# later reports never reach the snapshot at 12:00.
def test_future_and_not_yet_available_metar_are_excluded():
    row, lineage = snap(
        obs_table(*OBS),
        fc_table(ROUTINE),
        request("2023-06-01 12:00", "2023-06-01 18:00"),
    )
    assert row.metar_wind_kt == 7.0  # 10:52 report, not the 30 kt 11:52 one.
    assert row.metar_age_min == 68
    assert row.metar_visibility_min_sm_1h == 10.0
    assert not row.metar_ts_3h
    assert row.metar_pressure_tendency_3h_hpa == pytest.approx(-3.0)  # 10:52 - 08:52
    used = set(lineage.loc[lineage.feature_group == "metar_latest", "source_record_id"])
    assert used == {"m-2023-06-01 10:52"}


def test_partial_hour_uses_only_reports_available_by_t():
    obs = obs_table(
        metar("2023-06-01 11:52", vis=10.0),
        metar("2023-06-01 12:15", vis=2.0, wx=("TSRA",)),  # available 12:25
        metar("2023-06-01 12:25", vis=0.5, wx=("FG",)),  # available 12:35 > T
    )
    row, _ = snap(
        obs, fc_table(ROUTINE), request("2023-06-01 12:30", "2023-06-01 18:00")
    )
    assert row.metar_age_min == 15
    assert row.metar_visibility_sm == 2.0
    assert row.metar_visibility_min_sm_1h == 2.0
    assert row.metar_ts_3h and not row.metar_fg_3h
    assert row.metar_reports_3h == 2


# §7 test 2: an amendment issued after T cannot affect the snapshot; one issued before T supersedes.
def test_taf_amendment_after_t_is_ignored_and_before_t_supersedes():
    req = request("2023-06-01 12:00", "2023-06-01 18:00")
    row, lineage = snap(obs_table(*OBS), fc_table(ROUTINE, AMEND_1210), req)
    assert row.taf_visibility_min_sm == 6.0 and row.taf_ceiling_min_ft == 2500.0
    assert (
        row.taf_tempo
        and row.taf_ts_conditional
        and row.taf_cond_visibility_min_sm == 2.0
    )
    taf_refs = set(lineage.loc[lineage.feature_group == "taf", "source_ref"])
    assert taf_refs == {"R1130#01", "R1130#02"}

    row, lineage = snap(obs_table(*OBS), fc_table(ROUTINE, AMEND_1140, AMEND_1210), req)
    assert row.taf_visibility_min_sm == 3.0 and row.taf_ceiling_min_ft == 1200.0
    assert not row.taf_tempo  # The superseded routine's TEMPO is not resurrected.
    assert row.taf_is_amendment and row.taf_age_min == 20
    assert set(lineage.loc[lineage.feature_group == "taf", "source_ref"]) == {
        "A1140#00"
    }


# §7 test 3: a pre-T TAF valid after T is accepted; a TAF issued after T is rejected.
def test_pre_t_taf_valid_after_t_is_accepted_post_t_taf_rejected():
    row, _ = snap(
        obs_table(*OBS),
        fc_table(ROUTINE),
        request("2023-06-01 12:00", "2023-06-02 00:00"),
    )
    assert row.taf_lead_h == pytest.approx(12 + 40 / 60)
    assert row.taf_ceiling_min_ft == 2500.0 and row.status == "ok"

    row, _ = snap(
        obs_table(*OBS),
        fc_table(AMEND_1210),
        request("2023-06-01 12:00", "2023-06-01 18:00"),
    )
    assert row.reason_codes == ["taf_unavailable"] and row.status == "partial"
    assert pd.isna(row.taf_visibility_min_sm) and pd.isna(row.taf_age_min)


def test_window_beyond_bulletin_end_is_missing_not_borrowed():
    later = bulletin(
        "R1730",
        "2023-06-01 17:20",
        "2023-06-03 00:00",
        [("prevailing", "2023-06-01 17:20", "2023-06-03 00:00", 1.0, 300.0, (), None)],
    )
    row, lineage = snap(
        obs_table(*OBS),
        fc_table(ROUTINE, later),
        request("2023-06-01 12:00", "2023-06-02 18:00"),
    )
    assert row.reason_codes == ["taf_uncovered"]
    assert pd.isna(row.taf_visibility_min_sm) and pd.isna(row.taf_tempo)
    assert (lineage.feature_group != "taf").all()


def test_conflicting_bulletin_falls_back_to_previous_and_says_so():
    conflict = bulletin(
        "C1140",
        "2023-06-01 11:40",
        "2023-06-02 18:00",
        [("prevailing", "2023-06-01 11:40", "2023-06-02 18:00", 0.25, 100.0, (), None)],
        flags=("conflicting_bulletin_versions",),
    )
    row, _ = snap(
        obs_table(*OBS),
        fc_table(ROUTINE, conflict),
        request("2023-06-01 12:00", "2023-06-01 18:00"),
    )
    assert row.taf_visibility_min_sm == 6.0
    assert row.reason_codes == ["taf_conflict_fallback"]


def mutate_after(obs, fc, cutoff):
    """Change every record not available by cutoff and add new post-cutoff records."""
    obs = obs.copy()
    late = obs["available_at_utc"] > cutoff
    obs.loc[late, ["wind_kt", "visibility_sm", "pressure_hpa"]] = [99.0, 0.0, 950.0]
    obs.loc[late, "wx_codes"] = pd.Series(
        [["+TSRA"]] * late.sum(), index=obs.index[late]
    )
    fc = fc.copy()
    after = fc["available_at_utc"] > cutoff
    fc.loc[after, ["visibility_sm", "ceiling_ft"]] = [0.0, 0.0]
    obs = pd.concat(
        [
            obs,
            obs_table(
                metar(str(cutoff + pd.Timedelta(minutes=52)), wind=60.0, wx=("+TSRA",)),
                metar(
                    str(cutoff + pd.Timedelta(hours=3)), status="variable", wind=20.0
                ),
                # Observed before T but only available after it.
                metar(str(cutoff - pd.Timedelta(minutes=5)), wind=45.0, vis=0.25),
            ),
        ],
        ignore_index=True,
    )
    fc = pd.concat(
        [
            fc,
            fc_table(
                # Issued 5 min before T, available 5 min after it.
                bulletin(
                    "ISSUED_PRE_T",
                    str(cutoff - pd.Timedelta(minutes=5)),
                    "2023-06-02 18:00",
                    [
                        (
                            "prevailing",
                            str(cutoff - pd.Timedelta(minutes=5)),
                            "2023-06-02 18:00",
                            0.1,
                            100.0,
                            ("TS",),
                            None,
                        )
                    ],
                    amendment=True,
                ),
                bulletin(
                    "LATER",
                    str(cutoff + pd.Timedelta(hours=2)),
                    "2023-06-02 18:00",
                    [
                        (
                            "prevailing",
                            str(cutoff + pd.Timedelta(hours=2)),
                            "2023-06-02 18:00",
                            0.1,
                            100.0,
                            ("TS",),
                            None,
                        )
                    ],
                    amendment=True,
                ),
            ),
        ],
        ignore_index=True,
    )
    return obs, fc


# §7 test 9: adding or changing any record not available by T leaves the snapshot at T
# byte-identical. The cutoff is each request's own as_of_utc.
@pytest.mark.parametrize(
    "as_of,start,horizon",
    [
        ("2023-06-01 12:00", "2023-06-01 15:00", 3),
        ("2023-06-01 12:00", "2023-06-02 00:00", 12),
        ("2023-06-01 11:00", "2023-06-01 20:00", 9),
    ],
)
def test_mutating_post_t_records_leaves_snapshot_byte_identical(as_of, start, horizon):
    req = request(as_of, start).assign(horizon_h=horizon)
    obs, fc = obs_table(*OBS), fc_table(ROUTINE, AMEND_1210)
    base, base_lin = features.snapshot(obs, fc, req)
    out, lin = features.snapshot(*mutate_after(obs, fc, ts(as_of)), req)
    assert parquet_bytes(out) == parquet_bytes(base)
    assert parquet_bytes(lin) == parquet_bytes(base_lin)

    # Controls: the same kinds of change made to records available by T do alter the output.
    early = fc_table(
        bulletin(
            "EARLY",
            str(ts(as_of) - pd.Timedelta(minutes=15)),
            "2023-06-02 18:00",
            [
                (
                    "prevailing",
                    str(ts(as_of) - pd.Timedelta(minutes=15)),
                    "2023-06-02 18:00",
                    0.1,
                    100.0,
                    (),
                    None,
                )
            ],
            amendment=True,
        )
    )
    out, _ = features.snapshot(obs, pd.concat([fc, early], ignore_index=True), req)
    assert parquet_bytes(out) != parquet_bytes(base)
    changed = obs.copy()
    changed.loc[changed["available_at_utc"] <= ts(as_of), "wind_kt"] = 40.0
    out, _ = features.snapshot(changed, fc, req)
    assert parquet_bytes(out) != parquet_bytes(base)


def test_taf_issued_before_t_but_available_after_t_is_not_selected():
    pre = bulletin(
        "A1155",
        "2023-06-01 11:55",
        "2023-06-02 18:00",
        [
            (
                "prevailing",
                "2023-06-01 11:55",
                "2023-06-02 18:00",
                0.5,
                200.0,
                ("FG",),
                None,
            )
        ],
        amendment=True,
    )
    row, lineage = snap(
        obs_table(*OBS),
        fc_table(ROUTINE, pre),
        request("2023-06-01 12:00", "2023-06-01 18:00"),
    )
    assert row.taf_visibility_min_sm == 6.0 and row.taf_age_min == 40
    assert not lineage.source_ref.str.startswith("A1155").any()
    row, _ = snap(
        obs_table(*OBS),
        fc_table(ROUTINE, pre),
        request("2023-06-01 12:05", "2023-06-01 18:00"),
    )
    assert row.taf_visibility_min_sm == 0.5  # Selected once it is available.


def test_metar_available_exactly_at_t_is_included():
    obs = obs_table(*OBS[:3], metar("2023-06-01 11:50", wind=12.0))  # Available 12:00.
    row, _ = snap(
        obs, fc_table(ROUTINE), request("2023-06-01 12:00", "2023-06-01 18:00")
    )
    assert row.metar_wind_kt == 12.0 and row.metar_age_min == 10


def test_corrected_metar_is_never_used_and_skip_is_reported():
    obs = obs_table(
        *OBS[:3],
        metar(
            "2023-06-01 11:20", wind=25.0, vis=0.5, wx=("TSRA",), flags=("corrected",)
        ),
    )
    row, lineage = snap(
        obs, fc_table(ROUTINE), request("2023-06-01 12:00", "2023-06-01 18:00")
    )
    assert (
        row.metar_wind_kt == 7.0 and not row.metar_ts_3h
    )  # 10:52 report, not the COR.
    assert row.reason_codes == ["metar_cor_skipped"]
    assert "m-2023-06-01 11:20" not in set(lineage.source_record_id)

    # A COR too recent to have been the latest report anyway is not reported as skipped.
    obs = obs_table(*OBS[:3], metar("2023-06-01 11:55", flags=("corrected",)))
    row, _ = snap(
        obs, fc_table(ROUTINE), request("2023-06-01 12:00", "2023-06-01 18:00")
    )
    assert row.reason_codes == []


# Both id orders and both row orders, so neither id sorting nor row order can pass for the rule.
TIE_ORDERS = [
    ("a-madis", "z-official", False),
    ("z-madis", "a-official", False),
    ("a-madis", "z-official", True),
    ("z-madis", "a-official", True),
]


def tie_pair(observed, madis_rid, official_rid, official_first, **official):
    madis = metar(
        observed,
        status="missing",
        wind=np.nan,
        wind_from=np.nan,
        pressure=1000.0,
        flags=("madis_hf", "duplicate_observed_time"),
        rid=madis_rid,
    )
    off = metar(
        observed, flags=("duplicate_observed_time",), rid=official_rid, **official
    )
    return [off, madis] if official_first else [madis, off]


@pytest.mark.parametrize("madis_rid, official_rid, official_first", TIE_ORDERS)
def test_official_report_preferred_over_madis_on_observed_time_tie(
    madis_rid, official_rid, official_first
):
    obs = obs_table(
        *OBS[:2],
        *tie_pair(
            "2023-06-01 10:52", madis_rid, official_rid, official_first, wind=7.0
        ),
    )
    row, lineage = snap(
        obs, fc_table(ROUTINE), request("2023-06-01 12:00", "2023-06-01 18:00")
    )
    assert row.metar_wind_kt == 7.0 and row.metar_wind_status == "directional"
    assert set(
        lineage.loc[lineage.feature_group == "metar_latest", "source_record_id"]
    ) == {official_rid}


@pytest.mark.parametrize("madis_rid, official_rid, official_first", TIE_ORDERS)
def test_pressure_tendency_window_start_prefers_official_on_tie(
    madis_rid, official_rid, official_first
):
    # Window at T=12:00 starts with the 08:52 pair; the official report reads 1012 hPa,
    # MADIS 1000 hPa. Latest is 10:52 at 1015 hPa, so the tendency must be +3, not +15.
    obs = obs_table(
        *tie_pair(
            "2023-06-01 08:52", madis_rid, official_rid, official_first, pressure=1012.0
        ),
        metar("2023-06-01 09:52", pressure=1013.0),
        metar("2023-06-01 10:52", pressure=1015.0),
    )
    row, _ = snap(
        obs, fc_table(ROUTINE), request("2023-06-01 12:00", "2023-06-01 18:00")
    )
    assert row.metar_pressure_tendency_3h_hpa == pytest.approx(3.0)


def test_variable_taf_wind_counts_as_worst_case_tailwind():
    fc = fc_table(ROUTINE)
    fc.loc[1, ["wind_status", "wind_from_deg", "wind_kt"]] = ["variable", np.nan, 15.0]
    row, _ = snap(obs_table(*OBS), fc, request("2023-06-01 12:00", "2023-06-01 18:00"))
    assert row.taf_wind_status == "variable"
    assert row.taf_tailwind_max_kt_hdg == 15.0 and row.taf_tailwind_max_kt_rec == 15.0
    assert row.taf_crosswind_max_kt == 15.0


def test_null_target_end_means_one_hour_window():
    row, _ = snap(
        obs_table(*OBS),
        fc_table(ROUTINE),
        request("2023-06-01 12:00", "2023-06-01 16:00"),
    )
    assert row.target_end_utc == ts("2023-06-01 17:00")
    assert not row.taf_tempo  # TEMPO starts at 17:00, outside [16:00, 17:00).


def components(direction, speed, status, heading):
    return [
        s.iloc[0]
        for s in features.wind_components(
            pd.Series([direction], dtype="float64"),
            pd.Series([speed], dtype="float64"),
            pd.Series([status]),
            heading,
        )
    ]


@pytest.mark.parametrize(
    "direction,heading,expected",
    [
        (
            80,
            80,
            (10, 0, 0),
        ),  # Straight down the runway from the heading end: pure headwind.
        (260, 80, (-10, 10, 0)),  # From behind: pure tailwind.
        (260, 260, (10, 0, 0)),  # Same wind, reciprocal end.
        (170, 80, (0, 0, 10)),  # 90 degrees: pure crosswind.
        (350, 80, (0, 0, 10)),  # 90 degrees from the other side: crosswind is absolute.
        (
            350,
            10,
            (10 * np.cos(np.radians(20)), 0, 10 * np.sin(np.radians(20))),
        ),  # Wrap-around.
        (10, 350, (10 * np.cos(np.radians(20)), 0, 10 * np.sin(np.radians(20)))),
    ],
)
def test_wind_components_signs(direction, heading, expected):
    assert components(direction, 10, "directional", heading) == pytest.approx(
        expected, abs=1e-9
    )


def test_calm_variable_and_missing_wind_stay_distinct():
    assert components(np.nan, 0, "calm", 80) == [0, 0, 0]
    head, tail, cross = components(np.nan, 8, "variable", 80)
    assert (
        np.isnan(head) and np.isnan(tail) and cross == 8
    )  # Worst case: full speed across.
    assert all(np.isnan(x) for x in components(np.nan, np.nan, "missing", 80))


def test_favourable_end_uses_configured_heading_and_reciprocal():
    df = pd.DataFrame(
        {
            "airport_icao": ["KDFW"] * 3,
            "wind_from_deg": [0.0, 180.0, np.nan],
            "wind_kt": [12.0, 12.0, 6.0],
            "gust_kt": [20.0, np.nan, np.nan],
            "wind_status": ["directional", "directional", "variable"],
        }
    )
    out = features.add_components(df, "m_", "wind_kt", "gust_kt")
    assert out.m_best_end.tolist()[:2] == ["rec", "hdg"] and pd.isna(out.m_best_end[2])
    assert out.m_headwind_kt_best.tolist()[:2] == pytest.approx([12, 12])
    assert (
        out.m_tailwind_kt_hdg[0] == pytest.approx(12) and out.m_tailwind_kt_rec[0] == 0
    )
    assert out.m_gust_tailwind_kt_hdg[0] == pytest.approx(20)  # Gust where reported.
    assert out.m_gust_tailwind_kt_rec[1] == pytest.approx(
        12
    )  # Sustained speed otherwise.
    assert np.isnan(out.m_headwind_kt_best[2]) and out.m_crosswind_kt[2] == 6


def test_calendar_uses_airport_local_time():
    row, _ = snap(
        obs_table(*OBS),
        fc_table(ROUTINE),
        request("2023-06-01 12:00", "2023-06-01 16:00"),
    )
    assert (row.target_hour_utc, row.target_hour_local, row.target_weekday_local) == (
        16,
        12,
        3,
    )


def request_rows(rows):
    df = pd.DataFrame(
        rows,
        columns=[
            "prediction_id",
            "task",
            "flight_id",
            "as_of_utc",
            "target_start_utc",
            "target_end_utc",
            "horizon_h",
        ],
    )
    for c in ("as_of_utc", "target_start_utc", "target_end_utc"):
        df[c] = pd.to_datetime(df[c], utc=True).astype("datetime64[us, UTC]")
    return df.assign(
        airport_icao="KATL",
        horizon_h=df["horizon_h"].astype("int32"),
        schedule_snapshot_id="s1",
        cohort_version="v1",
        data_mode="fixture",
    )[features.REQUEST_COLUMNS]


REQUESTS = request_rows(
    [
        (
            "p1",
            "throughput",
            None,
            "2023-06-01 12:00",
            "2023-06-01 18:00",
            "2023-06-01 19:00",
            6,
        ),
        (
            "p2",
            "throughput",
            None,
            "2023-06-01 09:00",
            "2023-06-01 18:00",
            "2023-06-01 19:00",
            9,
        ),
        # A flight on the hour shares the throughput snapshot key; null end means 1 h.
        ("p3", "severe_delay", "f1", "2023-06-01 12:00", "2023-06-01 18:00", None, 6),
        ("p4", "severe_delay", "f2", "2023-06-01 12:00", "2023-06-01 18:00", None, 6),
        ("p5", "severe_delay", "f3", "2023-06-01 14:47", "2023-06-01 17:47", None, 3),
    ]
)


def test_request_path_matches_airport_hour_path_and_dedupes_keys():
    obs, fc = obs_table(*OBS), fc_table(ROUTINE, AMEND_1140)
    grid = features.airport_hour_requests(
        ["KATL"], ts("2023-06-01 17:00"), ts("2023-06-01 19:00"), [6, 9]
    )
    hourly, _ = features.snapshot(obs, fc, grid)
    out, lineage = features.request_snapshots(obs, fc, REQUESTS)
    feature_cols = [c for c in features.FEATURES if c != "airport_icao"]
    feature_cols += ["status", "reason_codes", "feature_version"]
    for pid, horizon in (("p1", 6), ("p2", 9), ("p3", 6)):
        a = out.loc[out.prediction_id == pid, feature_cols].reset_index(drop=True)
        b = hourly.loc[
            (hourly.horizon_h == horizon)
            & (hourly.target_start_utc == ts("2023-06-01 18:00")),
            feature_cols,
        ].reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b)
    assert out.snapshot_key.nunique() == 3  # p1/p3/p4 share one key.
    assert (
        out.loc[out.prediction_id == "p5", "target_hour_local"].item() == 13
    )  # 17:47Z = 13:47 EDT.
    assert pd.isna(out.loc[out.prediction_id == "p3", "target_end_utc"].item())
    p2 = out.loc[out.prediction_id == "p2"].iloc[0]
    assert (
        p2.status == "missing"
    )  # Nothing was available at 09:00, so no lineage either.
    assert p2.reason_codes == ["metar_unavailable", "taf_unavailable"]
    assert set(lineage.snapshot_key) == set(out.snapshot_key) - {p2.snapshot_key}


def dense_weather():
    """A METAR every 10 min and a TAF amendment every 30 min, each with distinct values, so any
    shift of as_of changes the selected report or bulletin."""
    start = ts("2023-06-01 05:00")
    obs = obs_table(
        *[
            metar(
                str(start + pd.Timedelta(minutes=10 * i)),
                wind=float(i),
                pressure=1000.0 + i,
            )
            for i in range(6 * 16)
        ]
    )
    fc = fc_table(
        *[
            bulletin(
                f"B{i:02d}",
                str(start + pd.Timedelta(minutes=30 * i + 5)),
                "2023-06-02 18:00",
                [
                    (
                        "prevailing",
                        str(start + pd.Timedelta(minutes=30 * i + 5)),
                        "2023-06-02 18:00",
                        0.25 + i / 10,
                        100.0 * (i + 1),
                        (),
                        None,
                    ),
                ],
                amendment=i > 0,
            )
            for i in range(32)
        ]
    )
    return obs, fc


FLIGHTS = request_rows(
    [
        (
            "t1",
            "throughput",
            None,
            "2023-06-01 12:00",
            "2023-06-01 18:00",
            "2023-06-01 19:00",
            6,
        ),
        ("f3", "severe_delay", "a", "2023-06-01 14:47", "2023-06-01 17:47", None, 3),
        ("f3b", "severe_delay", "b", "2023-06-01 13:05", "2023-06-01 16:05", None, 3),
        ("f6", "severe_delay", "c", "2023-06-01 11:13", "2023-06-01 17:13", None, 6),
        ("f9", "severe_delay", "d", "2023-06-01 08:31", "2023-06-01 17:31", None, 9),
        ("f12", "severe_delay", "e", "2023-06-01 07:22", "2023-06-01 19:22", None, 12),
        ("f6b", "severe_delay", "f", "2023-06-01 12:00", "2023-06-01 18:00", None, 6),
    ]
)
FEATURE_COLS = [c for c in features.FEATURES if c != "airport_icao"] + [
    "status",
    "reason_codes",
]


def direct(obs, fc, row):
    one = FLIGHTS[FLIGHTS.prediction_id == row.prediction_id]
    return features.snapshot(
        obs,
        fc,
        one[["airport_icao", "as_of_utc", "target_start_utc", "target_end_utc"]],
    )


# Off-the-hour flight request: data that becomes available in (as_of, next hour] must not reach
# it, and its snapshot equals a direct snapshot() at its exact as_of.
def test_flight_request_ignores_data_available_after_its_own_as_of():
    obs, fc = dense_weather()
    out, lineage = features.request_snapshots(obs, fc, FLIGHTS)
    late_obs = obs_table(
        metar("2023-06-01 14:38", wind=77.0, available="2023-06-01 14:48"),
        metar("2023-06-01 14:55", wind=88.0, vis=0.1),
    )
    late_fc = fc_table(
        bulletin(
            "LATE",
            "2023-06-01 14:45",
            "2023-06-02 18:00",
            [
                (
                    "prevailing",
                    "2023-06-01 14:45",
                    "2023-06-02 18:00",
                    0.1,
                    50.0,
                    ("TS",),
                    None,
                )
            ],
            amendment=True,
        ),
    )
    out2, lineage2 = features.request_snapshots(
        pd.concat([obs, late_obs], ignore_index=True),
        pd.concat([fc, late_fc], ignore_index=True),
        FLIGHTS,
    )
    pick = lambda df, pid: df[df.prediction_id == pid].reset_index(drop=True)
    assert parquet_bytes(pick(out2, "f3")) == parquet_bytes(pick(out, "f3"))
    key = pick(out, "f3").snapshot_key[0]
    lin = lambda df: df[df.snapshot_key == key].reset_index(drop=True)
    assert parquet_bytes(lin(lineage2)) == parquet_bytes(lin(lineage))

    row = FLIGHTS[FLIGHTS.prediction_id == "f3"].iloc[0]
    expected, _ = direct(obs, fc, row)
    pd.testing.assert_frame_equal(
        pick(out, "f3")[FEATURE_COLS], expected[FEATURE_COLS].reset_index(drop=True)
    )
    f3 = pick(out, "f3").iloc[0]
    assert (
        f3.metar_wind_kt == 57.0
    )  # 14:30 report (available 14:40); 14:40 is available 14:50.
    assert f3.taf_age_min == 12 and f3.taf_visibility_min_sm == pytest.approx(
        0.25 + 1.9
    )


def write_fixture_dir(path, obs, fc, requests):
    path.mkdir(parents=True, exist_ok=True)
    obs.to_parquet(path / "weather_observations.parquet")
    fc.to_parquet(path / "weather_forecasts.parquet")
    for name in ("weather_observations", "weather_forecasts"):
        (path / f"{name}.manifest.json").write_text(
            json.dumps({"sources": [{"sha256": name}]})
        )
    requests.to_parquet(path / "prediction_requests.parquet")


# Every written row, at every horizon, equals a direct snapshot() at that request's own as_of,
# and no lineage record was available after it.
def test_build_requests_rows_equal_direct_snapshots_at_each_requests_as_of(tmp_path):
    obs, fc = dense_weather()
    write_fixture_dir(tmp_path, obs, fc, FLIGHTS)
    summary = features.build_requests(tmp_path)
    snaps = pd.read_parquet(tmp_path / "feature_snapshots.parquet")
    lineage = pd.read_parquet(tmp_path / "feature_lineage.parquet")
    assert sorted(snaps.prediction_id) == sorted(FLIGHTS.prediction_id)
    assert (
        summary["unique_snapshot_keys"] == len(FLIGHTS) - 1
    )  # t1 and f6b share a key.
    assert snaps.metar_wind_kt.dtype == "float32"
    for _, row in FLIGHTS.iterrows():
        got = snaps[snaps.prediction_id == row.prediction_id].reset_index(drop=True)
        assert got.as_of_utc[0] == row.as_of_utc
        expected, _ = direct(obs, fc, row)
        expected = features.compact(expected[FEATURE_COLS].reset_index(drop=True))
        pd.testing.assert_frame_equal(got[FEATURE_COLS], expected)
    used = lineage.merge(snaps[["snapshot_key", "as_of_utc"]], on="snapshot_key")
    assert (used.contributing_available_at_utc <= used.as_of_utc).all()
    assert set(used.snapshot_key) == set(snaps.snapshot_key)


def test_requests_whose_as_of_disagrees_with_horizon_are_rejected():
    obs, fc = dense_weather()
    bad = FLIGHTS.copy()
    bad.loc[bad.horizon_h == 3, "as_of_utc"] += pd.Timedelta(hours=1)
    with pytest.raises(AssertionError, match="horizon"):
        features.request_snapshots(obs, fc, bad)


AUDIT_SCRIPT = """
import json, os, sys
from pathlib import Path
import airbus_challenge.features as F
import pandas, pyarrow, pyarrow.dataset, pyarrow.parquet  # noqa: F401
opened = []
def hook(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        opened.append(str(Path(os.fsdecode(args[0])).resolve()))
sys.addaudithook(hook)
F.build_requests(**json.loads(sys.argv[1]))
print(json.dumps({"module": F.__file__, "opened": opened}))
"""
COHORT = "data/processed/cohorts/loao_KATL_v1"
OUTCOME_FILES = [
    "data/processed/flights.parquet",
    "data/processed/airport_hourly.parquet",
    "data/processed/labels.parquet",
    "data/labels/labels.parquet",
    "data/raw/Flight_Data_With_Weather_Final.csv",
]


# Runs the real build in a fresh process (cold caches) inside a project folder where outcome
# tables exist but cannot be opened by anyone (mode 000), so a native pyarrow read fails too.
# A Python audit hook records every other file open; all must be on the allowlist.
# The cohort variant reads its own requests file and writes only inside its output directory.
@pytest.mark.parametrize("cohort", [False, True])
def test_request_build_opens_only_weather_requests_and_configs(tmp_path, cohort):
    repo = Path(__file__).resolve().parents[1]
    (tmp_path / "configs").mkdir()
    for cfg in (repo / "configs").glob("*.yaml"):
        (tmp_path / "configs" / cfg.name).write_text(cfg.read_text())
    obs, fc = dense_weather()
    write_fixture_dir(tmp_path / "data/processed", obs, fc, FLIGHTS)
    requests_rel = "data/processed/prediction_requests.parquet"
    kwargs, out_dir = {}, tmp_path / "data/processed"
    if cohort:
        requests_rel = f"{COHORT}/prediction_requests.parquet"
        (tmp_path / COHORT).mkdir(parents=True)
        (tmp_path / "data/processed/prediction_requests.parquet").rename(
            tmp_path / requests_rel
        )
        kwargs = {"requests_path": requests_rel, "output_dir": COHORT}
        out_dir = tmp_path / COHORT
    for rel in OUTCOME_FILES:
        decoy = tmp_path / rel
        decoy.parent.mkdir(parents=True, exist_ok=True)
        decoy.write_bytes(b"outcomes")
        decoy.chmod(0)
    cmd = [sys.executable, "-c", AUDIT_SCRIPT, json.dumps(kwargs)]
    if shutil.which("sandbox-exec"):
        # macOS: the kernel also denies native (pyarrow) reads of any outcome table, wherever it
        # lives, so an absolute path to the real data folder fails too.
        names = (
            r"/(flights|labels|airport_hourly)[^/]*\.parquet$|Flight_Data_With_Weather"
        )
        cmd = [
            "sandbox-exec",
            "-p",
            f'(version 1)(allow default)(deny file-read* (regex #"{names}"))',
            *cmd,
        ]
    run = subprocess.run(cmd, check=False, cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout.strip().splitlines()[-1])
    assert report["module"] == features.__file__
    root = tmp_path.resolve()
    allowed_inputs = {
        root / "data/processed" / n
        for n in (
            "weather_observations.parquet",
            "weather_forecasts.parquet",
            "weather_observations.manifest.json",
            "weather_forecasts.manifest.json",
        )
    } | {
        root / requests_rel,
        root / "configs/airports.yaml",
        root / "configs/experiment.yaml",
    }
    outputs = (".feature_snapshots.manifest.json.tmp",)
    bad = []
    for p in map(Path, report["opened"]):
        if p.is_relative_to(root):
            if p not in allowed_inputs and not (
                p.name in outputs and p.parent == out_dir.resolve()
            ):
                bad.append(p)
        elif "/data/" in str(p) or any(w in p.name for w in FORBIDDEN):
            bad.append(p)
    assert not bad, bad
    assert (out_dir / "feature_snapshots.parquet").exists()
    assert (out_dir / "feature_lineage.parquet").exists()
    if cohort:
        assert not (tmp_path / "data/processed/feature_snapshots.parquet").exists()
        manifest = json.loads((out_dir / "feature_snapshots.manifest.json").read_text())
        assert manifest["prediction_requests"]["path"] == requests_rel


FORBIDDEN = ("flights", "labels", "airport_hourly", "Flight_Data_With_Weather")


def test_feature_code_names_no_outcome_table():
    for module in (features, iem):
        source = Path(module.__file__).read_text()
        assert not [w for w in FORBIDDEN if w in source], module.__name__
