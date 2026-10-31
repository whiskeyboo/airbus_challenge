# Results: evaluate_dev

- Scope: development (2023 train; H1/H2 2024 scored); not the locked 2025 test
- Scored splits (half-open UTC): calibration 2024-07-01 to 2025-01-01, validation 2024-01-01 to 2024-07-01
- Commit: 5877a64aac7be3d91eee7cf0fc1d8a138bad7870 (commit_dirty=False)
- data_mode: real
- Label versions: 0.3.0
- Generated (UTC): 2026-10-31T07:52:13Z
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

**calibration**

| airport | model | vs climatology | vs seasonal_persistence | n |
|---|---|---|---|---|
| KATL | climatology | - | 0.174 [0.121, 0.224]; better than seasonal_persistence | 17640 |
| KATL | persistence | -3.456 [-3.849, -3.096]; worse than climatology | -2.679 [-3.080, -2.350]; worse than seasonal_persistence | 17640 |
| KATL | schedule | 0.036 [-0.007, 0.082]; not distinguishable from climatology | 0.204 [0.141, 0.263]; better than seasonal_persistence | 17640 |
| KATL | seasonal_persistence | -0.211 [-0.289, -0.138]; worse than climatology | - | 17640 |
| KATL | lgbm_throughput | 0.212 [0.161, 0.265]; better than climatology | 0.350 [0.287, 0.409]; better than seasonal_persistence | 17640 |
| KDFW | climatology | - | -0.138 [-0.244, -0.060]; worse than seasonal_persistence | 17536 |
| KDFW | persistence | -1.877 [-1.979, -1.774]; worse than climatology | -2.275 [-2.644, -1.996]; worse than seasonal_persistence | 17536 |
| KDFW | schedule | 0.008 [-0.015, 0.034]; not distinguishable from climatology | -0.129 [-0.252, -0.043]; worse than seasonal_persistence | 17536 |
| KDFW | seasonal_persistence | 0.121 [0.057, 0.196]; better than climatology | - | 17536 |
| KDFW | lgbm_throughput | 0.300 [0.266, 0.335]; better than climatology | 0.203 [0.118, 0.273]; better than seasonal_persistence | 17536 |
| pooled | climatology | - | -0.006 [-0.071, 0.054]; not distinguishable from seasonal_persistence | 35176 |
| pooled | persistence | -2.447 [-2.576, -2.308]; worse than climatology | -2.467 [-2.758, -2.199]; worse than seasonal_persistence | 35176 |
| pooled | schedule | 0.017 [-0.010, 0.047]; not distinguishable from climatology | 0.011 [-0.064, 0.082]; not distinguishable from seasonal_persistence | 35176 |
| pooled | seasonal_persistence | 0.006 [-0.057, 0.066]; not distinguishable from climatology | - | 35176 |
| pooled | lgbm_throughput | 0.272 [0.239, 0.307]; better than climatology | 0.267 [0.211, 0.320]; better than seasonal_persistence | 35176 |

**validation**

| airport | model | vs climatology | vs seasonal_persistence | n |
|---|---|---|---|---|
| KATL | climatology | - | 0.055 [-0.008, 0.120]; not distinguishable from seasonal_persistence | 17289 |
| KATL | persistence | -4.657 [-5.082, -4.268]; worse than climatology | -4.344 [-4.792, -3.941]; worse than seasonal_persistence | 17289 |
| KATL | schedule | -0.106 [-0.157, -0.059]; worse than climatology | -0.045 [-0.119, 0.021]; not distinguishable from seasonal_persistence | 17289 |
| KATL | seasonal_persistence | -0.059 [-0.136, 0.008]; not distinguishable from climatology | - | 17289 |
| KATL | lgbm_throughput | 0.212 [0.183, 0.242]; better than climatology | 0.256 [0.203, 0.308]; better than seasonal_persistence | 17289 |
| KDFW | climatology | - | 0.096 [0.037, 0.149]; better than seasonal_persistence | 17382 |
| KDFW | persistence | -2.339 [-2.588, -2.124]; worse than climatology | -2.020 [-2.291, -1.792]; worse than seasonal_persistence | 17382 |
| KDFW | schedule | -0.211 [-0.253, -0.178]; worse than climatology | -0.095 [-0.172, -0.031]; worse than seasonal_persistence | 17382 |
| KDFW | seasonal_persistence | -0.106 [-0.174, -0.039]; worse than climatology | - | 17382 |
| KDFW | lgbm_throughput | 0.194 [0.167, 0.225]; better than climatology | 0.271 [0.220, 0.324]; better than seasonal_persistence | 17382 |
| pooled | climatology | - | 0.083 [0.034, 0.128]; better than seasonal_persistence | 34671 |
| pooled | persistence | -3.215 [-3.444, -2.991]; worse than climatology | -2.864 [-3.139, -2.608]; worse than seasonal_persistence | 34671 |
| pooled | schedule | -0.178 [-0.211, -0.151]; worse than climatology | -0.080 [-0.146, -0.025]; worse than seasonal_persistence | 34671 |
| pooled | seasonal_persistence | -0.091 [-0.146, -0.035]; worse than climatology | - | 34671 |
| pooled | lgbm_throughput | 0.200 [0.177, 0.225]; better than climatology | 0.267 [0.224, 0.308]; better than seasonal_persistence | 34671 |

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

### Weather slices

| split | target | airport | horizon | model | slice | metric | value | n |
|---|---|---|---|---|---|---|---|---|
| calibration | cancellation | KATL | all | conditional_rate | weather:not_thunderstorm | brier | 0.015 [0.008, 0.024] | 684112 |
| calibration | cancellation | KATL | all | conditional_rate | weather:not_thunderstorm | average_precision | 0.018 | 684112 |
| calibration | cancellation | KATL | all | logistic | weather:not_thunderstorm | brier | 0.015 [0.008, 0.024] | 684112 |
| calibration | cancellation | KATL | all | logistic | weather:not_thunderstorm | average_precision | 0.025 | 684112 |
| calibration | cancellation | KATL | all | conditional_rate | weather:thunderstorm | brier | 0.028 [0.007, 0.058] | 14460 |
| calibration | cancellation | KATL | all | conditional_rate | weather:thunderstorm | average_precision | 0.049 | 14460 |
| calibration | cancellation | KATL | all | logistic | weather:thunderstorm | brier | 0.028 [0.008, 0.058] | 14460 |
| calibration | cancellation | KATL | all | logistic | weather:thunderstorm | average_precision | 0.049 | 14460 |
| calibration | cancellation | KATL | all | conditional_rate | weather:thunderstorm_unknown | brier | 0.001 | 56 |
| calibration | cancellation | KATL | all | conditional_rate | weather:thunderstorm_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | KATL | all | logistic | weather:thunderstorm_unknown | brier | 0.000 | 56 |
| calibration | cancellation | KATL | all | logistic | weather:thunderstorm_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | KATL | all | conditional_rate | weather:ifr | brier | 0.018 [0.005, 0.035] | 64688 |
| calibration | cancellation | KATL | all | conditional_rate | weather:ifr | average_precision | 0.026 | 64688 |
| calibration | cancellation | KATL | all | logistic | weather:ifr | brier | 0.019 [0.005, 0.035] | 64688 |
| calibration | cancellation | KATL | all | logistic | weather:ifr | average_precision | 0.048 | 64688 |
| calibration | cancellation | KATL | all | conditional_rate | weather:ifr_unknown | brier | 0.001 | 56 |
| calibration | cancellation | KATL | all | conditional_rate | weather:ifr_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | KATL | all | logistic | weather:ifr_unknown | brier | 0.000 | 56 |
| calibration | cancellation | KATL | all | logistic | weather:ifr_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | KATL | all | conditional_rate | weather:not_ifr | brier | 0.015 [0.007, 0.024] | 633884 |
| calibration | cancellation | KATL | all | conditional_rate | weather:not_ifr | average_precision | 0.017 | 633884 |
| calibration | cancellation | KATL | all | logistic | weather:not_ifr | brier | 0.015 [0.007, 0.024] | 633884 |
| calibration | cancellation | KATL | all | logistic | weather:not_ifr | average_precision | 0.025 | 633884 |
| calibration | cancellation | KATL | all | conditional_rate | weather:low_vis | brier | 0.013 [0.000, 0.022] | 13560 |
| calibration | cancellation | KATL | all | conditional_rate | weather:low_vis | average_precision | 0.019 | 13560 |
| calibration | cancellation | KATL | all | logistic | weather:low_vis | brier | 0.013 [0.000, 0.022] | 13560 |
| calibration | cancellation | KATL | all | logistic | weather:low_vis | average_precision | 0.023 | 13560 |
| calibration | cancellation | KATL | all | conditional_rate | weather:low_vis_unknown | brier | 0.001 | 56 |
| calibration | cancellation | KATL | all | conditional_rate | weather:low_vis_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | KATL | all | logistic | weather:low_vis_unknown | brier | 0.000 | 56 |
| calibration | cancellation | KATL | all | logistic | weather:low_vis_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | KATL | all | conditional_rate | weather:not_low_vis | brier | 0.015 [0.008, 0.025] | 685012 |
| calibration | cancellation | KATL | all | conditional_rate | weather:not_low_vis | average_precision | 0.018 | 685012 |
| calibration | cancellation | KATL | all | logistic | weather:not_low_vis | brier | 0.015 [0.008, 0.025] | 685012 |
| calibration | cancellation | KATL | all | logistic | weather:not_low_vis | average_precision | 0.025 | 685012 |
| calibration | cancellation | KATL | all | conditional_rate | weather:not_strong_crosswind | brier | 0.015 [0.008, 0.025] | 698084 |
| calibration | cancellation | KATL | all | conditional_rate | weather:not_strong_crosswind | average_precision | 0.018 | 698084 |
| calibration | cancellation | KATL | all | logistic | weather:not_strong_crosswind | brier | 0.015 [0.008, 0.025] | 698084 |
| calibration | cancellation | KATL | all | logistic | weather:not_strong_crosswind | average_precision | 0.025 | 698084 |
| calibration | cancellation | KATL | all | conditional_rate | weather:strong_crosswind | brier | 0.000 | 488 |
| calibration | cancellation | KATL | all | conditional_rate | weather:strong_crosswind | average_precision | n/a (single_class) | 488 |
| calibration | cancellation | KATL | all | logistic | weather:strong_crosswind | brier | 0.000 | 488 |
| calibration | cancellation | KATL | all | logistic | weather:strong_crosswind | average_precision | n/a (single_class) | 488 |
| calibration | cancellation | KATL | all | conditional_rate | weather:strong_crosswind_unknown | brier | 0.001 | 56 |
| calibration | cancellation | KATL | all | conditional_rate | weather:strong_crosswind_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | KATL | all | logistic | weather:strong_crosswind_unknown | brier | 0.000 | 56 |
| calibration | cancellation | KATL | all | logistic | weather:strong_crosswind_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:not_thunderstorm | brier | 0.010 [0.007, 0.014] | 640476 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:not_thunderstorm | average_precision | 0.013 | 640476 |
| calibration | cancellation | KDFW | all | logistic | weather:not_thunderstorm | brier | 0.010 [0.007, 0.015] | 640476 |
| calibration | cancellation | KDFW | all | logistic | weather:not_thunderstorm | average_precision | 0.011 | 640476 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:thunderstorm | brier | 0.126 | 8224 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:thunderstorm | average_precision | 0.171 | 8224 |
| calibration | cancellation | KDFW | all | logistic | weather:thunderstorm | brier | 0.129 | 8224 |
| calibration | cancellation | KDFW | all | logistic | weather:thunderstorm | average_precision | 0.105 | 8224 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:ifr | brier | 0.043 [0.017, 0.077] | 29224 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:ifr | average_precision | 0.047 | 29224 |
| calibration | cancellation | KDFW | all | logistic | weather:ifr | brier | 0.044 [0.017, 0.078] | 29224 |
| calibration | cancellation | KDFW | all | logistic | weather:ifr | average_precision | 0.036 | 29224 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:not_ifr | brier | 0.010 [0.007, 0.014] | 619476 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:not_ifr | average_precision | 0.013 | 619476 |
| calibration | cancellation | KDFW | all | logistic | weather:not_ifr | brier | 0.010 [0.007, 0.014] | 619476 |
| calibration | cancellation | KDFW | all | logistic | weather:not_ifr | average_precision | 0.012 | 619476 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:low_vis | brier | 0.058 | 4056 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:low_vis | average_precision | 0.250 | 4056 |
| calibration | cancellation | KDFW | all | logistic | weather:low_vis | brier | 0.060 | 4056 |
| calibration | cancellation | KDFW | all | logistic | weather:low_vis | average_precision | 0.105 | 4056 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:not_low_vis | brier | 0.012 [0.008, 0.016] | 644644 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:not_low_vis | average_precision | 0.014 | 644644 |
| calibration | cancellation | KDFW | all | logistic | weather:not_low_vis | brier | 0.012 [0.008, 0.017] | 644644 |
| calibration | cancellation | KDFW | all | logistic | weather:not_low_vis | average_precision | 0.012 | 644644 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:not_strong_crosswind | brier | 0.012 [0.008, 0.017] | 648624 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:not_strong_crosswind | average_precision | 0.014 | 648624 |
| calibration | cancellation | KDFW | all | logistic | weather:not_strong_crosswind | brier | 0.012 [0.008, 0.017] | 648624 |
| calibration | cancellation | KDFW | all | logistic | weather:not_strong_crosswind | average_precision | 0.012 | 648624 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:strong_crosswind | brier | 0.154 | 76 |
| calibration | cancellation | KDFW | all | conditional_rate | weather:strong_crosswind | average_precision | 0.158 | 76 |
| calibration | cancellation | KDFW | all | logistic | weather:strong_crosswind | brier | 0.158 | 76 |
| calibration | cancellation | KDFW | all | logistic | weather:strong_crosswind | average_precision | 0.158 | 76 |
| calibration | cancellation | pooled | all | conditional_rate | weather:not_thunderstorm | brier | 0.013 [0.008, 0.019] | 1324588 |
| calibration | cancellation | pooled | all | conditional_rate | weather:not_thunderstorm | average_precision | 0.013 | 1324588 |
| calibration | cancellation | pooled | all | logistic | weather:not_thunderstorm | brier | 0.013 [0.008, 0.019] | 1324588 |
| calibration | cancellation | pooled | all | logistic | weather:not_thunderstorm | average_precision | 0.015 | 1324588 |
| calibration | cancellation | pooled | all | conditional_rate | weather:thunderstorm | brier | 0.063 [0.026, 0.107] | 22684 |
| calibration | cancellation | pooled | all | conditional_rate | weather:thunderstorm | average_precision | 0.142 | 22684 |
| calibration | cancellation | pooled | all | logistic | weather:thunderstorm | brier | 0.065 [0.026, 0.109] | 22684 |
| calibration | cancellation | pooled | all | logistic | weather:thunderstorm | average_precision | 0.051 | 22684 |
| calibration | cancellation | pooled | all | conditional_rate | weather:thunderstorm_unknown | brier | 0.001 | 56 |
| calibration | cancellation | pooled | all | conditional_rate | weather:thunderstorm_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | pooled | all | logistic | weather:thunderstorm_unknown | brier | 0.000 | 56 |
| calibration | cancellation | pooled | all | logistic | weather:thunderstorm_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | pooled | all | conditional_rate | weather:ifr | brier | 0.026 [0.012, 0.041] | 93912 |
| calibration | cancellation | pooled | all | conditional_rate | weather:ifr | average_precision | 0.039 | 93912 |
| calibration | cancellation | pooled | all | logistic | weather:ifr | brier | 0.027 [0.012, 0.042] | 93912 |
| calibration | cancellation | pooled | all | logistic | weather:ifr | average_precision | 0.040 | 93912 |
| calibration | cancellation | pooled | all | conditional_rate | weather:ifr_unknown | brier | 0.001 | 56 |
| calibration | cancellation | pooled | all | conditional_rate | weather:ifr_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | pooled | all | logistic | weather:ifr_unknown | brier | 0.000 | 56 |
| calibration | cancellation | pooled | all | logistic | weather:ifr_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | pooled | all | conditional_rate | weather:not_ifr | brier | 0.013 [0.008, 0.019] | 1253360 |
| calibration | cancellation | pooled | all | conditional_rate | weather:not_ifr | average_precision | 0.014 | 1253360 |
| calibration | cancellation | pooled | all | logistic | weather:not_ifr | brier | 0.013 [0.008, 0.019] | 1253360 |
| calibration | cancellation | pooled | all | logistic | weather:not_ifr | average_precision | 0.015 | 1253360 |
| calibration | cancellation | pooled | all | conditional_rate | weather:low_vis | brier | 0.023 [0.009, 0.044] | 17616 |
| calibration | cancellation | pooled | all | conditional_rate | weather:low_vis | average_precision | 0.143 | 17616 |
| calibration | cancellation | pooled | all | logistic | weather:low_vis | brier | 0.024 [0.009, 0.046] | 17616 |
| calibration | cancellation | pooled | all | logistic | weather:low_vis | average_precision | 0.045 | 17616 |
| calibration | cancellation | pooled | all | conditional_rate | weather:low_vis_unknown | brier | 0.001 | 56 |
| calibration | cancellation | pooled | all | conditional_rate | weather:low_vis_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | pooled | all | logistic | weather:low_vis_unknown | brier | 0.000 | 56 |
| calibration | cancellation | pooled | all | logistic | weather:low_vis_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | pooled | all | conditional_rate | weather:not_low_vis | brier | 0.013 [0.008, 0.019] | 1329656 |
| calibration | cancellation | pooled | all | conditional_rate | weather:not_low_vis | average_precision | 0.014 | 1329656 |
| calibration | cancellation | pooled | all | logistic | weather:not_low_vis | brier | 0.013 [0.008, 0.019] | 1329656 |
| calibration | cancellation | pooled | all | logistic | weather:not_low_vis | average_precision | 0.016 | 1329656 |
| calibration | cancellation | pooled | all | conditional_rate | weather:not_strong_crosswind | brier | 0.014 [0.009, 0.020] | 1346708 |
| calibration | cancellation | pooled | all | conditional_rate | weather:not_strong_crosswind | average_precision | 0.015 | 1346708 |
| calibration | cancellation | pooled | all | logistic | weather:not_strong_crosswind | brier | 0.014 [0.009, 0.020] | 1346708 |
| calibration | cancellation | pooled | all | logistic | weather:not_strong_crosswind | average_precision | 0.016 | 1346708 |
| calibration | cancellation | pooled | all | conditional_rate | weather:strong_crosswind | brier | 0.021 | 564 |
| calibration | cancellation | pooled | all | conditional_rate | weather:strong_crosswind | average_precision | 0.039 | 564 |
| calibration | cancellation | pooled | all | logistic | weather:strong_crosswind | brier | 0.021 | 564 |
| calibration | cancellation | pooled | all | logistic | weather:strong_crosswind | average_precision | 0.021 | 564 |
| calibration | cancellation | pooled | all | conditional_rate | weather:strong_crosswind_unknown | brier | 0.001 | 56 |
| calibration | cancellation | pooled | all | conditional_rate | weather:strong_crosswind_unknown | average_precision | n/a (single_class) | 56 |
| calibration | cancellation | pooled | all | logistic | weather:strong_crosswind_unknown | brier | 0.000 | 56 |
| calibration | cancellation | pooled | all | logistic | weather:strong_crosswind_unknown | average_precision | n/a (single_class) | 56 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_thunderstorm | brier | 0.076 [0.067, 0.087] | 673840 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_thunderstorm | average_precision | 0.115 | 673840 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:not_thunderstorm | brier | 0.074 [0.066, 0.084] | 673840 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:not_thunderstorm | average_precision | 0.189 | 673840 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_thunderstorm | brier | 0.073 [0.065, 0.083] | 673840 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_thunderstorm | average_precision | 0.220 | 673840 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:thunderstorm | brier | 0.254 [0.201, 0.311] | 14052 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:thunderstorm | average_precision | 0.431 | 14052 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:thunderstorm | brier | 0.238 [0.188, 0.291] | 14052 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:thunderstorm | average_precision | 0.397 | 14052 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:thunderstorm | brier | 0.231 [0.183, 0.283] | 14052 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:thunderstorm | average_precision | 0.378 | 14052 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:thunderstorm_unknown | brier | 0.123 | 56 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:thunderstorm_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:thunderstorm_unknown | brier | 0.122 | 56 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:thunderstorm_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:thunderstorm_unknown | brier | 0.124 | 56 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:thunderstorm_unknown | average_precision | 0.130 | 56 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:ifr | brier | 0.109 [0.078, 0.145] | 63480 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:ifr | average_precision | 0.240 | 63480 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:ifr | brier | 0.109 [0.076, 0.148] | 63480 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:ifr | average_precision | 0.309 | 63480 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:ifr | brier | 0.106 [0.075, 0.144] | 63480 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:ifr | average_precision | 0.318 | 63480 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:ifr_unknown | brier | 0.123 | 56 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:ifr_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:ifr_unknown | brier | 0.122 | 56 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:ifr_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:ifr_unknown | brier | 0.124 | 56 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:ifr_unknown | average_precision | 0.130 | 56 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_ifr | brier | 0.077 [0.067, 0.087] | 624412 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_ifr | average_precision | 0.115 | 624412 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:not_ifr | brier | 0.074 [0.066, 0.084] | 624412 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:not_ifr | average_precision | 0.197 | 624412 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_ifr | brier | 0.073 [0.065, 0.082] | 624412 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_ifr | average_precision | 0.226 | 624412 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:low_vis | brier | 0.163 [0.080, 0.215] | 13388 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:low_vis | average_precision | 0.338 | 13388 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:low_vis | brier | 0.171 [0.077, 0.229] | 13388 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:low_vis | average_precision | 0.400 | 13388 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:low_vis | brier | 0.166 [0.074, 0.223] | 13388 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:low_vis | average_precision | 0.357 | 13388 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:low_vis_unknown | brier | 0.123 | 56 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:low_vis_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:low_vis_unknown | brier | 0.122 | 56 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:low_vis_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:low_vis_unknown | brier | 0.124 | 56 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:low_vis_unknown | average_precision | 0.130 | 56 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_low_vis | brier | 0.078 [0.069, 0.088] | 674504 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_low_vis | average_precision | 0.119 | 674504 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:not_low_vis | brier | 0.076 [0.067, 0.085] | 674504 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:not_low_vis | average_precision | 0.203 | 674504 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_low_vis | brier | 0.074 [0.066, 0.083] | 674504 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_low_vis | average_precision | 0.233 | 674504 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_strong_crosswind | brier | 0.080 [0.070, 0.091] | 687404 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_strong_crosswind | average_precision | 0.122 | 687404 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:not_strong_crosswind | brier | 0.077 [0.068, 0.088] | 687404 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:not_strong_crosswind | average_precision | 0.203 | 687404 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_strong_crosswind | brier | 0.076 [0.067, 0.086] | 687404 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_strong_crosswind | average_precision | 0.233 | 687404 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:strong_crosswind | brier | 0.273 | 488 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:strong_crosswind | average_precision | 0.581 | 488 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:strong_crosswind | brier | 0.246 | 488 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:strong_crosswind | average_precision | 0.581 | 488 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:strong_crosswind | brier | 0.240 | 488 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:strong_crosswind | average_precision | 0.374 | 488 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:strong_crosswind_unknown | brier | 0.123 | 56 |
| calibration | departure_delay_gt45 | KATL | all | conditional_rate | weather:strong_crosswind_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:strong_crosswind_unknown | brier | 0.122 | 56 |
| calibration | departure_delay_gt45 | KATL | all | logistic | weather:strong_crosswind_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:strong_crosswind_unknown | brier | 0.124 | 56 |
| calibration | departure_delay_gt45 | KATL | all | lgbm_delay | weather:strong_crosswind_unknown | average_precision | 0.130 | 56 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_thunderstorm | brier | 0.101 [0.094, 0.109] | 633748 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_thunderstorm | average_precision | 0.155 | 633748 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:not_thunderstorm | brier | 0.100 [0.093, 0.107] | 633748 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:not_thunderstorm | average_precision | 0.206 | 633748 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_thunderstorm | brier | 0.099 [0.092, 0.106] | 633748 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_thunderstorm | average_precision | 0.213 | 633748 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:thunderstorm | brier | 0.358 | 7156 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:thunderstorm | average_precision | 0.462 | 7156 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:thunderstorm | brier | 0.386 | 7156 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:thunderstorm | average_precision | 0.350 | 7156 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:thunderstorm | brier | 0.367 | 7156 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:thunderstorm | average_precision | 0.401 | 7156 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:ifr | brier | 0.140 [0.101, 0.200] | 27928 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:ifr | average_precision | 0.219 | 27928 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:ifr | brier | 0.148 [0.104, 0.216] | 27928 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:ifr | average_precision | 0.209 | 27928 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:ifr | brier | 0.143 [0.102, 0.205] | 27928 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:ifr | average_precision | 0.245 | 27928 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_ifr | brier | 0.102 [0.094, 0.111] | 612976 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_ifr | average_precision | 0.156 | 612976 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:not_ifr | brier | 0.101 [0.093, 0.109] | 612976 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:not_ifr | average_precision | 0.208 | 612976 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_ifr | brier | 0.100 [0.093, 0.108] | 612976 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_ifr | average_precision | 0.215 | 612976 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:low_vis | brier | 0.190 | 3812 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:low_vis | average_precision | 0.616 | 3812 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:low_vis | brier | 0.206 | 3812 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:low_vis | average_precision | 0.459 | 3812 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:low_vis | brier | 0.197 | 3812 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:low_vis | average_precision | 0.572 | 3812 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_low_vis | brier | 0.104 [0.095, 0.112] | 637092 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_low_vis | average_precision | 0.156 | 637092 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:not_low_vis | brier | 0.102 [0.094, 0.111] | 637092 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:not_low_vis | average_precision | 0.205 | 637092 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_low_vis | brier | 0.101 [0.094, 0.110] | 637092 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_low_vis | average_precision | 0.213 | 637092 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_strong_crosswind | brier | 0.104 [0.096, 0.113] | 640840 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_strong_crosswind | average_precision | 0.157 | 640840 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:not_strong_crosswind | brier | 0.103 [0.095, 0.111] | 640840 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:not_strong_crosswind | average_precision | 0.205 | 640840 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_strong_crosswind | brier | 0.102 [0.094, 0.110] | 640840 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_strong_crosswind | average_precision | 0.213 | 640840 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:strong_crosswind | brier | 0.112 | 64 |
| calibration | departure_delay_gt45 | KDFW | all | conditional_rate | weather:strong_crosswind | average_precision | 0.125 | 64 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:strong_crosswind | brier | 0.118 | 64 |
| calibration | departure_delay_gt45 | KDFW | all | logistic | weather:strong_crosswind | average_precision | 0.125 | 64 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:strong_crosswind | brier | 0.114 | 64 |
| calibration | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:strong_crosswind | average_precision | 0.142 | 64 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_thunderstorm | brier | 0.088 [0.081, 0.097] | 1307588 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_thunderstorm | average_precision | 0.143 | 1307588 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:not_thunderstorm | brier | 0.086 [0.079, 0.095] | 1307588 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:not_thunderstorm | average_precision | 0.195 | 1307588 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_thunderstorm | brier | 0.086 [0.078, 0.094] | 1307588 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_thunderstorm | average_precision | 0.212 | 1307588 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:thunderstorm | brier | 0.289 [0.232, 0.350] | 21208 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:thunderstorm | average_precision | 0.424 | 21208 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:thunderstorm | brier | 0.288 [0.223, 0.359] | 21208 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:thunderstorm | average_precision | 0.363 | 21208 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:thunderstorm | brier | 0.277 [0.216, 0.342] | 21208 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:thunderstorm | average_precision | 0.364 | 21208 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:thunderstorm_unknown | brier | 0.123 | 56 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:thunderstorm_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:thunderstorm_unknown | brier | 0.122 | 56 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:thunderstorm_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:thunderstorm_unknown | brier | 0.124 | 56 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:thunderstorm_unknown | average_precision | 0.130 | 56 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:ifr | brier | 0.118 [0.092, 0.151] | 91408 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:ifr | average_precision | 0.224 | 91408 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:ifr | brier | 0.121 [0.093, 0.156] | 91408 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:ifr | average_precision | 0.278 | 91408 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:ifr | brier | 0.117 [0.091, 0.150] | 91408 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:ifr | average_precision | 0.288 | 91408 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:ifr_unknown | brier | 0.123 | 56 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:ifr_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:ifr_unknown | brier | 0.122 | 56 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:ifr_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:ifr_unknown | brier | 0.124 | 56 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:ifr_unknown | average_precision | 0.130 | 56 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_ifr | brier | 0.090 [0.081, 0.099] | 1237388 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_ifr | average_precision | 0.144 | 1237388 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:not_ifr | brier | 0.087 [0.080, 0.096] | 1237388 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:not_ifr | average_precision | 0.200 | 1237388 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_ifr | brier | 0.086 [0.079, 0.095] | 1237388 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_ifr | average_precision | 0.217 | 1237388 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:low_vis | brier | 0.169 [0.108, 0.222] | 17200 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:low_vis | average_precision | 0.420 | 17200 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:low_vis | brier | 0.178 [0.110, 0.240] | 17200 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:low_vis | average_precision | 0.417 | 17200 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:low_vis | brier | 0.173 [0.106, 0.231] | 17200 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:low_vis | average_precision | 0.397 | 17200 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:low_vis_unknown | brier | 0.123 | 56 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:low_vis_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:low_vis_unknown | brier | 0.122 | 56 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:low_vis_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:low_vis_unknown | brier | 0.124 | 56 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:low_vis_unknown | average_precision | 0.130 | 56 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_low_vis | brier | 0.090 [0.083, 0.100] | 1311596 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_low_vis | average_precision | 0.145 | 1311596 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:not_low_vis | brier | 0.088 [0.081, 0.097] | 1311596 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:not_low_vis | average_precision | 0.200 | 1311596 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_low_vis | brier | 0.087 [0.080, 0.096] | 1311596 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_low_vis | average_precision | 0.218 | 1311596 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_strong_crosswind | brier | 0.091 [0.083, 0.101] | 1328244 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_strong_crosswind | average_precision | 0.146 | 1328244 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:not_strong_crosswind | brier | 0.090 [0.082, 0.098] | 1328244 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:not_strong_crosswind | average_precision | 0.199 | 1328244 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_strong_crosswind | brier | 0.089 [0.081, 0.097] | 1328244 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_strong_crosswind | average_precision | 0.219 | 1328244 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:strong_crosswind | brier | 0.254 | 552 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:strong_crosswind | average_precision | 0.569 | 552 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:strong_crosswind | brier | 0.231 | 552 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:strong_crosswind | average_precision | 0.569 | 552 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:strong_crosswind | brier | 0.226 | 552 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:strong_crosswind | average_precision | 0.372 | 552 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:strong_crosswind_unknown | brier | 0.123 | 56 |
| calibration | departure_delay_gt45 | pooled | all | conditional_rate | weather:strong_crosswind_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:strong_crosswind_unknown | brier | 0.122 | 56 |
| calibration | departure_delay_gt45 | pooled | all | logistic | weather:strong_crosswind_unknown | average_precision | 0.143 | 56 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:strong_crosswind_unknown | brier | 0.124 | 56 |
| calibration | departure_delay_gt45 | pooled | all | lgbm_delay | weather:strong_crosswind_unknown | average_precision | 0.130 | 56 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_thunderstorm | rmse | 8.621 [8.016, 9.343] | 17365 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_thunderstorm | mae | 5.862 [5.577, 6.201] | 17365 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_thunderstorm | rmse | 39.244 [38.767, 39.673] | 17365 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_thunderstorm | mae | 33.440 [32.954, 33.861] | 17365 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_thunderstorm | rmse | 8.279 [7.605, 9.025] | 17365 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_thunderstorm | mae | 5.820 [5.529, 6.160] | 17365 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_thunderstorm | rmse | 10.491 [9.570, 11.533] | 17365 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_thunderstorm | mae | 6.406 [5.903, 7.012] | 17365 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_thunderstorm | rmse | 6.712 [5.916, 7.662] | 17365 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_thunderstorm | mae | 4.323 [4.015, 4.709] | 17365 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:thunderstorm | rmse | 15.905 [12.847, 19.015] | 271 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:thunderstorm | mae | 12.197 [9.822, 15.004] | 271 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:thunderstorm | rmse | 29.821 [27.462, 32.052] | 271 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:thunderstorm | mae | 24.723 [22.472, 27.009] | 271 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:thunderstorm | rmse | 16.376 [13.855, 18.910] | 271 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:thunderstorm | mae | 12.400 [10.093, 14.702] | 271 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:thunderstorm | rmse | 17.513 [14.413, 20.503] | 271 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:thunderstorm | mae | 13.779 [11.269, 16.812] | 271 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:thunderstorm | rmse | 15.073 [12.552, 17.799] | 271 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:thunderstorm | mae | 11.313 [9.287, 13.645] | 271 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:thunderstorm_unknown | rmse | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:thunderstorm_unknown | mae | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:thunderstorm_unknown | rmse | 39.010 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:thunderstorm_unknown | mae | 36.250 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:thunderstorm_unknown | rmse | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:thunderstorm_unknown | mae | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:thunderstorm_unknown | rmse | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:thunderstorm_unknown | mae | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:thunderstorm_unknown | rmse | 0.428 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:thunderstorm_unknown | mae | 0.395 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:ifr | rmse | 10.155 [8.668, 11.654] | 1740 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:ifr | mae | 6.926 [6.081, 7.844] | 1740 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:ifr | rmse | 38.820 [37.359, 40.231] | 1740 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:ifr | mae | 32.934 [31.416, 34.494] | 1740 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:ifr | rmse | 10.402 [8.596, 12.137] | 1740 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:ifr | mae | 6.963 [5.992, 8.061] | 1740 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:ifr | rmse | 13.199 [10.397, 15.864] | 1740 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:ifr | mae | 8.023 [6.598, 9.639] | 1740 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:ifr | rmse | 9.556 [7.675, 11.422] | 1740 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:ifr | mae | 5.952 [4.910, 7.139] | 1740 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:ifr_unknown | rmse | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:ifr_unknown | mae | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:ifr_unknown | rmse | 39.010 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:ifr_unknown | mae | 36.250 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:ifr_unknown | rmse | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:ifr_unknown | mae | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:ifr_unknown | rmse | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:ifr_unknown | mae | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:ifr_unknown | rmse | 0.428 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:ifr_unknown | mae | 0.395 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_ifr | rmse | 8.615 [7.932, 9.359] | 15896 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_ifr | mae | 5.854 [5.529, 6.212] | 15896 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_ifr | rmse | 39.149 [38.654, 39.597] | 15896 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_ifr | mae | 33.347 [32.863, 33.771] | 15896 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_ifr | rmse | 8.222 [7.525, 9.039] | 15896 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_ifr | mae | 5.807 [5.493, 6.181] | 15896 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_ifr | rmse | 10.314 [9.447, 11.212] | 15896 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_ifr | mae | 6.354 [5.856, 6.879] | 15896 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_ifr | rmse | 6.564 [5.693, 7.535] | 15896 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_ifr | mae | 4.263 [3.924, 4.650] | 15896 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:low_vis | rmse | 12.084 [9.324, 13.946] | 400 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:low_vis | mae | 8.379 [6.480, 9.912] | 400 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:low_vis | rmse | 36.773 [33.774, 40.978] | 400 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:low_vis | mae | 30.508 [27.646, 34.976] | 400 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:low_vis | rmse | 12.887 [9.204, 14.936] | 400 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:low_vis | mae | 8.884 [6.800, 10.429] | 400 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:low_vis | rmse | 13.160 [10.049, 15.134] | 400 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:low_vis | mae | 8.710 [6.434, 10.426] | 400 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:low_vis | rmse | 11.823 [7.770, 14.017] | 400 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:low_vis | mae | 7.813 [5.257, 9.622] | 400 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:low_vis_unknown | rmse | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:low_vis_unknown | mae | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:low_vis_unknown | rmse | 39.010 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:low_vis_unknown | mae | 36.250 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:low_vis_unknown | rmse | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:low_vis_unknown | mae | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:low_vis_unknown | rmse | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:low_vis_unknown | mae | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:low_vis_unknown | rmse | 0.428 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:low_vis_unknown | mae | 0.395 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_low_vis | rmse | 8.687 [7.997, 9.422] | 17236 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_low_vis | mae | 5.904 [5.575, 6.259] | 17236 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_low_vis | rmse | 39.169 [38.696, 39.577] | 17236 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_low_vis | mae | 33.371 [32.895, 33.766] | 17236 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_low_vis | rmse | 8.332 [7.634, 9.143] | 17236 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_low_vis | mae | 5.853 [5.535, 6.216] | 17236 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_low_vis | rmse | 10.568 [9.652, 11.515] | 17236 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_low_vis | mae | 6.468 [5.934, 7.030] | 17236 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_low_vis | rmse | 6.761 [5.879, 7.744] | 17236 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_low_vis | mae | 4.351 [3.999, 4.753] | 17236 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_strong_crosswind | rmse | 8.758 [8.133, 9.468] | 17628 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_strong_crosswind | mae | 5.949 [5.638, 6.300] | 17628 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_strong_crosswind | rmse | 39.121 [38.628, 39.575] | 17628 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_strong_crosswind | mae | 33.311 [32.806, 33.750] | 17628 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_strong_crosswind | rmse | 8.438 [7.760, 9.209] | 17628 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_strong_crosswind | mae | 5.910 [5.603, 6.275] | 17628 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_strong_crosswind | rmse | 10.608 [9.706, 11.630] | 17628 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_strong_crosswind | mae | 6.508 [5.995, 7.109] | 17628 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_strong_crosswind | rmse | 6.889 [6.072, 7.847] | 17628 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_strong_crosswind | mae | 4.419 [4.095, 4.830] | 17628 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:strong_crosswind | rmse | 29.777 | 8 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:strong_crosswind | mae | 28.893 | 8 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:strong_crosswind | rmse | 26.053 | 8 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:strong_crosswind | mae | 23.000 | 8 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:strong_crosswind | rmse | 31.576 | 8 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:strong_crosswind | mae | 31.503 | 8 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:strong_crosswind | rmse | 36.056 | 8 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:strong_crosswind | mae | 30.000 | 8 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:strong_crosswind | rmse | 29.717 | 8 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:strong_crosswind | mae | 29.009 | 8 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:strong_crosswind_unknown | rmse | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | climatology | weather:strong_crosswind_unknown | mae | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:strong_crosswind_unknown | rmse | 39.010 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | persistence | weather:strong_crosswind_unknown | mae | 36.250 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:strong_crosswind_unknown | rmse | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | schedule | weather:strong_crosswind_unknown | mae | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:strong_crosswind_unknown | rmse | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:strong_crosswind_unknown | mae | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:strong_crosswind_unknown | rmse | 0.428 | 4 |
| calibration | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:strong_crosswind_unknown | mae | 0.395 | 4 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_thunderstorm | rmse | 12.913 [12.525, 13.358] | 17330 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_thunderstorm | mae | 9.280 [9.016, 9.574] | 17330 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_thunderstorm | rmse | 37.733 [37.304, 38.144] | 17330 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_thunderstorm | mae | 31.735 [31.326, 32.124] | 17330 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_thunderstorm | rmse | 12.838 [12.469, 13.194] | 17330 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_thunderstorm | mae | 9.739 [9.502, 9.988] | 17330 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_thunderstorm | rmse | 11.139 [10.179, 12.188] | 17330 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_thunderstorm | mae | 6.658 [6.174, 7.214] | 17330 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_thunderstorm | rmse | 8.901 [8.441, 9.386] | 17330 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_thunderstorm | mae | 5.821 [5.560, 6.088] | 17330 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:thunderstorm | rmse | 24.018 [16.042, 30.166] | 206 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:thunderstorm | mae | 15.812 [9.365, 22.368] | 206 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:thunderstorm | rmse | 33.392 [30.057, 36.972] | 206 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:thunderstorm | mae | 26.820 [23.592, 30.288] | 206 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:thunderstorm | rmse | 22.608 [14.693, 28.447] | 206 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:thunderstorm | mae | 15.777 [9.542, 21.720] | 206 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:thunderstorm | rmse | 28.884 [20.123, 36.230] | 206 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:thunderstorm | mae | 19.689 [12.686, 27.002] | 206 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:thunderstorm | rmse | 22.153 [14.703, 28.089] | 206 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:thunderstorm | mae | 14.702 [8.410, 20.881] | 206 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:ifr | rmse | 16.225 [12.903, 19.378] | 813 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:ifr | mae | 11.148 [9.060, 13.453] | 813 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:ifr | rmse | 35.949 [34.370, 37.816] | 813 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:ifr | mae | 30.374 [28.778, 32.160] | 813 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:ifr | rmse | 15.648 [12.896, 18.328] | 813 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:ifr | mae | 11.589 [9.695, 13.679] | 813 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:ifr | rmse | 18.434 [14.413, 22.335] | 813 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:ifr | mae | 11.121 [8.770, 14.004] | 813 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:ifr | rmse | 14.108 [11.019, 17.145] | 813 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:ifr | mae | 9.170 [7.314, 11.397] | 813 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_ifr | rmse | 12.927 [12.516, 13.384] | 16723 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_ifr | mae | 9.269 [9.009, 9.567] | 16723 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_ifr | rmse | 37.767 [37.327, 38.171] | 16723 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_ifr | mae | 31.741 [31.334, 32.123] | 16723 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_ifr | rmse | 12.853 [12.473, 13.231] | 16723 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_ifr | mae | 9.723 [9.475, 9.977] | 16723 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_ifr | rmse | 11.061 [10.036, 12.163] | 16723 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_ifr | mae | 6.602 [6.116, 7.169] | 16723 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_ifr | rmse | 8.858 [8.379, 9.388] | 16723 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_ifr | mae | 5.767 [5.498, 6.039] | 16723 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:low_vis | rmse | 22.343 | 88 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:low_vis | mae | 16.031 | 88 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:low_vis | rmse | 35.936 | 88 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:low_vis | mae | 29.864 | 88 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:low_vis | rmse | 20.887 | 88 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:low_vis | mae | 15.857 | 88 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:low_vis | rmse | 23.550 | 88 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:low_vis | mae | 14.136 | 88 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:low_vis | rmse | 21.458 | 88 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:low_vis | mae | 15.292 | 88 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_low_vis | rmse | 13.035 [12.583, 13.531] | 17448 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_low_vis | mae | 9.323 [9.042, 9.638] | 17448 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_low_vis | rmse | 37.693 [37.262, 38.103] | 17448 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_low_vis | mae | 31.686 [31.287, 32.083] | 17448 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_low_vis | rmse | 12.944 [12.522, 13.361] | 17448 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_low_vis | mae | 9.779 [9.515, 10.059] | 17448 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_low_vis | rmse | 11.415 [10.414, 12.489] | 17448 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_low_vis | mae | 6.775 [6.277, 7.373] | 17448 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_low_vis | rmse | 9.064 [8.513, 9.642] | 17448 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_low_vis | mae | 5.878 [5.583, 6.182] | 17448 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_strong_crosswind | rmse | 13.096 [12.616, 13.606] | 17524 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_strong_crosswind | mae | 9.356 [9.064, 9.686] | 17524 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_strong_crosswind | rmse | 37.685 [37.254, 38.099] | 17524 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_strong_crosswind | mae | 31.679 [31.276, 32.072] | 17524 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_strong_crosswind | rmse | 12.991 [12.552, 13.430] | 17524 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_strong_crosswind | mae | 9.805 [9.531, 10.098] | 17524 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_strong_crosswind | rmse | 11.511 [10.487, 12.561] | 17524 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_strong_crosswind | mae | 6.815 [6.316, 7.413] | 17524 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_strong_crosswind | rmse | 9.167 [8.565, 9.817] | 17524 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_strong_crosswind | mae | 5.924 [5.617, 6.254] | 17524 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:strong_crosswind | rmse | 16.191 | 12 |
| calibration | reporting_carrier_touchdowns | KDFW | all | climatology | weather:strong_crosswind | mae | 9.577 | 12 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:strong_crosswind | rmse | 37.135 | 12 |
| calibration | reporting_carrier_touchdowns | KDFW | all | persistence | weather:strong_crosswind | mae | 29.333 | 12 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:strong_crosswind | rmse | 18.496 | 12 |
| calibration | reporting_carrier_touchdowns | KDFW | all | schedule | weather:strong_crosswind | mae | 15.870 | 12 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:strong_crosswind | rmse | 1.826 | 12 |
| calibration | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:strong_crosswind | mae | 1.333 | 12 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:strong_crosswind | rmse | 11.381 | 12 |
| calibration | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:strong_crosswind | mae | 6.869 | 12 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_thunderstorm | rmse | 10.977 [10.626, 11.403] | 34695 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_thunderstorm | mae | 7.569 [7.361, 7.808] | 34695 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_thunderstorm | rmse | 38.497 [38.072, 38.887] | 34695 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_thunderstorm | mae | 32.588 [32.198, 32.958] | 34695 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_thunderstorm | rmse | 10.800 [10.471, 11.121] | 34695 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_thunderstorm | mae | 7.777 [7.600, 7.956] | 34695 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_thunderstorm | rmse | 10.820 [10.047, 11.711] | 34695 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_thunderstorm | mae | 6.532 [6.133, 7.024] | 34695 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_thunderstorm | rmse | 7.881 [7.438, 8.370] | 34695 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_thunderstorm | mae | 5.071 [4.854, 5.309] | 34695 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:thunderstorm | rmse | 19.821 [15.499, 23.577] | 477 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:thunderstorm | mae | 13.758 [10.516, 16.914] | 477 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:thunderstorm | rmse | 31.413 [29.660, 33.236] | 477 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:thunderstorm | mae | 25.629 [23.803, 27.483] | 477 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:thunderstorm | rmse | 19.316 [15.205, 22.742] | 477 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:thunderstorm | mae | 13.859 [10.827, 16.921] | 477 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:thunderstorm | rmse | 23.120 [17.830, 27.647] | 477 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:thunderstorm | mae | 16.331 [12.786, 19.996] | 477 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:thunderstorm | rmse | 18.466 [14.258, 21.832] | 477 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:thunderstorm | mae | 12.777 [9.711, 15.754] | 477 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:thunderstorm_unknown | rmse | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:thunderstorm_unknown | mae | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:thunderstorm_unknown | rmse | 39.010 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:thunderstorm_unknown | mae | 36.250 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:thunderstorm_unknown | rmse | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:thunderstorm_unknown | mae | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:thunderstorm_unknown | rmse | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:thunderstorm_unknown | mae | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:thunderstorm_unknown | rmse | 0.428 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:thunderstorm_unknown | mae | 0.395 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:ifr | rmse | 12.414 [10.823, 14.032] | 2553 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:ifr | mae | 8.270 [7.345, 9.262] | 2553 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:ifr | rmse | 37.929 [36.788, 39.205] | 2553 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:ifr | mae | 32.119 [30.929, 33.448] | 2553 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:ifr | rmse | 12.317 [10.805, 13.719] | 2553 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:ifr | mae | 8.436 [7.468, 9.339] | 2553 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:ifr | rmse | 15.065 [12.649, 17.281] | 2553 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:ifr | mae | 9.009 [7.656, 10.437] | 2553 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:ifr | rmse | 11.208 [9.543, 12.776] | 2553 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:ifr | mae | 6.977 [6.018, 7.957] | 2553 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:ifr_unknown | rmse | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:ifr_unknown | mae | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:ifr_unknown | rmse | 39.010 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:ifr_unknown | mae | 36.250 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:ifr_unknown | rmse | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:ifr_unknown | mae | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:ifr_unknown | rmse | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:ifr_unknown | mae | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:ifr_unknown | rmse | 0.428 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:ifr_unknown | mae | 0.395 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_ifr | rmse | 11.038 [10.647, 11.487] | 32619 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_ifr | mae | 7.605 [7.375, 7.865] | 32619 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_ifr | rmse | 38.447 [38.021, 38.849] | 32619 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_ifr | mae | 32.523 [32.115, 32.902] | 32619 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_ifr | rmse | 10.846 [10.526, 11.167] | 32619 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_ifr | mae | 7.815 [7.622, 7.996] | 32619 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_ifr | rmse | 10.704 [9.899, 11.602] | 32619 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_ifr | mae | 6.481 [6.047, 6.988] | 32619 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_ifr | rmse | 7.825 [7.380, 8.313] | 32619 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_ifr | mae | 5.034 [4.818, 5.271] | 32619 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:low_vis | rmse | 14.482 [11.189, 17.925] | 488 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:low_vis | mae | 9.759 [7.687, 12.065] | 488 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:low_vis | rmse | 36.623 [33.650, 40.185] | 488 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:low_vis | mae | 30.391 [27.367, 34.294] | 488 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:low_vis | rmse | 14.656 [11.558, 17.016] | 488 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:low_vis | mae | 10.141 [8.106, 11.974] | 488 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:low_vis | rmse | 15.555 [10.975, 19.956] | 488 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:low_vis | mae | 9.689 [6.956, 12.210] | 488 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:low_vis | rmse | 14.057 [10.326, 16.991] | 488 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:low_vis | mae | 9.161 [6.822, 11.175] | 488 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:low_vis_unknown | rmse | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:low_vis_unknown | mae | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:low_vis_unknown | rmse | 39.010 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:low_vis_unknown | mae | 36.250 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:low_vis_unknown | rmse | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:low_vis_unknown | mae | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:low_vis_unknown | rmse | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:low_vis_unknown | mae | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:low_vis_unknown | rmse | 0.428 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:low_vis_unknown | mae | 0.395 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_low_vis | rmse | 11.090 [10.722, 11.512] | 34684 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_low_vis | mae | 7.624 [7.410, 7.859] | 34684 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_low_vis | rmse | 38.434 [38.013, 38.825] | 34684 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_low_vis | mae | 32.524 [32.118, 32.899] | 34684 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_low_vis | rmse | 10.899 [10.566, 11.231] | 34684 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_low_vis | mae | 7.828 [7.644, 8.017] | 34684 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_low_vis | rmse | 11.002 [10.186, 11.905] | 34684 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_low_vis | mae | 6.622 [6.173, 7.115] | 34684 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_low_vis | rmse | 8.003 [7.522, 8.530] | 34684 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_low_vis | mae | 5.119 [4.888, 5.371] | 34684 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_strong_crosswind | rmse | 11.134 [10.755, 11.572] | 35152 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_strong_crosswind | mae | 7.648 [7.429, 7.900] | 35152 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_strong_crosswind | rmse | 38.412 [37.981, 38.818] | 35152 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_strong_crosswind | mae | 32.497 [32.097, 32.877] | 35152 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_strong_crosswind | rmse | 10.947 [10.598, 11.304] | 35152 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_strong_crosswind | mae | 7.852 [7.660, 8.046] | 35152 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_strong_crosswind | rmse | 11.068 [10.260, 11.969] | 35152 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_strong_crosswind | mae | 6.661 [6.236, 7.161] | 35152 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_strong_crosswind | rmse | 8.105 [7.593, 8.641] | 35152 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_strong_crosswind | mae | 5.169 [4.932, 5.432] | 35152 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:strong_crosswind | rmse | 22.626 | 20 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:strong_crosswind | mae | 17.303 | 20 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:strong_crosswind | rmse | 33.150 | 20 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:strong_crosswind | mae | 26.800 | 20 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:strong_crosswind | rmse | 24.578 | 20 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:strong_crosswind | mae | 22.123 | 20 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:strong_crosswind | rmse | 22.847 | 20 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:strong_crosswind | mae | 12.800 | 20 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:strong_crosswind | rmse | 20.760 | 20 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:strong_crosswind | mae | 15.725 | 20 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:strong_crosswind_unknown | rmse | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | climatology | weather:strong_crosswind_unknown | mae | 2.865 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:strong_crosswind_unknown | rmse | 39.010 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | persistence | weather:strong_crosswind_unknown | mae | 36.250 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:strong_crosswind_unknown | rmse | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | schedule | weather:strong_crosswind_unknown | mae | 4.058 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:strong_crosswind_unknown | rmse | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:strong_crosswind_unknown | mae | 0.000 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:strong_crosswind_unknown | rmse | 0.428 | 4 |
| calibration | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:strong_crosswind_unknown | mae | 0.395 | 4 |
| validation | cancellation | KATL | all | conditional_rate | weather:not_thunderstorm | brier | 0.004 [0.003, 0.006] | 660059 |
| validation | cancellation | KATL | all | conditional_rate | weather:not_thunderstorm | average_precision | 0.005 | 660059 |
| validation | cancellation | KATL | all | logistic | weather:not_thunderstorm | brier | 0.004 [0.003, 0.006] | 660059 |
| validation | cancellation | KATL | all | logistic | weather:not_thunderstorm | average_precision | 0.005 | 660059 |
| validation | cancellation | KATL | all | conditional_rate | weather:thunderstorm | brier | 0.016 [0.003, 0.029] | 7752 |
| validation | cancellation | KATL | all | conditional_rate | weather:thunderstorm | average_precision | 0.055 | 7752 |
| validation | cancellation | KATL | all | logistic | weather:thunderstorm | brier | 0.016 [0.004, 0.029] | 7752 |
| validation | cancellation | KATL | all | logistic | weather:thunderstorm | average_precision | 0.019 | 7752 |
| validation | cancellation | KATL | all | conditional_rate | weather:thunderstorm_unknown | brier | 0.000 | 464 |
| validation | cancellation | KATL | all | conditional_rate | weather:thunderstorm_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | KATL | all | logistic | weather:thunderstorm_unknown | brier | 0.000 | 464 |
| validation | cancellation | KATL | all | logistic | weather:thunderstorm_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | KATL | all | conditional_rate | weather:ifr | brier | 0.007 [0.004, 0.012] | 55908 |
| validation | cancellation | KATL | all | conditional_rate | weather:ifr | average_precision | 0.007 | 55908 |
| validation | cancellation | KATL | all | logistic | weather:ifr | brier | 0.007 [0.004, 0.012] | 55908 |
| validation | cancellation | KATL | all | logistic | weather:ifr | average_precision | 0.012 | 55908 |
| validation | cancellation | KATL | all | conditional_rate | weather:ifr_unknown | brier | 0.000 | 464 |
| validation | cancellation | KATL | all | conditional_rate | weather:ifr_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | KATL | all | logistic | weather:ifr_unknown | brier | 0.000 | 464 |
| validation | cancellation | KATL | all | logistic | weather:ifr_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | KATL | all | conditional_rate | weather:not_ifr | brier | 0.004 [0.003, 0.006] | 611903 |
| validation | cancellation | KATL | all | conditional_rate | weather:not_ifr | average_precision | 0.005 | 611903 |
| validation | cancellation | KATL | all | logistic | weather:not_ifr | brier | 0.004 [0.003, 0.006] | 611903 |
| validation | cancellation | KATL | all | logistic | weather:not_ifr | average_precision | 0.004 | 611903 |
| validation | cancellation | KATL | all | conditional_rate | weather:low_vis | brier | 0.006 [0.001, 0.011] | 12884 |
| validation | cancellation | KATL | all | conditional_rate | weather:low_vis | average_precision | 0.011 | 12884 |
| validation | cancellation | KATL | all | logistic | weather:low_vis | brier | 0.006 [0.001, 0.011] | 12884 |
| validation | cancellation | KATL | all | logistic | weather:low_vis | average_precision | 0.032 | 12884 |
| validation | cancellation | KATL | all | conditional_rate | weather:low_vis_unknown | brier | 0.000 | 464 |
| validation | cancellation | KATL | all | conditional_rate | weather:low_vis_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | KATL | all | logistic | weather:low_vis_unknown | brier | 0.000 | 464 |
| validation | cancellation | KATL | all | logistic | weather:low_vis_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | KATL | all | conditional_rate | weather:not_low_vis | brier | 0.004 [0.003, 0.006] | 654927 |
| validation | cancellation | KATL | all | conditional_rate | weather:not_low_vis | average_precision | 0.005 | 654927 |
| validation | cancellation | KATL | all | logistic | weather:not_low_vis | brier | 0.004 [0.003, 0.006] | 654927 |
| validation | cancellation | KATL | all | logistic | weather:not_low_vis | average_precision | 0.004 | 654927 |
| validation | cancellation | KATL | all | conditional_rate | weather:not_strong_crosswind | brier | 0.004 [0.003, 0.006] | 666359 |
| validation | cancellation | KATL | all | conditional_rate | weather:not_strong_crosswind | average_precision | 0.005 | 666359 |
| validation | cancellation | KATL | all | logistic | weather:not_strong_crosswind | brier | 0.005 [0.003, 0.006] | 666359 |
| validation | cancellation | KATL | all | logistic | weather:not_strong_crosswind | average_precision | 0.005 | 666359 |
| validation | cancellation | KATL | all | conditional_rate | weather:strong_crosswind | brier | 0.005 | 1452 |
| validation | cancellation | KATL | all | conditional_rate | weather:strong_crosswind | average_precision | 0.005 | 1452 |
| validation | cancellation | KATL | all | logistic | weather:strong_crosswind | brier | 0.006 | 1452 |
| validation | cancellation | KATL | all | logistic | weather:strong_crosswind | average_precision | 0.008 | 1452 |
| validation | cancellation | KATL | all | conditional_rate | weather:strong_crosswind_unknown | brier | 0.000 | 464 |
| validation | cancellation | KATL | all | conditional_rate | weather:strong_crosswind_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | KATL | all | logistic | weather:strong_crosswind_unknown | brier | 0.000 | 464 |
| validation | cancellation | KATL | all | logistic | weather:strong_crosswind_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | KDFW | all | conditional_rate | weather:not_thunderstorm | brier | 0.019 [0.013, 0.026] | 586435 |
| validation | cancellation | KDFW | all | conditional_rate | weather:not_thunderstorm | average_precision | 0.030 | 586435 |
| validation | cancellation | KDFW | all | logistic | weather:not_thunderstorm | brier | 0.019 [0.013, 0.026] | 586435 |
| validation | cancellation | KDFW | all | logistic | weather:not_thunderstorm | average_precision | 0.016 | 586435 |
| validation | cancellation | KDFW | all | conditional_rate | weather:thunderstorm | brier | 0.224 [0.142, 0.283] | 18776 |
| validation | cancellation | KDFW | all | conditional_rate | weather:thunderstorm | average_precision | 0.195 | 18776 |
| validation | cancellation | KDFW | all | logistic | weather:thunderstorm | brier | 0.224 [0.142, 0.284] | 18776 |
| validation | cancellation | KDFW | all | logistic | weather:thunderstorm | average_precision | 0.208 | 18776 |
| validation | cancellation | KDFW | all | conditional_rate | weather:ifr | brier | 0.084 [0.041, 0.134] | 37664 |
| validation | cancellation | KDFW | all | conditional_rate | weather:ifr | average_precision | 0.097 | 37664 |
| validation | cancellation | KDFW | all | logistic | weather:ifr | brier | 0.084 [0.041, 0.134] | 37664 |
| validation | cancellation | KDFW | all | logistic | weather:ifr | average_precision | 0.065 | 37664 |
| validation | cancellation | KDFW | all | conditional_rate | weather:not_ifr | brier | 0.021 [0.014, 0.030] | 567547 |
| validation | cancellation | KDFW | all | conditional_rate | weather:not_ifr | average_precision | 0.031 | 567547 |
| validation | cancellation | KDFW | all | logistic | weather:not_ifr | brier | 0.022 [0.014, 0.031] | 567547 |
| validation | cancellation | KDFW | all | logistic | weather:not_ifr | average_precision | 0.017 | 567547 |
| validation | cancellation | KDFW | all | conditional_rate | weather:low_vis | brier | 0.113 | 5944 |
| validation | cancellation | KDFW | all | conditional_rate | weather:low_vis | average_precision | 0.115 | 5944 |
| validation | cancellation | KDFW | all | logistic | weather:low_vis | brier | 0.112 | 5944 |
| validation | cancellation | KDFW | all | logistic | weather:low_vis | average_precision | 0.107 | 5944 |
| validation | cancellation | KDFW | all | conditional_rate | weather:not_low_vis | brier | 0.024 [0.016, 0.034] | 599267 |
| validation | cancellation | KDFW | all | conditional_rate | weather:not_low_vis | average_precision | 0.032 | 599267 |
| validation | cancellation | KDFW | all | logistic | weather:not_low_vis | brier | 0.025 [0.016, 0.035] | 599267 |
| validation | cancellation | KDFW | all | logistic | weather:not_low_vis | average_precision | 0.019 | 599267 |
| validation | cancellation | KDFW | all | conditional_rate | weather:not_strong_crosswind | brier | 0.024 [0.016, 0.034] | 603327 |
| validation | cancellation | KDFW | all | conditional_rate | weather:not_strong_crosswind | average_precision | 0.032 | 603327 |
| validation | cancellation | KDFW | all | logistic | weather:not_strong_crosswind | brier | 0.025 [0.016, 0.035] | 603327 |
| validation | cancellation | KDFW | all | logistic | weather:not_strong_crosswind | average_precision | 0.020 | 603327 |
| validation | cancellation | KDFW | all | conditional_rate | weather:strong_crosswind | brier | 0.271 | 1884 |
| validation | cancellation | KDFW | all | conditional_rate | weather:strong_crosswind | average_precision | 0.254 | 1884 |
| validation | cancellation | KDFW | all | logistic | weather:strong_crosswind | brier | 0.272 | 1884 |
| validation | cancellation | KDFW | all | logistic | weather:strong_crosswind | average_precision | 0.224 | 1884 |
| validation | cancellation | pooled | all | conditional_rate | weather:not_thunderstorm | brier | 0.011 [0.008, 0.015] | 1246494 |
| validation | cancellation | pooled | all | conditional_rate | weather:not_thunderstorm | average_precision | 0.026 | 1246494 |
| validation | cancellation | pooled | all | logistic | weather:not_thunderstorm | brier | 0.011 [0.008, 0.015] | 1246494 |
| validation | cancellation | pooled | all | logistic | weather:not_thunderstorm | average_precision | 0.013 | 1246494 |
| validation | cancellation | pooled | all | conditional_rate | weather:thunderstorm | brier | 0.163 [0.090, 0.223] | 26528 |
| validation | cancellation | pooled | all | conditional_rate | weather:thunderstorm | average_precision | 0.187 | 26528 |
| validation | cancellation | pooled | all | logistic | weather:thunderstorm | brier | 0.163 [0.090, 0.222] | 26528 |
| validation | cancellation | pooled | all | logistic | weather:thunderstorm | average_precision | 0.169 | 26528 |
| validation | cancellation | pooled | all | conditional_rate | weather:thunderstorm_unknown | brier | 0.000 | 464 |
| validation | cancellation | pooled | all | conditional_rate | weather:thunderstorm_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | pooled | all | logistic | weather:thunderstorm_unknown | brier | 0.000 | 464 |
| validation | cancellation | pooled | all | logistic | weather:thunderstorm_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | pooled | all | conditional_rate | weather:ifr | brier | 0.038 [0.020, 0.060] | 93572 |
| validation | cancellation | pooled | all | conditional_rate | weather:ifr | average_precision | 0.082 | 93572 |
| validation | cancellation | pooled | all | logistic | weather:ifr | brier | 0.038 [0.020, 0.060] | 93572 |
| validation | cancellation | pooled | all | logistic | weather:ifr | average_precision | 0.045 | 93572 |
| validation | cancellation | pooled | all | conditional_rate | weather:ifr_unknown | brier | 0.000 | 464 |
| validation | cancellation | pooled | all | conditional_rate | weather:ifr_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | pooled | all | logistic | weather:ifr_unknown | brier | 0.000 | 464 |
| validation | cancellation | pooled | all | logistic | weather:ifr_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | pooled | all | conditional_rate | weather:not_ifr | brier | 0.012 [0.009, 0.017] | 1179450 |
| validation | cancellation | pooled | all | conditional_rate | weather:not_ifr | average_precision | 0.027 | 1179450 |
| validation | cancellation | pooled | all | logistic | weather:not_ifr | brier | 0.013 [0.009, 0.017] | 1179450 |
| validation | cancellation | pooled | all | logistic | weather:not_ifr | average_precision | 0.013 | 1179450 |
| validation | cancellation | pooled | all | conditional_rate | weather:low_vis | brier | 0.040 [0.018, 0.074] | 18828 |
| validation | cancellation | pooled | all | conditional_rate | weather:low_vis | average_precision | 0.101 | 18828 |
| validation | cancellation | pooled | all | logistic | weather:low_vis | brier | 0.040 [0.018, 0.074] | 18828 |
| validation | cancellation | pooled | all | logistic | weather:low_vis | average_precision | 0.075 | 18828 |
| validation | cancellation | pooled | all | conditional_rate | weather:low_vis_unknown | brier | 0.000 | 464 |
| validation | cancellation | pooled | all | conditional_rate | weather:low_vis_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | pooled | all | logistic | weather:low_vis_unknown | brier | 0.000 | 464 |
| validation | cancellation | pooled | all | logistic | weather:low_vis_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | pooled | all | conditional_rate | weather:not_low_vis | brier | 0.014 [0.009, 0.019] | 1254194 |
| validation | cancellation | pooled | all | conditional_rate | weather:not_low_vis | average_precision | 0.028 | 1254194 |
| validation | cancellation | pooled | all | logistic | weather:not_low_vis | brier | 0.014 [0.010, 0.019] | 1254194 |
| validation | cancellation | pooled | all | logistic | weather:not_low_vis | average_precision | 0.015 | 1254194 |
| validation | cancellation | pooled | all | conditional_rate | weather:not_strong_crosswind | brier | 0.014 [0.010, 0.019] | 1269686 |
| validation | cancellation | pooled | all | conditional_rate | weather:not_strong_crosswind | average_precision | 0.028 | 1269686 |
| validation | cancellation | pooled | all | logistic | weather:not_strong_crosswind | brier | 0.014 [0.010, 0.019] | 1269686 |
| validation | cancellation | pooled | all | logistic | weather:not_strong_crosswind | average_precision | 0.015 | 1269686 |
| validation | cancellation | pooled | all | conditional_rate | weather:strong_crosswind | brier | 0.155 | 3336 |
| validation | cancellation | pooled | all | conditional_rate | weather:strong_crosswind | average_precision | 0.252 | 3336 |
| validation | cancellation | pooled | all | logistic | weather:strong_crosswind | brier | 0.156 | 3336 |
| validation | cancellation | pooled | all | logistic | weather:strong_crosswind | average_precision | 0.191 | 3336 |
| validation | cancellation | pooled | all | conditional_rate | weather:strong_crosswind_unknown | brier | 0.000 | 464 |
| validation | cancellation | pooled | all | conditional_rate | weather:strong_crosswind_unknown | average_precision | n/a (single_class) | 464 |
| validation | cancellation | pooled | all | logistic | weather:strong_crosswind_unknown | brier | 0.000 | 464 |
| validation | cancellation | pooled | all | logistic | weather:strong_crosswind_unknown | average_precision | n/a (single_class) | 464 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_thunderstorm | brier | 0.071 [0.064, 0.080] | 657227 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_thunderstorm | average_precision | 0.101 | 657227 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:not_thunderstorm | brier | 0.071 [0.064, 0.080] | 657227 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:not_thunderstorm | average_precision | 0.104 | 657227 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_thunderstorm | brier | 0.069 [0.063, 0.078] | 657227 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_thunderstorm | average_precision | 0.144 | 657227 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:thunderstorm | brier | 0.249 [0.138, 0.360] | 7624 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:thunderstorm | average_precision | 0.219 | 7624 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:thunderstorm | brier | 0.248 [0.136, 0.359] | 7624 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:thunderstorm | average_precision | 0.238 | 7624 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:thunderstorm | brier | 0.233 [0.136, 0.329] | 7624 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:thunderstorm | average_precision | 0.255 | 7624 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:thunderstorm_unknown | brier | 0.052 | 464 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:thunderstorm_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:thunderstorm_unknown | brier | 0.056 | 464 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:thunderstorm_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:thunderstorm_unknown | brier | 0.050 | 464 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:thunderstorm_unknown | average_precision | 0.038 | 464 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:ifr | brier | 0.094 [0.068, 0.128] | 55504 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:ifr | average_precision | 0.121 | 55504 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:ifr | brier | 0.094 [0.067, 0.128] | 55504 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:ifr | average_precision | 0.117 | 55504 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:ifr | brier | 0.091 [0.068, 0.121] | 55504 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:ifr | average_precision | 0.155 | 55504 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:ifr_unknown | brier | 0.052 | 464 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:ifr_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:ifr_unknown | brier | 0.056 | 464 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:ifr_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:ifr_unknown | brier | 0.050 | 464 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:ifr_unknown | average_precision | 0.038 | 464 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_ifr | brier | 0.071 [0.063, 0.079] | 609347 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_ifr | average_precision | 0.101 | 609347 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:not_ifr | brier | 0.071 [0.064, 0.079] | 609347 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:not_ifr | average_precision | 0.105 | 609347 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_ifr | brier | 0.070 [0.063, 0.076] | 609347 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_ifr | average_precision | 0.146 | 609347 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:low_vis | brier | 0.104 [0.059, 0.186] | 12804 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:low_vis | average_precision | 0.132 | 12804 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:low_vis | brier | 0.105 [0.060, 0.187] | 12804 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:low_vis | average_precision | 0.121 | 12804 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:low_vis | brier | 0.101 [0.060, 0.174] | 12804 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:low_vis | average_precision | 0.163 | 12804 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:low_vis_unknown | brier | 0.052 | 464 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:low_vis_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:low_vis_unknown | brier | 0.056 | 464 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:low_vis_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:low_vis_unknown | brier | 0.050 | 464 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:low_vis_unknown | average_precision | 0.038 | 464 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_low_vis | brier | 0.072 [0.064, 0.082] | 652047 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_low_vis | average_precision | 0.101 | 652047 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:not_low_vis | brier | 0.073 [0.064, 0.082] | 652047 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:not_low_vis | average_precision | 0.105 | 652047 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_low_vis | brier | 0.071 [0.063, 0.079] | 652047 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_low_vis | average_precision | 0.146 | 652047 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_strong_crosswind | brier | 0.073 [0.064, 0.083] | 663407 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:not_strong_crosswind | average_precision | 0.101 | 663407 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:not_strong_crosswind | brier | 0.073 [0.065, 0.083] | 663407 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:not_strong_crosswind | average_precision | 0.105 | 663407 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_strong_crosswind | brier | 0.071 [0.064, 0.080] | 663407 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:not_strong_crosswind | average_precision | 0.146 | 663407 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:strong_crosswind | brier | 0.123 | 1444 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:strong_crosswind | average_precision | 0.146 | 1444 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:strong_crosswind | brier | 0.123 | 1444 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:strong_crosswind | average_precision | 0.152 | 1444 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:strong_crosswind | brier | 0.122 | 1444 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:strong_crosswind | average_precision | 0.126 | 1444 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:strong_crosswind_unknown | brier | 0.052 | 464 |
| validation | departure_delay_gt45 | KATL | all | conditional_rate | weather:strong_crosswind_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:strong_crosswind_unknown | brier | 0.056 | 464 |
| validation | departure_delay_gt45 | KATL | all | logistic | weather:strong_crosswind_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:strong_crosswind_unknown | brier | 0.050 | 464 |
| validation | departure_delay_gt45 | KATL | all | lgbm_delay | weather:strong_crosswind_unknown | average_precision | 0.038 | 464 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_thunderstorm | brier | 0.123 [0.112, 0.133] | 575199 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_thunderstorm | average_precision | 0.192 | 575199 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:not_thunderstorm | brier | 0.122 [0.111, 0.132] | 575199 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:not_thunderstorm | average_precision | 0.208 | 575199 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_thunderstorm | brier | 0.118 [0.108, 0.127] | 575199 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_thunderstorm | average_precision | 0.268 | 575199 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:thunderstorm | brier | 0.433 [0.358, 0.494] | 14460 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:thunderstorm | average_precision | 0.536 | 14460 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:thunderstorm | brier | 0.423 [0.347, 0.484] | 14460 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:thunderstorm | average_precision | 0.551 | 14460 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:thunderstorm | brier | 0.340 [0.289, 0.381] | 14460 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:thunderstorm | average_precision | 0.584 | 14460 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:ifr | brier | 0.214 [0.167, 0.269] | 34420 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:ifr | average_precision | 0.377 | 34420 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:ifr | brier | 0.210 [0.164, 0.263] | 34420 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:ifr | average_precision | 0.422 | 34420 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:ifr | brier | 0.184 [0.151, 0.220] | 34420 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:ifr | average_precision | 0.501 | 34420 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_ifr | brier | 0.125 [0.114, 0.137] | 555239 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_ifr | average_precision | 0.194 | 555239 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:not_ifr | brier | 0.124 [0.113, 0.136] | 555239 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:not_ifr | average_precision | 0.210 | 555239 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_ifr | brier | 0.120 [0.110, 0.130] | 555239 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_ifr | average_precision | 0.276 | 555239 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:low_vis | brier | 0.297 | 5252 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:low_vis | average_precision | 0.382 | 5252 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:low_vis | brier | 0.284 | 5252 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:low_vis | average_precision | 0.508 | 5252 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:low_vis | brier | 0.267 | 5252 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:low_vis | average_precision | 0.471 | 5252 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_low_vis | brier | 0.129 [0.117, 0.141] | 584407 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_low_vis | average_precision | 0.200 | 584407 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:not_low_vis | brier | 0.128 [0.116, 0.139] | 584407 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:not_low_vis | average_precision | 0.214 | 584407 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_low_vis | brier | 0.122 [0.112, 0.133] | 584407 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_low_vis | average_precision | 0.293 | 584407 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_strong_crosswind | brier | 0.130 [0.117, 0.142] | 588299 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:not_strong_crosswind | average_precision | 0.201 | 588299 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:not_strong_crosswind | brier | 0.128 [0.116, 0.140] | 588299 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:not_strong_crosswind | average_precision | 0.217 | 588299 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_strong_crosswind | brier | 0.123 [0.112, 0.133] | 588299 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:not_strong_crosswind | average_precision | 0.295 | 588299 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:strong_crosswind | brier | 0.405 | 1360 |
| validation | departure_delay_gt45 | KDFW | all | conditional_rate | weather:strong_crosswind | average_precision | 0.497 | 1360 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:strong_crosswind | brier | 0.407 | 1360 |
| validation | departure_delay_gt45 | KDFW | all | logistic | weather:strong_crosswind | average_precision | 0.513 | 1360 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:strong_crosswind | brier | 0.342 | 1360 |
| validation | departure_delay_gt45 | KDFW | all | lgbm_delay | weather:strong_crosswind | average_precision | 0.515 | 1360 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_thunderstorm | brier | 0.095 [0.088, 0.103] | 1232426 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_thunderstorm | average_precision | 0.167 | 1232426 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:not_thunderstorm | brier | 0.095 [0.088, 0.103] | 1232426 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:not_thunderstorm | average_precision | 0.172 | 1232426 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_thunderstorm | brier | 0.092 [0.086, 0.100] | 1232426 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_thunderstorm | average_precision | 0.222 | 1232426 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:thunderstorm | brier | 0.369 [0.297, 0.427] | 22084 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:thunderstorm | average_precision | 0.487 | 22084 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:thunderstorm | brier | 0.362 [0.290, 0.422] | 22084 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:thunderstorm | average_precision | 0.497 | 22084 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:thunderstorm | brier | 0.303 [0.253, 0.348] | 22084 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:thunderstorm | average_precision | 0.547 | 22084 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:thunderstorm_unknown | brier | 0.052 | 464 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:thunderstorm_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:thunderstorm_unknown | brier | 0.056 | 464 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:thunderstorm_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:thunderstorm_unknown | brier | 0.050 | 464 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:thunderstorm_unknown | average_precision | 0.038 | 464 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:ifr | brier | 0.140 [0.111, 0.174] | 89924 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:ifr | average_precision | 0.287 | 89924 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:ifr | brier | 0.138 [0.110, 0.172] | 89924 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:ifr | average_precision | 0.298 | 89924 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:ifr | brier | 0.126 [0.104, 0.153] | 89924 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:ifr | average_precision | 0.377 | 89924 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:ifr_unknown | brier | 0.052 | 464 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:ifr_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:ifr_unknown | brier | 0.056 | 464 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:ifr_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:ifr_unknown | brier | 0.050 | 464 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:ifr_unknown | average_precision | 0.038 | 464 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_ifr | brier | 0.097 [0.089, 0.105] | 1164586 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_ifr | average_precision | 0.169 | 1164586 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:not_ifr | brier | 0.096 [0.088, 0.104] | 1164586 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:not_ifr | average_precision | 0.174 | 1164586 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_ifr | brier | 0.093 [0.086, 0.101] | 1164586 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_ifr | average_precision | 0.230 | 1164586 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:low_vis | brier | 0.160 [0.110, 0.238] | 18056 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:low_vis | average_precision | 0.287 | 18056 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:low_vis | brier | 0.157 [0.109, 0.232] | 18056 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:low_vis | average_precision | 0.355 | 18056 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:low_vis | brier | 0.149 [0.105, 0.218] | 18056 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:low_vis | average_precision | 0.334 | 18056 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:low_vis_unknown | brier | 0.052 | 464 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:low_vis_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:low_vis_unknown | brier | 0.056 | 464 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:low_vis_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:low_vis_unknown | brier | 0.050 | 464 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:low_vis_unknown | average_precision | 0.038 | 464 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_low_vis | brier | 0.099 [0.090, 0.108] | 1236454 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_low_vis | average_precision | 0.173 | 1236454 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:not_low_vis | brier | 0.099 [0.090, 0.108] | 1236454 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:not_low_vis | average_precision | 0.176 | 1236454 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_low_vis | brier | 0.095 [0.087, 0.103] | 1236454 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_low_vis | average_precision | 0.242 | 1236454 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_strong_crosswind | brier | 0.099 [0.091, 0.108] | 1251706 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:not_strong_crosswind | average_precision | 0.173 | 1251706 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:not_strong_crosswind | brier | 0.099 [0.091, 0.108] | 1251706 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:not_strong_crosswind | average_precision | 0.178 | 1251706 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_strong_crosswind | brier | 0.096 [0.088, 0.104] | 1251706 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:not_strong_crosswind | average_precision | 0.242 | 1251706 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:strong_crosswind | brier | 0.260 | 2804 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:strong_crosswind | average_precision | 0.438 | 2804 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:strong_crosswind | brier | 0.261 | 2804 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:strong_crosswind | average_precision | 0.428 | 2804 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:strong_crosswind | brier | 0.228 | 2804 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:strong_crosswind | average_precision | 0.461 | 2804 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:strong_crosswind_unknown | brier | 0.052 | 464 |
| validation | departure_delay_gt45 | pooled | all | conditional_rate | weather:strong_crosswind_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:strong_crosswind_unknown | brier | 0.056 | 464 |
| validation | departure_delay_gt45 | pooled | all | logistic | weather:strong_crosswind_unknown | average_precision | 0.049 | 464 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:strong_crosswind_unknown | brier | 0.050 | 464 |
| validation | departure_delay_gt45 | pooled | all | lgbm_delay | weather:strong_crosswind_unknown | average_precision | 0.038 | 464 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_thunderstorm | rmse | 6.516 [6.225, 6.814] | 17053 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_thunderstorm | mae | 4.717 [4.551, 4.893] | 17053 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_thunderstorm | rmse | 38.231 [37.960, 38.487] | 17053 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_thunderstorm | mae | 32.629 [32.374, 32.863] | 17053 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_thunderstorm | rmse | 7.337 [7.107, 7.586] | 17053 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_thunderstorm | mae | 5.539 [5.394, 5.690] | 17053 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_thunderstorm | rmse | 6.944 [6.449, 7.442] | 17053 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_thunderstorm | mae | 4.756 [4.485, 5.021] | 17053 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_thunderstorm | rmse | 5.124 [4.871, 5.411] | 17053 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_thunderstorm | mae | 3.662 [3.532, 3.808] | 17053 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:thunderstorm | rmse | 17.267 [9.552, 23.293] | 212 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:thunderstorm | mae | 10.806 [6.425, 15.718] | 212 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:thunderstorm | rmse | 33.447 [30.277, 36.229] | 212 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:thunderstorm | mae | 28.637 [25.197, 31.709] | 212 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:thunderstorm | rmse | 14.635 [8.468, 19.167] | 212 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:thunderstorm | mae | 9.186 [5.735, 12.819] | 212 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:thunderstorm | rmse | 16.723 [9.196, 22.341] | 212 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:thunderstorm | mae | 10.868 [6.641, 15.432] | 212 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:thunderstorm | rmse | 13.887 [8.475, 18.013] | 212 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:thunderstorm | mae | 7.983 [4.713, 11.526] | 212 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:thunderstorm_unknown | rmse | 3.836 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:thunderstorm_unknown | mae | 3.304 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:thunderstorm_unknown | rmse | 39.394 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:thunderstorm_unknown | mae | 33.083 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:thunderstorm_unknown | rmse | 4.239 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:thunderstorm_unknown | mae | 3.721 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:thunderstorm_unknown | rmse | 5.642 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:thunderstorm_unknown | mae | 4.500 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:thunderstorm_unknown | rmse | 2.826 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:thunderstorm_unknown | mae | 2.495 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:ifr | rmse | 8.739 [6.833, 10.847] | 1555 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:ifr | mae | 5.524 [4.772, 6.433] | 1555 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:ifr | rmse | 39.543 [38.379, 40.755] | 1555 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:ifr | mae | 33.975 [32.811, 35.234] | 1555 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:ifr | rmse | 7.953 [6.564, 9.516] | 1555 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:ifr | mae | 5.592 [4.968, 6.244] | 1555 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:ifr | rmse | 8.823 [7.057, 10.846] | 1555 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:ifr | mae | 5.633 [4.838, 6.567] | 1555 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:ifr | rmse | 7.098 [5.669, 8.659] | 1555 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:ifr | mae | 4.325 [3.663, 5.010] | 1555 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:ifr_unknown | rmse | 3.836 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:ifr_unknown | mae | 3.304 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:ifr_unknown | rmse | 39.394 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:ifr_unknown | mae | 33.083 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:ifr_unknown | rmse | 4.239 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:ifr_unknown | mae | 3.721 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:ifr_unknown | rmse | 5.642 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:ifr_unknown | mae | 4.500 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:ifr_unknown | rmse | 2.826 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:ifr_unknown | mae | 2.495 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_ifr | rmse | 6.523 [6.248, 6.864] | 15710 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_ifr | mae | 4.719 [4.557, 4.911] | 15710 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_ifr | rmse | 38.038 [37.709, 38.337] | 15710 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_ifr | mae | 32.442 [32.145, 32.704] | 15710 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_ifr | rmse | 7.421 [7.183, 7.685] | 15710 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_ifr | mae | 5.582 [5.421, 5.755] | 15710 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_ifr | rmse | 6.958 [6.434, 7.484] | 15710 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_ifr | mae | 4.752 [4.489, 5.034] | 15710 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_ifr | rmse | 5.110 [4.846, 5.427] | 15710 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_ifr | mae | 3.655 [3.527, 3.819] | 15710 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:low_vis | rmse | 8.375 [5.130, 12.738] | 411 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:low_vis | mae | 4.903 [3.658, 6.587] | 411 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:low_vis | rmse | 40.563 [38.622, 42.874] | 411 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:low_vis | mae | 34.917 [32.863, 37.302] | 411 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:low_vis | rmse | 9.052 [6.691, 12.845] | 411 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:low_vis | mae | 6.150 [5.004, 7.686] | 411 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:low_vis | rmse | 8.907 [5.591, 13.561] | 411 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:low_vis | mae | 5.197 [4.035, 7.128] | 411 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:low_vis | rmse | 7.336 [4.299, 11.082] | 411 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:low_vis | mae | 4.091 [2.757, 5.716] | 411 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:low_vis_unknown | rmse | 3.836 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:low_vis_unknown | mae | 3.304 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:low_vis_unknown | rmse | 39.394 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:low_vis_unknown | mae | 33.083 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:low_vis_unknown | rmse | 4.239 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:low_vis_unknown | mae | 3.721 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:low_vis_unknown | rmse | 5.642 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:low_vis_unknown | mae | 4.500 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:low_vis_unknown | rmse | 2.826 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:low_vis_unknown | mae | 2.495 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_low_vis | rmse | 6.708 [6.326, 7.121] | 16854 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_low_vis | mae | 4.789 [4.602, 5.005] | 16854 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_low_vis | rmse | 38.116 [37.833, 38.392] | 16854 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_low_vis | mae | 32.523 [32.261, 32.771] | 16854 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_low_vis | rmse | 7.427 [7.143, 7.733] | 16854 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_low_vis | mae | 5.570 [5.403, 5.739] | 16854 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_low_vis | rmse | 7.098 [6.572, 7.616] | 16854 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_low_vis | mae | 4.823 [4.527, 5.116] | 16854 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_low_vis | rmse | 5.261 [4.916, 5.645] | 16854 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_low_vis | mae | 3.706 [3.555, 3.882] | 16854 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_strong_crosswind | rmse | 6.725 [6.307, 7.177] | 17241 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:not_strong_crosswind | mae | 4.779 [4.590, 5.000] | 17241 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_strong_crosswind | rmse | 38.184 [37.903, 38.446] | 17241 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:not_strong_crosswind | mae | 32.587 [32.330, 32.829] | 17241 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_strong_crosswind | rmse | 7.451 [7.142, 7.782] | 17241 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:not_strong_crosswind | mae | 5.574 [5.404, 5.756] | 17241 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_strong_crosswind | rmse | 7.132 [6.580, 7.698] | 17241 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:not_strong_crosswind | mae | 4.824 [4.523, 5.121] | 17241 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_strong_crosswind | rmse | 5.296 [4.917, 5.717] | 17241 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:not_strong_crosswind | mae | 3.706 [3.549, 3.885] | 17241 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:strong_crosswind | rmse | 17.611 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:strong_crosswind | mae | 13.798 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:strong_crosswind | rmse | 31.987 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:strong_crosswind | mae | 28.000 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:strong_crosswind | rmse | 16.237 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:strong_crosswind | mae | 12.355 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:strong_crosswind | rmse | 13.784 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:strong_crosswind | mae | 10.333 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:strong_crosswind | rmse | 14.432 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:strong_crosswind | mae | 10.784 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:strong_crosswind_unknown | rmse | 3.836 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | climatology | weather:strong_crosswind_unknown | mae | 3.304 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:strong_crosswind_unknown | rmse | 39.394 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | persistence | weather:strong_crosswind_unknown | mae | 33.083 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:strong_crosswind_unknown | rmse | 4.239 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | schedule | weather:strong_crosswind_unknown | mae | 3.721 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:strong_crosswind_unknown | rmse | 5.642 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | seasonal_persistence | weather:strong_crosswind_unknown | mae | 4.500 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:strong_crosswind_unknown | rmse | 2.826 | 24 |
| validation | reporting_carrier_touchdowns | KATL | all | lgbm_throughput | weather:strong_crosswind_unknown | mae | 2.495 | 24 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_thunderstorm | rmse | 9.336 [8.854, 9.817] | 16886 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_thunderstorm | mae | 6.402 [6.094, 6.724] | 16886 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_thunderstorm | rmse | 33.059 [32.693, 33.414] | 16886 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_thunderstorm | mae | 27.754 [27.413, 28.093] | 16886 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_thunderstorm | rmse | 11.557 [11.149, 11.952] | 16886 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_thunderstorm | mae | 8.662 [8.405, 8.918] | 16886 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_thunderstorm | rmse | 10.314 [9.496, 11.090] | 16886 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_thunderstorm | mae | 6.686 [6.177, 7.171] | 16886 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_thunderstorm | rmse | 7.281 [6.789, 7.764] | 16886 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_thunderstorm | mae | 4.891 [4.632, 5.194] | 16886 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:thunderstorm | rmse | 21.117 [17.126, 24.066] | 496 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:thunderstorm | mae | 14.999 [11.169, 17.997] | 496 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:thunderstorm | rmse | 28.979 [26.568, 31.882] | 496 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:thunderstorm | mae | 23.363 [21.176, 26.176] | 496 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:thunderstorm | rmse | 21.334 [17.296, 24.469] | 496 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:thunderstorm | mae | 15.776 [12.657, 18.380] | 496 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:thunderstorm | rmse | 23.471 [18.813, 26.973] | 496 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:thunderstorm | mae | 16.976 [12.643, 20.314] | 496 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:thunderstorm | rmse | 20.250 [15.781, 23.638] | 496 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:thunderstorm | mae | 14.448 [10.786, 17.574] | 496 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:ifr | rmse | 12.476 [10.124, 15.193] | 1216 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:ifr | mae | 7.984 [6.563, 9.885] | 1216 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:ifr | rmse | 32.216 [30.883, 33.646] | 1216 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:ifr | mae | 27.375 [26.107, 28.851] | 1216 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:ifr | rmse | 14.278 [12.134, 16.789] | 1216 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:ifr | mae | 10.657 [9.268, 12.472] | 1216 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:ifr | rmse | 15.362 [12.254, 18.638] | 1216 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:ifr | mae | 9.694 [7.566, 12.117] | 1216 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:ifr | rmse | 11.525 [8.907, 14.522] | 1216 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:ifr | mae | 7.023 [5.512, 9.032] | 1216 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_ifr | rmse | 9.645 [9.065, 10.254] | 16166 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_ifr | mae | 6.547 [6.197, 6.913] | 16166 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_ifr | rmse | 33.004 [32.606, 33.376] | 16166 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_ifr | mae | 27.648 [27.292, 27.995] | 16166 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_ifr | rmse | 11.754 [11.231, 12.246] | 16166 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_ifr | mae | 8.731 [8.419, 9.035] | 16166 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_ifr | rmse | 10.501 [9.682, 11.294] | 16166 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_ifr | mae | 6.775 [6.254, 7.282] | 16166 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_ifr | rmse | 7.614 [6.976, 8.243] | 16166 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_ifr | mae | 5.024 [4.706, 5.363] | 16166 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:low_vis | rmse | 18.605 | 160 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:low_vis | mae | 12.921 | 160 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:low_vis | rmse | 31.767 | 160 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:low_vis | mae | 25.869 | 160 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:low_vis | rmse | 20.463 | 160 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:low_vis | mae | 16.112 | 160 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:low_vis | rmse | 20.361 | 160 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:low_vis | mae | 12.900 | 160 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:low_vis | rmse | 19.002 | 160 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:low_vis | mae | 12.816 | 160 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_low_vis | rmse | 9.752 [9.115, 10.354] | 17222 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_low_vis | mae | 6.589 [6.222, 6.971] | 17222 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_low_vis | rmse | 32.960 [32.585, 33.334] | 17222 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_low_vis | mae | 27.645 [27.288, 28.001] | 17222 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_low_vis | rmse | 11.840 [11.334, 12.344] | 17222 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_low_vis | mae | 8.798 [8.492, 9.100] | 17222 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_low_vis | rmse | 10.785 [9.886, 11.583] | 17222 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_low_vis | mae | 6.925 [6.363, 7.447] | 17222 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_low_vis | rmse | 7.774 [7.082, 8.429] | 17222 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_low_vis | mae | 5.093 [4.748, 5.447] | 17222 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_strong_crosswind | rmse | 9.835 [9.187, 10.447] | 17334 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:not_strong_crosswind | mae | 6.632 [6.268, 7.010] | 17334 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_strong_crosswind | rmse | 32.961 [32.581, 33.335] | 17334 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:not_strong_crosswind | mae | 27.643 [27.292, 27.988] | 17334 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_strong_crosswind | rmse | 11.926 [11.409, 12.447] | 17334 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:not_strong_crosswind | mae | 8.847 [8.539, 9.166] | 17334 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_strong_crosswind | rmse | 10.873 [9.986, 11.674] | 17334 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:not_strong_crosswind | mae | 6.962 [6.392, 7.487] | 17334 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_strong_crosswind | rmse | 7.896 [7.183, 8.568] | 17334 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:not_strong_crosswind | mae | 5.144 [4.802, 5.497] | 17334 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:strong_crosswind | rmse | 18.556 | 48 |
| validation | reporting_carrier_touchdowns | KDFW | all | climatology | weather:strong_crosswind | mae | 12.262 | 48 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:strong_crosswind | rmse | 28.569 | 48 |
| validation | reporting_carrier_touchdowns | KDFW | all | persistence | weather:strong_crosswind | mae | 22.688 | 48 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:strong_crosswind | rmse | 18.233 | 48 |
| validation | reporting_carrier_touchdowns | KDFW | all | schedule | weather:strong_crosswind | mae | 15.465 | 48 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:strong_crosswind | rmse | 20.650 | 48 |
| validation | reporting_carrier_touchdowns | KDFW | all | seasonal_persistence | weather:strong_crosswind | mae | 13.250 | 48 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:strong_crosswind | rmse | 19.307 | 48 |
| validation | reporting_carrier_touchdowns | KDFW | all | lgbm_throughput | weather:strong_crosswind | mae | 12.412 | 48 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_thunderstorm | rmse | 8.044 [7.729, 8.363] | 33939 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_thunderstorm | mae | 5.555 [5.380, 5.741] | 33939 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_thunderstorm | rmse | 35.751 [35.491, 35.993] | 33939 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_thunderstorm | mae | 30.204 [29.964, 30.441] | 33939 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_thunderstorm | rmse | 9.670 [9.397, 9.942] | 33939 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_thunderstorm | mae | 7.093 [6.925, 7.255] | 33939 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_thunderstorm | rmse | 8.784 [8.210, 9.298] | 33939 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_thunderstorm | mae | 5.716 [5.388, 6.017] | 33939 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_thunderstorm | rmse | 6.290 [5.954, 6.626] | 33939 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_thunderstorm | mae | 4.274 [4.100, 4.451] | 33939 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:thunderstorm | rmse | 20.042 [16.417, 22.871] | 708 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:thunderstorm | mae | 13.743 [10.845, 16.351] | 708 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:thunderstorm | rmse | 30.386 [28.296, 32.704] | 708 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:thunderstorm | mae | 24.942 [22.957, 27.388] | 708 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:thunderstorm | rmse | 19.570 [15.985, 22.451] | 708 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:thunderstorm | mae | 13.803 [11.214, 16.175] | 708 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:thunderstorm | rmse | 21.672 [17.536, 24.982] | 708 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:thunderstorm | mae | 15.147 [11.762, 18.038] | 708 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:thunderstorm | rmse | 18.575 [14.935, 21.489] | 708 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:thunderstorm | mae | 12.512 [9.599, 15.132] | 708 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:thunderstorm_unknown | rmse | 3.836 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:thunderstorm_unknown | mae | 3.304 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:thunderstorm_unknown | rmse | 39.394 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:thunderstorm_unknown | mae | 33.083 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:thunderstorm_unknown | rmse | 4.239 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:thunderstorm_unknown | mae | 3.721 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:thunderstorm_unknown | rmse | 5.642 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:thunderstorm_unknown | mae | 4.500 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:thunderstorm_unknown | rmse | 2.826 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:thunderstorm_unknown | mae | 2.495 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:ifr | rmse | 10.543 [8.952, 12.258] | 2771 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:ifr | mae | 6.604 [5.804, 7.559] | 2771 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:ifr | rmse | 36.509 [35.386, 37.855] | 2771 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:ifr | mae | 31.079 [29.985, 32.326] | 2771 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:ifr | rmse | 11.179 [9.723, 12.812] | 2771 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:ifr | mae | 7.815 [6.982, 8.834] | 2771 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:ifr | rmse | 12.134 [10.059, 14.291] | 2771 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:ifr | mae | 7.415 [6.282, 8.786] | 2771 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:ifr | rmse | 9.304 [7.708, 11.103] | 2771 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:ifr | mae | 5.509 [4.717, 6.517] | 2771 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:ifr_unknown | rmse | 3.836 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:ifr_unknown | mae | 3.304 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:ifr_unknown | rmse | 39.394 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:ifr_unknown | mae | 33.083 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:ifr_unknown | rmse | 4.239 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:ifr_unknown | mae | 3.721 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:ifr_unknown | rmse | 5.642 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:ifr_unknown | mae | 4.500 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:ifr_unknown | rmse | 2.826 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:ifr_unknown | mae | 2.495 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_ifr | rmse | 8.255 [7.890, 8.633] | 31876 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_ifr | mae | 5.646 [5.449, 5.848] | 31876 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_ifr | rmse | 35.574 [35.301, 35.849] | 31876 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_ifr | mae | 30.011 [29.750, 30.272] | 31876 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_ifr | rmse | 9.859 [9.540, 10.203] | 31876 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_ifr | mae | 7.179 [6.997, 7.366] | 31876 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_ifr | rmse | 8.932 [8.347, 9.483] | 31876 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_ifr | mae | 5.778 [5.445, 6.110] | 31876 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_ifr | rmse | 6.501 [6.089, 6.927] | 31876 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_ifr | mae | 4.350 [4.158, 4.552] | 31876 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:low_vis | rmse | 12.144 [8.570, 16.441] | 571 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:low_vis | mae | 7.150 [5.322, 9.751] | 571 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:low_vis | rmse | 38.303 [36.182, 40.296] | 571 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:low_vis | mae | 32.382 [30.052, 34.567] | 571 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:low_vis | rmse | 13.278 [9.833, 17.406] | 571 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:low_vis | mae | 8.941 [7.110, 11.837] | 571 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:low_vis | rmse | 13.163 [8.786, 18.386] | 571 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:low_vis | mae | 7.356 [5.497, 10.312] | 571 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:low_vis | rmse | 11.829 [8.140, 16.133] | 571 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:low_vis | mae | 6.536 [4.641, 9.215] | 571 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:low_vis_unknown | rmse | 3.836 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:low_vis_unknown | mae | 3.304 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:low_vis_unknown | rmse | 39.394 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:low_vis_unknown | mae | 33.083 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:low_vis_unknown | rmse | 4.239 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:low_vis_unknown | mae | 3.721 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:low_vis_unknown | rmse | 5.642 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:low_vis_unknown | mae | 4.500 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:low_vis_unknown | rmse | 2.826 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:low_vis_unknown | mae | 2.495 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_low_vis | rmse | 8.385 [7.961, 8.794] | 34076 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_low_vis | mae | 5.698 [5.481, 5.922] | 34076 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_low_vis | rmse | 35.604 [35.323, 35.853] | 34076 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_low_vis | mae | 30.058 [29.804, 30.296] | 34076 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_low_vis | rmse | 9.906 [9.564, 10.242] | 34076 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_low_vis | mae | 7.201 [7.014, 7.389] | 34076 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_low_vis | rmse | 9.149 [8.522, 9.686] | 34076 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_low_vis | mae | 5.885 [5.529, 6.212] | 34076 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_low_vis | rmse | 6.651 [6.188, 7.109] | 34076 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_low_vis | mae | 4.407 [4.200, 4.632] | 34076 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_strong_crosswind | rmse | 8.429 [7.993, 8.860] | 34575 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:not_strong_crosswind | mae | 5.708 [5.490, 5.928] | 34575 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_strong_crosswind | rmse | 35.661 [35.391, 35.901] | 34575 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:not_strong_crosswind | mae | 30.108 [29.871, 30.349] | 34575 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_strong_crosswind | rmse | 9.949 [9.578, 10.303] | 34575 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:not_strong_crosswind | mae | 7.215 [7.020, 7.406] | 34575 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_strong_crosswind | rmse | 9.200 [8.563, 9.758] | 34575 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:not_strong_crosswind | mae | 5.896 [5.545, 6.221] | 34575 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_strong_crosswind | rmse | 6.726 [6.249, 7.197] | 34575 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:not_strong_crosswind | mae | 4.427 [4.221, 4.645] | 34575 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:strong_crosswind | rmse | 18.246 | 72 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:strong_crosswind | mae | 12.774 | 72 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:strong_crosswind | rmse | 29.752 | 72 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:strong_crosswind | mae | 24.458 | 72 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:strong_crosswind | rmse | 17.593 | 72 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:strong_crosswind | mae | 14.428 | 72 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:strong_crosswind | rmse | 18.644 | 72 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:strong_crosswind | mae | 12.278 | 72 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:strong_crosswind | rmse | 17.831 | 72 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:strong_crosswind | mae | 11.870 | 72 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:strong_crosswind_unknown | rmse | 3.836 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | climatology | weather:strong_crosswind_unknown | mae | 3.304 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:strong_crosswind_unknown | rmse | 39.394 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | persistence | weather:strong_crosswind_unknown | mae | 33.083 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:strong_crosswind_unknown | rmse | 4.239 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | schedule | weather:strong_crosswind_unknown | mae | 3.721 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:strong_crosswind_unknown | rmse | 5.642 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | seasonal_persistence | weather:strong_crosswind_unknown | mae | 4.500 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:strong_crosswind_unknown | rmse | 2.826 | 24 |
| validation | reporting_carrier_touchdowns | pooled | all | lgbm_throughput | weather:strong_crosswind_unknown | mae | 2.495 | 24 |

Known limitations: [docs/LIMITATIONS.md](docs/LIMITATIONS.md).
