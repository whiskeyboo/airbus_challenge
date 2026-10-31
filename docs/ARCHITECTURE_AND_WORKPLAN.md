# Architecture and three-agent workplan

## Proposed repository layout

```text
AGENTS.md / CLAUDE.md / README.md
configs/                 lead-owned configuration
docs/                    shared specifications
docs/handoffs/agent-a/    A's updates
docs/handoffs/agent-b/    B's updates
docs/handoffs/agent-c/    C's updates
src/contracts/           lead-owned typed schemas and public interfaces
src/data_pipeline/       A: source adapters, raw validation, timestamps, labels
src/features/            A: feature registry, as-of construction, lineage
src/modeling/            B: baselines, train, calibrate, predict, explain
src/evaluation/          C: independent metric computation and event analysis
src/service/             C: API, replay, advisory policy
web/                     C: React/TypeScript interface
tests/fixtures/          A: shared versioned synthetic/reference fixtures
tests/data/              A
tests/temporal/          A; C reviews and adds independent evaluator tests
tests/modeling/          B
tests/evaluation/        C
tests/service/           C
tests/e2e/               C
data/raw/                ignored immutable source/cache files
data/processed/          ignored validated datasets
data/labels/             ignored outcome tables
artifacts/               ignored run-scoped models/predictions/reports
```

The code directories above are a proposed layout; this kit does not create empty implementation modules. Do not confuse the presence of documentation with running software.

## Dependency direction

Source adapters -> validated source tables -> as-of feature snapshots -> model predictions -> evaluator and service -> dashboard.

Label construction branches from validated outcome tables to the evaluator/training process. It must not flow into inference features. Serving and offline prediction use the same feature implementation; there is no second UI-specific feature builder.

The service invokes the model through a public interface and translates outputs into display/advisory contracts. B does not build endpoints. C does not retrain inside a request. A does not select final models using evaluation results.

## Shared public interfaces to implement first

The lead owns signatures, runtime schemas, and error semantics; agents own implementations in their directories:

- `validate_dataset(table_name, data, manifest)` -> structured validation report.
- `build_snapshot(request, source_snapshot, feature_spec)` -> features, lineage, status.
- `fit_model(training_dataset, model_spec)` -> versioned model bundle.
- `predict(model_bundle, feature_snapshots)` -> prediction contract.
- `evaluate(predictions, labels, evaluation_spec)` -> metric records and case artifacts.
- `replay(as_of_utc, airport, source_snapshot)` -> prediction response without future outcomes.

These are interface sketches, not existing APIs. Agree concrete Python types, serialization, and batch behaviour in the baseline commit. Explanations may be precomputed for replay; they must match the exact model/request.

## Phase 0: shared foundation (lead)

1. Confirm decisions, target branches, data permissions, stack, and scope.
2. Create a real repository or inspect the existing one; preserve current work.
3. Establish package layout, locked dependencies, formatting/type/lint tools, test runner, ignores, and CI.
4. Implement shared schemas, request/prediction JSON examples, and a tiny fixture manifest with A.
5. Register proposed split and source-access plan. Do not expose test outcomes to modelling.
6. Publish baseline commit and create the three agent branches/worktrees.

Exit gate: all agents can import the shared contracts and run a fixture validation command. Commands are documented only once they work.

## Phase 1: parallel vertical slice

| Agent | Work | Acceptance |
| --- | --- | --- |
| A | Inspect real columns; download small METAR/TAF/BTS samples; reconstruct timestamps; create one 3-hour snapshot | Raw/source validation, lineage, and meaningful temporal tests pass |
| B | Build baselines and a tiny model bundle against fixture contracts | Deterministic train/predict and separate cancellation semantics work |
| C | Build evaluator, API, timeline, and replay scaffold against marked fixtures | Contract tests pass; real/fixture and AAR/throughput labels visible |

Lead integrates a real 3-hour request for each airport. No large model search before this gate.

## Phase 2: source and feature expansion

A collects authorised archives with cache/retries, audits coverage and station mappings, builds complete UTC grids, handles TAF amendments, and produces versioned feature/label snapshots for all horizons.

B checks training eligibility and missingness, implements candidate regressors/classifiers, and prepares ablations and calibration without final-test access.

C independently recomputes baseline metrics, adds future-data invariance tests, implements degraded/unavailable states, and reviews prediction/outcome separation.

Exit gate: both airports/all horizons have traceable rows; unresolved records are counted; feature mutation tests pass. If AAR remains unavailable, throughput mode is explicit throughout.

## Phase 3: model selection and product integration

B compares validation candidates and fits calibration artifacts on the designated partition. C tests API/model parity, timeline evidence, alert episodes, and evaluation denominators. A verifies source availability assumptions and manifests. Lead freezes candidate/configuration and reviews the shared failure modes.

Exit gate: a frozen candidate, baselines, uncertainty artifacts, and complete reproducible run manifest exist. The dashboard uses real saved predictions for replay, not mock values.

## Phase 4: locked evaluation and release

C executes the independent held-out evaluator. Lead reviews results and claims; B helps interpret errors without tuning against final-test outcomes. A verifies coverage and input reproducibility. Humans review advisories and select one success, one failure, and one degraded-input case.

Exit gate: clean-environment replay, source-download smoke logs, held-out metrics, calibration checks, failure report, and a short reliable presentation.

## Integration cadence

- Merge small contract-compatible slices regularly, not one large branch at the end.
- Each handoff identifies the base commit, changed interfaces, exact checks, and artifacts.
- Breaking contract proposals include migration and downstream consequences. The lead versions and merges them before consumers switch.
- Dependency requests go to the lead; do not race on root lockfiles.
- For blocked dependencies, continue on pinned fixtures. Clearly separate fixture tests from real-data evidence.
- Check CI after merge and run one pinned end-to-end request for any interface change.

## Resource and release discipline

Start source tests with a bounded station/date range and estimate full data volume before scaling. Cache raw monthly partitions; use serial/paced requests where the provider requires it. Keep model search budgets explicit and log completed/failed runs.

No public deployment is implied by the development assignment. Offline cached replay must work without a live source connection; download automation is verified separately.
