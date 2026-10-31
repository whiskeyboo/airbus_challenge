import argparse
import json
import math
from pathlib import Path

import pandas as pd

from airbus_challenge.evaluate import (
    ALL_HORIZONS,
    CLIMATOLOGY,
    CONDITIONAL_RATE,
    LOGISTIC,
    POOLED,
    RECALL_NAMES,
    REPORTS,
    SEVERE,
    TARGET,
    TARGET_LABEL,
)

SEASONAL = "baseline_seasonal_persistence_v1"
CANCELLATION = "cancellation"
LIMITATIONS = "docs/LIMITATIONS.md"
DEV_SCOPE = "development (2023 train; H1/H2 2024 scored); not the locked 2025 test"
POOLED_LABEL = {
    "throughput": "pooled (airport-hour weighted)",
    "severe_delay": "pooled (flight weighted)",
}
WEATHER_METRICS = ["rmse", "mae", "brier", "average_precision"]


def is_baseline(model: str) -> bool:
    return model.startswith("baseline_")


def short(model: str) -> str:
    return model.removesuffix("_v1").removeprefix("baseline_")


def na(reason: str | None) -> str:
    return f"n/a ({reason or 'no reason given'})"


def fmt(record: dict | None, digits: int = 3) -> str:
    if record is None:
        return na("not in report")
    if record.get("value") is None:
        return na(record.get("reason"))
    text = f"{record['value']:.{digits}f}"
    if record.get("ci_low") is not None and record.get("ci_high") is not None:
        text += f" [{record['ci_low']:.{digits}f}, {record['ci_high']:.{digits}f}]"
    return text


def verdict(skill: dict | None, baseline: str) -> str:
    # Skill 0 is the baseline's own value, so only a CI clear of 0 decides.
    name = short(baseline)
    if skill is None or skill.get("value") is None:
        reason = "not in report" if skill is None else skill.get("reason")
        return f"not distinguishable from {name} ({na(reason)})"
    if skill.get("ci_low") is None or skill.get("ci_high") is None:
        return f"not distinguishable from {name} (no CI: {skill.get('ci_reason')})"
    if skill["ci_low"] > 0:
        return f"better than {name}"
    if skill["ci_high"] < 0:
        return f"worse than {name}"
    return f"not distinguishable from {name}"


def table(header: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]


def clean(record: dict) -> dict:
    # A DataFrame turns null floats into NaN; the report means null.
    return {
        k: None if isinstance(v, float) and math.isnan(v) else v
        for k, v in record.items()
    }


def pick(frame: pd.DataFrame, **match) -> dict | None:
    mask = pd.Series(True, index=frame.index)
    for column, value in match.items():
        mask &= frame[column].astype(str).eq(str(value))
    rows = frame[mask]
    return None if rows.empty else clean(rows.iloc[0].to_dict())


def airports(frame: pd.DataFrame) -> list[str]:
    places = sorted(set(frame["airport"]) - {POOLED, "macro"})
    return [*places, POOLED] if POOLED in set(frame["airport"]) else places


def place(airport: str, task: str) -> str:
    return POOLED_LABEL.get(task, POOLED) if airport == POOLED else airport


def n_of(frame: pd.DataFrame, **match) -> str:
    record = pick(frame, **match)
    return "n/a (not in report)" if record is None else str(record["n_predicted"])


def best_candidate(frame: pd.DataFrame) -> str | None:
    # Chosen on validation only, so the selection never looks at calibration.
    rows = frame[
        frame["model"].map(lambda m: not is_baseline(m))
        & frame["split"].eq("validation")
        & frame["metric"].eq("rmse")
        & frame["slice"].eq("common_support")
        & frame["horizon"].astype(str).eq(ALL_HORIZONS)
        & frame["value"].notna()
    ]
    pooled = rows[rows["airport"].eq(POOLED)]
    if len(pooled):
        return pooled.sort_values(["value", "model"])["model"].iloc[0]
    if rows.empty:
        return None
    return rows.groupby("model")["value"].mean().sort_values().index[0]


def skill_rows(frame: pd.DataFrame, split: str, baselines: list[str]) -> list[list]:
    rows = []
    for airport in airports(frame):
        for model in sorted(frame["model"].unique()):
            cells = []
            for baseline in baselines:
                if baseline == model:
                    cells.append("-")
                    continue
                skill = pick(
                    frame,
                    split=split,
                    airport=airport,
                    horizon=ALL_HORIZONS,
                    model=model,
                    slice="baseline_support",
                    metric=f"skill_vs_{baseline}",
                )
                text = fmt(skill)
                if skill is not None and skill.get("value") is not None:
                    text += f"; {verdict(skill, baseline)}"
                cells.append(text)
            n = n_of(
                frame,
                split=split,
                airport=airport,
                horizon=ALL_HORIZONS,
                model=model,
                slice="baseline_support",
            )
            rows.append([airport, short(model), *cells, n])
    return rows


def throughput_section(frame: pd.DataFrame) -> list[str]:
    lines = [f"## {TARGET_LABEL}", ""]
    if frame.empty:
        return lines + ["No throughput records in this report.", ""]
    models = sorted(frame["model"].unique())
    common = {"slice": "common_support", "metric": "rmse", "horizon": ALL_HORIZONS}
    rows = []
    for split in sorted(frame["split"].unique()):
        for airport in airports(frame):
            cells = [
                fmt(pick(frame, split=split, airport=airport, model=m, **common))
                for m in models
            ]
            n = n_of(frame, split=split, airport=airport, model=models[0], **common)
            rows.append([split, place(airport, "throughput"), *cells, n])
    unit = frame["unit"].dropna().iloc[0] if frame["unit"].notna().any() else ""
    lines += [
        f"RMSE ({unit}) on common support, all horizons, 95% CI in brackets.",
        "",
        *table(["split", "airport", *map(short, models), "n_predicted"], rows),
        "",
        (
            "Persistence is a simulated feed (last complete hour before issue) and is "
            "weak at 3-12 h; climatology and seasonal persistence are the baselines "
            "to beat."
        ),
        "",
    ]
    best = best_candidate(frame)
    shown = [m for m in [best, CLIMATOLOGY, SEASONAL] if m and m in models]
    lines += [
        "### RMSE by horizon",
        "",
        f"Best non-baseline model on validation: {best}."
        if best
        else "No non-baseline model with validation RMSE; baselines only.",
        "",
    ]
    horizons = sorted(set(frame["horizon"].astype(str)) - {ALL_HORIZONS}, key=int)
    for airport in airports(frame) if shown else []:
        rows = []
        for split in sorted(frame["split"].unique()):
            for horizon in [*horizons, ALL_HORIZONS]:
                match = {"split": split, "airport": airport, "horizon": horizon}
                match |= {"slice": "common_support", "metric": "rmse"}
                cells = [fmt(pick(frame, model=m, **match)) for m in shown]
                rows.append(
                    [split, horizon, *cells, n_of(frame, model=shown[0], **match)]
                )
        lines += [
            f"**{place(airport, 'throughput')}**",
            "",
            *table(["split", "horizon_h", *map(short, shown), "n_predicted"], rows),
            "",
        ]
    baselines = [CLIMATOLOGY, SEASONAL]
    lines += [
        "### Skill (1 - RMSE/RMSE_baseline on baseline support, all horizons)",
        "",
    ]
    if not frame["metric"].eq(f"skill_vs_{SEASONAL}").any():
        lines += [
            (
                "Skill vs seasonal persistence is n/a: evaluate.py computes skill "
                "only against its required baselines (persistence, climatology). "
                "The RMSE CIs above are unpaired, so they cannot settle it either."
            ),
            "",
        ]
    for split in sorted(frame["split"].unique()):
        header = ["airport", "model", *(f"vs {short(b)}" for b in baselines), "n"]
        lines += [
            f"**{split}**",
            "",
            *table(header, skill_rows(frame, split, baselines)),
            "",
        ]
    return lines


def binary_section(frame: pd.DataFrame, title: str, baselines: list[str]) -> list[str]:
    lines = [f"## {title}", ""]
    if frame.empty:
        return lines + ["No records for this target in this report.", ""]
    names = ["average_precision", "brier", *RECALL_NAMES]
    rows = []
    for split in sorted(frame["split"].unique()):
        for airport in airports(frame):
            for model in sorted(frame["model"].unique()):
                match = {"split": split, "airport": airport, "model": model}
                match |= {"horizon": ALL_HORIZONS, "slice": "common_support"}
                cells = [fmt(pick(frame, metric=m, **match)) for m in names]
                counts = pick(frame, **match)
                prevalence = (
                    na("not in report")
                    if counts is None
                    else fmt({"value": counts["prevalence"], "reason": "no rows"})
                )
                n = "n/a (not in report)" if counts is None else counts["n_predicted"]
                rows.append(
                    [
                        split,
                        place(airport, "severe_delay"),
                        short(model),
                        *cells,
                        prevalence,
                        n,
                    ]
                )
    header = ["split", "airport", "model", "AP", "Brier", "R@P0.25", "R@P0.5"]
    lines += [
        (
            "Common support, all horizons. Recall at precision is a curve summary, "
            "not a frozen alert threshold."
        ),
        "",
        *table([*header, "prevalence", "n"], rows),
        "",
        "Brier skill vs required baselines:",
        "",
    ]
    for split in sorted(frame["split"].unique()):
        header = ["airport", "model", *(f"vs {short(b)}" for b in baselines), "n"]
        lines += [
            f"**{split}**",
            "",
            *table(header, skill_rows(frame, split, baselines)),
            "",
        ]
    return lines


def cancellation_rate_section(frame: pd.DataFrame) -> list[str]:
    rates = frame[frame["metric"].eq("cancellation_rate")]
    lines = ["### Cancellation rate (excluded from the severe-delay denominator)", ""]
    if rates.empty:
        return lines + [na("no cancellation_rate records"), ""]
    rows = []
    for split in sorted(rates["split"].unique()):
        for airport in airports(rates):
            record = pick(
                rates.sort_values("model"),
                split=split,
                airport=airport,
                horizon=ALL_HORIZONS,
            )
            if record is None:
                continue
            cancelled = record["exclusions"].get("cancelled", 0)
            scheduled = record["n_eligible"] + cancelled
            rows.append(
                [
                    split,
                    place(airport, "severe_delay"),
                    fmt(record),
                    f"{cancelled}/{scheduled}",
                ]
            )
    return lines + [
        *table(["split", "airport", "rate", "cancelled/scheduled"], rows),
        "",
    ]


def scope_section(scope: list[dict]) -> list[str]:
    lines = ["## Scoring scope", ""]
    if not scope:
        return lines + ["No scoring_scope entries in this report.", ""]
    rows = []
    for entry in scope:
        dropped = entry["rows_dropped"]
        detail = ", ".join(f"{short(m)} {n}" for m, n in sorted(dropped.items()))
        rows.append(
            [
                entry["split"],
                entry["target"],
                entry["cohort"],
                entry["fit_cutoff_utc"],
                ", ".join(entry["set_by"]),
                f"{max(dropped.values(), default=0)} ({detail})",
                entry["rows_scored"],
                na(entry["reason"]) if entry["reason"] else "",
            ]
        )
    header = ["split", "target", "cohort", "fit cutoff (UTC)", "set by"]
    lines += [
        "Rows issued before the latest fit cutoff are dropped for every model.",
        "",
        *table([*header, "rows dropped", "rows scored", "null"], rows),
        "",
    ]
    return lines


def coverage_section(frame: pd.DataFrame) -> list[str]:
    own = frame[
        frame["slice"].eq("own_support")
        & frame["airport"].eq(POOLED)
        & frame["horizon"].astype(str).eq(ALL_HORIZONS)
    ].drop_duplicates(["split", "cohort", "target", "model"])
    rows = [
        [
            r["split"],
            r["target"],
            short(r["model"]),
            r["n_eligible"],
            r["n_excluded"],
            ", ".join(f"{k} {v}" for k, v in sorted(r["exclusions"].items())) or "-",
            r["n_degraded"],
        ]
        for r in own.sort_values(["split", "target", "model"]).to_dict("records")
    ]
    header = ["split", "target", "model", "n_eligible", "n_excluded", "exclusions"]
    return [
        "## Coverage (pooled, all horizons)",
        "",
        *table([*header, "n_degraded"], rows),
        "",
    ]


def weather_section(frame: pd.DataFrame) -> list[str]:
    weather = frame[
        frame["slice"].astype(str).str.startswith("weather:")
        & frame["metric"].isin(WEATHER_METRICS)
    ]
    if weather.empty:
        return ["Weather slices: none in this report.", ""]
    rows = [
        [
            r["split"],
            r["target"],
            r["airport"],
            r["horizon"],
            short(r["model"]),
            r["slice"],
            r["metric"],
            fmt(r),
            r["n_predicted"],
        ]
        for r in map(clean, weather.to_dict("records"))
    ]
    header = ["split", "target", "airport", "horizon", "model", "slice", "metric"]
    return ["### Weather slices", "", *table([*header, "value", "n"], rows), ""]


def render(report: dict) -> str:
    frame = pd.DataFrame(report["metrics"])
    frame["horizon"] = frame["horizon"].astype(str)
    dev = report.get("scope") == "dev"
    scope = DEV_SCOPE if dev else f"locked 2025 test ({report.get('experiment')})"
    bounds = ", ".join(
        f"{s} {b[0][:10]} to {b[1][:10]}"
        for s, b in report.get("split_bounds", {}).items()
    )
    basis = report.get("availability_basis", {})
    lines = [
        f"# Results: {report.get('run_id', 'evaluate')}",
        "",
        f"- Scope: {scope}",
        f"- Scored splits (half-open UTC): {bounds or 'n/a (no split_bounds)'}",
        f"- Commit: {report.get('commit')} (commit_dirty={report.get('commit_dirty')})",
        f"- data_mode: {report.get('data_mode')}",
        f"- Label versions: {', '.join(report.get('label_versions', [])) or 'n/a'}",
        f"- Generated (UTC): {report.get('generated_at_utc')}",
        "- Availability basis: "
        + (
            "; ".join(f"{short(m)}: {', '.join(v)}" for m, v in basis.items()) or "none"
        ),
        "",
    ]
    if report.get("data_mode") == "fixture":
        lines += ["**Fixture data: these numbers describe no real airport.**", ""]
    throughput = frame[frame["target"].eq(TARGET)]
    lines += throughput_section(throughput)
    severe = frame[frame["target"].eq(SEVERE)]
    lines += binary_section(
        severe,
        "Severe departure delay (>45 min, conditional on operating)",
        [CONDITIONAL_RATE, LOGISTIC],
    )
    lines += cancellation_rate_section(severe)
    lines += binary_section(
        frame[frame["target"].eq(CANCELLATION)],
        "Cancellation",
        [CONDITIONAL_RATE, LOGISTIC],
    )
    lines += scope_section(report.get("scoring_scope", []))
    lines += coverage_section(frame)
    lines += [
        "## Honesty notes",
        "",
        (
            "- A null metric reads n/a (reason); it is never 0. Values without a bracket "
            "have no CI (ci_reason in the metrics JSON)."
        ),
        (
            "- A model is called better only when its skill CI lies above 0, i.e. "
            "excludes the baseline's own value; otherwise it is not distinguishable."
        ),
        "- Arrival throughput is an AAR proxy: it reflects demand as well as capacity.",
        "",
        *weather_section(frame),
        f"Known limitations: [{LIMITATIONS}]({LIMITATIONS}).",
        "",
    ]
    return "\n".join(lines)


def output_path(metrics: Path, report: dict, reports: Path) -> Path:
    name = metrics.stem.replace("metrics", "RESULTS", 1) + ".md"
    folder = reports / "fixture" if report["data_mode"] == "fixture" else reports
    return folder / name


def main(metrics: Path, reports: Path | None = None) -> Path:
    report = json.loads(metrics.read_text())
    path = output_path(metrics, report, reports or REPORTS)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(report))
    print(path)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", type=Path, default=REPORTS / "metrics_dev.json")
    parser.add_argument("--reports", type=Path)
    args = parser.parse_args()
    main(args.metrics, args.reports)
