# Data contracts v0.1.0

Status: normative prose specification for implementation; no executable schema is supplied yet. Implement only the parts the pipeline in `CLAUDE.md` needs; code lives in `src/airbus_challenge/`.

## Common conventions

- Storage: Parquet, except raw source files and JSON serving/metrics artifacts.
- Types below use `string`, `bool`, `int32`, `float64`, `timestamp[us, UTC]`, and `list<string>`. Nullable means an explicit null, not a sentinel, NaN-as-business-value, or a fabricated zero.
- UTC timestamps are timezone aware; JSON timestamps use RFC 3339 with `Z`. All intervals are half-open `[start, end)`.
- Use canonical ICAO keys in derived tables. Preserve original station and BTS identifiers separately.
- Units occur in field names. Visibility is statute miles (`_sm`), ceiling feet (`_ft`), wind knots (`_kt`), temperature Celsius (`_c`), precipitation millimetres (`_mm`), pressure hPa (`_hpa`). Convert with documented constants and preserve raw values.
- IDs are deterministic hashes of documented canonical components, never Python's process-dependent `hash()`. Key composition changes require a version change.
- A versioned JSON manifest accompanies each dataset with schema/producer versions, hashes, source URLs/versions, retrieval time, row counts, min/max time, coverage, quality counts, and `data_mode = real | fixture`.
- Predictions are outcomes-free. Evaluators join labels through keys; labels must not be present in serving payloads.

## 1. Source records and availability

Common provenance fields on observations, forecasts, and operational event records:

| Field | Type | Rule |
| --- | --- | --- |
| `source_record_id` | string | Unique within source/version |
| `source_name`, `source_version` | string | Explicit provider and snapshot |
| `raw_ref` | string | Relative path/object reference plus record locator |
| `retrieved_at_utc` | timestamp | Actual retrieval, not historical availability |
| `available_at_utc` | timestamp, nullable | Evidenced historical availability or documented simulation |
| `availability_basis` | string | `measured`, `documented`, `simulated`, or `unknown` |
| `quality_flags` | list<string> | Empty list when no known flags |

Retrieval in 2026 does not mean historical data was unavailable in 2023. Conversely, an event in 2023 does not prove the final archive record was available then. Unknown availability records cannot be inference inputs until an explicit policy assigns them simulated availability.

## 2. Weather observations

Path: `data/processed/weather_observations.parquet`.

Key: `source_record_id`. Multiple reports in an hour are allowed; never enforce one row per hour at ingestion.

| Fields | Type / null rule |
| --- | --- |
| `airport_icao`, `station_id` | string, required |
| `observed_at_utc` | timestamp, required |
| Common provenance fields | Required as above |
| `wind_from_deg`, `wind_kt`, `gust_kt` | float64, nullable |
| `wind_variable` | bool, nullable |
| `visibility_sm`, `ceiling_ft` | float64, nullable |
| `temp_c`, `precip_1h_mm`, `pressure_hpa` | float64, nullable |
| `wx_codes` | list<string>, nullable |

Ceiling derives from the lowest relevant broken/overcast layer or vertical visibility. Preserve unlimited/clear versus missing using quality/condition flags; do not encode clear sky as a measured 0-foot ceiling. Missing gust does not mean a measured zero gust. Preserve trace/censored precipitation and visibility semantics. Repeated rolling one-hour precipitation reports must not be naively summed.

## 3. Archived forecasts

Path: `data/processed/weather_forecasts.parquet`.

Key: `(bulletin_id, segment_id)`. Preserve the complete raw bulletin and ordered groups.

| Fields | Type / rule |
| --- | --- |
| `bulletin_id`, `segment_id`, `airport_icao`, `station_id` | string, required |
| `issued_at_utc`, `valid_from_utc`, `valid_to_utc` | timestamp, required |
| `is_amendment`, `is_correction` | bool, required when known; otherwise null |
| `forecast_type` | string: prevailing/FM/BECMG/TEMPO/PROB30/PROB40 or explicit unknown |
| `probability` | float64 nullable; weather-group probability only |
| `wind_from_deg`, `wind_kt`, `gust_kt`, `visibility_sm`, `ceiling_ft` | float64, nullable |
| `wind_variable` | bool, nullable |
| `wx_codes` | list<string>, nullable |
| Common provenance fields | Required |

Do not overwrite an old bulletin with a later amendment. Reconstruct prevailing state within a single eligible bulletin; maintain conditional/temporary groups separately. Target-hour aggregation must be deterministic, versioned, and duration-aware. Do not fabricate quantitative precipitation forecasts from rain codes.

## 4. Flights and outcome archive

Path: `data/processed/flights.parquet`.

Key: `flight_id`, derived from source flight date, stable operating-carrier identifier, flight number, origin, destination, scheduled departure time, and a documented duplicate-resolution version. A source row hash is also retained. Preserve conflicts for audit rather than silently dropping them.

| Fields | Type / rule |
| --- | --- |
| `flight_id`, `carrier_id`, `flight_number`, `origin_icao`, `dest_icao` | string, required after mapping |
| `source_flight_date` | source local departure date |
| `scheduled_dep_utc`, `scheduled_arr_utc` | timestamp, nullable if unresolved |
| `actual_dep_utc`, `wheels_off_utc`, `wheels_on_utc`, `actual_arr_utc` | timestamp, nullable |
| `dep_delay_min`, `arr_delay_min` | float64 nullable; preserve negatives |
| `cancelled`, `diverted` | bool nullable |
| `schedule_snapshot_id`, `schedule_knowledge_basis` | string |
| `timestamp_status`, `quality_flags`, `source_record_id` | string/list/string |

This is an outcome archive, not a time-safe input table. Final tail assignment, actual times, delay causes, cancellation/diversion status, and outcome values must not pass directly into inference.

If operational state features are used, derive a separate event table:
`flight_events(flight_event_id, flight_id, event_type, event_time_utc, available_at_utc, availability_basis, source_record_id)`.
Simulated events must be distinguishable from actual historical status messages.

## 5. Airport-hour outcomes and demand

Path: `data/processed/airport_hourly.parquet`.
Key: `(airport_icao, hour_start_utc, source_snapshot_id)`.

| Fields | Type / rule |
| --- | --- |
| `airport_icao`, `source_snapshot_id` | string |
| `hour_start_utc`, `hour_end_utc` | timestamp; exactly one UTC hour |
| `scheduled_arrivals`, `scheduled_departures` | int32 nullable |
| `reporting_carrier_touchdowns`, `reporting_carrier_takeoffs` | int32 nullable |
| `official_aar` | float64 nullable |
| `aar_source`, `aar_aggregation_version` | string nullable |
| `coverage_status` | `complete_for_source_scope`, `partial`, `missing` |
| `coverage_fraction` | float64 nullable; define numerator/denominator if supplied |
| `schedule_knowledge_basis` | string |
| `data_mode` | `real` or `fixture`, required; one value per table |

Generate a complete UTC hour grid, not just hours with records. Use zero only when the source partition is complete for the declared reporting scope and no qualifying movement occurred. This does not imply coverage of every aircraft category. A 25-hour local day still has unique UTC hours.

## 6. Prediction requests and feature snapshots

`prediction_requests` key: `prediction_id`, one task-specific request per airport/flight, target, horizon and schedule definition. `prediction_id` is the SHA-256 of `task|airport_icao|flight_id|target_start_utc|horizon_h|cohort_version`, with an empty string for a null `flight_id`. Only `requests.py` builds it, from schedule fields and never from outcome columns.

Required columns:
`prediction_id`, `task`, `airport_icao`, `flight_id?`, `as_of_utc`, `target_start_utc`, `target_end_utc`, `horizon_h`, `schedule_snapshot_id?`, `cohort_version`, `data_mode`.

`task` is one of `throughput`, `severe_delay`.

A request is in scope for a split, task and `cohort_version` when its target falls in that split and `as_of_utc` is at or after the scope cutoff: the later of the end of train and the latest `fit_cutoff_utc` among the runs evaluated for that task, cohort and target. Earlier rows are dropped for every model, baselines included, and every model must then cover every in-scope request. The report's `scoring_scope` records, per split, the cutoff, the run that set it, rows dropped per model and rows scored; a split left with no rows reports null metrics with reason `no_rows_after_fit_cutoff`. A later-cutoff refit is therefore scored only from its own cutoff, never in-sample. Results are never pooled across cohorts. The CSV-only comparison and each leave-one-airport-out test use their own `cohort_version`; CSV-only versions start with `csv_only`.

For flights, `target_start_utc` is the scheduled departure instant and `target_end_utc` is null. For airport tasks, it is the target hour and end is start + 1 hour. `horizon_h` must equal the target-start/as-of difference in hours.

`feature_snapshots` has the same key plus typed feature columns, `feature_version`, `data_snapshot_id`, `status`, `reason_codes`, and source-age fields. The feature registry specifies type, unit, source, transform, missing policy, and serving support for each feature. It is frozen with the model.

Lineage is a separate long table:
`feature_lineage(prediction_id, feature_name, source_record_id, contributing_available_at_utc, availability_basis, transform_version)`.
Large rolling features can reference a hashed source partition and bounds if exact contributors remain reproducible.

`features.py` writes `data/processed/feature_snapshots.parquet`, one row per `prediction_id` for both tasks, adding `snapshot_key` and `window_end_utc` (`target_end_utc`, or target start + 1 h for flights). Requests sharing (airport, as_of, target_start, window_end) share one `snapshot_key` and are computed once. Continuous features are float32 in this table (float64 in the interim file). `data/processed/feature_lineage.parquet` is keyed by `snapshot_key` and `feature_group`, not `prediction_id` and `feature_name`; join through `feature_snapshots.snapshot_key` to trace a prediction. `features.py` reads only the weather tables, their manifests, the request columns of `prediction_requests` and `configs/`; a test enforces this on every file open.

Until `prediction_requests` exists, `features.py` writes `data/interim/weather_features_airport_hour.parquet` and `weather_features_lineage_airport_hour.parquet`, keyed by `(airport_icao, as_of_utc, target_start_utc, horizon_h)`. Requests join on that key to gain `prediction_id`. Lineage there is per `feature_group` (the `FEATURES` registry maps features to groups); `metar_window` rows reference a sha256 of the sorted contributor ids.

Weather `reason_codes` (policies in `docs/DECISIONS.md` P13-P15):

| Code | Meaning | Effect |
| --- | --- | --- |
| `metar_stale` | Latest eligible METAR older than 3 h | METAR features null, status `partial` |
| `metar_cor_skipped` | A corrected METAR would have been latest; the previous report was used | Features kept |
| `taf_unavailable` | No bulletin available by T | TAF features null |
| `taf_uncovered` | Target window ends after the chosen bulletin's end | TAF features null |
| `taf_conflict_fallback` | Latest bulletin had conflicting versions; previous eligible one used | Features kept |

## 7. Labels

Path: `data/labels/labels.parquet`.
Key: `(prediction_id, target_kind, label_version)`.

Fields: `prediction_id`, `target_kind`, `y_true` (nullable float64), `eligible` (bool), `exclusion_reason` (nullable string), `exclusion_detail` (nullable string), `outcome_available_at_utc` (nullable timestamp), `availability_basis`, `label_source`, `label_version`, `unit`, `data_mode` (`real` or `fixture`, required; one value per table).

`exclusion_reason` is null exactly when `eligible` is true. Otherwise it is one of `cancelled`, `coverage_incomplete`, `missing_outcome`, `quarantined`. `exclusion_detail` holds the producer's specific reason and follows the same null rule; evaluators don't validate its values.

| `exclusion_detail` | `exclusion_reason` |
| --- | --- |
| `cancelled` | `cancelled` |
| `timestamp_quarantined` | `quarantined` |
| `unresolved_arrival_fraction_gt_0.05` | `coverage_incomplete` |
| `missing_source_month` | `coverage_incomplete` |
| `unknown_cancellation_status` | `missing_outcome` |
| `missing_departure_delay` | `missing_outcome` |

Every prediction request in scope has a label row for each target it is scored on, including excluded ones, so denominators stay visible. A table holds one `label_version`.

Allowed main targets: `official_aar`, `reporting_carrier_touchdowns`, `throughput_over_clear_weather_p95`, `departure_delay_gt45`, `cancellation`. Binary outcomes must be exactly 0 or 1. Labels are outcomes, never features.

## 8. Predictions and serving

Path: `artifacts/<run_id>/predictions.parquet`.
Key: `(prediction_id, target_kind, model_version)`.

Fields: request keys, `target_kind`, `estimate` (nullable float64), `p10`, `p90` (nullable float64), `unit`, `status` (`available`, `degraded`, `unavailable`), `reason_codes`, `model_version`, `feature_version`, `data_snapshot_id`, `generated_at_utc`, `data_mode`.

- Regression estimate is the declared point estimator; classification estimate is a probability in [0,1].
- `p10/p90` are regression predictive quantiles, not classification confidence intervals. Enforce p10 <= p90; fix crossing with a documented method. A mean estimate need not mathematically lie between those quantiles.
- A model writes a row for every request in scope. A request it cannot score is `unavailable`, never omitted.
- `artifacts/<run_id>/manifest.json` records at least `run_id`, `data_mode`, `commit_dirty`, a timezone-aware `fit_cutoff_utc` and `prediction_requests_sha256`. The evaluator refuses a run that scores a request issued before its own cutoff, or whose requests hash differs from the requests table it reads. In a locked run, a baseline may not have a later cutoff than the candidate, so it cannot narrow the scored scope. A model for a leave-one-airport-out test also records `train_airports`.
- A locked-run claim is `<run_id>.json` (`run`, `approved_by`, `commit`, `predictions_sha256`, `claimed_at_utc`), created exclusively in the canonical `data/locked_runs/` and mirrored to the committed `reports/locked_runs/`. A claim found in either location blocks a rerun.
- Unavailable means null estimate and a nonempty reason list. Degraded means an actually validated fallback or model capability, not a random imputation.
- Baselines use the same schema with their own model IDs.
- Explanations use a companion table: prediction/model key, feature, feature value, contribution, contribution scale, explanation method. Probabilistic log-odds contributions are labelled as such.

Proposed API, implemented by C: `GET /health`, `POST /v1/predictions`, `GET /v1/replay`, `GET /v1/evaluation`. Freeze request/response JSON Schema and OpenAPI before connecting the UI. A prediction response includes keys above, weather evidence references, source ages, and advisories. Actual labels are exposed only by an explicitly requested replay-outcomes endpoint, never mixed into the forecast response.

## 9. Evaluation artifacts

`metrics.json` contains `run_id`, commit, config hash, data fingerprints, split bounds, target definitions, model IDs, and an array of metric records. Each metric record includes task, target, airport, horizon, slice, metric name/value, unit, n_eligible, n_predicted, n_excluded, prevalence where relevant, and confidence interval/method where computed. Undefined metrics are null with a reason, not zero.

Save alert episodes and replay cases separately with their definition versions. Never compute evaluation metrics inside the UI.

## Required validation

Validate uniqueness, nullable rules, units, UTC types, time ordering, horizons, allowed enums, binary labels, probability bounds, coverage before zero-fill, and schema compatibility. Error messages include the key and failure rule. Quarantine data defects; fail loudly for a broken contract.
