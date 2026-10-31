# Assignment: Agent A — data and temporal correctness

You own source ingestion, validated data, historical timestamp reconstruction, labels, feature snapshots, and source lineage. Read root `AGENTS.md` and its linked specifications before editing. Work only in your ownership boundary unless the integration lead assigns a shared change.

## First work package

1. Inspect actual source files and report columns, row grain, coverage, and missingness. Reproduce the provided-file audit; do not infer columns from filenames.
2. Review open decisions. Prepare supplemental adapters, but do not claim competition permission or AAR access.
3. Coordinate concrete schema/fixture needs with the lead before B/C depend on them.
4. Test small METAR, TAF, and BTS retrieval/parse samples. Preserve raw bytes and access-test evidence. Do not scale before validating timestamps and estimating download volume.
5. Implement one request per airport at the 3-hour horizon, including lineage and explicit availability basis.
6. Supply fixtures for TAF amendment, midnight/DST, cancellation, source gap, and missing wind direction.

## Subsequent deliverables

- Cached, retry-aware, rate-limited, resumable downloaders with a documented local-source fallback.
- Official raw-to-canonical field mappings and station/airport mapping checks.
- BTS local-clock reconstruction with independent duration checks and quarantine reporting.
- Complete airport UTC grids; zero only with adequate source completeness.
- Separate immutable outcome labels and inference-safe features.
- Archived TAF selection and segment expansion without future amendments.
- METAR trends and target-period forecast features, with runway-relative components.
- Coverage/source-quality report, including the effect of excluded records.
- No-op/reproducible reruns on the same pinned inputs.

## Tests you own

Temporal and timestamp tests in `docs/TEMPORAL_RULES.md`, unit conversions, duplicate handling, raw schema assertions, missing versus zero, TAF amendments, and exact target boundaries. Implement meaningful expected outcomes, not just schema snapshots.

## Definition of done

Both airports/all horizons produce reproducible validated snapshots and separately joined labels with manifests. A future-data mutation cannot change an earlier snapshot. The lead can run a documented raw-to-feature slice. Report unresolved availability assumptions instead of concealing them.

Post a handoff with exact commands and artifacts. Do not select a model or inspect final-test model errors to change feature design.
