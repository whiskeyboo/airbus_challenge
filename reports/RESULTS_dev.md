# Results: evaluate_dev

- Scope: development (2023 train; H1/H2 2024 scored); not the locked 2025 test
- Scored splits (half-open UTC): calibration 2024-07-01 to 2025-01-01, validation 2024-01-01 to 2024-07-01
- Commit: 41efc6034787ba4d832c5536cbb0e04cebc946fe (commit_dirty=False)
- data_mode: real
- Label versions: 0.2.0
- Generated (UTC): 2026-10-31T07:25:49Z
- Availability basis: conditional_rate: retrospective_schedule; logistic: retrospective_schedule; persistence: simulated_feed; schedule: retrospective_schedule; seasonal_persistence: simulated_feed

## arrival throughput (AAR proxy)

RMSE (touchdowns/hour) on common support, all horizons, 95% CI in brackets.

| split | airport | climatology | persistence | schedule | seasonal_persistence | lgbm_throughput | n_predicted |
|---|---|---|---|---|---|---|---|
| calibration | KATL | 8.778 [8.165, 9.489] | 39.116 [38.617, 39.572] | 8.462 [7.785, 9.230] | 10.633 [9.726, 11.650] | 6.916 [6.112, 7.880] | 17640 |
| calibration | KDFW | 13.098 [12.622, 13.614] | 37.685 [37.256, 38.097] | 12.996 [12.555, 13.432] | 11.508 [10.482, 12.560] | 9.168 [8.566, 9.818] | 17536 |
| calibration | pooled (airport-hour weighted) | 11.143 [10.770, 11.575] | 38.409 [37.981, 38.815] | 10.959 [10.612, 11.314] | 11.077 [10.275, 11.969] | 8.117 [7.608, 8.659] | 35176 |
| validation | KATL | 6.749 [6.323, 7.198] | 38.178 [37.899, 38.438] | 7.467 [7.156, 7.810] | 7.144 [6.582, 7.723] | 5.317 [4.937, 5.736] | 17289 |
| validation | KDFW | 9.869 [9.208, 10.477] | 32.949 [32.572, 33.328] | 11.948 [11.406, 12.478] | 10.912 [10.017, 11.752] | 7.950 [7.229, 8.661] | 17382 |
| validation | pooled (airport-hour weighted) | 8.459 [8.017, 8.898] | 35.652 [35.378, 35.898] | 9.968 [9.592, 10.325] | 9.227 [8.579, 9.784] | 6.766 [6.277, 7.253] | 34671 |

Persistence is a simulated feed (last complete hour before issue) and is weak at 3-12 h; climatology and seasonal persistence are the baselines to beat.

### RMSE by horizon

Best non-baseline model on validation: lgbm_throughput_v1.

**KATL**

| split | horizon_h | lgbm_throughput | climatology | seasonal_persistence | n_predicted |
|---|---|---|---|---|---|
| calibration | 3 | 6.888 [6.090, 7.832] | 8.780 [8.166, 9.491] | 10.633 [9.726, 11.651] | 4410 |
| calibration | 6 | 6.897 [6.080, 7.866] | 8.780 [8.165, 9.491] | 10.633 [9.726, 11.651] | 4410 |
| calibration | 9 | 6.926 [6.112, 7.883] | 8.780 [8.165, 9.491] | 10.634 [9.727, 11.651] | 4410 |
| calibration | 12 | 6.953 [6.140, 7.907] | 8.774 [8.158, 9.486] | 10.630 [9.723, 11.649] | 4410 |
| calibration | all | 6.916 [6.112, 7.880] | 8.778 [8.165, 9.489] | 10.633 [9.726, 11.650] | 17640 |
| validation | 3 | 5.334 [4.944, 5.761] | 6.757 [6.330, 7.202] | 7.145 [6.584, 7.723] | 4330 |
| validation | 6 | 5.285 [4.908, 5.711] | 6.747 [6.322, 7.197] | 7.145 [6.579, 7.724] | 4324 |
| validation | 9 | 5.318 [4.920, 5.746] | 6.746 [6.313, 7.222] | 7.143 [6.571, 7.739] | 4319 |
| validation | 12 | 5.332 [4.952, 5.754] | 6.746 [6.313, 7.222] | 7.144 [6.571, 7.741] | 4316 |
| validation | all | 5.317 [4.937, 5.736] | 6.749 [6.323, 7.198] | 7.144 [6.582, 7.723] | 17289 |

**KDFW**

| split | horizon_h | lgbm_throughput | climatology | seasonal_persistence | n_predicted |
|---|---|---|---|---|---|
| calibration | 3 | 9.121 [8.536, 9.759] | 13.088 [12.612, 13.603] | 11.500 [10.479, 12.552] | 4385 |
| calibration | 6 | 9.151 [8.552, 9.795] | 13.102 [12.627, 13.617] | 11.506 [10.481, 12.560] | 4382 |
| calibration | 9 | 9.189 [8.587, 9.831] | 13.106 [12.634, 13.622] | 11.521 [10.492, 12.572] | 4384 |
| calibration | 12 | 9.212 [8.588, 9.898] | 13.097 [12.616, 13.616] | 11.503 [10.483, 12.553] | 4385 |
| calibration | all | 9.168 [8.566, 9.818] | 13.098 [12.622, 13.614] | 11.508 [10.482, 12.560] | 17536 |
| validation | 3 | 7.884 [7.188, 8.558] | 9.882 [9.223, 10.489] | 10.904 [10.001, 11.745] | 4350 |
| validation | 6 | 7.935 [7.222, 8.640] | 9.856 [9.190, 10.465] | 10.911 [10.015, 11.747] | 4347 |
| validation | 9 | 7.975 [7.201, 8.747] | 9.870 [9.183, 10.517] | 10.917 [10.050, 11.776] | 4344 |
| validation | 12 | 8.005 [7.219, 8.781] | 9.869 [9.183, 10.520] | 10.917 [10.048, 11.777] | 4341 |
| validation | all | 7.950 [7.229, 8.661] | 9.869 [9.208, 10.477] | 10.912 [10.017, 11.752] | 17382 |

**pooled (airport-hour weighted)**

| split | horizon_h | lgbm_throughput | climatology | seasonal_persistence | n_predicted |
|---|---|---|---|---|---|
| calibration | 3 | 8.079 [7.575, 8.606] | 11.138 [10.757, 11.567] | 11.074 [10.268, 11.964] | 8795 |
| calibration | 6 | 8.099 [7.596, 8.640] | 11.146 [10.770, 11.577] | 11.077 [10.273, 11.968] | 8792 |
| calibration | 9 | 8.133 [7.623, 8.673] | 11.148 [10.771, 11.582] | 11.085 [10.290, 11.981] | 8794 |
| calibration | 12 | 8.158 [7.650, 8.711] | 11.141 [10.762, 11.571] | 11.074 [10.268, 11.969] | 8795 |
| calibration | all | 8.117 [7.608, 8.659] | 11.143 [10.770, 11.575] | 11.077 [10.275, 11.969] | 35176 |
| validation | 3 | 6.734 [6.265, 7.193] | 8.469 [8.029, 8.910] | 9.222 [8.571, 9.775] | 8680 |
| validation | 6 | 6.745 [6.259, 7.231] | 8.450 [8.006, 8.890] | 9.227 [8.579, 9.785] | 8671 |
| validation | 9 | 6.782 [6.237, 7.321] | 8.458 [8.005, 8.907] | 9.230 [8.622, 9.866] | 8663 |
| validation | 12 | 6.805 [6.256, 7.326] | 8.457 [8.005, 8.908] | 9.231 [8.620, 9.864] | 8657 |
| validation | all | 6.766 [6.277, 7.253] | 8.459 [8.017, 8.898] | 9.227 [8.579, 9.784] | 34671 |

### Skill (1 - RMSE/RMSE_baseline on baseline support, all horizons)

Skill vs seasonal persistence is n/a: evaluate.py computes skill only against its required baselines (persistence, climatology). The RMSE CIs above are unpaired, so they cannot settle it either.

**calibration**

| airport | model | vs climatology | vs seasonal_persistence | n |
|---|---|---|---|---|
| KATL | climatology | - | n/a (not in report) | 17648 |
| KATL | persistence | -3.453 [-3.823, -3.097]; worse than climatology | n/a (not in report) | 17648 |
| KATL | schedule | 0.036 [-0.008, 0.090]; not distinguishable from climatology | n/a (not in report) | 17648 |
| KATL | seasonal_persistence | -0.211 [-0.289, -0.138]; worse than climatology | - | 17640 |
| KATL | lgbm_throughput | 0.212 [0.159, 0.275]; better than climatology | n/a (not in report) | 17648 |
| KDFW | climatology | - | n/a (not in report) | 17580 |
| KDFW | persistence | -1.880 [-1.982, -1.776]; worse than climatology | n/a (not in report) | 17580 |
| KDFW | schedule | 0.008 [-0.015, 0.034]; not distinguishable from climatology | n/a (not in report) | 17580 |
| KDFW | seasonal_persistence | 0.121 [0.057, 0.196]; better than climatology | - | 17536 |
| KDFW | lgbm_throughput | 0.300 [0.266, 0.336]; better than climatology | n/a (not in report) | 17580 |
| pooled | climatology | - | n/a (not in report) | 35228 |
| pooled | persistence | -2.448 [-2.585, -2.299]; worse than climatology | n/a (not in report) | 35228 |
| pooled | schedule | 0.017 [-0.010, 0.046]; not distinguishable from climatology | n/a (not in report) | 35228 |
| pooled | seasonal_persistence | 0.006 [-0.057, 0.066]; not distinguishable from climatology | - | 35176 |
| pooled | lgbm_throughput | 0.271 [0.237, 0.307]; better than climatology | n/a (not in report) | 35228 |

**validation**

| airport | model | vs climatology | vs seasonal_persistence | n |
|---|---|---|---|---|
| KATL | climatology | - | n/a (not in report) | 17345 |
| KATL | persistence | -4.665 [-5.051, -4.273]; worse than climatology | n/a (not in report) | 17345 |
| KATL | schedule | -0.107 [-0.157, -0.064]; worse than climatology | n/a (not in report) | 17345 |
| KATL | seasonal_persistence | -0.059 [-0.136, 0.008]; not distinguishable from climatology | - | 17289 |
| KATL | lgbm_throughput | 0.212 [0.181, 0.245]; better than climatology | n/a (not in report) | 17345 |
| KDFW | climatology | - | n/a (not in report) | 17402 |
| KDFW | persistence | -2.341 [-2.589, -2.129]; worse than climatology | n/a (not in report) | 17402 |
| KDFW | schedule | -0.211 [-0.253, -0.178]; worse than climatology | n/a (not in report) | 17402 |
| KDFW | seasonal_persistence | -0.106 [-0.174, -0.039]; worse than climatology | - | 17382 |
| KDFW | lgbm_throughput | 0.194 [0.167, 0.225]; better than climatology | n/a (not in report) | 17402 |
| pooled | climatology | - | n/a (not in report) | 34747 |
| pooled | persistence | -3.220 [-3.454, -3.011]; worse than climatology | n/a (not in report) | 34747 |
| pooled | schedule | -0.179 [-0.207, -0.152]; worse than climatology | n/a (not in report) | 34747 |
| pooled | seasonal_persistence | -0.091 [-0.146, -0.035]; worse than climatology | - | 34671 |
| pooled | lgbm_throughput | 0.200 [0.177, 0.226]; better than climatology | n/a (not in report) | 34747 |

## Severe departure delay (>45 min, conditional on operating)

Common support, all horizons. Recall at precision is a curve summary, not a frozen alert threshold.

| split | airport | model | AP | Brier | R@P0.25 | R@P0.5 | prevalence | n |
|---|---|---|---|---|---|---|---|---|
| calibration | KATL | conditional_rate | 0.123 | 0.080 [0.070, 0.091] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.089 | 687948 |
| calibration | KATL | logistic | 0.204 | 0.077 [0.068, 0.088] | 0.343 | 0.005 | 0.089 | 687948 |
| calibration | KATL | lgbm_delay | 0.234 | 0.076 [0.067, 0.086] | 0.404 | n/a (precision_not_reached) | 0.089 | 687948 |
| calibration | KDFW | conditional_rate | 0.157 | 0.104 [0.096, 0.113] | 0.004 | n/a (precision_not_reached) | 0.120 | 640904 |
| calibration | KDFW | logistic | 0.205 | 0.103 [0.095, 0.111] | 0.270 | 0.000 | 0.120 | 640904 |
| calibration | KDFW | lgbm_delay | 0.213 | 0.102 [0.094, 0.110] | 0.268 | 0.005 | 0.120 | 640904 |
| calibration | pooled (flight weighted) | conditional_rate | 0.147 | 0.091 [0.083, 0.101] | 0.002 | n/a (precision_not_reached) | 0.104 | 1328852 |
| calibration | pooled (flight weighted) | logistic | 0.199 | 0.090 [0.082, 0.099] | 0.302 | 0.000 | 0.104 | 1328852 |
| calibration | pooled (flight weighted) | lgbm_delay | 0.219 | 0.089 [0.081, 0.097] | 0.350 | n/a (precision_not_reached) | 0.104 | 1328852 |
| validation | KATL | conditional_rate | 0.101 | 0.073 [0.064, 0.083] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.079 | 665315 |
| validation | KATL | logistic | 0.105 | 0.073 [0.065, 0.083] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.079 | 665315 |
| validation | KATL | lgbm_delay | 0.146 | 0.071 [0.064, 0.080] | 0.062 | 0.000 | 0.079 | 665315 |
| validation | KDFW | conditional_rate | 0.201 | 0.130 [0.118, 0.143] | 0.003 | n/a (precision_not_reached) | 0.155 | 589659 |
| validation | KDFW | logistic | 0.217 | 0.129 [0.117, 0.141] | 0.160 | 0.001 | 0.155 | 589659 |
| validation | KDFW | lgbm_delay | 0.296 | 0.123 [0.113, 0.134] | 0.595 | 0.065 | 0.155 | 589659 |
| validation | pooled (flight weighted) | conditional_rate | 0.174 | 0.100 [0.092, 0.109] | 0.002 | n/a (precision_not_reached) | 0.115 | 1254974 |
| validation | pooled (flight weighted) | logistic | 0.178 | 0.099 [0.091, 0.109] | 0.067 | 0.000 | 0.115 | 1254974 |
| validation | pooled (flight weighted) | lgbm_delay | 0.243 | 0.096 [0.089, 0.104] | 0.360 | 0.003 | 0.115 | 1254974 |

Brier skill vs required baselines:

**calibration**

| airport | model | vs conditional_rate | vs logistic | n |
|---|---|---|---|---|
| KATL | conditional_rate | - | -0.031 [-0.045, -0.017]; worse than logistic | 687948 |
| KATL | logistic | 0.030 [0.016, 0.043]; better than conditional_rate | - | 687948 |
| KATL | lgbm_delay | 0.047 [0.031, 0.066]; better than conditional_rate | 0.018 [0.011, 0.026]; better than logistic | 687948 |
| KDFW | conditional_rate | - | -0.013 [-0.025, 0.001]; not distinguishable from logistic | 640904 |
| KDFW | logistic | 0.012 [-0.001, 0.024]; not distinguishable from conditional_rate | - | 640904 |
| KDFW | lgbm_delay | 0.019 [0.007, 0.032]; better than conditional_rate | 0.007 [-0.000, 0.014]; not distinguishable from logistic | 640904 |
| pooled | conditional_rate | - | -0.021 [-0.032, -0.008]; worse than logistic | 1328852 |
| pooled | logistic | 0.020 [0.008, 0.031]; better than conditional_rate | - | 1328852 |
| pooled | lgbm_delay | 0.032 [0.018, 0.045]; better than conditional_rate | 0.012 [0.007, 0.017]; better than logistic | 1328852 |

**validation**

| airport | model | vs conditional_rate | vs logistic | n |
|---|---|---|---|---|
| KATL | conditional_rate | - | 0.007 [0.002, 0.013]; better than logistic | 665315 |
| KATL | logistic | -0.007 [-0.013, -0.002]; worse than conditional_rate | - | 665315 |
| KATL | lgbm_delay | 0.018 [-0.000, 0.035]; not distinguishable from conditional_rate | 0.025 [0.008, 0.042]; better than logistic | 665315 |
| KDFW | conditional_rate | - | -0.011 [-0.020, -0.003]; worse than logistic | 589659 |
| KDFW | logistic | 0.011 [0.003, 0.019]; better than conditional_rate | - | 589659 |
| KDFW | lgbm_delay | 0.053 [0.033, 0.073]; better than conditional_rate | 0.043 [0.024, 0.062]; better than logistic | 589659 |
| pooled | conditional_rate | - | -0.004 [-0.010, 0.002]; not distinguishable from logistic | 1254974 |
| pooled | logistic | 0.004 [-0.002, 0.010]; not distinguishable from conditional_rate | - | 1254974 |
| pooled | lgbm_delay | 0.039 [0.024, 0.053]; better than conditional_rate | 0.036 [0.021, 0.050]; better than logistic | 1254974 |

### Cancellation rate (excluded from the severe-delay denominator)

| split | airport | rate | cancelled/scheduled |
|---|---|---|---|
| calibration | KATL | 0.015 | 10680/698628 |
| calibration | KDFW | 0.012 | 7796/648700 |
| calibration | pooled (flight weighted) | 0.014 | 18476/1347328 |
| validation | KATL | 0.004 | 2960/668275 |
| validation | KDFW | 0.026 | 15552/605211 |
| validation | pooled (flight weighted) | 0.015 | 18512/1273486 |

## Cancellation

Common support, all horizons. Recall at precision is a curve summary, not a frozen alert threshold.

| split | airport | model | AP | Brier | R@P0.25 | R@P0.5 | prevalence | n |
|---|---|---|---|---|---|---|---|---|
| calibration | KATL | conditional_rate | 0.018 | 0.015 [0.008, 0.025] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.015 | 698628 |
| calibration | KATL | logistic | 0.025 | 0.015 [0.008, 0.025] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.015 | 698628 |
| calibration | KDFW | conditional_rate | 0.014 | 0.012 [0.008, 0.017] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.012 | 648700 |
| calibration | KDFW | logistic | 0.012 | 0.012 [0.008, 0.017] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.012 | 648700 |
| calibration | pooled (flight weighted) | conditional_rate | 0.015 | 0.014 [0.009, 0.020] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.014 | 1347328 |
| calibration | pooled (flight weighted) | logistic | 0.016 | 0.014 [0.009, 0.020] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.014 | 1347328 |
| validation | KATL | conditional_rate | 0.005 | 0.004 [0.003, 0.006] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.004 | 668275 |
| validation | KATL | logistic | 0.005 | 0.005 [0.003, 0.006] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.004 | 668275 |
| validation | KDFW | conditional_rate | 0.033 | 0.025 [0.016, 0.036] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.026 | 605211 |
| validation | KDFW | logistic | 0.020 | 0.025 [0.017, 0.036] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.026 | 605211 |
| validation | pooled (flight weighted) | conditional_rate | 0.029 | 0.014 [0.010, 0.019] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.015 | 1273486 |
| validation | pooled (flight weighted) | logistic | 0.015 | 0.014 [0.010, 0.020] | n/a (precision_not_reached) | n/a (precision_not_reached) | 0.015 | 1273486 |

Brier skill vs required baselines:

**calibration**

| airport | model | vs conditional_rate | vs logistic | n |
|---|---|---|---|---|
| KATL | conditional_rate | - | 0.001 [-0.002, 0.003]; not distinguishable from logistic | 698628 |
| KATL | logistic | -0.001 [-0.003, 0.002]; not distinguishable from conditional_rate | - | 698628 |
| KDFW | conditional_rate | - | 0.007 [-0.005, 0.015]; not distinguishable from logistic | 648700 |
| KDFW | logistic | -0.007 [-0.015, 0.005]; not distinguishable from conditional_rate | - | 648700 |
| pooled | conditional_rate | - | 0.003 [-0.002, 0.008]; not distinguishable from logistic | 1347328 |
| pooled | logistic | -0.003 [-0.009, 0.002]; not distinguishable from conditional_rate | - | 1347328 |

**validation**

| airport | model | vs conditional_rate | vs logistic | n |
|---|---|---|---|---|
| KATL | conditional_rate | - | 0.018 [0.011, 0.027]; better than logistic | 668275 |
| KATL | logistic | -0.018 [-0.028, -0.011]; worse than conditional_rate | - | 668275 |
| KDFW | conditional_rate | - | 0.014 [0.008, 0.022]; better than logistic | 605211 |
| KDFW | logistic | -0.014 [-0.023, -0.008]; worse than conditional_rate | - | 605211 |
| pooled | conditional_rate | - | 0.014 [0.008, 0.023]; better than logistic | 1273486 |
| pooled | logistic | -0.015 [-0.023, -0.008]; worse than conditional_rate | - | 1273486 |

## Scoring scope

Rows issued before the latest fit cutoff are dropped for every model.

| split | target | cohort | fit cutoff (UTC) | set by | rows dropped | rows scored | null |
|---|---|---|---|---|---|---|---|
| calibration | cancellation | retrospective_schedule_v1 | 2024-01-01T00:00:00Z | baselines_flight_dev | 0 (conditional_rate 0, logistic 0) | 1347328 |  |
| validation | cancellation | retrospective_schedule_v1 | 2024-01-01T00:00:00Z | baselines_flight_dev | 0 (conditional_rate 0, logistic 0) | 1273486 |  |
| calibration | departure_delay_gt45 | retrospective_schedule_v1 | 2024-01-01T00:00:00Z | baselines_flight_dev, lgbm_delay_dev | 0 (conditional_rate 0, logistic 0, lgbm_delay 0) | 1347328 |  |
| validation | departure_delay_gt45 | retrospective_schedule_v1 | 2024-01-01T00:00:00Z | baselines_flight_dev, lgbm_delay_dev | 0 (conditional_rate 0, logistic 0, lgbm_delay 0) | 1273486 |  |
| calibration | reporting_carrier_touchdowns | retrospective_schedule_v1 | 2024-01-01T00:00:00Z | baselines_dev, lgbm_throughput_dev | 0 (climatology 0, persistence 0, schedule 0, seasonal_persistence 0, lgbm_throughput 0) | 35328 |  |
| validation | reporting_carrier_touchdowns | retrospective_schedule_v1 | 2024-01-01T00:00:00Z | baselines_dev, lgbm_throughput_dev | 0 (climatology 0, persistence 0, schedule 0, seasonal_persistence 0, lgbm_throughput 0) | 34884 |  |

## Coverage (pooled, all horizons)

| split | target | model | n_eligible | n_excluded | exclusions | n_degraded |
|---|---|---|---|---|---|---|
| calibration | cancellation | conditional_rate | 1347328 | 0 | - | 0 |
| calibration | cancellation | logistic | 1347328 | 0 | - | 0 |
| calibration | departure_delay_gt45 | conditional_rate | 1328852 | 18476 | cancelled 18476 | 0 |
| calibration | departure_delay_gt45 | logistic | 1328852 | 18476 | cancelled 18476 | 0 |
| calibration | departure_delay_gt45 | lgbm_delay | 1328852 | 18476 | cancelled 18476 | 12804 |
| calibration | reporting_carrier_touchdowns | climatology | 35272 | 56 | coverage_incomplete 56 | 0 |
| calibration | reporting_carrier_touchdowns | persistence | 35272 | 56 | coverage_incomplete 56 | 0 |
| calibration | reporting_carrier_touchdowns | schedule | 35272 | 56 | coverage_incomplete 56 | 0 |
| calibration | reporting_carrier_touchdowns | seasonal_persistence | 35272 | 56 | coverage_incomplete 56 | 0 |
| calibration | reporting_carrier_touchdowns | lgbm_throughput | 35272 | 56 | coverage_incomplete 56 | 268 |
| validation | cancellation | conditional_rate | 1273486 | 0 | - | 0 |
| validation | cancellation | logistic | 1273486 | 0 | - | 0 |
| validation | departure_delay_gt45 | conditional_rate | 1254974 | 18512 | cancelled 18512 | 0 |
| validation | departure_delay_gt45 | logistic | 1254974 | 18512 | cancelled 18512 | 0 |
| validation | departure_delay_gt45 | lgbm_delay | 1254974 | 18512 | cancelled 18512 | 3816 |
| validation | reporting_carrier_touchdowns | climatology | 34812 | 72 | coverage_incomplete 72 | 0 |
| validation | reporting_carrier_touchdowns | persistence | 34812 | 72 | coverage_incomplete 72 | 0 |
| validation | reporting_carrier_touchdowns | schedule | 34812 | 72 | coverage_incomplete 72 | 0 |
| validation | reporting_carrier_touchdowns | seasonal_persistence | 34812 | 72 | coverage_incomplete 72 | 0 |
| validation | reporting_carrier_touchdowns | lgbm_throughput | 34812 | 72 | coverage_incomplete 72 | 100 |

## Honesty notes

- A null metric reads n/a (reason); it is never 0. Values without a bracket have no CI (ci_reason in the metrics JSON).
- A model is called better only when its skill CI lies above 0, i.e. excludes the baseline's own value; otherwise it is not distinguishable.
- Arrival throughput is an AAR proxy: it reflects demand as well as capacity.

Weather slices: none in this report.

Known limitations: [docs/LIMITATIONS.md](docs/LIMITATIONS.md).
