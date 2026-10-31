import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import make_requests

from airbus_challenge import baselines, evaluate
from airbus_challenge.baselines import (
    RETROSPECTIVE_SCHEDULE,
    SIMULATED_FEED,
    SOURCE_PATHS,
    TARGET,
)
from airbus_challenge.download import sha256
from airbus_challenge.evaluate import (
    CAPACITY_RATIO,
    CLIMATOLOGY,
    CONDITIONAL_RATE,
    DAY_OFFSET,
    LOCKED_EXPERIMENTS,
    LOGISTIC,
    MIN_CI_DAYS,
    PERSISTENCE,
    REQUEST_KEYS,
    SEVERE,
    TARGET_LABELS,
    _brier_skill,
    _ci,
    _colours,
    _label,
    _mean,
    _rmse_skill,
    availability_basis,
    baseline_support,
    candidate_sha256,
    check_baselines,
    check_contract,
    check_label_keys,
    check_locked_candidates,
    check_requests,
    classification_metrics,
    evaluate_target,
    join_labels,
    load_labels,
    load_predictions,
    macro_records,
    main,
    mark_scored,
    regression_metrics,
    reliability,
    required_baselines,
    scoring_scope,
    skill_metrics,
    squared_errors,
    worst_misses,
)

MODEL = "lgbm_v1"
OTHER_MODEL = "lgbm_v2"
UNIT = "touchdowns/hour"
PROBABILITY = "probability"
DAY_ONE = "2024-03-05 15:00"
DAY_TWO = "2024-03-06 15:00"
TEST_DAY = "2025-03-05 15:00"


def ts(text: str) -> pd.Timestamp:
    return pd.Timestamp(text, tz="UTC")


def daily(n: int, start: str = "2024-03-01 15:00") -> list[str]:
    return [str(t) for t in pd.date_range(start, periods=n, freq="D", tz="UTC")]


def predictions_for(
    icao: str,
    targets: list[str],
    estimates: dict[str, list[float]],
    horizons=(3,),
    target_kind: str = TARGET,
    unit: str = UNIT,
) -> pd.DataFrame:
    requests = make_requests(icao, [ts(t) for t in targets], list(horizons))
    frames = []
    for model, values in estimates.items():
        estimate = pd.Series(values, index=requests.index, dtype="float64")
        frames.append(
            requests.assign(
                target_kind=target_kind,
                estimate=estimate,
                p10=np.nan,
                p90=np.nan,
                unit=unit,
                status=np.where(estimate.isna(), "unavailable", "available"),
                reason_codes=[["none"]] * len(requests),
                model_version=model,
                feature_version="fixture",
                data_snapshot_id="fixture-0",
                generated_at_utc=ts("2026-10-31"),
            )
        )
    return pd.concat(frames, ignore_index=True)


def labels_for(
    predictions: pd.DataFrame,
    y_true: list[float | None],
    unit: str = UNIT,
    data_mode: str = "fixture",
) -> pd.DataFrame:
    rows = predictions.drop_duplicates(["prediction_id", "target_kind"])
    return pd.DataFrame(
        {
            "prediction_id": rows["prediction_id"].to_numpy(),
            "target_kind": rows["target_kind"].to_numpy(),
            "y_true": pd.Series(y_true, dtype="float64"),
            "eligible": [y is not None for y in y_true],
            "exclusion_reason": [
                None if y is not None else "cancelled" for y in y_true
            ],
            "exclusion_detail": [
                None if y is not None else "cancelled" for y in y_true
            ],
            "label_version": "fixture",
            "unit": unit,
            "data_mode": data_mode,
        }
    )


def requests_of(predictions: pd.DataFrame) -> pd.DataFrame:
    return predictions[REQUEST_KEYS].drop_duplicates(ignore_index=True)


def scored(predictions: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    return mark_scored(join_labels(predictions, labels).assign(split="validation"))


def records_of(table: pd.DataFrame, labels: pd.DataFrame, basis=None) -> list[dict]:
    return evaluate_target(scored(table, labels), basis or {})


def rows_matching(records: list[dict], **match) -> list[dict]:
    return [r for r in records if all(r[k] == v for k, v in match.items())]


def record(records: list[dict], **match) -> dict:
    rows = rows_matching(records, **match)
    assert len(rows) == 1, rows
    return rows[0]


def value(records: list[dict], **match) -> float | None:
    return record(records, **match)["value"]


def by_metric(metrics: list[dict]) -> dict[str, dict]:
    return {m["metric"]: m for m in metrics}


def throughput_table(targets=(DAY_ONE, DAY_TWO)) -> pd.DataFrame:
    return predictions_for(
        "KATL",
        list(targets),
        {MODEL: [12.0, 21.0], PERSISTENCE: [14.0, 24.0], CLIMATOLOGY: [10.0, 20.0]},
    )


def severe_table(estimates: list[float], y: list[float | None]):
    table = predictions_for(
        "KATL",
        daily(len(y)),
        {MODEL: estimates},
        target_kind=SEVERE,
        unit=PROBABILITY,
    )
    return table, labels_for(table, y, PROBABILITY)


# Point metrics


def test_rmse_mae_and_bias_on_known_errors():
    table = throughput_table()
    rows = scored(table, labels_for(table, [10.0, 20.0]))
    metrics = by_metric(regression_metrics(rows[rows["model_version"].eq(MODEL)]))
    assert metrics["rmse"]["value"] == pytest.approx(np.sqrt((4 + 1) / 2))
    assert metrics["mae"]["value"] == pytest.approx(1.5)
    assert metrics["bias"]["value"] == pytest.approx(1.5)


def test_bias_is_estimate_minus_truth():
    table = predictions_for("KATL", [DAY_ONE], {MODEL: [8.0]})
    rows = scored(table, labels_for(table, [10.0]))
    assert by_metric(regression_metrics(rows))["bias"]["value"] == -2


def test_interval_coverage_width_and_pinball_on_known_values():
    table = predictions_for("KATL", [DAY_ONE, DAY_TWO], {MODEL: [12.0, 21.0]})
    table = table.assign(p10=[8.0, 22.0], p90=[13.0, 26.0])
    metrics = by_metric(
        regression_metrics(scored(table, labels_for(table, [10.0, 20.0])))
    )
    assert metrics["p10_p90_coverage"]["value"] == pytest.approx(0.5)
    assert metrics["p10_p90_width"]["value"] == pytest.approx(4.5)
    assert metrics["pinball_loss"]["value"] == pytest.approx((0.25 + 1.2) / 2)


def test_interval_bounds_count_as_covered():
    table = predictions_for("KATL", [DAY_ONE], {MODEL: [12.0]})
    table = table.assign(p10=[10.0], p90=[13.0])
    metrics = by_metric(regression_metrics(scored(table, labels_for(table, [10.0]))))
    assert metrics["p10_p90_coverage"]["value"] == 1


@pytest.mark.parametrize("p10", [[np.nan, np.nan], [9.0, np.nan]])
def test_incomplete_intervals_are_null_with_a_reason_not_zero(p10):
    table = predictions_for("KATL", [DAY_ONE, DAY_TWO], {MODEL: [12.0, 21.0]})
    table = table.assign(p10=p10, p90=[13.0, 26.0])
    metrics = by_metric(
        regression_metrics(scored(table, labels_for(table, [10.0, 20.0])))
    )
    assert metrics["p10_p90_coverage"]["value"] is None
    assert metrics["p10_p90_coverage"]["reason"] == "no_complete_intervals"


def test_average_precision_on_known_values():
    table, labels = severe_table([0.9, 0.8, 0.7, 0.1], [1, 0, 1, 0])
    metrics = by_metric(classification_metrics(scored(table, labels)))
    assert metrics["average_precision"]["value"] == pytest.approx((1 + 2 / 3) / 2)


def test_recall_at_precision_takes_the_best_recall():
    table, labels = severe_table([0.9, 0.8, 0.7, 0.6, 0.5], [1, 1, 0, 1, 0])
    metrics = by_metric(classification_metrics(scored(table, labels)))
    assert metrics["recall_at_precision_0.5"]["value"] == 1


def test_recall_at_precision_is_null_when_never_reached():
    table, labels = severe_table([0.1, 0.9, 0.8, 0.7], [1, 0, 0, 0])
    metrics = by_metric(classification_metrics(scored(table, labels)))
    assert metrics["recall_at_precision_0.5"]["value"] is None
    assert metrics["recall_at_precision_0.5"]["reason"] == "precision_not_reached"
    assert metrics["recall_at_precision_0.25"]["value"] == 1


def test_single_class_metrics_are_null_not_zero():
    table, labels = severe_table([0.1, 0.2], [0, 0])
    metrics = by_metric(classification_metrics(scored(table, labels)))
    assert metrics["average_precision"]["value"] is None
    assert metrics["average_precision"]["reason"] == "single_class"
    assert metrics["recall_at_precision_0.5"]["value"] is None
    assert metrics["brier"]["value"] == pytest.approx(0.025)


# Skill and common support


def test_regression_skill_is_measured_against_both_baselines():
    table = throughput_table()
    records = records_of(table, labels_for(table, [10.0, 20.0]))
    airport = {"model": MODEL, "airport": "KATL", "horizon": 3}
    rmse_model = np.sqrt(5 / 2)
    assert value(records, metric=f"skill_vs_{PERSISTENCE}", **airport) == pytest.approx(
        1 - rmse_model / 4
    )
    # Climatology is exactly right here, so its error is zero and skill is undefined.
    row = record(records, metric=f"skill_vs_{CLIMATOLOGY}", **airport)
    assert row["value"] is None
    assert row["reason"] == "baseline_error_zero"


def test_binary_skill_compares_brier_scores():
    table = predictions_for(
        "KATL",
        [DAY_ONE, DAY_TWO],
        {MODEL: [0.8, 0.2], CONDITIONAL_RATE: [0.5, 0.5], LOGISTIC: [0.6, 0.4]},
        target_kind=SEVERE,
        unit=PROBABILITY,
    )
    records = records_of(table, labels_for(table, [1.0, 0.0], PROBABILITY))
    skill = value(
        records,
        metric=f"skill_vs_{CONDITIONAL_RATE}",
        model=MODEL,
        airport="KATL",
        horizon=3,
    )
    assert skill == pytest.approx(1 - 0.04 / 0.25)


def test_skill_uses_only_rows_every_model_scored():
    table = predictions_for(
        "KATL",
        [DAY_ONE, DAY_TWO],
        {MODEL: [11.0, 100.0], PERSISTENCE: [12.0, 20.0], CLIMATOLOGY: [13.0, np.nan]},
    )
    records = records_of(table, labels_for(table, [10.0, 20.0]))
    skill = value(
        records,
        metric=f"skill_vs_{PERSISTENCE}",
        model=MODEL,
        airport="KATL",
        horizon=3,
    )
    assert skill == pytest.approx(1 - 1 / 2)
    assert not rows_matching(
        records, slice="own_support", metric=f"skill_vs_{CLIMATOLOGY}"
    )


def test_skill_is_null_with_a_reason_when_a_baseline_is_absent():
    table = predictions_for("KATL", [DAY_ONE], {MODEL: [12.0], PERSISTENCE: [14.0]})
    records = records_of(table, labels_for(table, [10.0]))
    row = record(
        records,
        metric=f"skill_vs_{CLIMATOLOGY}",
        model=MODEL,
        airport="KATL",
        horizon=3,
    )
    assert (row["value"], row["reason"]) == (None, "baseline_absent")


def test_skill_ci_keeps_rows_on_their_own_days():
    days = MIN_CI_DAYS + 10
    targets = [
        str(t)
        for t in pd.date_range("2024-03-01 15:00", periods=days, freq="D", tz="UTC")
        for t in (t, t + pd.Timedelta(hours=1))
    ]
    n = len(targets)
    table = predictions_for(
        "KATL",
        targets,
        {
            MODEL: np.arange(1.0, n + 1),
            PERSISTENCE: np.full(n, 5.0),
            CLIMATOLOGY: np.ones(n),
        },
    )
    # Scrambled ids split each day's rows apart unless days follow the pivot's order.
    order = np.random.default_rng(1).permutation(n)
    ids = dict(zip(table["prediction_id"].unique(), [f"{i:04d}" for i in order]))
    table["prediction_id"] = table["prediction_id"].map(ids)
    rows = scored(table, labels_for(table, [0.0] * n))
    squared = squared_errors(rows)
    days_by_id = rows.drop_duplicates("prediction_id").set_index("prediction_id")["day"]
    support = baseline_support(squared, MODEL, TARGET)
    metric = next(
        m
        for m in skill_metrics(support, days_by_id, MODEL, TARGET)
        if m["metric"] == f"skill_vs_{PERSISTENCE}"
    )
    model_rows = rows[rows["model_version"].eq(MODEL)].sort_values("prediction_id")
    expected = _ci(
        model_rows["day"],
        _rmse_skill,
        (model_rows["estimate"] ** 2).to_numpy(),
        np.full(n, 25.0),
    )
    assert metric["ci_low"] == pytest.approx(expected["ci_low"])


def test_common_support_drops_rows_any_model_could_not_score():
    table = predictions_for(
        "KATL",
        [DAY_ONE, DAY_TWO],
        {MODEL: [12.0, 21.0], PERSISTENCE: [np.nan, 24.0], CLIMATOLOGY: [10.0, 20.0]},
    )
    records = records_of(table, labels_for(table, [10.0, 20.0]))
    match = {"metric": "rmse", "airport": "KATL", "horizon": 3, "model": MODEL}
    assert record(records, slice="own_support", **match)["n_predicted"] == 2
    common = record(records, slice="common_support", **match)
    assert common["n_predicted"] == 1
    assert common["value"] == pytest.approx(1.0)


def test_unavailable_rows_do_not_count_as_predicted():
    table = predictions_for(
        "KATL",
        [DAY_ONE, DAY_TWO],
        {PERSISTENCE: [np.nan, 24.0], CLIMATOLOGY: [10.0, 20.0]},
    )
    records = records_of(table, labels_for(table, [10.0, 20.0]))
    row = record(
        records,
        metric="rmse",
        airport="KATL",
        horizon=3,
        model=PERSISTENCE,
        slice="own_support",
    )
    assert (row["n_eligible"], row["n_predicted"]) == (2, 1)
    assert (row["n_days"], row["n_targets"]) == (1, 1)


@pytest.mark.parametrize(
    ("kind", "unit", "names"),
    [
        (
            TARGET,
            UNIT,
            {"rmse": UNIT, "pinball_loss": UNIT, "p10_p90_coverage": "share"},
        ),
        (
            SEVERE,
            PROBABILITY,
            {"brier": "probability^2", "average_precision": "share"},
        ),
    ],
)
def test_a_model_with_no_estimates_reports_every_metric_as_null(kind, unit, names):
    first, second = required_baselines(kind)
    table = predictions_for(
        "KATL",
        [DAY_ONE],
        {MODEL: [np.nan], first: [0.5], second: [0.5]},
        target_kind=kind,
        unit=unit,
    )
    records = records_of(table, labels_for(table, [1.0], unit))
    common = {
        "model": MODEL,
        "airport": "KATL",
        "horizon": 3,
        "slice": "common_support",
    }
    skill = {**common, "slice": "baseline_support"}
    for name, expected_unit in names.items():
        row = record(records, metric=name, **common)
        assert (row["value"], row["unit"]) == (None, expected_unit)
        assert row["reason"] == "no_predicted_rows"
    for name, expected_unit in {f"skill_vs_{first}": "share"}.items():
        row = record(records, metric=name, **skill)
        assert (row["value"], row["unit"]) == (None, expected_unit)
        assert row["reason"] == "no_predicted_rows"


# Bootstrap


def test_ci_brackets_the_estimate_and_repeats_exactly():
    n = MIN_CI_DAYS + 10
    rng = np.random.default_rng(0)
    y = rng.poisson(20, n).astype(float)
    table = predictions_for("KATL", daily(n), {MODEL: y + rng.normal(0, 2, n)})
    rows = scored(table, labels_for(table, list(y)))
    first = regression_metrics(rows)[0]
    assert first["ci_low"] < first["value"] < first["ci_high"]
    assert first["ci_method"].startswith("operational_day_block")
    assert regression_metrics(rows)[0] == first


def test_ci_is_null_below_the_minimum_day_count():
    table = predictions_for("KATL", daily(MIN_CI_DAYS - 1), {MODEL: [1.0] * 19})
    rows = scored(table, labels_for(table, [2.0] * (MIN_CI_DAYS - 1)))
    rmse = regression_metrics(rows)[0]
    assert (rmse["ci_low"], rmse["ci_method"]) == (None, None)
    assert rmse["ci_reason"] == "too_few_days"
    assert rmse["value"] == 1


def test_ci_is_null_when_a_resample_is_not_finite():
    errors = np.r_[np.zeros(MIN_CI_DAYS - 1), [1.0]]
    days = pd.Series(np.arange(MIN_CI_DAYS))
    result = _ci(days, _brier_skill, np.ones(MIN_CI_DAYS), errors)
    assert result["ci_low"] is None
    assert result["ci_reason"] == "nonfinite_resample"


def test_correlated_rows_widen_the_day_block_ci():
    rng = np.random.default_rng(3)
    n_days, per_day = 40, 24
    shared = np.repeat(rng.normal(0, 1, n_days), per_day)
    blocked = _ci(pd.Series(np.repeat(np.arange(n_days), per_day)), _mean, shared)
    by_row = _ci(pd.Series(np.arange(n_days * per_day)), _mean, shared)
    assert blocked["ci_high"] - blocked["ci_low"] > 3 * (
        by_row["ci_high"] - by_row["ci_low"]
    )


def test_one_operational_day_spans_airports_horizons_and_midnight_utc():
    late = ["2024-03-05 23:00", "2024-03-06 01:00"]
    table = pd.concat(
        [
            predictions_for(icao, late, {MODEL: [1.0] * 4}, horizons=(3, 12))
            for icao in ("KATL", "KDFW")
        ],
        ignore_index=True,
    )
    joined = join_labels(table, labels_for(table, [1.0] * len(table)))
    assert joined["day"].nunique() == 1


def test_the_operational_day_turns_over_at_0800_utc():
    assert DAY_OFFSET == pd.Timedelta(hours=8)
    table = predictions_for(
        "KATL", ["2024-03-05 07:00", "2024-03-05 08:00"], {MODEL: [1.0, 2.0]}
    )
    joined = join_labels(table, labels_for(table, [1.0, 2.0]))
    assert joined["day"].nunique() == 2


# Denominators and exclusions


def test_cancelled_flights_are_excluded_not_negative():
    table, labels = severe_table([0.9, 0.2, 0.2, 0.2], [1, 0, 0, None])
    records = records_of(table, labels)
    row = record(
        records, metric="brier", airport="KATL", horizon=3, slice="own_support"
    )
    assert (row["n_eligible"], row["n_predicted"]) == (3, 3)
    assert row["n_excluded"] == 1
    assert row["exclusions"] == {"cancelled": 1}
    assert row["prevalence"] == pytest.approx(1 / 3)
    assert row["value"] == pytest.approx((0.01 + 0.04 + 0.04) / 3)
    rate = record(
        records,
        metric="cancellation_rate",
        airport="KATL",
        horizon=3,
        slice="own_support",
    )
    assert rate["value"] == pytest.approx(0.25)


def test_prevalence_uses_the_rows_a_model_scored():
    table, labels = severe_table([np.nan, 0.2, 0.2, 0.2], [1, 1, 0, 0])
    records = records_of(table, labels)
    row = record(
        records, metric="brier", airport="KATL", horizon=3, slice="own_support"
    )
    assert row["prevalence"] == pytest.approx(1 / 3)
    assert row["n_eligible"] == 4


def test_cancellation_rate_ignores_other_exclusions():
    table, labels = severe_table([0.5] * 4, [1, 0, None, None])
    labels.loc[labels.index[3], "exclusion_reason"] = "quarantined"
    records = records_of(table, labels)
    rate = rows_matching(records, metric="cancellation_rate", airport="KATL", horizon=3)
    assert len(rate) == 1
    assert rate[0]["slice"] == "own_support"
    assert rate[0]["value"] == pytest.approx(1 / 3)


# Aggregates


def test_macro_averages_airports_and_pooled_weights_rows():
    katl = predictions_for("KATL", [DAY_ONE], {MODEL: [14.0]})
    kdfw = predictions_for(
        "KDFW",
        [DAY_ONE, DAY_TWO, "2024-03-07 15:00"],
        {MODEL: [11.0, 21.0, 31.0]},
    )
    table = pd.concat([katl, kdfw], ignore_index=True)
    records = records_of(table, labels_for(table, [10.0, 10.0, 20.0, 30.0]))
    records += macro_records(records)
    match = {"metric": "mae", "horizon": 3, "slice": "own_support"}
    assert value(records, airport="macro", **match) == pytest.approx((4 + 1) / 2)
    assert value(records, airport="pooled", **match) == pytest.approx((4 + 3) / 4)


@pytest.mark.parametrize("metric", ["average_precision", "brier"])
def test_macro_is_null_when_one_airport_is_undefined(metric):
    katl = predictions_for(
        "KATL", [DAY_ONE], {MODEL: [np.nan]}, target_kind=SEVERE, unit=PROBABILITY
    )
    kdfw = predictions_for(
        "KDFW",
        [DAY_ONE, DAY_TWO],
        {MODEL: [0.9, 0.1]},
        target_kind=SEVERE,
        unit=PROBABILITY,
    )
    table = pd.concat([katl, kdfw], ignore_index=True)
    records = records_of(table, labels_for(table, [0.0, 1.0, 0.0], PROBABILITY))
    records += macro_records(records)
    row = record(
        records, metric=metric, airport="macro", horizon=3, slice="own_support"
    )
    assert row["value"] is None
    assert row["reason"] == "undefined_for_an_airport"


def test_macro_is_null_when_an_airport_has_no_record():
    katl = predictions_for("KATL", [DAY_ONE], {MODEL: [12.0, 12.0]}, horizons=(3, 6))
    kdfw = predictions_for("KDFW", [DAY_ONE], {MODEL: [12.0]}, horizons=(3,))
    table = pd.concat([katl, kdfw], ignore_index=True)
    records = records_of(table, labels_for(table, [10.0] * 3))
    records += macro_records(records)
    row = record(records, metric="mae", airport="macro", horizon=6, slice="own_support")
    assert row["value"] is None


def test_macro_sums_exclusions():
    katl, labels_a = severe_table([0.5, 0.5], [1, None])
    kdfw = katl.assign(
        airport_icao="KDFW", prediction_id=katl["prediction_id"] + "|dfw"
    )
    labels_b = labels_a.assign(prediction_id=labels_a["prediction_id"] + "|dfw")
    records = records_of(
        pd.concat([katl, kdfw], ignore_index=True),
        pd.concat([labels_a, labels_b], ignore_index=True),
    )
    macro = macro_records(records)
    row = record(macro, metric="brier", horizon=3, slice="own_support")
    assert row["exclusions"] == {"cancelled": 2}
    assert row["n_excluded"] == 2


# Reliability and worst misses


def test_reliability_bins_keep_their_denominators():
    table, labels = severe_table([i / 40 for i in range(20)], [0] * 19 + [1])
    bins = [b for b in reliability(scored(table, labels)) if b["airport"] == "pooled"]
    assert sum(b["n"] for b in bins) == 20
    assert len(bins) == 10
    assert bins[-1]["observed_rate"] == pytest.approx(0.5)


def test_reliability_keeps_tied_probabilities_in_one_bin():
    table, labels = severe_table([0.5] * 20, [0] * 15 + [1] * 5)
    bins = [b for b in reliability(scored(table, labels)) if b["airport"] == "pooled"]
    assert len(bins) == 1
    assert bins[0]["n"] == 20


def test_reliability_reports_each_airport_on_common_rows():
    table = predictions_for(
        "KATL",
        [DAY_ONE, DAY_TWO],
        {MODEL: [0.2, 0.8], PERSISTENCE: [np.nan, 0.5], CLIMATOLOGY: [0.5, 0.5]},
        target_kind=SEVERE,
        unit=PROBABILITY,
    )
    bins = reliability(scored(table, labels_for(table, [0.0, 1.0], PROBABILITY)))
    assert {b["airport"] for b in bins} == {"KATL", "pooled"}
    assert all(b["n"] == 1 for b in bins)
    assert {b["model"] for b in bins} == {MODEL, PERSISTENCE, CLIMATOLOGY}


def test_worst_misses_show_one_row_per_airport_day_with_baselines():
    table = predictions_for(
        "KATL",
        [
            "2024-03-05 15:00",
            "2024-03-05 16:00",
            "2024-03-06 15:00",
            "2024-03-07 15:00",
        ],
        {MODEL: [50.0, 60.0, 30.0, 25.0], PERSISTENCE: [10.0, 11.0, 12.0, 13.0]},
    )
    misses = worst_misses(scored(table, labels_for(table, [10.0, 10.0, 10.0, 10.0])))
    assert [m["error"] for m in misses] == [50.0, 20.0, 15.0]
    assert misses[0]["target_start_utc"] == "2024-03-05T16:00:00Z"
    assert misses[0]["baseline_estimates"] == {PERSISTENCE: 11.0}
    assert misses[0]["target_label"] == "arrival throughput (AAR proxy)"
    assert misses[0]["explanation"] is None
    assert misses[0]["explanation_reason"] == "needs_feature_snapshots"


# Labelling


def test_capacity_ratio_keeps_the_proxy_label():
    assert "(AAR proxy)" in TARGET_LABELS[CAPACITY_RATIO]


def test_simulated_inputs_stay_marked_in_records_and_legends():
    table = throughput_table()
    table["reason_codes"] = [
        [SIMULATED_FEED]
        if m == PERSISTENCE
        else [RETROSPECTIVE_SCHEDULE, "other"]
        if m == CLIMATOLOGY
        else []
        for m in table["model_version"]
    ]
    basis = availability_basis(table)
    assert basis == {
        PERSISTENCE: [SIMULATED_FEED],
        CLIMATOLOGY: [RETROSPECTIVE_SCHEDULE],
    }
    records = records_of(table, labels_for(table, [10.0, 20.0]), basis)
    row = record(
        records,
        metric="rmse",
        model=PERSISTENCE,
        airport="KATL",
        horizon=3,
        slice="own_support",
    )
    assert row["availability_basis"] == [SIMULATED_FEED]
    assert "simulated feed" in _label(PERSISTENCE, basis)


def test_each_candidate_gets_its_own_colour():
    colours = _colours([MODEL, OTHER_MODEL, PERSISTENCE])
    assert len(set(colours.values())) == 3
    assert list(colours)[:2] == [MODEL, OTHER_MODEL]


# Contract checks


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.assign(estimate=1.7), "probability outside"),
        (lambda d: d.assign(estimate=-0.1), "probability outside"),
        (lambda d: d.assign(p10=2.0, p90=1.0), "p10 above p90"),
        (lambda d: d.assign(horizon_h=7), "horizon_h outside"),
    ],
)
def test_contract_breaks_are_refused(change, message):
    table, _ = severe_table([0.5], [1])
    with pytest.raises(ValueError, match=message):
        check_contract(change(table))


def test_a_valid_table_passes_the_contract():
    check_contract(severe_table([0.5], [1])[0])


def test_a_prediction_id_that_disagrees_with_its_request_is_refused():
    # A 2025 request carried on a 2024 timestamp would otherwise pass as dev.
    leaked = predictions_for("KATL", [TEST_DAY], {MODEL: [1.0]})
    requests = requests_of(leaked)
    table = leaked.assign(
        target_start_utc=ts(DAY_ONE),
        target_end_utc=ts(DAY_ONE) + pd.Timedelta(hours=1),
        as_of_utc=ts(DAY_ONE) - pd.Timedelta(hours=3),
    )
    with pytest.raises(ValueError, match="no matching request"):
        check_requests(table.assign(split="validation"), requests)


def test_a_prediction_with_no_request_is_refused():
    table = throughput_table().assign(split="validation")
    with pytest.raises(ValueError, match="no matching request"):
        check_requests(table, requests_of(table).iloc[1:])


def scope_of(table: pd.DataFrame, requests: pd.DataFrame, cutoffs=None):
    table = table.assign(split=evaluate.split_of(table["target_start_utc"]))
    if "run" not in table:
        table = table.assign(run="run")
    return scoring_scope(table, requests, cutoffs or {"run": ts(FIT_CUTOFF)})


def test_a_model_cannot_drop_requests_it_could_not_score():
    table = throughput_table()
    dropped = table[
        table["model_version"].ne(MODEL) | table["target_start_utc"].eq(ts(DAY_ONE))
    ]
    with pytest.raises(ValueError, match=f"{MODEL} has no"):
        scope_of(dropped, requests_of(table))


def test_marking_a_request_unavailable_satisfies_the_check():
    table = predictions_for("KATL", [DAY_ONE, DAY_TWO], {MODEL: [1.0, np.nan]})
    scope_of(table, requests_of(table))


def test_requests_outside_the_scored_scope_are_not_expected():
    table = throughput_table()
    other = predictions_for(
        "KATL",
        [TEST_DAY, "2024-01-01 02:00", "2024-09-01 15:00"],
        {MODEL: [1.0, 1.0, 1.0]},
    )
    requests = pd.concat([requests_of(table), requests_of(other)], ignore_index=True)
    # 2024-01-01 02:00 was issued before the fit cutoff, so nothing should score it.
    requests = requests[requests["target_start_utc"].ne(ts("2024-09-01 15:00"))]
    scope_of(table, requests)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.drop(index=0), "no label"),
        (lambda d: d.assign(unit="arrivals"), "unit"),
        (lambda d: pd.concat([d, d]), "more than one label"),
        (lambda d: d.assign(label_version=["a", "b"]), "one label_version"),
    ],
)
def test_broken_label_keys_fail_loudly(tmp_path, change, message):
    table = throughput_table()
    path = write_labels(change(labels_for(table, [10.0, 20.0])), tmp_path)
    with pytest.raises(ValueError, match=message):
        check_label_keys(path, table)


def write_labels(labels: pd.DataFrame, tmp_path) -> str:
    path = tmp_path / "labels.parquet"
    labels.to_parquet(path)
    return path


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.assign(y_true=2.0), "exactly 0 or 1"),
        (lambda d: d.assign(y_true=np.nan), "without an outcome"),
        (lambda d: d.assign(exclusion_reason="cancelled"), "null exactly when"),
        (
            lambda d: d.assign(
                eligible=False, exclusion_reason=None, exclusion_detail="x"
            ),
            "null exactly when",
        ),
        (
            lambda d: d.assign(
                eligible=False, exclusion_reason="canceled", exclusion_detail="x"
            ),
            "unknown exclusion_reason",
        ),
    ],
)
def test_invalid_labels_are_refused(tmp_path, change, message):
    table, labels = severe_table([0.5], [1])
    path = write_labels(change(labels), tmp_path)
    with pytest.raises(ValueError, match=message):
        load_labels(path, table["prediction_id"].unique().tolist())


def test_a_cancelled_flight_loads_without_a_binary_outcome(tmp_path):
    table, labels = severe_table([0.5, 0.5], [1, None])
    path = write_labels(labels, tmp_path)
    loaded = load_labels(path, table["prediction_id"].unique().tolist())
    assert loaded["eligible"].tolist() == [True, False]


def test_dev_labels_never_load_rows_outside_the_prediction_set(tmp_path):
    dev = throughput_table()
    test = predictions_for("KATL", [TEST_DAY], {MODEL: [1.0]})
    labels = pd.concat(
        [labels_for(dev, [10.0, 20.0]), labels_for(test, [99.0])], ignore_index=True
    )
    path = write_labels(labels, tmp_path)
    loaded = load_labels(path, dev["prediction_id"].unique().tolist())
    assert 99.0 not in set(loaded["y_true"])
    assert len(loaded) == 2


# Baselines beside every model


def test_a_model_needs_both_baselines():
    table = predictions_for("KATL", [DAY_ONE], {MODEL: [12.0], PERSISTENCE: [9]})
    with pytest.raises(ValueError, match="baseline_climatology_v1"):
        check_baselines(table.assign(split="validation"))


def full_cell(icao: str, split: str, horizon: int = 3) -> pd.DataFrame:
    table = predictions_for(
        icao,
        [DAY_ONE],
        {MODEL: [1.0], PERSISTENCE: [1.0], CLIMATOLOGY: [1.0]},
        horizons=(horizon,),
    )
    return table.assign(split=split)


def test_baselines_in_every_cell_pass():
    check_baselines(
        pd.concat(
            [full_cell("KATL", "validation"), full_cell("KDFW", "validation")],
            ignore_index=True,
        )
    )


@pytest.mark.parametrize(
    "other",
    [
        full_cell("KATL", "calibration"),
        full_cell("KDFW", "validation"),
        full_cell("KATL", "validation", horizon=6),
    ],
    ids=["split", "airport", "horizon"],
)
def test_baselines_are_checked_cell_by_cell(other):
    cell = other[other["model_version"].eq(MODEL)]
    table = pd.concat([full_cell("KATL", "validation"), cell], ignore_index=True)
    with pytest.raises(ValueError, match="needs baselines"):
        check_baselines(table)


def test_a_baseline_with_no_estimates_does_not_count():
    table = predictions_for(
        "KATL", [DAY_ONE], {MODEL: [1.0], PERSISTENCE: [np.nan], CLIMATOLOGY: [1.0]}
    )
    with pytest.raises(ValueError, match="needs baselines"):
        check_baselines(table.assign(split="validation"))


def test_a_model_and_baselines_must_share_a_row():
    table = predictions_for(
        "KATL",
        [DAY_ONE, DAY_TWO],
        {MODEL: [1.0, np.nan], PERSISTENCE: [np.nan, 1.0], CLIMATOLOGY: [1.0, 1.0]},
    )
    with pytest.raises(ValueError, match="shares no row"):
        check_baselines(table.assign(split="validation"))


def test_baselines_alone_need_no_model():
    check_baselines(
        predictions_for("KATL", [DAY_ONE], {PERSISTENCE: [1.0]}).assign(
            split="validation"
        )
    )


# Scope


FIT_CUTOFF = "2024-01-01T00:00:00+00:00"


def write_run(
    table: pd.DataFrame, root, run: str = "run", dirty: bool = False, **manifest
) -> None:
    baselines.write_predictions(
        table.drop(columns=["split", "day", "run"], errors="ignore"),
        root / run / "predictions.parquet",
    )
    requests = root.parent / "requests.parquet"
    manifest = {
        "run_id": run,
        "data_mode": table["data_mode"].iloc[0],
        "commit_dirty": dirty,
        "fit_cutoff_utc": FIT_CUTOFF,
        "prediction_requests_sha256": sha256(requests) if requests.exists() else None,
        **manifest,
    }
    (root / run / "manifest.json").write_text(json.dumps(manifest))


def rebind(inputs: list) -> None:
    # A test that rewrites the requests table re-binds every run manifest to it.
    for path in inputs[2].glob("*/manifest.json"):
        manifest = json.loads(path.read_text())
        manifest["prediction_requests_sha256"] = sha256(inputs[1])
        path.write_text(json.dumps(manifest))


@pytest.mark.parametrize(
    ("targets", "locked"),
    [
        ([TEST_DAY], False),
        ([DAY_ONE], True),
        (["2023-06-01 15:00"], False),
        ([DAY_ONE, TEST_DAY], False),
        ([DAY_ONE, TEST_DAY], True),
    ],
)
def test_predictions_outside_the_run_scope_are_refused(tmp_path, targets, locked):
    table = predictions_for("KATL", targets, {MODEL: [1.0] * len(targets)})
    write_run(table, tmp_path)
    with pytest.raises(ValueError):
        load_predictions(tmp_path, ["run"], locked)


@pytest.fixture
def clean_git(monkeypatch):
    monkeypatch.setattr(baselines, "git", lambda *args: "")
    monkeypatch.setattr(evaluate, "git", lambda *args: "")


@pytest.fixture(autouse=True)
def canonical(monkeypatch, tmp_path):
    # Every test sees tmp canonical paths, so none can touch the real ledger.
    monkeypatch.setattr(evaluate, "LABELS", tmp_path / "labels.parquet")
    monkeypatch.setattr(evaluate, "REQUESTS", tmp_path / "requests.parquet")
    monkeypatch.setattr(evaluate, "REPORTS", tmp_path / "reports")
    for module in (baselines, evaluate):
        monkeypatch.setattr(module, "LEDGER", tmp_path / "ledger")
        monkeypatch.setattr(module, "LEDGER_MIRROR", tmp_path / "mirror")


def run_inputs(table: pd.DataFrame, labels: pd.DataFrame, tmp_path) -> list:
    artifacts = tmp_path / "artifacts"
    requests_path = tmp_path / "requests.parquet"
    requests_of(table).to_parquet(requests_path)
    write_run(table, artifacts)
    labels_path = write_labels(labels, tmp_path)
    return [
        labels_path,
        requests_path,
        artifacts,
        tmp_path / "reports",
        tmp_path / "ledger",
        tmp_path / "mirror",
    ]


def test_fixture_run_never_writes_the_reported_metrics(tmp_path, clean_git):
    table = throughput_table()
    inputs = run_inputs(table, labels_for(table, [10.0, 20.0]), tmp_path)
    reports = inputs[3]
    path = main(["run"], *inputs)
    assert path == reports / "fixture" / "metrics_dev.json"
    assert not (reports / "metrics.json").exists()
    report = json.loads(path.read_text())
    assert report["data_mode"] == "fixture"
    assert report["scope"] == "dev"
    assert report["label_versions"] == ["fixture"]
    assert report["seed"] == evaluate.EXPERIMENT["seed"]
    assert len(report["uv_lock_sha256"]) == 64
    assert report["split_bounds"]["validation"][0] == "2024-01-01T00:00:00Z"
    assert report["target_labels"][TARGET] == "arrival throughput (AAR proxy)"
    figures = reports / "fixture" / "figures"
    assert (figures / f"rmse_{TARGET}_validation_fixture-v0.png").exists()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda t, y: (
                t.assign(
                    estimate=np.nan,
                    status="unavailable",
                    reason_codes=[["x"]] * len(t),
                    p10=2.0,
                    p90=1.0,
                ),
                y,
            ),
            "p10 above",
        ),
        (lambda t, y: (t[t["model_version"].ne(CLIMATOLOGY)], y), "needs baselines"),
        (lambda t, y: (t.iloc[1:], y), "has no"),
        (lambda t, y: (t, y.assign(data_mode="real")), "mixed data_mode"),
        (lambda t, y: (t, y.drop(columns="data_mode")), "data_mode column"),
        (
            lambda t, y: (t.assign(data_mode="Real"), y.assign(data_mode="Real")),
            "outside",
        ),
    ],
)
def test_main_runs_every_check_before_scoring(tmp_path, clean_git, change, message):
    table = throughput_table()
    labels = labels_for(table, [10.0, 20.0])
    changed, changed_labels = change(table, labels)
    inputs = run_inputs(changed, changed_labels, tmp_path)
    requests = requests_of(table).assign(data_mode=changed["data_mode"].iloc[0])
    requests.to_parquet(inputs[1])
    rebind(inputs)
    with pytest.raises(ValueError, match=message):
        main(["run"], *inputs)
    assert not inputs[3].exists()


def real_test_table() -> pd.DataFrame:
    table = predictions_for(
        "KATL",
        [TEST_DAY],
        {MODEL: [8.0], PERSISTENCE: [9.0], CLIMATOLOGY: [12.0]},
    )
    return table.assign(data_mode="real")


def locked_inputs(tmp_path, table=None, label_mode: str = "real") -> list:
    table = real_test_table() if table is None else table
    return run_inputs(table, labels_for(table, [10.0], data_mode=label_mode), tmp_path)


def locked_run(
    inputs: list, approved_by: str | None = "tester", runs=("run",)
) -> object:
    # Canonical paths come from the patched constants, not from arguments.
    return main(
        list(runs), artifacts=inputs[2], locked_test=True, approved_by=approved_by
    )


def assert_nothing_happened(inputs: list) -> None:
    assert not (inputs[3] / "metrics.json").exists()
    assert not inputs[4].exists()
    assert not inputs[5].exists()


def test_locked_run_claims_then_writes_once(tmp_path, clean_git):
    inputs = locked_inputs(tmp_path)
    path = locked_run(inputs)
    assert path.name == "metrics.json"
    assert json.loads(path.read_text())["approved_by"] == "tester"
    claim = json.loads((inputs[4] / "evaluate_primary.json").read_text())
    assert claim["approved_by"] == "tester"
    written = path.read_bytes()
    with pytest.raises(FileExistsError, match="runs once"):
        locked_run(inputs)
    assert path.read_bytes() == written


def test_locked_run_stays_spent_if_the_report_is_deleted(tmp_path, clean_git):
    inputs = locked_inputs(tmp_path)
    locked_run(inputs).unlink()
    with pytest.raises(FileExistsError, match="runs once"):
        locked_run(inputs)


def test_locked_run_refuses_fixture_labels(tmp_path, clean_git):
    inputs = locked_inputs(tmp_path, label_mode="fixture")
    with pytest.raises(ValueError, match="mixed data_mode"):
        locked_run(inputs)
    assert_nothing_happened(inputs)


def test_locked_run_refuses_fixture_data(tmp_path, clean_git):
    table = real_test_table().assign(data_mode="fixture")
    inputs = locked_inputs(tmp_path, table, label_mode="fixture")
    with pytest.raises(ValueError, match="needs real data"):
        locked_run(inputs)
    assert_nothing_happened(inputs)


def test_locked_run_needs_approval(tmp_path, clean_git):
    inputs = locked_inputs(tmp_path)
    with pytest.raises(ValueError, match="approved_by"):
        locked_run(inputs, approved_by=None)
    assert_nothing_happened(inputs)


def test_locked_run_refuses_uncommitted_code(tmp_path, monkeypatch):
    inputs = locked_inputs(tmp_path)
    monkeypatch.setattr(baselines, "git", lambda *args: " M uv.lock")
    monkeypatch.setattr(evaluate, "git", lambda *args: "abc")
    with pytest.raises(ValueError, match="committed"):
        locked_run(inputs)
    assert_nothing_happened(inputs)


def test_dirty_check_covers_code_and_locked_dependencies(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(baselines, "git", lambda *args: seen.append(args) or "")
    monkeypatch.setattr(evaluate, "git", lambda *args: "abc")
    locked_run(locked_inputs(tmp_path))
    assert seen == [("status", "--porcelain", "--", *SOURCE_PATHS)]


def test_locked_run_refuses_a_baselines_only_run(tmp_path, clean_git):
    table = real_test_table()
    inputs = locked_inputs(tmp_path, table[table["model_version"].ne(MODEL)])
    with pytest.raises(ValueError, match="one frozen model"):
        locked_run(inputs)
    assert_nothing_happened(inputs)


def test_locked_run_refuses_several_candidates(tmp_path, clean_git):
    table = real_test_table()
    extra = table[table["model_version"].eq(MODEL)].assign(model_version=OTHER_MODEL)
    inputs = locked_inputs(tmp_path, pd.concat([table, extra], ignore_index=True))
    with pytest.raises(ValueError, match="one frozen model"):
        locked_run(inputs)
    assert_nothing_happened(inputs)


def test_every_target_needs_a_candidate():
    table = real_test_table()
    only_baselines = predictions_for(
        "KATL", [TEST_DAY], {PERSISTENCE: [0.5]}, target_kind=SEVERE, unit=PROBABILITY
    )
    with pytest.raises(ValueError, match="one frozen model"):
        check_locked_candidates(pd.concat([table, only_baselines], ignore_index=True))


MANIFEST = {"fit_cutoff_utc": FIT_CUTOFF}


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        (
            {
                **MANIFEST,
                "run_id": "run",
                "data_mode": "fixture",
                "commit_dirty": False,
            },
            "real data",
        ),
        (
            {**MANIFEST, "run_id": "run", "data_mode": "real", "commit_dirty": True},
            "uncommitted",
        ),
        (
            {**MANIFEST, "run_id": "run", "data_mode": "real", "commit_dirty": None},
            "uncommitted",
        ),
        (
            {**MANIFEST, "run_id": "other", "data_mode": "real", "commit_dirty": False},
            "belongs to",
        ),
    ],
)
def test_locked_run_reads_each_run_manifest(tmp_path, clean_git, manifest, message):
    inputs = locked_inputs(tmp_path)
    manifest = {**manifest, "prediction_requests_sha256": sha256(inputs[1])}
    (inputs[2] / "run" / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=message):
        locked_run(inputs)
    assert_nothing_happened(inputs)


def test_a_crash_before_scoring_spends_the_locked_run(tmp_path, clean_git, monkeypatch):
    inputs = locked_inputs(tmp_path)

    def crash(*args):
        raise RuntimeError("crash after reading labels")

    with monkeypatch.context() as patch:
        patch.setattr(evaluate, "load_labels", crash)
        with pytest.raises(RuntimeError, match="crash"):
            locked_run(inputs)
    with pytest.raises(FileExistsError, match="runs once"):
        locked_run(inputs)


def test_a_figure_failure_publishes_no_report(tmp_path, clean_git, monkeypatch):
    inputs = locked_inputs(tmp_path)

    def crash(*args):
        raise RuntimeError("figure failed")

    monkeypatch.setattr(evaluate, "rmse_figure", crash)
    with pytest.raises(RuntimeError, match="figure failed"):
        locked_run(inputs)
    assert not (inputs[3] / "metrics.json").exists()


def test_dev_run_needs_no_approval_and_records_a_dirty_tree(tmp_path, monkeypatch):
    table = throughput_table()
    inputs = run_inputs(table, labels_for(table, [10.0, 20.0]), tmp_path)
    monkeypatch.setattr(baselines, "git", lambda *args: " M src/x.py")
    monkeypatch.setattr(evaluate, "git", lambda *args: " M src/x.py")
    report = json.loads(main(["run"], *inputs).read_text())
    assert report["commit_dirty"] is True
    assert report["approved_by"] is None


def test_baseline_run_scores_end_to_end_on_the_fixture(hourly, tmp_path, clean_git):
    targets = pd.date_range("2024-03-01", periods=240, freq="h", tz="UTC")
    requests = pd.concat(
        [make_requests(icao, targets) for icao in ["KATL", "KDFW"]], ignore_index=True
    )
    predictions, _ = baselines.baseline_predictions(hourly, requests)
    truth = hourly.set_index(["airport_icao", "hour_start_utc"])[TARGET]
    rows = predictions.drop_duplicates("prediction_id")
    keys = pd.MultiIndex.from_frame(rows[["airport_icao", "target_start_utc"]])
    labels = pd.DataFrame(
        {
            "prediction_id": rows["prediction_id"].to_numpy(),
            "target_kind": TARGET,
            "y_true": truth.reindex(keys).astype("float64").to_numpy(),
            "eligible": True,
            "exclusion_reason": None,
            "exclusion_detail": None,
            "label_version": "fixture",
            "unit": UNIT,
            "data_mode": "fixture",
        }
    )
    table = predictions.assign(
        data_snapshot_id="fixture-0", generated_at_utc=ts("2026-10-31")
    )
    path = main(["run"], *run_inputs(table, labels, tmp_path))
    report = json.loads(path.read_text())
    rmse = record(
        report["metrics"],
        metric="rmse",
        model=CLIMATOLOGY,
        airport="macro",
        horizon=12,
        slice="common_support",
    )
    assert rmse["value"] > 0
    assert rmse["ci_reason"] == "not_resampled"
    assert report["availability_basis"][PERSISTENCE] == [SIMULATED_FEED]
    assert report["worst_misses"] == []


# Findings pinned from the re-audit


def test_a_stray_outcome_column_cannot_override_labels(tmp_path):
    table = throughput_table().assign(y_true=0.0)
    (tmp_path / "run").mkdir()
    table.to_parquet(tmp_path / "run" / "predictions.parquet")
    with pytest.raises(ValueError, match="y_true"):
        load_predictions(tmp_path, ["run"], False)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.assign(estimate=np.inf), "finite"),
        (lambda d: d.assign(reason_codes=None), "reason_codes"),
    ],
)
def test_unscorable_values_are_refused_on_read(change, message):
    with pytest.raises(ValueError, match=message):
        check_contract(change(throughput_table()))


@pytest.mark.parametrize(
    "column", ["airport_icao", "as_of_utc", "horizon_h", "task", "cohort_version"]
)
def test_every_request_field_must_match(column):
    table = throughput_table().assign(split="validation")
    requests = requests_of(table)
    replacement = ts("2024-03-01") if column == "as_of_utc" else None
    values = {
        "airport_icao": "KDFW",
        "horizon_h": 6,
        "task": "other",
        "cohort_version": "other",
    }
    requests[column] = replacement if column == "as_of_utc" else values[column]
    with pytest.raises(ValueError, match="no matching request"):
        check_requests(table, requests)


def test_a_duplicate_request_id_is_refused():
    table = throughput_table().assign(split="validation")
    requests = pd.concat([requests_of(table), requests_of(table).iloc[[0]]])
    with pytest.raises(ValueError, match="duplicate prediction_id"):
        check_requests(table, requests)


def test_scope_keeps_other_tasks_and_cohorts_apart():
    table = throughput_table()
    other = requests_of(predictions_for("KDFW", [DAY_ONE], {MODEL: [1.0]}))
    extra = pd.concat(
        [other.assign(task="other_task"), other.assign(cohort_version="csv_only_v1")],
        ignore_index=True,
    ).assign(prediction_id=lambda d: "other-" + d.index.astype(str))
    scope_of(table, pd.concat([requests_of(table), extra], ignore_index=True))


def test_labels_are_checked_after_requests_in_a_dev_run(
    tmp_path, clean_git, monkeypatch
):
    table = throughput_table()
    inputs = run_inputs(table, labels_for(table, [10.0, 20.0]), tmp_path)
    requests_of(table).iloc[1:].to_parquet(inputs[1])
    rebind(inputs)

    def never(*args):
        raise AssertionError("labels were read before the requests check")

    monkeypatch.setattr(evaluate, "load_labels", never)
    with pytest.raises(ValueError, match="no matching request"):
        main(["run"], *inputs)


@pytest.mark.parametrize(
    "breakage",
    [
        lambda t, y, r: (t.iloc[1:], y, r),
        lambda t, y, r: (t[t["model_version"].ne(CLIMATOLOGY)], y, r),
        lambda t, y, r: (t, y.assign(unit="arrivals"), r),
        lambda t, y, r: (t, pd.concat([y, y]), r),
        lambda t, y, r: (t, y.iloc[:0], r),
        lambda t, y, r: (t.assign(data_snapshot_id=t["model_version"]), y, r),
        lambda t, y, r: (t, y, r.assign(data_mode="fixture")),
    ],
    ids=["dropped", "baseline", "unit", "duplicate", "missing", "snapshot", "requests"],
)
def test_input_defects_never_spend_the_locked_run(tmp_path, clean_git, breakage):
    table = real_test_table()
    labels = labels_for(table, [10.0], data_mode="real")
    changed, changed_labels, requests = breakage(table, labels, requests_of(table))
    inputs = run_inputs(changed, changed_labels, tmp_path)
    requests.to_parquet(inputs[1])
    rebind(inputs)
    with pytest.raises(ValueError):
        locked_run(inputs)
    assert_nothing_happened(inputs)


def test_labels_load_only_after_the_claim(tmp_path, clean_git, monkeypatch):
    inputs = locked_inputs(tmp_path)
    claim = inputs[4] / "evaluate_primary.json"
    load = evaluate.load_labels
    seen = []

    def spy(*args):
        seen.append(claim.exists())
        return load(*args)

    monkeypatch.setattr(evaluate, "load_labels", spy)
    locked_run(inputs)
    assert seen == [True]


def test_every_run_manifest_is_read(tmp_path, clean_git):
    table = real_test_table()
    inputs = locked_inputs(tmp_path, table[table["model_version"].eq(MODEL)])
    baseline_rows = table[table["model_version"].ne(MODEL)]
    write_run(baseline_rows, inputs[2], "baselines", dirty=True)
    with pytest.raises(ValueError, match="uncommitted"):
        locked_run(inputs, runs=("run", "baselines"))
    assert_nothing_happened(inputs)


def test_a_candidate_with_nothing_usable_cannot_spend_the_run(tmp_path, clean_git):
    table = real_test_table()
    empty = table["model_version"].eq(MODEL)
    table.loc[empty, "estimate"] = np.nan
    table.loc[empty, "status"] = "unavailable"
    inputs = locked_inputs(tmp_path, table)
    with pytest.raises(ValueError, match="no usable estimate"):
        locked_run(inputs)
    assert_nothing_happened(inputs)


def test_a_candidate_must_cover_every_cell():
    frames = [
        real_test_table(),
        predictions_for(
            "KDFW",
            [TEST_DAY],
            {MODEL: [np.nan], PERSISTENCE: [1.0], CLIMATOLOGY: [1.0]},
        ).assign(data_mode="real"),
    ]
    table = pd.concat(frames, ignore_index=True).assign(split="test")
    with pytest.raises(ValueError, match="no usable estimate"):
        check_locked_candidates(table)


def locked_as(inputs: list, experiment: str) -> object:
    return main(
        ["run"],
        artifacts=inputs[2],
        locked_test=True,
        approved_by="tester",
        experiment=experiment,
    )


def test_each_declared_experiment_runs_once_and_writes_apart(tmp_path, clean_git):
    assert {"primary", "csv_only", "leave_out_KATL"} <= set(LOCKED_EXPERIMENTS)
    inputs = locked_inputs(
        tmp_path, real_test_table().assign(cohort_version="csv_only_v1")
    )
    path = locked_as(inputs, "csv_only")
    assert path.name == "metrics_csv_only.json"
    assert json.loads(path.read_text())["experiment"] == "csv_only"
    with pytest.raises(FileExistsError, match="runs once"):
        locked_as(inputs, "csv_only")


@pytest.mark.parametrize(
    ("cohort", "experiment", "message"),
    [
        ("fixture-v0", "csv_only", "only CSV cohorts"),
        ("csv_only_v1", "primary", "must not score CSV"),
        ("csv_only_v1", "leave_out_KATL", "must not score CSV"),
    ],
)
def test_a_locked_experiment_is_bound_to_its_cohort(
    tmp_path, clean_git, cohort, experiment, message
):
    inputs = locked_inputs(tmp_path, real_test_table().assign(cohort_version=cohort))
    with pytest.raises(ValueError, match=message):
        locked_as(inputs, experiment)
    assert_nothing_happened(inputs)


def test_leave_one_airport_out_scores_only_the_held_out_airport(tmp_path, clean_git):
    inputs = locked_inputs(tmp_path)
    write_run(real_test_table(), inputs[2], train_airports=["KATL"])
    with pytest.raises(ValueError, match="scores only KDFW"):
        locked_as(inputs, "leave_out_KDFW")
    assert_nothing_happened(inputs)


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        ({}, "needs train_airports"),
        ({"train_airports": ["KATL", "KDFW"]}, "trained on"),
    ],
)
def test_leave_one_airport_out_needs_a_model_trained_without_it(
    tmp_path, clean_git, manifest, message
):
    inputs = locked_inputs(tmp_path)
    write_run(real_test_table(), inputs[2], **manifest)
    with pytest.raises(ValueError, match=message):
        locked_as(inputs, "leave_out_KATL")
    assert_nothing_happened(inputs)


def test_the_same_forecasts_cannot_be_locked_again_under_new_names(tmp_path, clean_git):
    inputs = locked_inputs(tmp_path)
    write_run(real_test_table(), inputs[2], train_airports=["KDFW"])
    locked_as(inputs, "leave_out_KATL")
    table = real_test_table()
    renamed = table.assign(
        cohort_version="primary_v2",
        prediction_id=table["prediction_id"] + "|v2",
        model_version=table["model_version"].replace(MODEL, OTHER_MODEL),
    )
    second = locked_inputs(tmp_path, renamed)
    with pytest.raises(FileExistsError, match="claimed as evaluate_leave_out_KATL"):
        locked_as(second, "primary")
    assert not (second[3] / "metrics.json").exists()


def test_the_candidate_hash_ignores_names_but_not_forecasts():
    table = real_test_table()
    renamed = table.assign(
        cohort_version="other",
        prediction_id=table["prediction_id"] + "|x",
        model_version=table["model_version"].replace(MODEL, OTHER_MODEL),
    )
    assert candidate_sha256(renamed) == candidate_sha256(table)
    changed = table.assign(estimate=table["estimate"] + 1)
    assert candidate_sha256(changed) != candidate_sha256(table)


def test_a_claim_refuses_predictions_already_claimed(tmp_path):
    baselines.claim_locked_run("first", "tester", "abc", "hash-1")
    with pytest.raises(FileExistsError, match="claimed as first"):
        baselines.claim_locked_run("second", "tester", "abc", "hash-1")
    baselines.claim_locked_run("third", "tester", "abc", "hash-2")
    third = json.loads((tmp_path / "ledger" / "third.json").read_text())
    assert third["predictions_sha256"] == "hash-2"


def test_another_reports_folder_cannot_buy_a_second_locked_run(
    tmp_path, clean_git, monkeypatch
):
    inputs = locked_inputs(tmp_path)
    locked_run(inputs)
    elsewhere = tmp_path / "elsewhere"
    with pytest.raises(ValueError, match="canonical"):
        main(
            ["run"],
            artifacts=inputs[2],
            reports=elsewhere,
            locked_test=True,
            approved_by="tester",
        )
    # Even a moved canonical reports folder finds the run spent.
    monkeypatch.setattr(evaluate, "REPORTS", elsewhere)
    with pytest.raises(FileExistsError, match="runs once"):
        locked_run(inputs)
    assert not elsewhere.exists()


@pytest.mark.parametrize(
    "moved", ["labels_path", "requests_path", "reports", "ledger", "mirror"]
)
def test_locked_main_refuses_non_canonical_paths(tmp_path, clean_git, moved):
    inputs = locked_inputs(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    sources = {"labels_path": inputs[0], "requests_path": inputs[1]}
    path = (
        Path(shutil.copy(sources[moved], elsewhere))
        if moved in sources
        else (elsewhere / moved)
    )
    with pytest.raises(
        ValueError, match=f"canonical .*'{moved.removesuffix('_path')}'"
    ):
        main(
            ["run"],
            artifacts=inputs[2],
            locked_test=True,
            approved_by="tester",
            **{moved: path},
        )
    assert_nothing_happened(inputs)
    assert not list(tmp_path.rglob("evaluate_*.json"))
    assert not list(tmp_path.rglob("metrics*.json"))


@pytest.mark.parametrize("flag", ["--reports", "--requests"])
def test_the_locked_cli_keeps_the_default_paths(monkeypatch, flag):
    def never(*args, **kwargs):
        raise AssertionError("main ran")

    monkeypatch.setattr(evaluate, "main", never)
    with pytest.raises(SystemExit):
        evaluate.cli(["--locked-test", "--approved-by", "tester", flag, "elsewhere"])


def test_the_dev_cli_passes_other_paths_through(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(evaluate, "main", lambda runs, **kwargs: seen.update(kwargs))
    evaluate.cli(["--reports", str(tmp_path), "--requests", str(tmp_path / "r")])
    assert (seen["reports"], seen["requests_path"]) == (tmp_path, tmp_path / "r")
    assert "ledger" not in seen


def test_an_undeclared_experiment_is_refused(tmp_path, clean_git):
    inputs = locked_inputs(tmp_path)
    with pytest.raises(ValueError, match="experiment outside"):
        main(["run"], *inputs, experiment="primary_retry")


def two_cohorts() -> pd.DataFrame:
    full = throughput_table()
    subset = full.assign(
        cohort_version="csv_only_v1",
        prediction_id=full["prediction_id"] + "|csv",
        estimate=full["estimate"] + 1,
    )
    return pd.concat([full, subset], ignore_index=True)


def test_cohorts_never_share_a_cell(tmp_path, clean_git):
    table = two_cohorts()
    inputs = run_inputs(table, labels_for(table, [10.0, 20.0] * 2), tmp_path)
    report = json.loads(main(["run"], *inputs).read_text())
    assert report["cohorts"] == ["csv_only_v1", "fixture-v0"]
    match = {
        "metric": "mae",
        "model": MODEL,
        "airport": "KATL",
        "horizon": 3,
        "slice": "own_support",
    }
    assert value(report["metrics"], cohort="fixture-v0", **match) == pytest.approx(1.5)
    assert value(report["metrics"], cohort="csv_only_v1", **match) == pytest.approx(2.5)


def test_a_run_can_be_restricted_to_one_cohort(tmp_path, clean_git):
    table = two_cohorts()
    inputs = run_inputs(table, labels_for(table, [10.0, 20.0] * 2), tmp_path)
    path = main(["run"], *inputs, cohorts=["csv_only_v1"], experiment="csv_only")
    assert path.name == "metrics_dev_csv_only.json"
    assert json.loads(path.read_text())["cohorts"] == ["csv_only_v1"]


def test_per_airport_candidates_get_skill_in_their_own_cells():
    frames = [
        predictions_for(
            "KATL",
            [DAY_ONE],
            {
                MODEL: [12.0],
                OTHER_MODEL: [np.nan],
                PERSISTENCE: [14.0],
                CLIMATOLOGY: [9.0],
            },
        ),
        predictions_for(
            "KDFW",
            [DAY_ONE],
            {
                MODEL: [np.nan],
                OTHER_MODEL: [12.0],
                PERSISTENCE: [14.0],
                CLIMATOLOGY: [9.0],
            },
        ),
    ]
    table = pd.concat(frames, ignore_index=True).assign(split="validation")
    check_baselines(table)
    records = records_of(table, labels_for(table, [10.0, 10.0]))
    for model, airport in [(MODEL, "KATL"), (OTHER_MODEL, "KDFW")]:
        skill = value(
            records,
            metric=f"skill_vs_{PERSISTENCE}",
            model=model,
            airport=airport,
            horizon=3,
        )
        assert skill == pytest.approx(0.5)


def test_an_empty_optional_baseline_does_not_block_a_cell():
    table = predictions_for(
        "KATL",
        [DAY_ONE],
        {
            MODEL: [1.0],
            PERSISTENCE: [1.0],
            CLIMATOLOGY: [1.0],
            "baseline_schedule_v1": [np.nan],
        },
    )
    check_baselines(table.assign(split="validation"))


def test_a_lookalike_baseline_name_counts_as_a_candidate():
    table = predictions_for("KATL", [DAY_ONE], {"baseline_mine_v1": [1.0]})
    with pytest.raises(ValueError, match="needs baselines"):
        check_baselines(table.assign(split="validation"))


def test_colours_cover_more_candidates_than_the_palette():
    models = [f"model_{i}" for i in range(5)]
    assert set(_colours(models)) == set(models)


def test_a_single_airport_run_reports_macro_as_null():
    table = throughput_table()
    records = records_of(table, labels_for(table, [10.0, 20.0]))
    row = record(
        macro_records(records),
        metric="mae",
        model=MODEL,
        horizon=3,
        slice="own_support",
    )
    assert (row["value"], row["reason"]) == (None, "undefined_for_an_airport")


def test_inputs_are_hashed_before_they_are_read(tmp_path, clean_git, monkeypatch):
    table = throughput_table()
    inputs = run_inputs(table, labels_for(table, [10.0, 20.0]), tmp_path)
    events = []
    hash_file, load = evaluate.sha256, evaluate.load_predictions

    def spy_hash(path):
        events.append("hash")
        return hash_file(path)

    def spy_load(*args):
        events.append("load")
        return load(*args)

    monkeypatch.setattr(evaluate, "sha256", spy_hash)
    monkeypatch.setattr(evaluate, "load_predictions", spy_load)
    main(["run"], *inputs)
    assert events.index("hash") < events.index("load")


# Settled contract from the integration review


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.assign(
            exclusion_detail=None, eligible=False, exclusion_reason="cancelled"
        ),
        lambda d: d.assign(exclusion_detail="unexpected"),
    ],
    ids=["ineligible_without_detail", "eligible_with_detail"],
)
def test_exclusion_detail_follows_eligibility(tmp_path, change):
    table, labels = severe_table([0.5], [1])
    path = write_labels(change(labels), tmp_path)
    with pytest.raises(ValueError, match="exclusion_detail must be null"):
        load_labels(path, table["prediction_id"].unique().tolist())


def test_exclusion_detail_values_are_not_validated(tmp_path):
    table, labels = severe_table([0.5, 0.5], [1, None])
    labels["exclusion_detail"] = [None, "anything_the_producer_says"]
    path = write_labels(labels, tmp_path)
    assert len(load_labels(path, table["prediction_id"].unique().tolist())) == 2


def test_severe_delay_needs_its_own_baselines():
    table = predictions_for(
        "KATL",
        [DAY_ONE],
        {MODEL: [0.5], PERSISTENCE: [0.5], CLIMATOLOGY: [0.5]},
        target_kind=SEVERE,
        unit=PROBABILITY,
    )
    with pytest.raises(ValueError, match="baseline_conditional_rate_v1"):
        check_baselines(table.assign(split="validation"))


def test_models_and_baselines_share_one_scored_row_set():
    table = throughput_table()
    scope_of(table, requests_of(table))
    # A request only the candidate scores leaves the baselines short of it.
    extra = predictions_for("KATL", ["2024-03-07 15:00"], {MODEL: [1.0]})
    everything = pd.concat([table, extra], ignore_index=True)
    with pytest.raises(ValueError, match=f"{CLIMATOLOGY} has no"):
        scope_of(everything, requests_of(everything))


# Re-review: fit cutoffs, common support and main-level checks


def test_a_run_refitted_past_its_scored_rows_is_refused(tmp_path, clean_git):
    # Refitted on train + validation, then scored in-sample on validation.
    table = throughput_table()
    inputs = run_inputs(table, labels_for(table, [10.0, 20.0]), tmp_path)
    write_run(table, inputs[2], fit_cutoff_utc="2024-07-01T00:00:00+00:00")
    with pytest.raises(ValueError, match="before the fit cutoff"):
        main(["run"], *inputs)
    assert not inputs[3].exists()


@pytest.mark.parametrize(
    ("cutoff", "message"),
    [(None, "needs fit_cutoff_utc"), ("2024-01-01T00:00:00", "needs a timezone")],
)
def test_every_run_declares_a_fit_cutoff(tmp_path, clean_git, cutoff, message):
    table = throughput_table()
    inputs = run_inputs(table, labels_for(table, [10.0, 20.0]), tmp_path)
    write_run(table, inputs[2], fit_cutoff_utc=cutoff)
    with pytest.raises(ValueError, match=message):
        main(["run"], *inputs)


def test_rows_before_the_scope_are_dropped_not_scored(tmp_path, clean_git):
    # An earlier cutoff lets the candidate score a request issued before the
    # end of train; it is dropped, so skill compares one row set.
    table = throughput_table()
    early = predictions_for("KATL", ["2024-01-01 02:00"], {MODEL: [5.0]})
    everything = pd.concat([table, early], ignore_index=True)
    is_model = table["model_version"].eq(MODEL)
    inputs = run_inputs(
        table[~is_model], labels_for(everything, [10.0, 20.0, 5.0]), tmp_path
    )
    requests_of(everything).to_parquet(inputs[1])
    rebind(inputs)
    candidate = pd.concat([table[is_model], early], ignore_index=True)
    write_run(candidate, inputs[2], "model", fit_cutoff_utc="2023-12-01T00:00:00+00:00")
    report = json.loads(main(["run", "model"], *inputs).read_text())
    (scope,) = report["scoring_scope"]
    assert scope["fit_cutoff_utc"] == "2024-01-01T00:00:00Z"
    assert scope["set_by"] == ["run"]
    assert scope["rows_dropped"] == {MODEL: 1, PERSISTENCE: 0, CLIMATOLOGY: 0}
    assert scope["rows_scored"] == 2
    pooled = [
        r
        for r in report["metrics"]
        if r["airport"] == "pooled" and r["horizon"] == "all" and r["metric"] == "rmse"
    ]
    assert {r["n_predicted"] for r in pooled if r["slice"] == "own_support"} == {2}


def test_main_refuses_a_requests_table_with_mixed_data_modes(tmp_path, clean_git):
    table = throughput_table()
    inputs = run_inputs(table, labels_for(table, [10.0, 20.0]), tmp_path)
    # Out of scope, so only the data_mode check can see it.
    stray = requests_of(predictions_for("KDFW", ["2023-06-01 15:00"], {MODEL: [1.0]}))
    stray = stray.assign(prediction_id="real-request", data_mode="real")
    pd.concat([requests_of(table), stray], ignore_index=True).to_parquet(inputs[1])
    rebind(inputs)
    with pytest.raises(ValueError, match="mixed data_mode"):
        main(["run"], *inputs)


def test_all_horizon_common_support_compares_one_row_set():
    table = predictions_for(
        "KATL",
        [DAY_ONE],
        {MODEL: [12.0, np.nan], PERSISTENCE: [14.0, 14.0], CLIMATOLOGY: [10.0, 10.0]},
        horizons=(3, 6),
    )
    records = records_of(table, labels_for(table, [10.0, 10.0]))
    for airport in ["KATL", "pooled"]:
        n = {
            model: record(
                records,
                metric="rmse",
                slice="common_support",
                airport=airport,
                horizon="all",
                model=model,
            )["n_predicted"]
            for model in [MODEL, PERSISTENCE, CLIMATOLOGY]
        }
        assert n == {MODEL: 1, PERSISTENCE: 1, CLIMATOLOGY: 1}


def test_pooled_reliability_compares_one_row_set():
    table = predictions_for(
        "KATL",
        [DAY_ONE],
        {MODEL: [0.2, np.nan], CONDITIONAL_RATE: [0.5, 0.5], LOGISTIC: [0.4, 0.4]},
        horizons=(3, 6),
        target_kind=SEVERE,
        unit=PROBABILITY,
    )
    bins = reliability(scored(table, labels_for(table, [0.0, 1.0], PROBABILITY)))
    n = {}
    for b in bins:
        n[b["model"], b["airport"]] = n.get((b["model"], b["airport"]), 0) + b["n"]
    assert set(n.values()) == {1}
    assert {model for model, _ in n} == {MODEL, CONDITIONAL_RATE, LOGISTIC}


# 2-A3b: fit-cutoff scoring scope and the requests binding

REFIT = "2024-07-01T00:00:00+00:00"
BEFORE_REFIT = "2024-07-01 01:00"  # issued 2024-06-30 22:00 at 3 h
AFTER_REFIT = "2024-07-02 15:00"


def refit_inputs(tmp_path, extra=()) -> tuple[list, pd.DataFrame]:
    targets = [DAY_ONE, BEFORE_REFIT, AFTER_REFIT, *extra]
    n = len(targets)
    base = predictions_for(
        "KATL", targets, {PERSISTENCE: [9.0] * n, CLIMATOLOGY: [11.0] * n}
    )
    inputs = run_inputs(base, labels_for(base, [10.0] * n), tmp_path)
    candidate = predictions_for("KATL", [AFTER_REFIT], {MODEL: [10.5]})
    write_run(candidate, inputs[2], "model", fit_cutoff_utc=REFIT)
    return inputs, candidate


def test_a_later_refit_gets_its_own_scope(tmp_path, clean_git, monkeypatch):
    # A truthful train + validation refit declares its real cutoff and is scored
    # only from there; validation has nothing left and reports null.
    inputs, candidate = refit_inputs(tmp_path)
    load = evaluate.load_labels
    seen = []
    monkeypatch.setattr(
        evaluate, "load_labels", lambda path, ids: seen.extend(ids) or load(path, ids)
    )
    report = json.loads(main(["run", "model"], *inputs).read_text())
    assert seen == [candidate["prediction_id"].iloc[0]]
    scope = {s["split"]: s for s in report["scoring_scope"]}
    assert scope["validation"]["rows_scored"] == 0
    assert scope["validation"]["reason"] == "no_rows_after_fit_cutoff"
    assert scope["validation"]["rows_dropped"] == {
        MODEL: 0,
        PERSISTENCE: 1,
        CLIMATOLOGY: 1,
    }
    assert scope["calibration"]["fit_cutoff_utc"] == "2024-07-01T00:00:00Z"
    assert scope["calibration"]["set_by"] == ["model"]
    assert scope["calibration"]["rows_dropped"][PERSISTENCE] == 1
    assert scope["calibration"]["rows_scored"] == 1
    validation = [r for r in report["metrics"] if r["split"] == "validation"]
    assert {r["model"] for r in validation} == {MODEL, PERSISTENCE, CLIMATOLOGY}
    assert {r["value"] for r in validation} == {None}
    assert {r["reason"] for r in validation} == {"no_rows_after_fit_cutoff"}
    calibration = [
        r
        for r in report["metrics"]
        if r["split"] == "calibration" and r["metric"] == "rmse"
    ]
    assert {r["n_predicted"] for r in calibration if r["slice"] == "own_support"} == {1}


def test_a_refit_must_still_cover_its_own_scope(tmp_path, clean_git):
    inputs, _ = refit_inputs(tmp_path, extra=["2024-07-03 15:00"])
    with pytest.raises(ValueError, match=f"{MODEL} has no"):
        main(["run", "model"], *inputs)
    assert not inputs[3].exists()


@pytest.mark.parametrize("manifest", [{"prediction_requests_sha256": None}, {}])
def test_a_run_built_from_other_requests_is_refused(tmp_path, clean_git, manifest):
    table = throughput_table()
    inputs = run_inputs(table, labels_for(table, [10.0, 20.0]), tmp_path)
    if manifest:
        write_run(table, inputs[2], **manifest)
    else:
        # The same predictions, but the requests table changed after the run.
        extra = requests_of(predictions_for("KDFW", [DAY_ONE], {MODEL: [1.0]}))
        pd.concat([requests_of(table), extra]).to_parquet(inputs[1])
    with pytest.raises(ValueError, match="another prediction requests table"):
        main(["run"], *inputs)
    assert not inputs[3].exists()


def test_a_baseline_cannot_narrow_the_locked_scope(tmp_path, clean_git):
    table = real_test_table()
    is_model = table["model_version"].eq(MODEL)
    inputs = locked_inputs(tmp_path, table[is_model])
    write_run(
        table[~is_model], inputs[2], "baselines", fit_cutoff_utc="2025-02-01T00:00:00Z"
    )
    with pytest.raises(ValueError, match="narrow the locked scope"):
        locked_run(inputs, runs=("run", "baselines"))
    assert_nothing_happened(inputs)


def test_dropped_rows_cannot_change_the_locked_hash(tmp_path, clean_git):
    table = real_test_table()
    early = predictions_for("KATL", ["2025-01-01 01:00"], {MODEL: [3.0]})
    padded = pd.concat([table, early.assign(data_mode="real")], ignore_index=True)
    padded = padded.assign(split=evaluate.split_of(padded["target_start_utc"]))
    scoped = padded[padded["as_of_utc"].ge(ts("2025-01-01"))]
    assert candidate_sha256(scoped) == candidate_sha256(
        table.assign(split=evaluate.split_of(table["target_start_utc"]))
    )
