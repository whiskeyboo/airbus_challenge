# Assignment: Agent B — models and uncertainty

You own baselines, training, calibration, prediction bundles, explanations, and model documentation. Read root `AGENTS.md`, contracts, temporal rules, and the evaluation protocol first. Work in your ownership boundary.

## First work package

1. Inspect the shared executable schemas once the lead publishes them. If unavailable, propose concrete signatures; do not create a competing contract package.
2. Build deterministic baselines against clearly marked fixtures.
3. Implement one 3-hour model path that produces the shared prediction format. Keep labels out of serving output.
4. Reject unsupported target kinds and schema/feature versions. Do not silently train on an arrival-delay field or throughput under an AAR name.
5. Demonstrate training/inference feature consistency and model-bundle loading.

## Subsequent deliverables

- Calendar/schedule, persistence where implementable, and logistic baselines.
- Gradient-boosted airport regression, conditional severe-departure classifier, and separate cancellation model.
- Schedule/observation/forecast/wind/operational-context ablations.
- Pooled versus horizon-specific and airport-specific comparisons on chronological validation.
- Training-only preprocessing and zero-shot transfer variants without target-airport calibration.
- Probability calibration and regression quantile/interval calibration on the designated partition.
- Feature registry frozen with model bundles; model/data/code/config fingerprints.
- Explanation artifacts that identify feature value, contribution scale, and method.
- A model card documenting target, population, data, availability assumptions, training window, validation, limits, and serving support.

## Constraints

- Exact threshold is departure delay >45 minutes. Cancellation is not a negative severe-delay label.
- Fit no calibration, thresholds, imputers, or hyperparameters on final test.
- Treat simulated operations features as an experimental assumption; retain a weather-plus-schedule variant.
- Do not assume 12-hour skill or impose narrower intervals by narrative. Measure it.
- Do not call feature contributions causal explanations.
- Model complexity is justified by validation benefit, not by available time.

## Definition of done

The lead can train, load, and predict reproducibly from a pinned development dataset. Baselines, all horizons, calibration artifacts, model cards, and candidate-selection evidence exist. C can evaluate the frozen predictions without importing your metric implementation.

Hand off exact commands, model IDs, feature versions, development results, failures, and untested assumptions. Final-test evaluation is owned independently by C/lead; do not tune after viewing it.
