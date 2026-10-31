"""TEMPORAL_RULES.md §7 tests 1, 2, 3, 5 and 9 for weather features, plus wind components.

Test 4 (future flight statuses) is out of scope here: weather features read no flight data.
"""

import io

import numpy as np
import pandas as pd
import pytest

from airbus_challenge import features

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


def test_official_report_preferred_over_madis_on_observed_time_tie():
    obs = obs_table(
        *OBS[:2],
        metar(
            "2023-06-01 10:52",
            status="missing",
            wind=np.nan,
            wind_from=np.nan,
            flags=("madis_hf", "duplicate_observed_time"),
            rid="a-madis",
        ),
        metar(
            "2023-06-01 10:52",
            wind=7.0,
            flags=("duplicate_observed_time",),
            rid="z-official",
        ),
    )
    row, lineage = snap(
        obs, fc_table(ROUTINE), request("2023-06-01 12:00", "2023-06-01 18:00")
    )
    assert row.metar_wind_kt == 7.0 and row.metar_wind_status == "directional"
    assert set(
        lineage.loc[lineage.feature_group == "metar_latest", "source_record_id"]
    ) == {"z-official"}


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
