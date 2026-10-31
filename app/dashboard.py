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
    st.header("Choose a past moment")
    icao = st.selectbox(
        "Airport",
        list(AIRPORTS),
        format_func=lambda a: f"{AIRPORTS[a]['iata']} ({a})",
        key="airport",
    )
    day = st.date_input(
        "Date (UTC)", key="day", min_value=date(2023, 1, 1), max_value=date(2025, 7, 31)
    )
    hour = st.selectbox(
        "Time (UTC)", list(range(24)), key="hour", format_func=lambda h: f"{h:02d}:00Z"
    )
    t = pd.Timestamp(day).tz_localize("UTC") + pd.Timedelta(hours=hour)
    local = dd.local_time(ROOT, icao, t)
    st.markdown(
        f"**{t:%d %b %Y, %H:%M UTC}**  \n{local:%I:%M %p %Z} at {AIRPORTS[icao]['iata']}"
    )
    runs = dd.list_runs(ROOT)
    run = (
        st.selectbox(
            "Forecast set",
            runs,
            index=dd.default_run_index(runs),
            format_func=dd.run_label,
            key="run",
            help="Choose a model or a simpler baseline to compare.",
        )
        if runs
        else None
    )
    st.caption(
        "Looking back at a past forecast. Weather report availability is simulated "
        "with a 10-minute delay."
    )

st.title(f"{AIRPORTS[icao]['iata']}: next 12 hours from {t:%d %b %Y, %H:%M UTC}")
st.caption(
    "Advisory information for review by a traffic management coordinator. It does not issue "
    "clearances or start traffic management initiatives."
)
st.warning(
    "Historical demonstration, not a live airport system. Results are provisional: "
    "validation was used while selecting the model, and some lower-quality predictions "
    "have not been separately validated."
)
with st.expander("About this demonstration"):
    st.write(
        "The candidate models used the first half of 2024 to choose when to stop training, "
        "but their saved fit cutoff is 1 January 2024. Validation scores are therefore not "
        "independent. Some degraded predictions do not have a validated fallback."
    )
    st.write(
        "Weather and schedule availability are simulated for replay; this is not a live feed."
    )
replay_tab, cases_tab, eval_tab = st.tabs(
    ["Overview", "Explore past cases", "How accurate is it?"]
)

# Replay at T --------------------------------------------------------------------------------

with replay_tab:
    ev = timed("evidence", evidence, icao, t)
    snaps = ev["snapshots"]
    st.header("At a glance")
    st.caption(
        "A summary of the selected forecast, not an instruction to airport staff."
    )
    rows = timed("run_rows", run_rows, run, icao, t) if run else pd.DataFrame()
    rec = None
    if run is None:
        st.info(
            f"Predictions {dd.not_generated('train')} (or `airbus_challenge.baselines`)."
        )
    elif rows.empty:
        st.info(
            "No predictions are available for this airport and time. Try a different date or forecast set."
        )
    else:
        models = dd.advisory_models(rows)
        model = st.selectbox("Arrival model", models, format_func=dd.run_label, key="adv_model") if models else None  # fmt: skip
        used = dd.advisory_rows(rows, model)
        # The run's WP-D7 calibration.json when present, else the provisional thresholds.
        policy = recommend.load_policy(ROOT / dd.ARTIFACTS / run)
        rec = recommend.recommend(used, reference(), policy)
        if rec["threshold_label"] == recommend.THRESHOLD_LABEL:
            st.warning(
                "This run has no calibrated alert policy. Its provisional advisory levels "
                "are for demonstration and are not validated for operational use."
            )
        st.subheader("Overall assessment")
        level_text = {
            "normal": "No alert was raised by the selected rules.",
            "watch": "Some forecasts need closer attention.",
            "act": "At least one forecast crossed an action threshold.",
            "abstain": "There is not enough information for a complete assessment.",
        }
        (st.warning if rec["level"] in ("abstain", "watch", "act") else st.success)(
            level_text.get(rec["level"], "Assessment unavailable.")
        )
        cards = dd.advisory_cards(rec)
        for col, card in zip(st.columns(len(cards)), cards):
            value = {
                "ABSTAIN": "Unavailable",
                "NO DATA": "Unavailable",
                "WATCH": "Watch",
                "ACT": "Act",
                "NORMAL": "Normal",
            }.get(card["value"], card["value"])
            title = {
                "Arrival throughput (AAR proxy)": "Landings",
                "Severe delay (>45 min, if operated)": "Departure delays",
                "Cancellation (reported separately)": "Cancellations",
            }.get(card["title"], card["title"])
            col.metric(title, value, help=card["help"])
            col.caption(card["detail"])
        st.caption(
            "Normal: no alert · Watch: keep an eye on it · Act: a rule's threshold was reached · Unavailable: not enough information."
        )
        with st.expander("How was this assessment made?"):
            st.caption(
                "Rules and thresholds are chosen from the selected forecast set. Missing inputs can make an assessment unavailable."
            )
            comps = dd.component_table(rec)
            for _, component in comps[comps.level.eq("abstain")].iterrows():
                st.markdown(
                    f"- **{component.kind.replace('_', ' ').title()}:** {component.reasons or 'Information unavailable.'}"
                )
            st.dataframe(comps, hide_index=True)
            st.markdown(f"**Policy:** `{rec['threshold_label']}`")
            st.json(
                {
                    k: v
                    for k, v in rec["thresholds"].items()
                    if k not in ("label", "source")
                },
                expanded=False,
            )
            st.caption("This assessment uses the forecast set's current calibrated or provisional rules.")
        if rec["cancellation"] is None:
            st.caption("No cancellation predictions are available for this selection.")

    st.header("What this means")
    if rec is None:
        st.info("Choose a time with a forecast to see a summary.")
    else:
        drivers = dd.load_drivers(ROOT, run, used["prediction_id"])
        stamps = dd.brief_timestamps(t, ev, used)
        summary = dd.plain_brief(rec)
        st.markdown("**Predicted arrivals**")
        if not summary["arrivals"]:
            st.info("Arrival predictions are unavailable for this selection.")
        else:
            for item in summary["arrivals"]:
                text = f"In {item['horizon_h']} hours: **{item['estimate']:.1f} landings per hour**"
                if pd.notna(item["p10"]) and pd.notna(item["p90"]):
                    text += f" (model range {item['p10']:.1f}–{item['p90']:.1f})"
                st.markdown(f"- {text}")
            st.caption(
                "The model range is an estimate, not a guarantee. Arrivals reflect demand as well as runway capacity."
            )
        st.markdown("**Flight-delay risk**")
        st.write(summary["delay"])
        if not drivers:
            st.info(
                "The factors behind these forecasts are not available for this selection."
            )
        else:
            st.caption(
                "Contributing factors are available below. They are associations, not necessarily causes."
            )
        with st.expander("See contributing factors and source times"):
            if drivers:
                st.dataframe(pd.DataFrame(drivers), hide_index=True)
            else:
                st.write("No per-prediction contributing factors are available.")
            time_labels = {
                "as_of_utc": "Forecast time",
                "metar_available_at_utc": "Weather report available",
                "taf_available_at_utc": "Weather forecast available",
                "predictions_generated_at_utc": "Prediction file generated",
            }
            for name, value in stamps.items():
                st.write(f"{time_labels.get(name, name)}: {fmt_t(value)}")
        key = ("brief_llm", run, icao, str(t), model)
        if st.button(
            "Generate a written summary",
            key="brief_llm",
            disabled=not dd.can_generate_brief(rec, drivers, stamps),
            help="Requires flight-risk predictions, contributing factors, and source times; uses a language model.",
        ):
            st.session_state[key] = dd.make_brief(rec, drivers, stamps, use_llm=True)
        if key in st.session_state:
            written = st.session_state[key]
            if written["path"] == "llm":
                st.write(written["text"])
            else:
                st.info(
                    "A written summary is unavailable right now. The forecast and any missing information are shown above."
                )

    st.header("Expected arrivals")
    st.caption(
        "Compare the predicted number of landings with the schedule. Each point is a forecast for one hour, 3–12 hours ahead."
    )
    if run is None:
        st.info("No prediction runs found in artifacts/.")
    else:
        table = timed("forecast", forecast, run, icao, t)
        if table.empty:
            st.warning(
                "No predictions are available for this airport and time. Try a date in 2024 or choose a different forecast set."
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
                    name=dd.run_label(model) if kind == "model" else f"{dd.run_label(model)} (baseline)", error_y=err,
                )  # fmt: skip
            fig.update_layout(
                title="Expected landings compared with the schedule",
                xaxis_title="future hour (UTC)", yaxis_title="landings per hour",
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
            with st.expander("See forecast numbers and data quality"):
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

    st.header("Weather at the time")
    st.caption(
        "Reports and forecasts available at the selected time; source availability is simulated."
    )
    if snaps.empty:
        st.warning(f"Insufficient data: no weather snapshot for {icao} at {fmt_t(t)}.")
    else:
        first = snaps.iloc[0]
        st.markdown(
            f"**Weather data:** {dd.STATUS.get(first.status, 'Status unavailable.')}"
        )
        codes = sorted({c for rc in snaps.reason_codes for c in rc})
        with st.expander("See weather reports, runway winds and forecast details"):
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
                    winds.drop(columns=["wind_status", "note"]).round(1),
                    hide_index=True,
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

    with st.expander("Compare with what actually happened", expanded=False):
        st.caption(
            "Reveal the historical outcome to compare it with the forecast. It was not known when the forecast was made."
        )
        if st.toggle(
            "Show historical outcomes", key="show_outcomes"
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
    st.caption(
        "Choose an example, then open Overview to explore what was known and predicted."
    )
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
