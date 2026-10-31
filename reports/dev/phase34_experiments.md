Development results only (H1/H2 2024); the locked 2025 test is not run (DECISIONS R11).

# Phases 2–4 development experiments

All results below use real 2023/2024 data. No locked 2025 assessment was run. Parameter fitting uses 2023; early stopping uses H1 2024. H1 2024 scores are therefore model-selection diagnostics. H2 2024 scores are development comparisons, not a final independent test.

## Throughput ablations

Arrival throughput is BTS reporting-carrier touchdowns/hour, an AAR proxy influenced by both demand and capacity. The five cumulative variants are schedule/calendar → past METAR observations → archived TAF forecasts → runway-relative wind components → optional simulated operations. Wind intensity is introduced with direction-relative components at the runway stage.

All variants and the existing in-airport model are evaluated together with four required/reference baselines. Each column uses exactly the same common-support rows across these models. Entries are RMSE in touchdowns/hour with 95% operational-day block-bootstrap intervals (1,000 resamples, 08:00 UTC day anchor). Counts are prediction rows over four horizons; an airport-hour can occur once per horizon.

| Model | ATL validation | DFW validation | ATL calibration | DFW calibration |
|---|---:|---:|---:|---:|
| Schedule/calendar | 5.523 [5.083, 6.046] | 8.529 [7.697, 9.316] | 6.900 [6.125, 7.823] | 9.581 [8.958, 10.242] |
| Add observations | 5.419 [4.989, 5.932] | 8.285 [7.464, 9.054] | 6.813 [6.013, 7.752] | 9.337 [8.711, 9.987] |
| Add forecasts | 5.384 [5.005, 5.851] | 7.952 [7.243, 8.643] | 6.788 [6.002, 7.708] | 9.410 [8.823, 10.035] |
| Add runway components | 5.321 [4.949, 5.778] | 7.946 [7.223, 8.662] | 6.786 [5.984, 7.708] | 9.235 [8.649, 9.874] |
| Add simulated operations | 5.325 [4.942, 5.779] | 7.854 [7.131, 8.565] | 6.795 [5.992, 7.721] | 9.103 [8.537, 9.727] |
| Existing in-airport model | 5.314 [4.940, 5.768] | 7.952 [7.227, 8.665] | 6.743 [5.949, 7.667] | 9.158 [8.580, 9.778] |
| Schedule baseline | 7.471 [7.156, 7.842] | 11.953 [11.404, 12.481] | 8.290 [7.636, 9.041] | 12.997 [12.626, 13.408] |
| Climatology baseline | 6.746 [6.328, 7.239] | 9.873 [9.209, 10.485] | 8.663 [8.075, 9.357] | 13.111 [12.688, 13.595] |
| Seasonal persistence | 7.143 [6.567, 7.745] | 10.931 [10.032, 11.766] | 10.480 [9.585, 11.466] | 11.432 [10.289, 12.484] |
| Ordinary persistence | 38.197 [37.930, 38.456] | 33.000 [32.631, 33.370] | 39.208 [38.714, 39.636] | 37.704 [37.311, 38.136] |

Common-support n in column order: 17208, 17274, 17372, 17438.

On H2 2024, adding runway/weather information improves the schedule-only model at both airports. Adding simulated operations changes ATL RMSE from 6.786 to 6.795 and DFW from 9.235 to 9.103; it does not improve both airports. These comparisons do not establish statistically significant gains or justify changing frozen thresholds. The existing in-airport model is a reference, not a matched ablation: its original training-label availability and selection/subsampling differ from the new fit-eligible exports.

Per-horizon MAE, bias, interval coverage/width, pinball loss, baseline skill, weather slices, availability and exclusions are in [the ablation evaluator report](experiments/ablations/metrics_dev.json). Each run manifest records feature names, fitted categories, training/validation sizes, selected rounds, request/label/feature hashes and runtime. `runtime_s` measures that step; `peak_rss_mb` is the process lifetime high-water mark. The five ablations and two transfer fits shared one process, so later RSS values include earlier stages and are not isolated per-model memory measurements. Run manifests honestly record that fitting used the current uncommitted experiment source; they do not claim the final PR commit existed at fit time.

## Strict airport transfer

Each model fits 2023 labels and selects iterations on H1 2024 validation labels from the source airport only. The held-out airport category and airport-specific 2023 schedule normalizers are omitted from model inputs. Held-out outcomes do not fit parameters, categories, early stopping, capacity references or calibrators. Source-only calibration prediction companions are saved; no held-out calibration is used. Capacity ratios are omitted for this experiment.

All three models in each row share the same scored prediction rows. RMSE and intervals use touchdowns/hour. The ordinary persistence comparator is explicitly simulated operational context.

| Source → held-out | Split | n | Transfer LightGBM | Source-fitted schedule | Held-out persistence |
|---|---|---:|---:|---:|---:|
| KDFW → KATL | validation | 17273 | 8.556 [8.284, 8.855] | 9.493 [9.287, 9.713] | 38.197 [37.924, 38.457] |
| KDFW → KATL | calibration | 17460 | 9.674 [9.189, 10.245] | 10.149 [9.846, 10.516] | 39.195 [38.701, 39.626] |
| KATL → KDFW | validation | 17390 | 11.242 [10.700, 11.790] | 13.386 [12.718, 14.043] | 32.959 [32.581, 33.333] |
| KATL → KDFW | calibration | 17525 | 12.476 [11.984, 13.029] | 13.519 [13.018, 14.034] | 37.708 [37.283, 38.116] |

The transfer model has lower point RMSE than the source-fitted schedule comparator in both directions. Calibration-period RMSE is worse than the in-airport runway model: 9.674 versus 6.786 at ATL, and 12.476 versus 9.235 at DFW. Those cross-report figures use slightly different common supports, so they describe the transfer gap rather than a paired significance test. The full canonical in-airport reference is included in the ablation table above.

The fitted-model mutation regression changes held-out outcomes in both the training export and validation labels, refits source-only point/quantile models, and confirms identical held-out prediction frames. Additional tests enforce source categorical vocabulary, cohort membership and availability.

Reports: [ATL holdout](experiments/loao/metrics_dev_leave_out_KATL.json), [DFW holdout](experiments/loao/metrics_dev_leave_out_KDFW.json).

## Capacity-ratio baseline scoring

The normal evaluator now accepts `--labels`, so the existing ratio runs are scored against `data/labels/ratio_labels_primary.parquet`. Units are dimensionless ratios to the training-only benign-weather p95 reference. They remain a demand-and-capacity proxy, not official airport capacity.

| Split | Airport | Common-support n | Climatology RMSE | Persistence RMSE |
|---|---|---:|---:|---:|
| validation | KATL | 17345 | 0.191 [0.179, 0.203] | 0.402 [0.394, 0.411] |
| validation | KDFW | 17402 | 0.282 [0.264, 0.303] | 0.408 [0.391, 0.425] |
| calibration | KATL | 17648 | 0.237 [0.215, 0.264] | 0.451 [0.436, 0.467] |
| calibration | KDFW | 17580 | 0.314 [0.303, 0.327] | 0.481 [0.467, 0.494] |

[Full ratio evaluator report](experiments/ratio/metrics_dev.json). Ratio LightGBM, severe-delay ablations and severe-delay LOAO candidates are optional extensions and were not run in this batch.

## CSV-only comparison

The CSV is roughly 1% of the broader reporting-carrier source, so its smaller denominators give wider uncertainty and limit weather-subgroup conclusions. True CSV-only LightGBM fits and selects only sample-member departures within each time partition. The separate paired model reuses the frozen all-BTS delay booster and scores exactly the same CSV prediction requests; it is not described as CSV-only training. The paired artifact is bound to the original booster hash and exact CSV request hash.

Conditional severe delay excludes cancelled flights. Common-support prediction rows and unique operated flights are: ATL validation 6,487 / 1,623; DFW validation 5,844 / 1,461; ATL calibration 6,654 / 1,665; DFW calibration 6,272 / 1,568. Horizons repeat a flight up to four times, and missing inputs can remove individual horizon rows. Unique-flight severe-delay prevalence is respectively 8.07%, 15.88%, 8.59% and 11.22%.

Average precision (higher is better):

| Model | ATL validation | DFW validation | ATL calibration | DFW calibration |
|---|---:|---:|---:|---:|
| Conditional-rate baseline | 0.10297 | 0.21577 | 0.13451 | 0.15319 |
| Logistic baseline | 0.10550 | 0.22225 | 0.20219 | 0.20072 |
| True CSV-only LightGBM | 0.13499 | 0.27865 | 0.18223 | 0.19573 |
| Frozen all-BTS model on identical CSV subset | 0.15436 | 0.29188 | 0.21196 | 0.22484 |

Brier score (lower is better), with 95% operational-day block-bootstrap intervals:

| Model | ATL validation | DFW validation | ATL calibration | DFW calibration |
|---|---:|---:|---:|---:|
| Conditional-rate baseline | 0.07383 [0.05919, 0.08926] | 0.13260 [0.11437, 0.15083] | 0.07708 [0.06324, 0.09118] | 0.09793 [0.08462, 0.11221] |
| Logistic baseline | 0.07442 [0.05993, 0.08979] | 0.13176 [0.11385, 0.14987] | 0.07466 [0.06170, 0.08783] | 0.09675 [0.08315, 0.11017] |
| True CSV-only LightGBM | 0.07303 [0.05915, 0.08752] | 0.12956 [0.11138, 0.14718] | 0.07558 [0.06197, 0.08903] | 0.09715 [0.08307, 0.11170] |
| Frozen all-BTS model on identical CSV subset | 0.07208 [0.05842, 0.08605] | 0.12722 [0.11045, 0.14406] | 0.07405 [0.06091, 0.08769] | 0.09515 [0.08184, 0.10861] |

The frozen all-BTS model has better point average precision and Brier score than true CSV-only training on this identical sample. Brier intervals overlap; no statistically significant gain is claimed. Average-precision confidence intervals are not implemented and remain null in the evaluator output.

The calibration CSV population before weather/common-support filtering contains ATL 1,700 scheduled flights: 23 cancellations and 1,677 eligible operated flights, including 149 severe delays. DFW has 1,592 scheduled flights: 18 cancellations and 1,574 eligible operated flights, including 176 severe delays. The common-support flight denominators above are smaller. Cancellation baseline outcomes remain separate from conditional-delay labels.

[Full CSV evaluator report, including cancellation baselines and weather/coverage slices](experiments/csv_only/metrics_dev_csv_only.json).

## Calibration and delivery boundaries

The multi-target calibrator accepts arrival, delay and cancellation predictions with distinct model IDs. Its regression interval and alert paths are conditional on throughput rows being present, so binary-only runs remain usable. The actual failure reproduced for the combined real run was missing capacity-ratio labels in the ordinary primary label file; the ratio label supplement is now an explicit input. The ordinary primary labels remain version 0.2.0, and the explicit ratio supplement is version 0.4.0; the frozen primary data files are unchanged.

The combined real calibration rerun produces the expected 80% interval policy and throughput thresholds: act ratio 0.70, watch ratio 0.85. There are 9,851 act prediction rows in the threshold-assessment period; 61.19% have actual throughput below 70% of the reference. Those are repeated horizon-specific prediction rows, not 9,851 distinct airport-hours. Calibration-period threshold assessment is not a final test.

`--labels` is available for development evaluation only; locked evaluation continues to require canonical paths and its one-time release mechanism. LOAO scoring requires every held-out request, source-only learned-model manifests, the matching cohort direction, and the schedule/persistence transfer comparator pair. All generated reports declare `data_mode=real`.

The new candidates emit available or unavailable rows; they do not present an unvalidated fallback as degraded. The earlier canonical model retains its previously disclosed fallback/selection limitations. Leakage audits were excluded under the lead’s instruction; implementation regression tests and the normal evaluator were run. No locked outcome assessment or test-guided selection occurred.

## Run index and reproduction

Each entry has `artifacts/<run_id>/manifest.json` and `predictions.parquet`. Fit/model metadata is recorded as generated; source commits and dirty flags are not rewritten to imply a later PR commit existed during fitting. RSS is the process lifetime high-water mark, cumulative across shared batches.

| Run ID | Runtime (s) | Process peak RSS (MiB) |
|---|---:|---:|
| `ablation_reporting_carrier_touchdowns_schedule_dev` | 8.439 | 1439.1 |
| `ablation_reporting_carrier_touchdowns_observations_dev` | 11.370 | 1646.6 |
| `ablation_reporting_carrier_touchdowns_forecasts_dev` | 12.127 | 1646.6 |
| `ablation_reporting_carrier_touchdowns_runway_dev` | 11.588 | 1873.0 |
| `ablation_reporting_carrier_touchdowns_operations_dev` | 13.512 | 3049.4 |
| `lgbm_throughput_dev_leave_out_KATL` | 7.516 | 3049.4 |
| `lgbm_throughput_dev_leave_out_KDFW` | 7.887 | 3049.4 |
| `lgbm_delay_csv_only_dev` | 1.416 | 478.4 |
| `lgbm_delay_csv_paired_dev` | 0.537 | 332.5 |
| `experiment_baselines_csv_only_v1` | 0.466 | 375.5 |
| `experiment_baselines_loao_KATL_v1` | 1.826 | 411.3 |
| `experiment_baselines_loao_KDFW_v1` | 1.876 | 411.3 |

Run from the repository root after dependency installation with `uv sync`. These commands reproduce development candidates and scoring; optional paths retain the generated primary data.

```sh
uv run python -m airbus_challenge.experiments --cohort retrospective_schedule_v1 --targets reporting_carrier_touchdowns --variants schedule observations forecasts runway operations
uv run python -m airbus_challenge.experiments --cohort loao_KATL_v1 --variants runway
uv run python -m airbus_challenge.experiments --cohort loao_KDFW_v1 --variants runway
uv run python -m airbus_challenge.experiments --cohort csv_only_v1 --variants runway
uv run python -c "from airbus_challenge.experiments import paths; from airbus_challenge.experiment_baselines import run; [run(c, *paths(c), tasks=['severe_delay'] if c == 'csv_only_v1' else ['throughput']) for c in ['csv_only_v1', 'loao_KATL_v1', 'loao_KDFW_v1']]"
uv run python -m airbus_challenge.experiment_csv
uv run python -m airbus_challenge.evaluate --runs baselines_dev lgbm_throughput_dev ablation_reporting_carrier_touchdowns_schedule_dev ablation_reporting_carrier_touchdowns_observations_dev ablation_reporting_carrier_touchdowns_forecasts_dev ablation_reporting_carrier_touchdowns_runway_dev ablation_reporting_carrier_touchdowns_operations_dev --reports reports/dev/experiments/ablations
uv run python -m airbus_challenge.evaluate --runs lgbm_throughput_dev_leave_out_KATL experiment_baselines_loao_KATL_v1 --cohorts loao_KATL_v1 --experiment leave_out_KATL --requests data/processed/cohorts/loao_KATL_v1/prediction_requests.parquet --labels data/labels/cohorts/loao_KATL_v1/labels.parquet --reports reports/dev/experiments/loao
uv run python -m airbus_challenge.evaluate --runs lgbm_throughput_dev_leave_out_KDFW experiment_baselines_loao_KDFW_v1 --cohorts loao_KDFW_v1 --experiment leave_out_KDFW --requests data/processed/cohorts/loao_KDFW_v1/prediction_requests.parquet --labels data/labels/cohorts/loao_KDFW_v1/labels.parquet --reports reports/dev/experiments/loao
uv run python -m airbus_challenge.evaluate --runs ratio_baselines_dev --labels data/labels/ratio_labels_primary.parquet --reports reports/dev/experiments/ratio
uv run python -m airbus_challenge.evaluate --runs experiment_baselines_csv_only_v1 lgbm_delay_csv_only_dev lgbm_delay_csv_paired_dev --cohorts csv_only_v1 --experiment csv_only --requests data/processed/cohorts/csv_only_v1/prediction_requests.parquet --labels data/labels/cohorts/csv_only_v1/labels.parquet --reports reports/dev/experiments/csv_only
uv run python -m airbus_challenge.calibrate --run lgbm_dev --runs baselines_dev baselines_flight_dev --ratio-labels data/labels/ratio_labels_primary.parquet
```

The additive cohort baseline helper is in `airbus_challenge.experiment_baselines`; the frozen paired model scorer is `airbus_challenge.experiment_csv`. Their generated manifests bind cohort requests and source-fit inputs. The paired prediction manifest records the frozen all-BTS booster SHA.
