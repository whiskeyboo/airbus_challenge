"""Code-only alert rules. No LLM: every level, number and threshold here comes from code."""

import argparse
from pathlib import Path

import pandas as pd

from airbus_challenge.baselines import (
    AIRPORTS,
    ARTIFACTS,
    EXPERIMENT,
    HOURLY,
    TARGET,
    TARGET_LABEL,
)

SEVERE = EXPERIMENT["targets"]["severe_delay"]
CANCELLATION = "cancellation"
SEVERE_LABEL = (
    f"severe departure delay (>{EXPERIMENT['targets']['severe_delay_threshold_min']} min), "
    "probability conditional on the flight operating"
)
THRESHOLD_LABEL = "provisional_until_WP-D7"
# Placeholders until the lead fixes operating thresholds under WP-D7 (docs/PHASE_PLAN.md §7).
# Not tuned on any split. Every output carries THRESHOLD_LABEL.
THRESHOLDS = {
    "label": THRESHOLD_LABEL,
    "source": "placeholder values, not fitted; pending lead decision WP-D7",
    # Share of the train-only clear-weather p95 for that airport and local hour.
    "throughput_ratio_watch": 0.85,  # estimate below -> watch
    "throughput_ratio_act": 0.70,  # estimate below -> act; p10 below -> watch
    "min_reference_fit_hours": 20,  # fewer benign training hours -> no usable ceiling
    "severe_delay_probability_watch": 0.20,  # any flight strictly above -> watch
    "severe_delay_probability_act": 0.35,  # any flight strictly above -> act
}
RANK = {"normal": 0, "abstain": 1, "watch": 2, "act": 3}
MESSAGES = {
    "throughput.normal": f"{TARGET_LABEL} near the clear-weather ceiling.",
    "throughput.watch": f"{TARGET_LABEL} may fall below the clear-weather ceiling.",
    "throughput.act": f"{TARGET_LABEL} expected well below the clear-weather ceiling.",
    "throughput.abstain": f"No recommendation for {TARGET_LABEL}: insufficient data.",
    "severe_delay.normal": f"Low {SEVERE_LABEL}.",
    "severe_delay.watch": f"Elevated {SEVERE_LABEL} for some flights.",
    "severe_delay.act": f"High {SEVERE_LABEL} for some flights.",
    "severe_delay.abstain": "No recommendation for severe delay: insufficient data.",
    "overall.normal": "No alert under provisional thresholds.",
    "overall.watch": "Watch: at least one rule crossed a provisional watch threshold.",
    "overall.act": "Act: at least one rule crossed a provisional act threshold.",
    "overall.abstain": "Abstain: some inputs are missing, so no all-clear is given.",
}


def _iso(t) -> str | None:
    return None if pd.isna(t) else pd.Timestamp(t).isoformat()


def _num(x) -> float | None:
    return None if pd.isna(x) else float(x)


def _component(kind: str, level: str, **fields) -> dict:
    key = f"{kind}.{level}"
    return {
        "kind": kind,
        "level": level,
        "message_key": key,
        "message": MESSAGES[key],
    } | fields


def _model(rows: pd.DataFrame, kind: str) -> str | None:
    versions = rows["model_version"].dropna().unique()
    if len(versions) > 1:
        raise ValueError(
            f"{kind}: one model_version per recommendation, got {list(versions)}"
        )
    return versions[0] if len(versions) else None


def _available(rows: pd.DataFrame) -> pd.Series:
    return rows["status"].ne("unavailable") & rows["estimate"].notna()


def _ceiling(icao: str, target_start, reference: pd.DataFrame | None) -> dict | None:
    if reference is None:
        return None
    hour = pd.Timestamp(target_start).tz_convert(AIRPORTS[icao]["timezone"]).hour
    match = reference[
        reference["airport_icao"].eq(icao) & reference["airport_local_hour"].eq(hour)
    ]
    if match.empty:
        return None
    row = match.iloc[0]
    return {
        "airport_local_hour": hour,
        "clear_weather_p95_arrivals_per_hour": _num(
            row["clear_weather_p95_arrivals_per_hour"]
        ),
        "clear_weather_fit_hours": int(row["clear_weather_fit_hours"]),
        "clear_weather_reference_id": row.get("clear_weather_reference_id"),
        "clear_weather_fit_end_utc": _iso(row.get("clear_weather_fit_end_utc")),
    }


def throughput(row: pd.Series, reference: pd.DataFrame | None) -> dict:
    t = THRESHOLDS
    ceiling = _ceiling(row["airport_icao"], row["target_start_utc"], reference)
    common = {
        "label": TARGET_LABEL,
        "unit": row["unit"],
        "status": row["status"],
        "horizon_h": int(row["horizon_h"]),
        "model_version": row["model_version"],
        "timestamps": {
            "as_of_utc": _iso(row["as_of_utc"]),
            "target_start_utc": _iso(row["target_start_utc"]),
            "generated_at_utc": _iso(row.get("generated_at_utc")),
            "clear_weather_fit_end_utc": ceiling
            and ceiling["clear_weather_fit_end_utc"],
        },
        "thresholds": {
            k: t[k]
            for k in (
                "throughput_ratio_watch",
                "throughput_ratio_act",
                "min_reference_fit_hours",
            )
        },
        "reference": ceiling,
    }
    reasons = list(
        row.get("reason_codes") if row.get("reason_codes") is not None else []
    )
    if row["status"] == "unavailable" or pd.isna(row["estimate"]):
        return _component(
            "throughput",
            "abstain",
            reasons=reasons or ["estimate_missing"],
            numbers={},
            **common,
        )
    p95 = ceiling and ceiling["clear_weather_p95_arrivals_per_hour"]
    if (
        not p95
        or p95 <= 0
        or ceiling["clear_weather_fit_hours"] < t["min_reference_fit_hours"]
    ):
        return _component("throughput", "abstain", reasons=reasons + ["no_usable_clear_weather_reference"],
                          numbers={"estimate": _num(row["estimate"])}, **common)  # fmt: skip
    ratio = row["estimate"] / p95
    ratio_p10 = None if pd.isna(row["p10"]) else row["p10"] / p95
    if ratio < t["throughput_ratio_act"]:
        level = "act"
    elif ratio < t["throughput_ratio_watch"] or (
        ratio_p10 is not None and ratio_p10 < t["throughput_ratio_act"]
    ):
        level = "watch"
    else:
        level = "normal"
    numbers = {
        "estimate": _num(row["estimate"]),
        "p10": _num(row["p10"]),
        "p90": _num(row["p90"]),
        "clear_weather_p95": p95,
        "ratio_estimate": float(ratio),
        "ratio_p10": None if ratio_p10 is None else float(ratio_p10),
    }
    if row["status"] == "degraded":
        reasons.append("degraded_prediction")
    return _component("throughput", level, reasons=reasons, numbers=numbers, **common)


def _flights(rows: pd.DataFrame, kind: str) -> tuple[pd.DataFrame, dict]:
    ok = _available(rows)
    p = rows.loc[ok, "estimate"]
    if not p.between(0, 1).all():
        raise ValueError(f"{kind}: probability outside [0, 1]")
    summary = {
        "n_flights": len(rows),
        "n_scored": int(ok.sum()),
        "n_unavailable": int((~ok).sum()),
        "max_probability": _num(p.max()) if len(p) else None,
        "mean_probability": _num(p.mean()) if len(p) else None,
    }
    return rows[ok], summary


def _flight_times(rows: pd.DataFrame) -> dict:
    return {
        "as_of_utc": _iso(rows["as_of_utc"].iloc[0]),
        "first_target_start_utc": _iso(rows["target_start_utc"].min()),
        "last_target_start_utc": _iso(rows["target_start_utc"].max()),
        "generated_at_utc": _iso(rows["generated_at_utc"].max())
        if "generated_at_utc" in rows
        else None,
    }


def severe_delay(rows: pd.DataFrame) -> dict:
    t = THRESHOLDS
    scored, numbers = _flights(rows, SEVERE)
    p = scored["estimate"]
    numbers |= {
        "n_above_watch": int(p.gt(t["severe_delay_probability_watch"]).sum()),
        "n_above_act": int(p.gt(t["severe_delay_probability_act"]).sum()),
        "top_flights": [
            {
                "flight_id": r.flight_id,
                "target_start_utc": _iso(r.target_start_utc),
                "probability": float(r.estimate),
            }
            for r in scored.nlargest(3, "estimate").itertuples()
        ],
    }
    reasons = sorted({c for rc in rows["reason_codes"].dropna() for c in rc})
    common = {
        "label": SEVERE_LABEL,
        "model_version": _model(rows, SEVERE),
        "timestamps": _flight_times(rows),
        "thresholds": {
            k: t[k]
            for k in ("severe_delay_probability_watch", "severe_delay_probability_act")
        },
        "numbers": numbers,
        "reasons": reasons,
    }
    if scored.empty:
        return _component("severe_delay", "abstain", **common)
    level = (
        "act"
        if numbers["n_above_act"]
        else "watch"
        if numbers["n_above_watch"]
        else "normal"
    )
    return _component("severe_delay", level, **common)


def cancellation(rows: pd.DataFrame) -> dict:
    """Reported beside, never folded into, the severe-delay probability. No alert rule yet."""
    _, numbers = _flights(rows, CANCELLATION)
    return {
        "kind": "cancellation",
        "reported_separately": True,
        "alert_rule": None,
        "model_version": _model(rows, CANCELLATION),
        "numbers": numbers,
        "timestamps": _flight_times(rows),
    }


def recommend(predictions: pd.DataFrame, reference: pd.DataFrame | None = None) -> dict:
    """Rows for one airport and issue time; reference = train-only clear-weather table."""
    icaos, issues = (
        predictions["airport_icao"].unique(),
        predictions["as_of_utc"].unique(),
    )
    if len(icaos) != 1 or len(issues) != 1:
        raise ValueError(
            "recommend() takes rows for exactly one airport and one as_of_utc"
        )
    by_kind = dict(tuple(predictions.groupby("target_kind")))
    components = []
    tp = by_kind.get(TARGET)
    if tp is None:
        components.append(
            _component(
                "throughput", "abstain", reasons=["no_prediction_rows"], numbers={}
            )
        )
    else:
        _model(tp, TARGET)
        components += [
            throughput(r, reference)
            for _, r in tp.sort_values("target_start_utc").iterrows()
        ]
    sd = by_kind.get(SEVERE)
    components.append(
        severe_delay(sd) if sd is not None
        else _component("severe_delay", "abstain", reasons=["no_prediction_rows"], numbers={})
    )  # fmt: skip
    level = max((c["level"] for c in components), key=RANK.get)
    known = {TARGET, SEVERE, CANCELLATION}
    return {
        "airport_icao": icaos[0],
        "as_of_utc": _iso(issues[0]),
        "level": level,
        "message_key": f"overall.{level}",
        "message": MESSAGES[f"overall.{level}"],
        "threshold_label": THRESHOLD_LABEL,
        "thresholds": THRESHOLDS,
        "components": components,
        "cancellation": cancellation(by_kind[CANCELLATION])
        if CANCELLATION in by_kind
        else None,
        "ignored_target_kinds": sorted(set(by_kind) - known),
    }


def advisories(recs: list[dict]) -> pd.DataFrame:
    """One row per component, the table app/dashboard.py reads."""
    rows = [
        {
            "airport_icao": r["airport_icao"],
            "as_of_utc": pd.Timestamp(r["as_of_utc"]),
            "overall_level": r["level"],
            "kind": c["kind"],
            "level": c["level"],
            "message": c["message"],
            "horizon_h": c.get("horizon_h"),
            "target_start_utc": (c.get("timestamps") or {}).get("target_start_utc"),
            "numbers": str(c.get("numbers")),
            "reasons": ", ".join(c.get("reasons") or []),
            "threshold_label": r["threshold_label"],
        }
        for r in recs
        for c in r["components"]
    ]
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    run = ARTIFACTS / args.run
    preds = pd.read_parquet(run / "predictions.parquet")
    ref_cols = ["airport_icao", "airport_local_hour", "clear_weather_p95_arrivals_per_hour",
                "clear_weather_fit_hours", "clear_weather_reference_id", "clear_weather_fit_end_utc"]  # fmt: skip
    reference = pd.read_parquet(Path(HOURLY), columns=ref_cols).drop_duplicates(
        ["airport_icao", "airport_local_hour"]
    )
    recs = [
        recommend(g, reference) for _, g in preds.groupby(["airport_icao", "as_of_utc"])
    ]
    out = advisories(recs)
    out.to_parquet(run / "advisories.parquet", index=False)
    print(out.groupby(["airport_icao", "kind", "level"]).size())


if __name__ == "__main__":
    main()
