# Assignment: Agent C — independent evaluation and product

You own the evaluator, API, historical replay, UI, advisory rendering, and integration tests. Read root `AGENTS.md` and all shared contracts/evaluation rules first. Work inside your ownership boundary.

## First work package

1. Build a tiny independently computed evaluator against fixture predictions and labels. Make denominators, exclusions, null metrics, and targets explicit.
2. Freeze API examples with the lead; do not invent a separate UI schema.
3. Build a fixture-backed timeline for two airports showing target identity, horizon, probabilities/intervals, evidence age, and forecast status.
4. Keep fixture mode visibly labelled. Keep future outcomes out of forecast responses.
5. Add an end-to-end request test and prepare adapters for B's model bundle and A's snapshot function.

## Subsequent deliverables

- Independent RMSE/MAE/bias, classification/calibration, uncertainty, and operational-alert metrics.
- Airport/horizon/weather/demand slices, clustered uncertainty estimates, and transfer reports.
- Reproducible frozen-run manifests and evaluation artifacts.
- Historical replay with as-of selection, forecast updates, and separately requested outcome reveal.
- Source evidence, issued/valid times, source age, model attribution, and appropriately worded advisories.
- Degraded/unavailable states with reason codes; validated fallback only.
- Independent post-T mutation tests and offline/serving parity checks.
- Normal, adverse-weather, and missing-source demonstration scenarios.

## Product constraints

Never title throughput as AAR. Label severe-delay probability as conditional on operation and show cancellation risk separately. Preserve units. Do not compute metrics or features in the browser. Do not retrain on API requests. An optional LLM may only explain validated structured values and evidence; deterministic briefing is the default.

Advisories support human review. No universal GDP initiation threshold, clearance generation, or automatic intervention is authorised. Do not publish or send external messages without explicit user authorisation.

## Definition of done

Both airports/all horizons display real predictions in reproducible replay. The evaluator independently reproduces headline results. Missing inputs, target distinction, model versions, and evidence times are visible. At least one failure is explained candidly. UI/API tests pass on a pinned scenario.

Hand off exact commands and tested behaviours. Keep test-period access controlled by the lead, and do not send final-test errors back for model tuning during the locked run.
