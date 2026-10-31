# Evaluation and experiment protocol

Status: proposed design. Exact source coverage and dates must be accepted and frozen by the team before final-test access.

## 1. Proposed primary partitions

Use target UTC time for partitioning, not archive row order or retrieval time.

| Partition | Half-open UTC bounds | Use |
| --- | --- | --- |
| Train | 2023-01-01 to 2024-01-01 | Initial fitting |
| Validation | 2024-01-01 to 2024-07-01 | Model/features/hyperparameters |
| Calibration | 2024-07-01 to 2025-01-01 | Probability/interval calibration and alert policy |
| Final test | 2025-01-01 to 2025-08-01 | One locked assessment (R09) |

The supplied CSV ends July 2025, so the test ends there too (`docs/DECISIONS.md` R09). August-December 2025 may only be reported as a separately labelled supplemental-data check. If permitted data cannot support these periods, revise the protocol based on coverage, record why, and freeze it before comparing test performance. Report a provided-data subset separately when useful; do not splice populations into one score.

Use rolling validation within the validation period with explicit chronological folds. After selecting settings, a candidate may refit on train+validation, then calibrate on the calibration partition. Freeze it before testing. All fitting rows must have eligible outcomes known by the fit cutoff; do not assume a source's publication time equals the flight event time.

If final-test findings motivate further model development, call them exploratory and obtain a new untouched assessment period where possible. Preserve the original result.

## 2. Baselines and ablations

Airport baselines: training climatology by airport/local hour/weekday with a documented sparse-cell fallback; persistence using the latest eligible observation/operational target; seasonal persistence; schedule-only regression for throughput.

Do not present official-AAR persistence if no historically available AAR feed exists. Distinguish a retrospective oracle benchmark from an implementable baseline. Baselines and candidate models share feature availability assumptions and evaluation rows.

Flight baselines: historical conditional rate (`baseline_conditional_rate_v1`) and logistic regression (`baseline_logistic_v1`); separate cancellation baseline. Fit rates on training only, with smoothing and fallbacks for rare groups.

Ablations: schedule/calendar -> add past observations -> add archived forecasts -> add runway-relative components -> add operational context. Compare at each horizon. Do not use test ablations to choose the model.

Model variants: pooled versus separate horizons; pooled versus per-airport models. Start with gradient boosting before deep sequence models. Added complexity needs measurable validation benefit.

## 3. Metrics

| Task | Required measures |
| --- | --- |
| Official AAR or separately named throughput | RMSE, MAE, bias, baseline skill, sample size |
| Regression uncertainty | Empirical p10-p90 coverage, average width, quantile loss |
| Conditional severe departure delay | PR-AUC/average precision with implementation named, prevalence, Brier score, reliability, precision/recall |
| Cancellation | Separate discrimination/calibration and denominator |
| Operational alerts | Recall at fixed validation-selected alert burden, false alert episodes/airport-day, first-alert lead time |
| Missing/degraded input handling | Coverage, abstention rate/reasons, performance on predicted rows and common-support rows |

Baseline skill for a nonzero baseline RMSE: `1 - RMSE_model / RMSE_baseline`. Negative skill is allowed. Undefined metrics are null with an explanation.

Report airport x horizon results first: per-airport RMSE is the headline metric. Then macro-average across airports and show pooled aggregates, which are airport-hour weighted and labelled as such. Compare delay rates or expected severely delayed departures per 100 scheduled flights; do not compare raw total delay minutes as if airport sizes were equal.

Use actual denominators. Conditional severe-delay probabilities must not be described as probabilities over all scheduled flights. For airport cohorts with zero scheduled departures, the rate is undefined, not zero.

## 4. Weather and event slices

Slice source: `data/processed/eval_weather_slices.parquet` from `slices.py` (`eval-weather-slices/0.1.0`), one row per airport and UTC hour from realised METARs observed in that hour, in hindsight and including corrected reports. `thunderstorm`: any weather code containing TS, including VCTS. `ifr`: ceiling below 1,000 ft or visibility below 3 sm. `low_vis`: visibility below 1 sm. `strong_crosswind`: crosswind of 20 kt or more, variable wind at full speed. Hours with no METAR have `coverage = missing`. Evaluation only: it is never a predictor, and `registry.model_inputs` refuses its columns.

Evaluate all eligible hours first. Add prespecified slices for high/low demand, relevant weather regimes, forecast age, missingness, season, and airport. Observed target weather and final storm events are allowed for retrospective slicing, never for features.

Build a versioned event definition before tuning: event type, airport spatial association, onset/offset, merging gap, and minimum duration. County reports are not automatically airport observations. Keep uncertainty in storm location/timing visible.

Persist alerts into episodes under a frozen policy. Count repeat hourly warnings as one episode where appropriate. Define event matching, early-warning window, duplicate-alert handling, and false-alert denominator in config before scoring. These operational thresholds are currently unset; do not invent defaults and call them validated.

Forecast horizon and event lead time are different. A 12-hour target forecast is not necessarily a warning 12 hours before storm onset. Compute lead time against an independently defined observed event onset.

## 5. Transfer and uncertainty

Train ATL -> test DFW, then reverse, with no destination-airport fitting, scaling, threshold tuning, or calibration in the zero-shot test. Compare against separately trained in-airport models as a reference. If target-airport adaptation is explored, label it as a different experiment.

Two airports support a limited transfer stress test, not global validation. Unknown-airport configuration acceptance is a software portability test, not evidence of forecast skill.

Estimate metric uncertainty by resampling days or storm episodes to respect correlation. Repeated horizons and adjacent hours are not independent samples. State the block definition and number of resamples (proposed 1,000; confirm compute cost). Bootstrap days run from 08:00 UTC, so evening storm hours stay in one block. Calibration has no automatic guarantee under distribution shift: check coverage by airport/horizon/weather.

## 6. Locked-run manifest

Before final scoring, record dataset hashes and source scope, split/cohort definitions, exclusion policies, label versions, feature registry, latency assumptions, model/hyperparameters, calibration artifacts, alert policy, random seeds, code commit, environment, and all metric definitions.

Each locked experiment runs once and is bound to its content: `csv_only` scores only CSV cohorts, `leave_out_X` scores only airport X with a model whose `train_airports` exclude X, and the claim stores a hash of the candidate forecasts, so the same forecasts can't be claimed again under another experiment, cohort or model name. A claim is created exclusively in `data/locked_runs/`, the canonical ledger that every worktree shares, then copied to `reports/locked_runs/`, a mirror to commit. A claim is refused if either location already holds its name or its forecast hash. With `locked_test`, `main()` itself refuses any non-canonical ledger, mirror, reports, requests, labels or hourly path, so calling it from Python can't bypass the CLI check. Another machine with its own `data/` stays a procedural risk: the committed mirror only covers it once the claim is pushed and pulled.

The evaluator loads saved predictions and labels independently. Never let the UI recompute metrics. Save prediction-level errors for analysis, but do not feed final-test failure cases back into the locked candidate.

## 7. Failure report and presentation

Include worst airport-hour errors, false alerts, missed severe delays, probability reliability failures, and unavailable/degraded predictions. For each case show the information genuinely known at T, prediction, interval/probability, outcome, plausible limitation, and whether a useful human advisory was possible.

Report model-attribution explanations as associations. Prediction improvement is measured impact. Claimed fuel, cost, or prevented-delay benefits require an explicit simulation/counterfactual method and assumptions; a replay alone cannot establish those benefits.
