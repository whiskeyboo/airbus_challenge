# Agent work plan

This is the entry point for assignments and current status. The detailed execution plan, task IDs, acceptance checks, and gates are in [PHASE_PLAN.md](PHASE_PLAN.md). Scientific rules remain in `CLAUDE.md`, [TEMPORAL_RULES.md](TEMPORAL_RULES.md), [DATA_CONTRACTS.md](DATA_CONTRACTS.md), [EVALUATION_PLAN.md](EVALUATION_PLAN.md), and [DECISIONS.md](DECISIONS.md).

## People and roles

| Person / role | Responsibility |
|---|---|
| Project lead (you) | Directs Agents 1 and 2 (flights/outcomes and weather/features); approves scientific decisions, scope and the final-test release; designates reviewers and performs manual PR merges |
| Teammate | Directs Agent 3 (modelling, evaluation and product) |
| Integration reviewer | Checks interfaces and evidence, arranges the required leakage audit, and recommends merge; authors do not approve their own scientific changes |

Agent numbers describe software ownership, independent of which person launches an agent. A chat working as Agent 1 remains Agent 1 unless the lead explicitly reassigns it.

## Ownership

| | Agent 1: flights and outcomes | Agent 2: weather and features | Agent 3: modelling and product |
|---|---|---|---|
| Code | `clean.py`, `requests.py`, `targets.py` | `iem.py`, `features.py` | `baselines.py`, `train.py`, `evaluate.py`, `recommend.py`, `explain.py`, `app/dashboard.py` |
| Data writer | Flights, request cohorts, airport-hour outcomes, labels; a separate simulated operational feed if approved | Weather observations/forecasts, feature snapshots, lineage, feature registry, evaluation-only weather slices | Frozen model bundles, saved predictions, explanations, metrics, alert episodes, replay artifacts |
| Tests | `tests/test_flights.py` | `tests/test_iem.py`, `tests/test_leakage.py` | Baseline, training, evaluation, recommendation, explanation and dashboard tests |
| Main obligation | Correct identities, timestamps, cohorts, exclusions and label provenance | Inputs respect each request's exact issue time, with traceable contributors | Honest comparisons, model-fit cutoffs, calibrated outputs and a reviewable product |

The lead/integrator owns shared configuration, contracts, dependencies, and scientific rules. Changes to those files use a focused PR; this planning PR is explicitly requested by the lead. New modules or output writers must be assigned before implementation. Do not let two agents overwrite the same dataset.

Worktrees remain separate: Agent 1 uses `~/ac-flights` / `flights`, Agent 2 uses `~/ac-weather` / `weather`, and Agent 3 uses `~/ac-model` / `model`. Reuse the established absolute `data/` and `.env` symlinks; never commit those links or secrets. Documentation-only branches are separate review work, not a reassignment of an agent's software role.

## Verified status: 31 October 2026

This is a snapshot, not a live status feed. Recheck the linked PR and branch head before resuming an item.

| Deliverable | Evidence / state | Remaining work |
|---|---|---|
| Source downloaders, flights, requests and labels | PR #3 and Phase 2 cohort/ratio work in [PR #8](https://github.com/whiskeyboo/airbus_challenge/pull/8) merged; real four-cohort candidate generated | Agent 2 regenerates matching snapshots/lineage in the candidate directory; integrate the timing follow-up |
| Clear-weather reference and ratio labels | Primary ratio labels generated; `p10-capacity/2` fits 14,035 complete benign training hours available by the cutoff, supporting all 48 cells | Agent 3 consumes the versioned ratio target; strict holdout cohorts intentionally omit airport-fitted ratios |
| P10 and P12 | Accepted and recorded in `DECISIONS.md` | Keep their versions and exclusion evidence visible; do not request P10 approval again |
| Weather tables and request-keyed weather snapshots | Merged on `main` at `9df015c`; processed snapshot/lineage files exist | Verify new cohorts, add demand, finish registry/provenance manifests and evaluate-only weather slices |
| Snapshot lineage | Normalized `(snapshot_key, feature_group)` rows; predictions join through their snapshot row | Preserve that documented mapping; do not require an unnecessary per-prediction expansion |
| Throughput baselines and evaluator | [PR #2](https://github.com/whiskeyboo/airbus_challenge/pull/2) merged at `6547c72`, including follow-up guard fixes | Verify the merged fixes against review probes; retain current-head audit evidence and reproduce the approved development report for G3 |
| Development baseline smoke run | Reviewer reported real validation results in PR #2 | Reproduce an approved development report on merged, fingerprinted inputs |
| Flight baselines, model training, product and locked assessment | Not yet accepted as delivered | Phases 3–7 below |

The project is mainly in Phase 2, with the Phase 3 baseline/evaluation foundation now merged. Model training (`train.py`) is not yet on `main`. The earlier note saying request-keyed feature snapshots did not exist is superseded by the merged feature work. Their existence does not establish that demand features, the full registry, manifest verification or additional cohorts are complete.

## Phases and gates

| Phase | Outcome | Exit gate |
|---|---|---|
| 1. Foundations | Ingested sources, outcome archive, primary requests, weather and initial snapshots | G1: merged producers regenerate; known defects and incomplete interfaces are listed |
| 2. Model-ready integration | Agreed cohort/label/availability contracts and joined, traceable features | G2: a named experiment's inputs pass contract and temporal checks |
| 3. Baselines and development evaluation | Reproducible simple comparators and trusted development metrics | G3: current-head evaluator audit accepted; development report published |
| 4. Models, calibration and transfer | Selected model bundles and prespecified uncertainty/alert policies | G4: model, feature, cohort and policy choices frozen without 2025 selection |
| 5. Replay product and rehearsal | Working recommendations, explanations and dashboard on development cases | G5: failure, missing-input and offline/replay parity checks pass |
| 6. Locked final assessment | One lead-approved assessment batch on Jan–Jul 2025 | G6: fixed ledger claims, immutable outputs and honest final reports |
| 7. Delivery and maintenance handoff | Reproducible release, pitch, limitations and ownership | G7: independent rehearsal and handoff accepted |

Phases overlap where dependencies allow. Agent 3 can build model/product fixtures now; a development report for the primary cohort need not wait for optional operations features. No phase label grants permission to run the locked assessment.

## Start here on the next agent turn

- **Agent 1:** Phase 2 producer work `2-A1a`–`2-A1d` is implemented and generated. Candidate: `data/processed/candidates/agent1_phase2/` (20,337,984 requests; 40,313,856 labels; 45,360 hours; all `real`). `handoff.json` contains hashes, cohort roles and the Agent 2 command. Label schema 0.4.0 uses the disclosed `simulated-outcomes/1` timing; the existing ±2 min tolerance is retained. Schedule-only drift findings were completed before the lead stopped further audits; no additional auditor run was launched. Canonical feature/data bundles await coordinated integration.
- **Agent 2:** `2-A2a`–`2-A2e`: verify the merged request snapshots, add schedule demand, separately gate simulated operations, complete the registry/manifests, and produce evaluation-only slices.
- **Agent 3:** `2-A3a`–`2-A3b`, then `3-A3a`: verify PR #2's merged review fixes, arrange the required current-head audit when the lead lifts any applicable hold, and build flight baselines on fixtures in parallel.
- **Lead/integrator:** track the Agent 2 candidate handoff and downstream WP-D5–WP-D7 decisions. P10/P12 and cohort/ratio contracts are accepted; WP-D1/WP-D2 implementation choices are recorded. Coordinate integration and manual PR merges with the teammate.

## Collaboration and delivery rules

1. Work in the assigned worktree. Sync to merged `main` before new work, preserving existing changes; do not merge someone else's unreviewed branch.
2. Inspect real source columns, read the relevant phase and contract sections, then implement one reviewable task at a time. Use `uv`; do not change dependencies independently.
3. Keep a single writer per shared artifact and publish via temporary-file rename. Cohort/registry changes invalidate dependent snapshots, predictions and manifests; regenerate them together.
4. Run `uv run ruff check --fix` and `uv run pytest`; add temporal/contract tests appropriate to the change. Feature, training and evaluation changes require the lead-designated leakage review on the exact proposed commit.
5. Commit with a clear message and no `Co-Authored-By` trailer. Push the assigned branch to open/update a detailed PR. Never merge or enable auto-merge automatically.
6. Handoff the commit, input/output hashes and row counts, data modes, cohort/split coverage, test/audit evidence, limitations and next task. A local file without merged, reproducible code is not delivered.
7. Raw test-period data may be prepared for approved ingestion, labels and integrity/coverage checks. Model development/evaluation readers must select only development partitions before loading outcome values; 2025 scores, errors and model-selection feedback remain sealed until G6. The ATL schedule-only audit has the narrow scope in `2-A1d`.
8. Do not claim a held or previous audit has run on new changes. Planning work does not lift an audit hold or authorize a final-test release.

Use the checkpoint and handoff templates at the end of [PHASE_PLAN.md](PHASE_PLAN.md). Keep this status table updated in the PR that completes an interface or gate.
