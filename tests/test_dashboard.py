import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
from streamlit.testing.v1 import AppTest

from airbus_challenge import dashboard_data as dd
from airbus_challenge import explain, recommend

REPO = Path(__file__).resolve().parents[1]
APP = REPO / "app/dashboard.py"
T = pd.Timestamp("2024-05-27 18:00", tz="UTC")
REAL = (
    all(
        (REPO / p).exists()
        for p in (dd.SNAPSHOTS, dd.LINEAGE, dd.HOURLY, dd.REQUESTS, dd.LABELS)
    )
    and (REPO / "artifacts/baselines_dev/predictions.parquet").exists()
)


def utc(s):
    return pd.Timestamp(s, tz="UTC")


def times(*values):
    return pd.Series(pd.to_datetime(list(values), utc=True)).astype(
        "datetime64[us, UTC]"
    )


@pytest.fixture
def root(tmp_path):
    """A tiny project: configs plus one snapshot hour at KDFW, its weather, predictions and outcomes."""
    shutil.copytree(REPO / "configs", tmp_path / "configs")
    (tmp_path / "data/processed").mkdir(parents=True)
    (tmp_path / "data/labels").mkdir()
    keys = [f"k{h}" for h in dd.HORIZONS]
    pd.DataFrame(
        {
            "prediction_id": [f"p{h}" for h in dd.HORIZONS],
            "task": "throughput",
            "airport_icao": "KDFW",
            "as_of_utc": times(*[T] * 4),
            "target_start_utc": times(
                *[T + pd.Timedelta(hours=h) for h in dd.HORIZONS]
            ),
            "horizon_h": np.array(dd.HORIZONS, dtype="int32"),
            "snapshot_key": keys,
            "status": "ok",
            "reason_codes": [["metar_cor_skipped"], [], [], []],
            "metar_age_min": np.float32(67),
            "metar_wind_status": "directional",
            "metar_headwind_kt_hdg": np.float32(4.5),
        }
    ).to_parquet(tmp_path / dd.SNAPSHOTS)
    pd.DataFrame(
        {
            "snapshot_key": ["k3", "k3", "k6"],
            "feature_group": ["metar_latest", "taf", "taf"],
            "source_record_id": ["m1", "s0", "s1"],
            "source_ref": ["x", "B1#00", "B1#01"],
            "contributing_available_at_utc": times(
                "2024-05-27 17:03", "2024-05-27 17:41", "2024-05-27 17:41"
            ),
        }
    ).to_parquet(tmp_path / dd.LINEAGE)
    pd.DataFrame(
        {
            "source_record_id": ["m1", "m2"],
            "observed_at_utc": times("2024-05-27 16:53", "2024-05-27 18:53"),
            "available_at_utc": times("2024-05-27 17:03", "2024-05-27 19:03"),
            "raw_metar": ["KDFW 271653Z 12009KT 8SM FEW020", "KDFW 271853Z FUTURE"],
            "availability_basis": "simulated",
            "wind_status": "directional",
            "wind_from_deg": 120.0,
            "wind_kt": 9.0,
            "gust_kt": np.nan,
        }
    ).to_parquet(tmp_path / dd.OBSERVATIONS)
    issued, avail = utc("2024-05-27 17:31"), utc("2024-05-27 17:41")
    pd.DataFrame(
        {
            "bulletin_id": "B1",
            "segment_id": ["00", "01", "02"],
            "issued_at_utc": times(issued, issued, issued),
            "available_at_utc": times(avail, avail, avail),
            "availability_basis": "simulated",
            "is_amendment": False,
            "is_correction": False,
            "forecast_type": ["prevailing", "FM", "FM"],
            "probability": np.nan,
            "valid_from_utc": times(issued, "2024-05-27 23:00", "2024-05-28 10:00"),
            "valid_to_utc": times(
                "2024-05-27 23:00", "2024-05-28 10:00", "2024-05-29 00:00"
            ),
            "bulletin_valid_to_utc": times(*["2024-05-29 00:00"] * 3),
            "raw_group": [
                "12009KT 6SM HZ",
                "FM272300 VCTS SCT050CB",
                "FM281000 SCT250",
            ],
        }
    ).to_parquet(tmp_path / dd.FORECASTS)
    hours = times(*[T + pd.Timedelta(hours=i) for i in range(13)])
    pd.DataFrame(
        {
            "airport_icao": "KDFW",
            "hour_start_utc": hours,
            "scheduled_arrivals": np.arange(13, dtype="int32") + 50,
            "scheduled_arrivals_coverage_status": "complete_for_source_scope",
            "schedule_knowledge_basis": "retrospective_schedule",
            "scheduled_departures": np.int32(40),
            "reporting_carrier_touchdowns": np.int32(30),
            "coverage_status": "complete_for_source_scope",
        }
    ).to_parquet(tmp_path / dd.HOURLY)
    run = tmp_path / dd.ARTIFACTS / "fixture_run"
    run.mkdir(parents=True)
    pd.DataFrame(
        {
            "prediction_id": [f"p{h}" for h in dd.HORIZONS],
            "task": "throughput",
            "airport_icao": "KDFW",
            "as_of_utc": times(*[T] * 4),
            "target_start_utc": times(
                *[T + pd.Timedelta(hours=h) for h in dd.HORIZONS]
            ),
            "horizon_h": np.array(dd.HORIZONS, dtype="int32"),
            "target_kind": "reporting_carrier_touchdowns",
            "estimate": [31.0, np.nan, 25.0, 2.0],
            "p10": np.nan,
            "p90": np.nan,
            "unit": "touchdowns/hour",
            "status": ["available", "unavailable", "available", "available"],
            "reason_codes": [
                ["simulated_feed"],
                ["simulated_feed", "source_hour_incomplete"],
                [],
                [],
            ],
            "model_version": "baseline_persistence_v1",
            "feature_version": "baseline-v1",
            "generated_at_utc": times(*[T] * 4),
        }
    ).to_parquet(run / "predictions.parquet")
    pd.DataFrame(
        {
            "prediction_id": ["f1", "f2", "f3", "f4"],
            "task": "severe_delay",
            "airport_icao": "KDFW",
            "horizon_h": np.int32(3),
            "target_start_utc": times(
                "2024-05-28 00:10",
                "2024-05-28 00:20",
                "2024-05-28 00:40",
                "2024-05-28 01:05",
            ),
        }
    ).to_parquet(tmp_path / dd.REQUESTS)
    pd.DataFrame(
        {
            "prediction_id": ["f1", "f2", "f3", "f4"],
            "target_kind": "departure_delay_gt45",
            "y_true": [1.0, 0.0, np.nan, 1.0],
            "eligible": [True, True, False, True],
            "exclusion_reason": [None, None, "cancelled", None],
        }
    ).to_parquet(tmp_path / dd.LABELS)
    return tmp_path


# (b) loaders on fixtures --------------------------------------------------------------------


def test_evidence_uses_lineage_records_and_taf_segments_covering_the_next_12h(root):
    ev = dd.load_evidence(root, "KDFW", T)
    assert list(ev["snapshots"].horizon_h) == [3, 6, 9, 12]
    assert (
        ev["metar"]["raw_metar"] == "KDFW 271653Z 12009KT 8SM FEW020"
    )  # Not the 18:53 report.
    assert ev["taf"]["bulletin"]["bulletin_id"] == "B1"
    assert list(ev["taf"]["segments"].segment_id) == [
        "00",
        "01",
    ]  # 02 starts after T+13 h.
    assert dd.load_evidence(root, "KDFW", T + pd.Timedelta(hours=1))["snapshots"].empty


def test_runway_winds_per_end_and_wind_status_notes(root):
    snap = pd.Series(
        {"metar_wind_status": "directional", "metar_headwind_kt_hdg": 4.5,
         "metar_tailwind_kt_hdg": 0.0, "metar_tailwind_kt_rec": 4.5,
         "metar_crosswind_kt": 7.8, "metar_best_end": "hdg"}
    )  # fmt: skip
    w = dd.runway_winds(root, "KDFW", snap)
    assert list(w["runway end (heading °)"]) == ["180", "000"]
    assert list(w["headwind (kt)"]) == [4.5, -4.5] and list(w["favourable end"]) == [
        True,
        False,
    ]
    variable = snap.copy()
    variable[["metar_wind_status", "metar_headwind_kt_hdg", "metar_best_end"]] = [
        "variable",
        np.nan,
        None,
    ]
    w = dd.runway_winds(root, "KDFW", variable)
    assert w["headwind (kt)"].isna().all() and "worst case" in w.note[0]
    calm = snap.copy()
    calm["metar_wind_status"] = "calm"
    assert "Calm" in dd.runway_winds(root, "KDFW", calm).note[0]


def test_forecast_table_marks_unavailable_rows_as_insufficient_data(root):
    preds = dd.load_predictions(root, "fixture_run", "KDFW", T)
    table = dd.forecast_table(preds, dd.load_schedule(root, "KDFW", T))
    assert list(table.horizon_h) == [3, 6, 9, 12]
    six = table[table.horizon_h == 6].iloc[0]
    assert pd.isna(six.shown) and six.note == "insufficient data"
    assert list(table.scheduled_arrivals) == [53, 56, 59, 62]
    assert set(table.kind) == {"baseline"}
    assert dd.load_predictions(
        root, "fixture_run", "KDFW", utc("2023-08-11 08:00")
    ).empty
    assert dd.list_runs(root) == ["fixture_run"]
    assert dd.load_advisories(root, "fixture_run", "KDFW", T) is None


def test_departure_outcomes_exclude_cancelled_flights_from_the_share(root):
    out = dd.load_replay_outcomes(root, "KDFW", T)
    dep = out["departures"].set_index("hour_start_utc")
    zero = dep.loc[utc("2024-05-28 00:00")]
    assert (
        zero.scheduled_departures,
        zero.operated_with_outcome,
        zero.delayed_gt45,
        zero.cancelled,
    ) == (3, 2, 1, 1)
    assert zero.severe_delay_share == 0.5
    assert len(out["hourly"]) == 13


# Product outputs: advisories, brief, failure cases -------------------------------------------


def test_advisory_from_saved_rows_abstains_without_reference_and_reads_saved_table(
    root,
):
    rows = dd.load_run_rows(root, "fixture_run", "KDFW", T)
    assert dd.advisory_models(rows) == ["baseline_persistence_v1"]
    rec = recommend.recommend(dd.advisory_rows(rows), dd.load_reference(root))
    assert (
        rec["level"] == "abstain"
        and rec["threshold_label"] == "provisional_until_WP-D7"
    )
    comps = dd.component_table(rec)
    six = comps[comps.horizon_h.eq(6)].iloc[0]
    assert six.level == "abstain" and "source_hour_incomplete" in six.reasons
    assert comps[comps.kind.eq("severe_delay")].iloc[0].reasons == "no_prediction_rows"
    assert rec["cancellation"] is None
    recommend.advisories([rec]).to_parquet(
        root / dd.ARTIFACTS / "fixture_run/advisories.parquet"
    )
    saved = dd.load_advisories(root, "fixture_run", "KDFW", T)
    assert len(saved) == len(comps) and set(saved.threshold_label) == {
        "provisional_until_WP-D7"
    }


def test_advisory_rows_keep_one_model_per_kind_candidate_first():
    preds = pd.DataFrame(
        {
            "target_kind": ["reporting_carrier_touchdowns"] * 3 + ["cancellation"] * 2,
            "model_version": ["baseline_persistence_v1", "candidate_v1", "baseline_clim_v1",
                              "baseline_canc_v1", "canc_v1"],
        }
    )  # fmt: skip
    assert dd.advisory_models(preds) == ["candidate_v1", "baseline_clim_v1", "baseline_persistence_v1"]  # fmt: skip
    picked = dd.advisory_rows(preds).groupby("target_kind").model_version.unique()
    assert picked.map(list).to_dict() == {
        "cancellation": ["canc_v1"],
        "reporting_carrier_touchdowns": ["candidate_v1"],
    }
    chosen = dd.advisory_rows(preds, "baseline_persistence_v1")
    assert set(chosen.model_version) == {"baseline_persistence_v1", "canc_v1"}


REC = {
    "airport_icao": "KDFW", "as_of_utc": T.isoformat(), "level": "normal",
    "threshold_label": "provisional_until_WP-D7", "cancellation": None,
    "components": [{"kind": "throughput", "level": "normal", "message": "ok", "reasons": [],
                    "horizon_h": 3, "unit": "touchdowns/hour",
                    "timestamps": {"target_start_utc": "2024-05-27T21:00:00+00:00"},
                    "numbers": {"estimate": 50.0, "p10": 45.0, "p90": 55.0,
                                "clear_weather_p95": 52.0, "ratio_estimate": 0.96}}],
}  # fmt: skip
DRIVERS = [{"feature": "metar_crosswind_kt", "value": 18.0, "contribution": -3.1,
            "contribution_scale": "touchdowns/hour"}]  # fmt: skip


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(explain, "load_dotenv", lambda: None)
    monkeypatch.setattr(explain, "OpenAI", lambda **_: pytest.fail("no network calls"))


def test_brief_path_template_by_default_and_insufficient_data_without_drivers(
    no_key, root
):
    stamps = {"as_of_utc": T.isoformat()}
    assert dd.load_drivers(root, "fixture_run", ["p3"]) == []
    out = dd.make_brief(REC, DRIVERS, stamps)
    assert out["path"] == "template" and out["reason"] == ["LLM not requested"]
    assert "metar_crosswind_kt" in out["text"]
    out = dd.make_brief(REC, [], stamps)
    assert out["path"] == "insufficient_data" and "no SHAP drivers" in out["reason"]
    out = dd.make_brief(REC, DRIVERS, stamps, use_llm=True)  # Clicked, but no key.
    assert out["path"] == "template" and out["reason"] == ["no OPENAI_API_KEY"]


def test_drivers_and_brief_timestamps_from_run_artifacts(root):
    pd.DataFrame(
        {"prediction_id": ["p3", "p3", "p9"], "feature": ["a", "b", "c"],
         "value": [1.0, 2.0, 3.0], "contribution": [0.1, -0.5, 9.0],
         "contribution_scale": "touchdowns/hour"}
    ).to_parquet(root / dd.ARTIFACTS / "fixture_run" / dd.DRIVERS)  # fmt: skip
    assert [d["feature"] for d in dd.load_drivers(root, "fixture_run", ["p3"])] == [
        "b",
        "a",
    ]
    ev = dd.load_evidence(root, "KDFW", T)
    stamps = dd.brief_timestamps(
        T, ev, dd.load_run_rows(root, "fixture_run", "KDFW", T)
    )
    assert stamps == {
        "as_of_utc": "2024-05-27T18:00:00+00:00",
        "metar_available_at_utc": "2024-05-27T17:03:00+00:00",
        "taf_available_at_utc": "2024-05-27T17:41:00+00:00",
        "predictions_generated_at_utc": "2024-05-27T18:00:00+00:00",
    }


def test_failure_cases_present_and_missing(root):
    assert dd.list_failure_files(root) == []
    assert dd.load_failure_cases(root / "reports/failure_cases_dev.json") is None
    case = {
        "prediction_id": "p1", "model": "candidate_v1", "target": "reporting_carrier_touchdowns",
        "target_label": "arrival throughput (AAR proxy)", "airport": "KATL", "horizon": 12,
        "as_of_utc": "2024-03-05T03:00:00Z", "target_start_utc": "2024-03-05T15:00:00Z",
        "prediction": {"estimate": 50.0, "p10": 45.0, "p90": 55.0, "unit": "touchdowns/hour"},
        "outcome": {"y_true": 30.0, "error": 20.0, "abs_error": 20.0},
        "explanation_status": "ok", "advisory_possible": False,
        "advisory_reason": "no adverse weather feature or wide interval at T: nothing to act on",
        "limitations": [{"code": "outside_interval", "text": "outcome outside the p10-p90 interval"}],
        "known_at_issue": {"source_ages_min": {"metar_age_min": 20.0, "taf_age_min": None},
                           "sources": [{"feature_group": "taf", "source_ref": "B#00",
                                        "available_at_utc": "2024-03-05T02:41:00Z", "age_min": 19.0}]},
    }  # fmt: skip
    path = root / "reports/fixture/failure_cases_dev.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"run_id": "failures-x", "cases": [case]}))
    assert dd.list_failure_files(root) == [path]
    v = dd.failure_case_view(dd.load_failure_cases(path)["cases"][0])
    assert (
        v["summary"]["estimate"],
        v["summary"]["outcome"],
        v["summary"]["error"],
    ) == (50.0, 30.0, 20.0)
    assert v["advisory_possible"] is False and v["advisory_reason"].startswith(
        "no adverse"
    )
    assert v["limitations"] == [
        "outside_interval: outcome outside the p10-p90 interval"
    ]
    assert v["source_ages_min"]["metar_age_min"] == 20.0 and v[
        "sources"
    ].age_min.tolist() == [19.0]
    empty = dd.failure_case_view(case | {"known_at_issue": None})
    assert empty["sources"].empty and empty["source_ages_min"] == {}


# (c) forecast and evidence loaders never read outcomes; (d) only the replay loader does --------


def spy_reads(monkeypatch):
    reads = []
    real = dd._read

    def spy(path, columns=None, filter=None):
        cols = columns if columns is not None else pq.read_schema(path).names
        reads.append((Path(path), set(cols)))
        return real(path, columns, filter)

    monkeypatch.setattr(dd, "_read", spy)
    return reads


def test_forecast_and_evidence_loaders_read_no_outcome_file_or_column(
    root, monkeypatch
):
    reads = spy_reads(monkeypatch)
    dd.load_evidence(root, "KDFW", T)
    dd.forecast_table(
        dd.load_predictions(root, "fixture_run", "KDFW", T),
        dd.load_schedule(root, "KDFW", T),
    )
    dd.load_advisories(root, "fixture_run", "KDFW", T)
    dd.load_run_rows(root, "fixture_run", "KDFW", T)
    dd.load_reference(root)
    assert reads, "loaders must read through _read"
    for path, cols in reads:
        assert path.relative_to(root).as_posix() not in dd.OUTCOME_FILES | {dd.REQUESTS}
        assert not cols & dd.OUTCOME_COLUMNS, (path, cols & dd.OUTCOME_COLUMNS)

    reads.clear()
    dd.load_replay_outcomes(root, "KDFW", T)
    paths = {p.relative_to(root).as_posix() for p, _ in reads}
    assert dd.LABELS in paths and any(c & dd.OUTCOME_COLUMNS for _, c in reads)


def test_dashboard_data_reads_parquet_only_through_read():
    source = Path(dd.__file__).read_text()
    assert source.count("ds.dataset(") == 1
    assert "read_parquet" not in source and "read_table" not in source


# (a) the app renders headlessly ----------------------------------------------------------------


@pytest.mark.skipif(
    not REAL,
    reason="needs processed data and artifacts/baselines_dev (run airbus_challenge.baselines)",
)
def test_app_default_case_renders_and_does_not_load_outcomes(monkeypatch):
    calls = []
    real = dd.load_replay_outcomes
    monkeypatch.setattr(
        dd, "load_replay_outcomes", lambda *a: calls.append(a) or real(*a)
    )
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.run()
    assert not at.exception
    assert at.title[0].value == "KDFW: next 12 hours from 2024-05-27 18:00Z"
    assert [h.value for h in at.header][:3] == [
        "Known at T",
        "Forecast for the next 12 h",
        "Advisories",
    ]
    assert at.code[0].value.startswith("KDFW 271653Z")
    assert any(
        "arrival throughput (AAR proxy)" in str(d.value.columns.tolist())
        for d in at.dataframe
    )
    assert not calls  # Hindsight data is not loaded until the user asks.
    outcome_tables = lambda: [
        d for d in at.dataframe if "reporting_carrier_touchdowns" in d.value.columns
    ]
    assert not outcome_tables()

    at.toggle(key="show_outcomes").set_value(True).run()
    assert not at.exception and len(calls) == 1
    assert len(outcome_tables()) == 1


@pytest.mark.skipif(
    not REAL,
    reason="needs processed data and artifacts/baselines_dev (run airbus_challenge.baselines)",
)
def test_app_case_without_predictions_says_so():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    at.button(key="case_1").click().run()  # KATL 2023-08-11 08:00Z, train split.
    assert not at.exception
    assert at.title[0].value == "KATL: next 12 hours from 2023-08-11 08:00Z"
    assert any("No predictions for this period" in w.value for w in at.warning)
    assert at.code[0].value.startswith("KATL 110652Z")


def test_replay_rejects_locked_test_before_reading_outcomes(root, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("test-period outcomes must not be opened")

    monkeypatch.setattr(dd, "_read", forbidden)
    with pytest.raises(ValueError, match="Locked test outcomes"):
        dd.load_replay_outcomes(root, "KDFW", pd.Timestamp("2024-12-31T12:00Z"))
    assert dd.replay_window_is_development(root, pd.Timestamp("2024-12-31T11:00Z"))


def test_default_run_prefers_the_combined_model_run():
    assert dd.default_run_index(["baselines_dev", "lgbm_dev", "lgbm_throughput_dev"]) == 1
    assert dd.default_run_index(["baselines_dev", "lgbm_delay_dev", "lgbm_throughput_dev"]) == 2
    assert dd.default_run_index(["baselines_dev"]) == 0


def test_advisory_cards_show_worst_level_and_missing_outcomes():
    rec = {
        "components": [
            {"kind": "throughput", "level": "normal", "horizon_h": 3, "message": "m"},
            {"kind": "throughput", "level": "watch", "horizon_h": 6, "message": "m"},
            {"kind": "severe_delay", "level": "abstain", "message": "m",
             "reasons": ["no_prediction_rows"]},
        ],
        "cancellation": None,
    }  # fmt: skip
    cards = {c["title"]: c for c in dd.advisory_cards(rec)}
    assert cards["Arrival throughput (AAR proxy)"]["value"] == "WATCH"
    assert cards["Severe delay (>45 min, if operated)"]["value"] == "ABSTAIN"
    assert "no_prediction_rows" in cards["Severe delay (>45 min, if operated)"]["detail"]
    assert cards["Cancellation (reported separately)"]["value"] == "NO DATA"
