# Project specification

Status: proposed implementation specification based on the supplied Challenge 5 brief and the reviewed plan. Open items are tracked in [DECISIONS.md](DECISIONS.md).

## User and workflow

Primary user: airport traffic management coordinator reviewing likely weather-related constraints and departure disruption at Atlanta and Dallas Fort Worth over the next 12 hours.

The prototype supports review of forecasts, demand, weather evidence, uncertainty, and historical outcomes. It produces advisories for human consideration. It does not issue clearances or initiate traffic management measures.

Primary product mode: historical replay. Keep any later live-weather demonstration separate from validated end-to-end live operational inference.

## Required scope

- Scored airports: KATL/ATL and KDFW/DFW, including arriving and departing flights.
- Lead times: 3, 6, 9, 12 hours.
- Fixed headings from the brief: 80 degrees at ATL, 180 at DFW.
- Multi-source weather/flight integration using timestamps and airport identifiers.
- Airport-hour forecast with RMSE evaluation and truthful label naming.
- Severe departure-delay classification using a strict greater-than-45-minute threshold.
- Public-data download and processing scripts.
- Interactive risk timeline, historical trends, evidence, uncertainty, and reviewable recommendations.
- Time-leakage controls, runway-relative winds, volume-normalised comparisons, and cross-airport tests.

## Target definitions

### Official AAR

`target_kind = official_aar`; units: arrivals/hour. Label source must identify the exact FAA/organiser variable, temporal resolution, aggregation method, missing/sentinel treatment, and source version. If using subhourly rates, average by duration within the UTC target hour; do not sum rate values. Missing subintervals require coverage rules.

AAR is a declared operational acceptance rate, not necessarily intrinsic physical runway capacity. Policies, configuration, and other operational constraints affect it.

### Realised throughput

`target_kind = reporting_carrier_touchdowns`; units: touchdowns/hour. Count qualifying reporting-carrier touchdowns in a complete source partition using `WHEELS_ON`. Exclude cancelled flights. Resolve diversions explicitly; never allocate a touchdown to an intended destination merely because it appears in `DEST`.

This is a separate target. It reflects demand, prior disruptions, management actions, and incomplete market coverage. Do not title its output or RMSE as AAR. A capacity indicator inferred from high-demand throughput is experimental and must not be presented as observed AAR.

### Severe departure delay

`target_kind = departure_delay_gt45`; label is 1 when `DEP_DELAY > 45`, otherwise 0, only among operated flights with valid departure-delay outcomes. Exactly 45 minutes is negative. Keep exclusions and denominator visible. Cancelled or unresolved records have a null severe-delay label, not 0.

The served probability is conditional on operation. Label it accordingly. Track cancellation separately and show it alongside this probability. Do not add two probabilities with different conditioning or describe their sum as a calibrated disruption probability.

### Cancellation

`target_kind = cancellation`; label is the final cancellation flag for the scheduled departure cohort. Retain cancellations in schedule demand even though they do not produce movements. Unknown outcomes are null.

### Secondary analyses

Arrival delay, inferred capacity reduction, live weather, and additional-airport portability are secondary. They cannot replace required targets or delay core delivery.

## Prediction population and clock

- Airport task: target UTC hour `[s, s+1h)`; issue at `T = s - h`.
- Flight task: schedule-anchored cohort; issue at `T = scheduled_departure_utc - h`.
- Preserve the schedule version/knowledge assumption used to identify the flight and target time.
- If historical status proves the flight had already departed or was cancelled and known as such by T, mark it ineligible for a new predeparture warning. Do not use final outcome status to infer knowledge at T.
- Main evaluation uses a documented retrospective schedule cohort when status snapshots are unavailable. This differs from a live pending-flight service.

## Acceptance criteria

1. One pinned source snapshot can reproduce data validation, features, baseline predictions, metrics, and a replay scenario.
2. Both airports and all horizons are represented, with denominators and source coverage reported.
3. AAR label status and throughput distinction are visible in the API, figures, dashboard, and README.
4. Post-cutoff information cannot change an earlier feature snapshot.
5. Baselines and models use the same eligible evaluation rows, with abstention results reported separately.
6. Probabilities and intervals are evaluated rather than merely displayed.
7. The dashboard supports normal, adverse-weather, and missing-source scenarios; outcomes are revealed separately from forecasts.
8. At least one success case, one false alert or miss, and one source-quality case are documented.
9. Automatic downloads are demonstrated by logs and validated outputs. Cached replay is a separate resilience mode.
10. Reported impact distinguishes measured prediction/alert improvements from simulated monetary or fuel benefits.

## Non-goals for the first release

Autonomous ATC actions; fleet-specific legal wind limits; a causal estimate of weather damage; globally validated performance; an LLM as a numeric predictor; and an unqualified claim of live readiness.

## Rubric evidence

| Criterion | Weight | Evidence |
| --- | --- | --- |
| Problem realism | 20% | Named user, concrete review workflow, credible operating constraints |
| Technical soundness | 25% | Working integration, suitable statistical methods, correct targets |
| Honest evaluation | 20% | Held-out results, baselines, slices, named failures |
| Trust and traceability | 20% | Source times, lineage, calibration, unavailable states, human review |
| Impact | 10% | Measured error/alert/lead-time improvements with stated assumptions |
| Time discipline | 5% | Reliable scoped demo, reproducibility, submission readiness |
