import json

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
from airbus_challenge.evaluate import (
    CAPACITY_RATIO,
    CLIMATOLOGY,
    DAY_OFFSET,
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
    check_baselines,
    check_contract,
    check_locked_candidates,
    check_requests,
    classification_metrics,
    evaluate_target,
    join_labels,
    load_labels,
    load_predictions,
    macro_records,
    main,
    mark_common,
    regression_metrics,
    reliability,
    skill_metrics,
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
            "label_version": "fixture",
            "unit": unit,
            "data_mode": data_mode,
        }
    )


def requests_of(predictions: pd.DataFrame) -> pd.DataFrame:
    return predictions[REQUEST_KEYS].drop_duplicates(ignore_index=True)


def scored(predictions: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    return mark_common(join_labels(predictions, labels).assign(split="validation"))


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
        {MODEL: [0.8, 0.2], PERSISTENCE: [0.5, 0.5], CLIMATOLOGY: [0.6, 0.4]},
        target_kind=SEVERE,
        unit=PROBABILITY,
    )
    records = records_of(table, labels_for(table, [1.0, 0.0], PROBABILITY))
    skill = value(
        records,
        metric=f"skill_vs_{PERSISTENCE}",
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
    metric = next(
        m
        for m in skill_metrics(rows, MODEL, False)
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
    table = predictions_for(
        "KATL",
        [DAY_ONE],
        {MODEL: [np.nan], PERSISTENCE: [0.5], CLIMATOLOGY: [0.5]},
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
    for name, expected_unit in {**names, f"skill_vs_{PERSISTENCE}": "share"}.items():
        row = record(records, metric=name, **common)
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


def test_a_model_cannot_drop_requests_it_could_not_score():
    table = throughput_table().assign(split="validation")
    dropped = table[
        table["model_version"].ne(MODEL) | table["target_start_utc"].eq(ts(DAY_ONE))
    ]
    with pytest.raises(ValueError, match=f"{MODEL} has no"):
        check_requests(dropped, requests_of(table))


def test_marking_a_request_unavailable_satisfies_the_check():
    table = predictions_for("KATL", [DAY_ONE, DAY_TWO], {MODEL: [1.0, np.nan]}).assign(
        split="validation"
    )
    check_requests(table, requests_of(table))


def test_requests_outside_the_scored_scope_are_not_expected():
    table = throughput_table().assign(split="validation")
    other = predictions_for(
        "KATL",
        [TEST_DAY, "2024-01-01 02:00", "2024-09-01 15:00"],
        {MODEL: [1.0, 1.0, 1.0]},
    )
    requests = pd.concat([requests_of(table), requests_of(other)], ignore_index=True)
    # 2024-01-01 02:00 was issued before the fit cutoff, so nothing should score it.
    requests = requests[requests["target_start_utc"].ne(ts("2024-09-01 15:00"))]
    check_requests(table, requests)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.drop(index=0), "no label"),
        (lambda d: d.assign(unit="arrivals"), "unit"),
    ],
)
def test_broken_labels_fail_loudly(change, message):
    table = throughput_table()
    labels = change(labels_for(table, [10.0, 20.0]))
    with pytest.raises(ValueError, match=message):
        join_labels(table, labels)


def write_labels(labels: pd.DataFrame, tmp_path) -> str:
    path = tmp_path / "labels.parquet"
    labels.to_parquet(path)
    return path


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.assign(y_true=2.0), "exactly 0 or 1"),
        (lambda d: d.assign(y_true=np.nan), "without an outcome"),
        (lambda d: pd.concat([d, d]), "more than one label"),
        (lambda d: d.assign(exclusion_reason="cancelled"), "null exactly when"),
        (
            lambda d: d.assign(eligible=False, exclusion_reason=None),
            "null exactly when",
        ),
        (
            lambda d: d.assign(eligible=False, exclusion_reason="canceled"),
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
    with pytest.raises(ValueError, match="shared by every model"):
        check_baselines(table.assign(split="validation"))


def test_baselines_alone_need_no_model():
    check_baselines(
        predictions_for("KATL", [DAY_ONE], {PERSISTENCE: [1.0]}).assign(
            split="validation"
        )
    )


# Scope


def write_run(table: pd.DataFrame, root, run: str = "run", dirty: bool = False) -> None:
    baselines.write_predictions(
        table.drop(columns=["split", "day"], errors="ignore"),
        root / run / "predictions.parquet",
    )
    manifest = {"data_mode": table["data_mode"].iloc[0], "commit_dirty": dirty}
    (root / run / "manifest.json").write_text(json.dumps(manifest))


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


def run_inputs(table: pd.DataFrame, labels: pd.DataFrame, tmp_path) -> list:
    artifacts = tmp_path / "artifacts"
    write_run(table, artifacts)
    labels_path = write_labels(labels, tmp_path)
    requests_path = tmp_path / "requests.parquet"
    requests_of(table).to_parquet(requests_path)
    return [labels_path, requests_path, artifacts, tmp_path / "reports"]


def test_fixture_run_never_writes_the_reported_metrics(tmp_path, clean_git):
    table = throughput_table()
    inputs = run_inputs(table, labels_for(table, [10.0, 20.0]), tmp_path)
    reports = inputs[-1]
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
    assert (reports / "fixture" / "figures" / f"rmse_{TARGET}_validation.png").exists()


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
    requests = requests_of(table)
    changed, changed_labels = change(table, labels)
    inputs = run_inputs(changed, changed_labels, tmp_path)
    requests.to_parquet(inputs[1])
    with pytest.raises(ValueError, match=message):
        main(["run"], *inputs)
    assert not inputs[-1].exists()


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
    return main(list(runs), *inputs, locked_test=True, approved_by=approved_by)


def assert_nothing_happened(inputs: list) -> None:
    reports = inputs[-1]
    assert not (reports / "metrics.json").exists()
    assert not (reports / "locked_runs").exists()


def test_locked_run_claims_then_writes_once(tmp_path, clean_git):
    inputs = locked_inputs(tmp_path)
    path = locked_run(inputs)
    assert path.name == "metrics.json"
    assert json.loads(path.read_text())["approved_by"] == "tester"
    claim = json.loads(
        (inputs[-1] / "locked_runs/evaluate_locked_test.json").read_text()
    )
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


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        ({"data_mode": "fixture", "commit_dirty": False}, "needs real data"),
        ({"data_mode": "real", "commit_dirty": True}, "uncommitted"),
    ],
)
def test_locked_run_reads_each_run_manifest(tmp_path, clean_git, manifest, message):
    inputs = locked_inputs(tmp_path)
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
    assert not (inputs[-1] / "metrics.json").exists()


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
