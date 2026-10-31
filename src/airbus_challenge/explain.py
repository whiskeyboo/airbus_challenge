"""Short brief from given facts only. The LLM writes words; code supplies and checks every number."""

import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from airbus_challenge.baselines import EXPERIMENT
from airbus_challenge.recommend import CANCELLATION, THRESHOLD_LABEL

DEFAULT_MODEL = "gpt-5-mini"
NUMBER = re.compile(r"\d+(?:\.\d+)?")
SYSTEM = (
    "You write a short operational brief (at most 120 words) for an airport operations "
    "coordinator. Use ONLY the JSON facts given. Copy every number and timestamp exactly as "
    "written in the facts; never compute, round, convert or add a number. Cite the input "
    "timestamps. Call it 'arrival throughput (AAR proxy)'. Severe-delay probability is "
    "conditional on the flight operating; mention cancellation separately. Describe SHAP "
    "drivers as associations, not causes. Say the thresholds are provisional. If a fact you "
    "need is missing, write 'insufficient data' instead of guessing."
)


def _r(x, nd=2):
    return None if x is None else round(float(x), nd)


def facts(recommendation: dict, drivers: list[dict], timestamps: dict) -> dict:
    """Code-rounded facts: the only numbers the brief may contain."""
    comps = []
    for c in recommendation["components"]:
        n = c.get("numbers") or {}
        f = {
            "kind": c["kind"],
            "level": c["level"],
            "message": c["message"],
            "reasons": c.get("reasons", []),
        }
        if c["kind"] == "throughput":
            f |= {
                "horizon_h": c.get("horizon_h"),
                "target_start_utc": (c.get("timestamps") or {}).get("target_start_utc"),
                "unit": c.get("unit"),
                "estimate": _r(n.get("estimate"), 1),
                "p10": _r(n.get("p10"), 1),
                "p90": _r(n.get("p90"), 1),
                "clear_weather_p95": _r(n.get("clear_weather_p95"), 1),
                "ratio_to_clear_weather_p95": _r(n.get("ratio_estimate")),
            }
        else:
            f |= {
                "n_flights_scored": n.get("n_scored"),
                "max_probability_pct": _r(100 * n["max_probability"], 0)
                if n.get("max_probability") is not None
                else None,
                "n_flights_above_watch": n.get("n_above_watch"),
                "n_flights_above_act": n.get("n_above_act"),
            }
        comps.append(f)
    canc = recommendation.get("cancellation")
    cn = canc["numbers"] if canc else {}
    return {
        "airport_icao": recommendation["airport_icao"],
        "as_of_utc": recommendation["as_of_utc"],
        "level": recommendation["level"],
        "threshold_label": recommendation.get("threshold_label", THRESHOLD_LABEL),
        "severe_delay_threshold_min": EXPERIMENT["targets"][
            "severe_delay_threshold_min"
        ],
        "components": comps,
        CANCELLATION: None
        if not canc
        else {
            "max_probability_pct": _r(100 * cn["max_probability"], 0)
            if cn.get("max_probability") is not None
            else None,
            "n_flights_scored": cn.get("n_scored"),
        },
        "drivers_associations_not_causes": [
            {
                "feature": d["feature"],
                "value": _r(d["value"]),
                "contribution": _r(d["contribution"], 3),
                "scale": d.get("contribution_scale", ""),
            }
            for d in drivers
        ],
        "input_timestamps": timestamps,
    }


def missing(recommendation: dict, drivers: list[dict], timestamps: dict) -> list[str]:
    out = [f"{c['kind']}: {', '.join(c.get('reasons') or ['abstain'])}"
           for c in recommendation["components"] if c["level"] == "abstain"]  # fmt: skip
    if not drivers:
        out.append("no SHAP drivers")
    if not timestamps:
        out.append("no input timestamps")
    return out


def _interval(c: dict) -> str:
    if c["p10"] is None or c["p90"] is None:
        return " (no interval)"
    return f" (p10 {c['p10']}, p90 {c['p90']})"


def template(f: dict) -> str:
    level = f["level"].upper()
    lines = [
        f"{f['airport_icao']}, issued {f['as_of_utc']}: level {level} (thresholds {f['threshold_label']})."
    ]
    for c in f["components"]:
        if c["level"] == "abstain":
            lines.append(f"{c['kind']}: insufficient data ({', '.join(c['reasons'])}).")
        elif c["kind"] == "throughput":
            lines.append(
                f"Arrival throughput (AAR proxy), hour {c['target_start_utc']} (h={c['horizon_h']}): "
                f"{c['estimate']} {c['unit']}{_interval(c)}, "
                f"{c['ratio_to_clear_weather_p95']} of the clear-weather p95 {c['clear_weather_p95']}."
            )
        else:
            lines.append(
                f"Severe departure delay (>{f['severe_delay_threshold_min']} min, if the flight operates): "
                f"max {c['max_probability_pct']}% over {c['n_flights_scored']} flights; "
                f"{c['n_flights_above_watch']} above watch, {c['n_flights_above_act']} above act."
            )
    if f[CANCELLATION]:
        c = f[CANCELLATION]
        lines.append(f"Cancellation, reported separately: max {c['max_probability_pct']}% "
                     f"over {c['n_flights_scored']} flights.")  # fmt: skip
    drivers = "; ".join(f"{d['feature']}={d['value']} ({d['contribution']:+} {d['scale']})".strip()
                        for d in f["drivers_associations_not_causes"])  # fmt: skip
    lines.append(f"Top drivers (SHAP associations, not causes): {drivers}.")
    times = "; ".join(f"{k} {v}" for k, v in f["input_timestamps"].items())
    lines.append(f"Inputs: {times}.")
    return " ".join(lines)


def _numbers(text: str) -> set[float]:
    return {float(x) for x in NUMBER.findall(text)}


def unsupported_numbers(text: str, f: dict) -> list[str]:
    allowed = _numbers(json.dumps(f))
    return sorted({x for x in NUMBER.findall(text) if float(x) not in allowed})


def default_client():
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        return None
    return OpenAI(timeout=20)


def brief(
    recommendation: dict, drivers: list[dict], timestamps: dict, client=None
) -> dict:
    """path: llm | template | insufficient_data. The LLM text is used only if every number checks out."""
    f = facts(recommendation, drivers, timestamps)
    gaps = missing(recommendation, drivers, timestamps)
    if gaps:
        text = f"Insufficient data for a full brief: {'; '.join(gaps)}. " + template(f)
        return {"text": text, "path": "insufficient_data", "reason": gaps, "facts": f}
    client = client or default_client()
    if client is None:
        return {
            "text": template(f),
            "path": "template",
            "reason": ["no OPENAI_API_KEY"],
            "facts": f,
        }
    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    try:
        reply = client.responses.create(
            model=model, instructions=SYSTEM, input=json.dumps(f)
        ).output_text
    except (OpenAIError, TimeoutError, ConnectionError) as e:
        return {
            "text": template(f),
            "path": "template",
            "reason": [f"llm_error: {type(e).__name__}"],
            "facts": f,
        }
    bad = unsupported_numbers(reply, f)
    if bad:
        return {"text": template(f), "path": "template", "facts": f, "rejected_llm_text": reply,
                "reason": [f"llm number not in facts: {', '.join(bad)}"]}  # fmt: skip
    return {
        "text": reply.strip(),
        "path": "llm",
        "reason": [],
        "model": model,
        "facts": f,
    }
