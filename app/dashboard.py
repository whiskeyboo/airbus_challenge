"""Historical replay dashboard: what was known at issue time T, the forecast, and (on request)
what actually happened. Run with: uv run streamlit run app/dashboard.py"""

import json
import time
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from airbus_challenge import dashboard_data as dd
from airbus_challenge import recommend

ROOT = Path(__file__).resolve().parents[1]
CASES = dd.load_cases(ROOT / "app/cases.yaml")
AIRPORTS = dd.airports(ROOT)
LABEL = dd.THROUGHPUT_LABEL
timings: dict[str, float] = {}


def timed(name, fn, *args):
    start = time.perf_counter()
    out = fn(*args)
    timings[name] = time.perf_counter() - start
    return out


@st.cache_data(show_spinner=False)
def evidence(icao: str, t: pd.Timestamp) -> dict:
    return dd.load_evidence(ROOT, icao, t)


@st.cache_data(show_spinner=False)
def forecast(run: str, icao: str, t: pd.Timestamp) -> pd.DataFrame:
    return dd.forecast_table(
        dd.load_predictions(ROOT, run, icao, t), dd.load_schedule(ROOT, icao, t)
    )


@st.cache_data(show_spinner=False)
def advisories(run: str, icao: str, t: pd.Timestamp):
    return dd.load_advisories(ROOT, run, icao, t)


@st.cache_data(show_spinner=False)
def run_rows(run: str, icao: str, t: pd.Timestamp) -> pd.DataFrame:
    return dd.load_run_rows(ROOT, run, icao, t)


@st.cache_data(show_spinner=False)
def reference():
    return dd.load_reference(ROOT)


@st.cache_data(show_spinner=False)
def replay_outcomes(icao: str, t: pd.Timestamp) -> dict:
    return dd.load_replay_outcomes(ROOT, icao, t)


def set_case(case: dict) -> None:
    t = pd.Timestamp(case["t"])
    st.session_state.airport = case["airport"]
    st.session_state.day = t.date()
    st.session_state.hour = t.hour
    st.session_state.show_outcomes = False  # Hindsight is opted into per case.


def fmt_t(t) -> str:
    return "–" if pd.isna(t) else pd.Timestamp(t).strftime("%Y-%m-%d %H:%MZ")


def fmt(x, unit: str, digits: int = 0) -> str:
    return "–" if x is None or pd.isna(x) else f"{x:.{digits}f} {unit}"


# Sidebar ------------------------------------------------------------------------------------

st.set_page_config(page_title="Airport capacity and delay risk: replay", layout="wide")
if "airport" not in st.session_state:
    set_case(CASES[0])
with st.sidebar:
    st.header("Issue time T")
    icao = st.selectbox("Airport", list(AIRPORTS), key="airport")
    day = st.date_input(
        "Date (UTC)", key="day", min_value=date(2023, 1, 1), max_value=date(2025, 7, 31)
    )
    hour = st.selectbox(
        "Hour (UTC)", list(range(24)), key="hour", format_func=lambda h: f"{h:02d}:00Z"
    )
    t = pd.Timestamp(day).tz_localize("UTC") + pd.Timedelta(hours=hour)
    local = dd.local_time(ROOT, icao, t)
    st.markdown(
        f"**T = {t:%Y-%m-%d %H:%M} UTC**  \n{local:%Y-%m-%d %H:%M %Z} at {icao}"
    )
    runs = dd.list_runs(ROOT)
    run = st.selectbox("Prediction run", runs, key="run") if runs else None
    st.caption(
        "Historical replay, not live data. Weather counts as available 10 min after "
        "observation or issue (simulated latency)."
    )

st.title(f"{icao}: next 12 hours from {t:%Y-%m-%d %H:%MZ}")
st.caption(
    "Advisory information for review by a traffic management coordinator. It does not issue "
    "clearances or start traffic management initiatives."
)
st.warning(
    "Development demonstration: candidate models used H1 2024 for early stopping, although "
    "their recorded fit cutoff is 1 January 2024. Validation scores are not independent; "
    "some degraded predictions have no validated fallback. Treat these outputs as provisional."
)
replay_tab, cases_tab, eval_tab = st.tabs(
    ["Replay at T", "Failure cases", "Evaluation (read-only)"]
)

# Replay at T --------------------------------------------------------------------------------

with replay_tab:
    st.header("Known at T")
    ev = timed("evidence", evidence, icao, t)
    snaps = ev["snapshots"]
    if snaps.empty:
        st.warning(f"Insufficient data: no weather snapshot for {icao} at {fmt_t(t)}.")
    else:
        first = snaps.iloc[0]
        st.markdown(
            f"**Weather status:** `{first.status}`: {dd.STATUS.get(first.status, '')}"
        )
        codes = sorted({c for rc in snaps.reason_codes for c in rc})
        for line in dd.reason_text(codes):
            st.markdown(f"- {line}")
        metar_col, taf_col = st.columns(2)
        with metar_col:
            st.subheader("Latest METAR")
            m = ev["metar"]
            if m is None:
                st.info("No METAR available at T.")
            else:
                st.code(m["raw_metar"], language=None)
                st.markdown(
                    f"Observed {fmt_t(m['observed_at_utc'])}, available {fmt_t(m['available_at_utc'])} "
                    f"({m['availability_basis']}, 10-min latency). Age at T: "
                    f"{fmt(first.metar_age_min, 'min')}. Wind status: **{first.metar_wind_status}**."
                )
            winds = dd.runway_winds(ROOT, icao, first)
            st.markdown(
                f"Runway-relative wind at T (runway heading {AIRPORTS[icao]['runway_heading_deg']}°, "
                "used as given; true vs magnetic unconfirmed)"
            )
            st.dataframe(
                winds.drop(columns=["wind_status", "note"]).round(1), hide_index=True
            )
            if winds.note[0]:
                st.caption(winds.note[0])
        with taf_col:
            st.subheader("TAF in force at T")
            taf = ev["taf"]
            if taf is None:
                st.info("Insufficient data: no TAF available at T.")
            else:
                b = taf["bulletin"]
                kind = (
                    "correction" if b["is_correction"]
                    else "amendment" if b["is_amendment"] else "routine"
                )  # fmt: skip
                st.markdown(
                    f"`{b['bulletin_id']}` ({kind}). Issued {fmt_t(b['issued_at_utc'])}, available "
                    f"{fmt_t(b['available_at_utc'])} ({b['availability_basis']}). Age at T: "
                    f"{fmt(first.taf_age_min, 'min')}. Valid to {fmt_t(b['bulletin_valid_to_utc'])}."
                )
                segs = taf["segments"].assign(
                    valid_from=lambda d: d.valid_from_utc.map(fmt_t),
                    valid_to=lambda d: d.valid_to_utc.map(fmt_t),
                )
                st.dataframe(
                    segs[
                        [
                            "forecast_type",
                            "probability",
                            "valid_from",
                            "valid_to",
                            "raw_group",
                        ]
                    ],
                    hide_index=True,
                )
        st.markdown("**TAF for each target hour** (worst case over the hour)")
        per_hour = pd.DataFrame(
            {
                "target hour (UTC)": snaps.target_start_utc.map(fmt_t),
                "lead (h)": snaps.horizon_h,
                "visibility min (sm)": snaps.taf_visibility_min_sm,
                "ceiling min (ft)": snaps.taf_ceiling_min_ft,
                "crosswind max (kt)": snaps.taf_crosswind_max_kt,
                "tailwind max hdg end (kt)": snaps.taf_tailwind_max_kt_hdg,
                "tailwind max rec end (kt)": snaps.taf_tailwind_max_kt_rec,
                "TS prevailing": snaps.taf_ts_prevailing,
                "TS in TEMPO/PROB": snaps.taf_ts_conditional,
                "PROB max": snaps.taf_prob_max,
                "status": snaps.status,
            }
        )
        st.dataframe(per_hour.round(1), hide_index=True)

    st.header("Forecast for the next 12 h")
    if run is None:
        st.info("No prediction runs found in artifacts/.")
    else:
        table = timed("forecast", forecast, run, icao, t)
        if table.empty:
            st.warning(
                f"No predictions for this period in run `{run}`. Dev baselines cover only the "
                "validation (H1 2024) and calibration (H2 2024) splits."
            )
        else:
            fig = go.Figure()
            sched = table.drop_duplicates("target_start_utc")
            fig.add_bar(
                x=sched.target_start_utc, y=sched.scheduled_arrivals, name="scheduled arrivals",
                marker_color="lightgray",
            )  # fmt: skip
            for model, rows in table.groupby("model_version"):
                kind = rows.kind.iloc[0]
                err = None
                if rows.p90.notna().any():
                    err = {
                        "type": "data",
                        "array": rows.p90 - rows.shown,
                        "arrayminus": rows.shown - rows.p10,
                    }
                fig.add_scatter(
                    x=rows.target_start_utc, y=rows.shown, mode="lines+markers",
                    name=f"{model} ({kind})", error_y=err,
                )  # fmt: skip
            fig.update_layout(
                title=f"Predicted {LABEL} vs scheduled arrivals, issued at {fmt_t(t)}",
                xaxis_title="target hour (UTC)", yaxis_title="arrivals per hour",
                legend_orientation="h",
            )  # fmt: skip
            st.plotly_chart(fig, key="forecast_chart")
            if (table.status == "unavailable").any():
                st.warning(
                    "Some rows have insufficient data; they are blank in the chart."
                )
            shown = table.assign(
                **{
                    "target hour (UTC)": table.target_start_utc.map(fmt_t),
                    f"{LABEL} (touchdowns/h)": table.shown.round(1),
                    "reasons": table.reason_codes.map(
                        lambda r: ", ".join(r) if len(r) else ""
                    ),
                }
            )
            st.dataframe(
                shown[["model_version", "kind", "horizon_h", "target hour (UTC)",
                       f"{LABEL} (touchdowns/h)", "p10", "p90", "status", "note", "reasons",
                       "scheduled_arrivals"]],
                hide_index=True,
            )  # fmt: skip
            st.caption(
                "Scheduled arrivals are the retrospective BTS schedule (as flown), not a schedule "
                "snapshot known at T. The AAR proxy reflects demand as well as capacity."
            )
            for line in dd.reason_text(
                sorted({c for rc in table.reason_codes for c in rc})
            ):
                st.caption(line)

    st.header("Advisories")
    rows = timed("run_rows", run_rows, run, icao, t) if run else pd.DataFrame()
    rec = None
    if run is None:
        st.info(
            f"Predictions {dd.not_generated('train')} (or `airbus_challenge.baselines`)."
        )
    elif rows.empty:
        st.info(
            f"No prediction rows for {icao} at {fmt_t(t)} in run `{run}`: no advisory."
        )
    else:
        models = dd.advisory_models(rows)
        model = st.selectbox("Throughput model for the advisory", models, key="adv_model") if models else None  # fmt: skip
        used = dd.advisory_rows(rows, model)
        # The run's WP-D7 calibration.json when present, else the provisional thresholds.
        policy = recommend.load_policy(ROOT / dd.ARTIFACTS / run)
        rec = recommend.recommend(used, reference(), policy)
        if rec["threshold_label"] == recommend.THRESHOLD_LABEL:
            st.warning(
                "This run has no calibrated alert policy. Its provisional advisory levels "
                "are for demonstration and are not validated for operational use."
            )
        st.subheader(f"Level: {rec['level'].upper()}")
        (st.warning if rec["level"] in ("abstain", "watch", "act") else st.success)(
            rec["message"]
        )
        st.caption(
            f"Computed by code rules in recommend.py from the saved prediction rows. Thresholds "
            f"are `{rec['threshold_label']}`: {rec['thresholds']['source']}."
        )
        comps = dd.component_table(rec)
        abstain = comps[comps.level.eq("abstain")]
        for _, c in abstain.iterrows():
            st.markdown(f"- **abstain** ({c.kind}): {c.reasons or 'no reason given'}")
        st.dataframe(comps, hide_index=True)
        st.markdown(f"**Thresholds** (`{rec['threshold_label']}`)")
        st.json({k: v for k, v in rec["thresholds"].items() if k not in ("label", "source")},
                expanded=False)  # fmt: skip
        canc = rec["cancellation"]
        st.markdown("**Cancellation** (reported separately; no alert rule; severe-delay "
                    "probability is conditional on the flight operating)")  # fmt: skip
        if canc is None:
            st.info("No cancellation predictions in this run.")
        else:
            st.json(canc["numbers"], expanded=False)
        if rec["ignored_target_kinds"]:
            st.caption(
                f"Ignored target kinds: {', '.join(rec['ignored_target_kinds'])}"
            )
        saved = timed("advisories", advisories, run, icao, t)
        with st.expander("Saved advisories.parquet for this run"):
            if saved is None:
                st.info(dd.not_generated(f"recommend --run {run}"))
            else:
                st.dataframe(saved, hide_index=True)

    st.header("Brief")
    if rec is None:
        st.info("No advisory, so no brief.")
    else:
        drivers = dd.load_drivers(ROOT, run, used["prediction_id"])
        if not drivers:
            st.caption(
                f"No per-prediction SHAP drivers ({dd.DRIVERS}) in run `{run}`; global gain "
                "importance is not a per-prediction driver, so the brief says insufficient data."
            )
        stamps = dd.brief_timestamps(t, ev, used)
        key = ("brief_llm", run, icao, str(t), model)
        if st.button("Write brief with LLM (network call)", key="brief_llm"):
            st.session_state[key] = dd.make_brief(rec, drivers, stamps, use_llm=True)
        b = st.session_state.get(key) or dd.make_brief(rec, drivers, stamps)
        st.markdown(
            f"Path: **{b['path']}**"
            + (f" ({'; '.join(b['reason'])})" if b["reason"] else "")
        )
        st.write(b["text"])
        st.caption("SHAP drivers are associations, not causes. Every number in the brief comes "
                   "from code; the LLM only writes words and is checked against the facts.")  # fmt: skip

    with st.expander(
        "What actually happened (hindsight: not known at T)", expanded=False
    ):
        st.caption(
            "Realised outcomes, for replay review only. Never used by the forecast above."
        )
        if st.toggle(
            "Load realised outcomes", key="show_outcomes"
        ) and not dd.replay_window_is_development(ROOT, t):
            st.warning(
                "Locked 2025 outcomes are unavailable in this development replay."
            )
        elif st.session_state.show_outcomes:
            out = timed("replay_outcomes", replay_outcomes, icao, t)
            hourly = out["hourly"]
            fig = go.Figure()
            fig.add_bar(x=hourly.hour_start_utc, y=hourly.reporting_carrier_touchdowns,
                        name="realised touchdowns")  # fmt: skip
            fig.add_scatter(x=hourly.hour_start_utc, y=hourly.scheduled_arrivals,
                            mode="lines+markers", name="scheduled arrivals")  # fmt: skip
            fig.update_layout(
                title=f"Hindsight: realised touchdowns per hour at {icao} after {fmt_t(t)}",
                xaxis_title="hour (UTC)", yaxis_title="arrivals per hour",
            )  # fmt: skip
            st.plotly_chart(fig, key="hindsight_chart")
            st.dataframe(hourly, hide_index=True)
            st.markdown("**Departures: share delayed > 45 min among operated flights**")
            st.dataframe(out["departures"], hide_index=True)
            st.caption(
                "Cancelled flights are excluded from the share and counted separately."
            )

# Failure cases ------------------------------------------------------------------------------

with cases_tab:
    st.caption("Clicking a case sets the sidebar; then open the Replay tab.")
    for i, case in enumerate(CASES):
        st.subheader(case["title"])
        st.markdown(
            f"{case['airport']}, T = {fmt_t(pd.Timestamp(case['t']))}. {case['description']}"
        )
        st.button("Open this case", key=f"case_{i}", on_click=set_case, args=(case,))

    st.header("Worst misses (failures.py report)")
    fail_files = dd.list_failure_files(ROOT)
    if not fail_files:
        st.info(
            f"Failure cases {dd.not_generated('failures --metrics reports/metrics_dev.json')}"
        )
    else:
        fpath = st.selectbox("Failure-case file", fail_files,
                             format_func=lambda p: str(p.relative_to(ROOT)))  # fmt: skip
        report = dd.load_failure_cases(fpath)
        st.caption(
            f"Run `{report.get('run_id')}`, rules `{report.get('rules_version')}`, scope "
            f"**{report.get('scope')}**, data mode `{report.get('data_mode')}`. Read from file; "
            f"nothing is recomputed. {report.get('hindsight_weather', '')}"
        )
        for i, case in enumerate(report.get("cases", [])):
            v = dd.failure_case_view(case)
            s = v["summary"]
            with st.expander(f"{s['airport']} h={s['horizon_h']} {s['target']}: predicted "
                             f"{s['estimate']} vs outcome {s['outcome']} (error {s['error']})"):  # fmt: skip
                st.dataframe(pd.DataFrame([s]), hide_index=True)
                possible = {True: "yes", False: "no", None: "unknown"}[
                    v["advisory_possible"]
                ]
                st.markdown(
                    f"**Advisory possible at T:** {possible}: {v['advisory_reason']}"
                )
                st.markdown("**Limitations**")
                for line in v["limitations"] or ["none flagged"]:
                    st.markdown(f"- {line}")
                st.markdown(f"**Sources known at issue time** (explanation status "
                            f"`{v['explanation_status']}`); ages in minutes at T: "
                            f"{v['source_ages_min'] or 'insufficient data'}")  # fmt: skip
                if v["sources"].empty:
                    st.info("Insufficient data: no source records at T.")
                else:
                    st.dataframe(v["sources"], hide_index=True, key=f"fail_src_{i}")

# Evaluation ---------------------------------------------------------------------------------

with eval_tab:
    files = dd.list_metric_files(ROOT)
    if not files:
        st.info("No metrics file found in reports/.")
    else:
        path = st.selectbox(
            "Metrics file", files, format_func=lambda p: str(p.relative_to(ROOT))
        )
        report = json.loads(path.read_text())
        st.markdown(
            f"Run `{report.get('run_id')}`, scope **{report.get('scope')}**, data mode "
            f"`{report.get('data_mode')}`, commit `{str(report.get('commit'))[:10]}`, generated "
            f"{report.get('generated_at_utc')}. Displayed as stored; nothing is recomputed here."
        )
        records = dd.metric_records(report)
        metric = st.selectbox(
            "Metric", sorted(records.metric.unique()), index=None, placeholder="rmse"
        )
        st.dataframe(records[records.metric == (metric or "rmse")], hide_index=True)

with st.sidebar:
    st.caption("Load times: " + ", ".join(f"{k} {v:.2f} s" for k, v in timings.items()))
