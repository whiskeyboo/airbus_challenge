# Decision register

This is the authoritative register for decisions that change scientific meaning or shared interfaces. A proposed default is permission to prepare reversible scaffolding, not evidence of organiser approval or a frozen experiment.

## Established requirements

| ID | Requirement | Basis |
| --- | --- | --- |
| R01 | Three parallel agents under `CLAUDE.md`, coordinated by `docs/WORK_PLAN.md`; replaces the single-agent rule from commit 066be0d | User decision, 2026-10-31 |
| R02 | Ample time; prioritise a comprehensive, rigorous project | User instruction |
| R03 | ATL and DFW; headings 80 and 180 degrees | Challenge 5 brief, pages 5-6 |
| R04 | Forecast 3-12 hours ahead; use 3/6/9/12 as planned horizons | Brief plus reviewed plan |
| R05 | Severe departure delay is strictly >45 minutes | Brief, page 5 |
| R06 | Avoid time leakage and include runway directionality | Brief, page 5 |
| R07 | Preserve AAR/throughput distinction | FAA definition and reviewed methodological correction |
| R08 | Train the severe-delay model on all BTS flights. The provided CSV flights, identified by `in_provided_csv`, are reported as a separate CSV-only comparison | User decision, 2026-10-31 (closes O08) |
| R09 | Final test is 2025-01-01 to 2025-08-01, frozen before any test access. It matches the provided CSV, so the CSV-only comparison is scored on the same months. Aug-Dec 2025 may only appear as a separately labelled extra check on supplemental data | User decision, 2026-10-31 (closes O09) |
| R10 | Keep the current `.env` Drive folder. The folder printed in the brief returns HTTP 401 to scripted access, so it cannot be fetched automatically; the CSV matches the audited profile in `docs/SOURCES.md` (148,273 rows, 123 columns, 2023-01-01 to 2025-07-31) | User decision, 2026-10-31 (closes O10) |

## Proposed implementation defaults

| ID | Default | Owner | Change policy |
| --- | --- | --- | --- |
| P01 | Historical replay before live integration | Lead | Record scope change |
| P02 | Python 3.12 with `uv`; Streamlit dashboard | Lead | Accepted 2026-10-31 (locked in `pyproject.toml`) |
| P03 | Seed 42; UTC internally; schema version 0.1.0 | Lead | Version and record changes |
| P04 | 2023 train; Jan-Jun 2024 validation; Jul-Dec 2024 calibration; 2025 final test (Jan-Jul with provided CSV) | Lead | Accepted 2026-10-31; source of truth `configs/experiment.yaml` |
| P05 | Main airport prototype may use clearly named throughput while AAR is unresolved | Lead | Does not satisfy true-AAR validation |
| P06 | Separate conditional severe-delay and cancellation models | Lead/B | Preserve probability semantics |
| P07 | Forecast updates hourly; flight lead times anchored to scheduled departure | Lead | Record cohort/version policy |
| P08 | Supplemental data work starts with source documentation and small access tests | Lead/A | Confirm competition permission before incorporating into scored results |
| P09 | Persistence uses the last complete hour before T (the hour starting at T - 1h) and is marked as a simulated feed, because BTS publishes months later. Climatology and schedule-only baselines are reported alongside | Integrator | Proposed 2026-10-31 |
| P10 | Benign hours for the clear-weather ceiling: ceiling at least 3,000 ft or none, visibility at least 5 sm, no weather codes (`configs/experiment.yaml`) | Integrator | Accepted 2026-10-31 by the project lead. An hour is benign only if it has at least one METAR and every report meets the rule; corrected or incomplete reports reject it. Reference = 95th percentile per airport x local hour, fitted on 2023 complete hours with no unresolved arrivals (`targets.py`, PR #4) |
| P11 | Airport timezones come from `airportsdata`, with an explicit override for airports it lacks (PBI so far) | Integrator | Proposed 2026-10-31; check coverage on all BTS months |
| P12 | Arrival-throughput coverage (`targets.py`): count resolved wheels-on per UTC hour; each unresolved arrival adds 1 to `n_unresolved` in every UTC hour it could fall in (unbounded: its local service date). Cancelled and diverted-away flights are not arrivals. `coverage_status` is `complete_for_source_scope` if `n_unresolved` = 0, `partial` if > 0, `missing` if the source month is absent. An hour is label-eligible unless missing or `n_unresolved / (n_resolved + n_unresolved)` > 0.05; ineligible hours keep a null target with `exclusion_detail`, never zero. A month with > 1% quarantined arrivals is flagged degraded, not excluded. Severe-delay labels are per flight. A flight with a missing flight number keeps a source-based `flight_id` and is counted if its times resolve | Integrator | Accepted 2026-10-31 on the real build: 45,360 airport-hours, 197 partial, 60 excluded at 5% (KATL 26, KDFW 34; 197 at 0%, 48 at 10%). Exclusion rate 0.29% in IFR/thunderstorm hours vs 0.12% otherwise: concentrated in bad weather but about 10 hours, so metrics are reported with exclusions visible |
| P13 | Simulated availability: METAR and TAF usable 10 min after observation/issue (`availability_basis = simulated`). Corrected (COR) METARs have unknown send time, so `available_at` is null and they are never used | Integrator | Accepted 2026-10-31 (`iem.py`). A 5 min latency is only a separately labelled sensitivity check. Model-card cost of dropping CORs: 2,699 of 181,056 feature rows (1.5%) use a METAR about 128 min old instead of about 68, and 116 of the 132 `metar_stale` rows come from it |
| P14 | `metar-select/1`: METAR windows select on `available_at` in (T-6h, T]; latest report by observed time, official preferred over MADIS on ties; latest older than 3 h makes METAR features null (`metar_stale`) | Integrator | Accepted 2026-10-31 (`features.py`) |
| P15 | `taf-select/1`: latest bulletin with `available_at` <= T (amendments/corrections supersede). Bulletins with conflicting versions are skipped for the previous eligible one (`taf_conflict_fallback`). A target window past the bulletin end is missing (`taf_uncovered`), never filled from another bulletin. Multi-hour windows use worst case | Integrator | Accepted 2026-10-31 (`features.py`) |
| P16 | Wind components: calm = 0; variable = crosswind at full speed, METAR head/tailwind null, TAF tailwind at full speed on both ends; missing = null. Gust components fall back to sustained speed. Headings as given (O03) | Integrator | Accepted 2026-10-31 (`features.py`) |

## Resolved from the brief (team decisions, 2026-10-31)

Basis: `Autonomous SG 2026_Airbus Track.pdf`, Challenge 5, pages 5-6. These are readings of the brief, not organiser answers; revisit if the organisers say otherwise.

| ID | Question | Decision | Evidence in brief |
| --- | --- | --- | --- |
| O02 | Supplemental public data permitted? | **Yes.** BTS, IEM METAR/TAF and NOAA storm data are in scope. CSV-only results are still reported as a separate ablation. | "ingests publicly available weather observations (METARs/TAFs and NOAA storm logs)"; "Scripts that download and process public datasets automatically" |
| O01 | Official hourly AAR available? | **No. Confirmed by organisers 2026-10-31:** BTS hourly arrival counts are an acceptable stand-in, RMSE in arrivals per hour. Labelled "arrival throughput (AAR proxy)". | "Accurate prediction of Arrival Acceptance Rates, measured by Root Mean Squared Error"; provided data has no AAR |
| O04 | Live inference required? | **No.** Historical replay with an issue-time slider in the dashboard. Live is optional stretch only. | "Dashboard that displays risk scores alongside historical trends" |
| O03 | Headings true or magnetic? | **Unspecified; use as given** and compare directly with METAR wind (true north). Documented as an assumption; error is a few degrees. | "All flights take-off and land at heading degree 80 / 180" |

## Open items

| ID | Question | Why it matters | Safe work meanwhile |
| --- | --- | --- | --- |
| O05 | Which repository, agent tools, runtime and hosting environment will be used? | Determines setup and deployment | Prepare portable interfaces; no external deployment |
| O06 | What historical schedule/status knowledge can be evidenced? | Prevents availability overclaims | Declare retrospective simulation and exclude unsupported features |
| O07 | Is sufficient AAR/TAF/flight coverage available for proposed partitions? | Determines defensible evaluation window | Coverage audit only; do not choose periods based on test skill |

The agents must not invent organiser answers. The humans may send these questions; coding agents must not send external messages without explicit authorisation.

## Pending delivery decisions

The lead-requested [phased plan](PHASE_PLAN.md#2-lead-decisions-and-dependencies) names WP-D1–WP-D7 for coordination. Status is recorded per row; entries not explicitly marked accepted remain pending. Record the selected policy and evidence in this register before dependent real fitting or final release:

| Plan ID | Decision needed | Dependency |
|---|---|---|
| WP-D1 | **Selected 2026-10-31 under the lead's instruction to complete Agent 1 using best judgment, following the concrete timing proposal:** `simulated-outcomes/1`: hourly outcomes at hour end +10 min; delay at departure +10 min; cancellation at latest resolved scheduled/actual flight time +24 h. Mark `availability_basis = simulated`; empirical BTS publication times remain unknown. Labels and P10 fitting require availability at/before the declared fit cutoff. | Implemented simulation; every model run must declare and enforce it |
| WP-D2 | **Selected 2026-10-31 under the same delegated completion instruction:** retain the existing ±2 min clock/duration tolerance. The numeric rule and quarantine results do not change, so the existing raw archive does not need reconstruction solely to update decision status. | Future cleaner manifests and candidate handoff record the selected rule |
| WP-D3 | **Accepted 2026-10-31 by the project lead:** CSV-only sample-member departures and paired delay/cancellation labels; LOAO requests include source and held-out airports, with training restricted to other airports and scoring to the named held-out airport. `DATA_CONTRACTS` §6 records the versioned manifest interface. | Approved cohort production; consumer-side fit/score guards still required |
| WP-D4 | **Accepted 2026-10-31 by the project lead:** add primary-cohort `throughput_over_clear_weather_p95` labels under `throughput`; `missing_capacity_reference` and `nonpositive_capacity_reference` map to canonical `missing_outcome`. Ratio extension introduced in label schema/version 0.3.0 (0.4.0 adds simulated timing); preserve P12 reasons and omit held-out-airport-normalized ratio labels in strict LOAO. | Approved ratio-label producer; baseline/model support remains downstream work |
| WP-D5 | Timestamped simulated operational-feed latency, coverage and freshness policy | Operations-context features |
| WP-D6 | Strict zero-shot transfer comparator and treatment of held-out-airport normalizers | LOAO comparison |
| WP-D7 | **Accepted 2026-10-31 by Agent 3's director; lead confirmation pending.** Policy `wp-d7-v1` (`calibrate.py`): H2 2024 only, by target time: calibration-fit Jul 1–Oct 1 2024, threshold-assessment Oct 1 2024–Jan 1 2025; 2025 never read. Isotonic per model and binary target (severe delay, cancellation), saved as JSON breakpoints. Throughput: per-airport split-conformal additive margin m ≥ 0 so 80% fall in [p10−m, p90+m] (null if no p10/p90); act when widened p10 < 0.70 × clear-weather p95, tightened by 0.05 to ≥ 0.50 until ≥ 50% of act-hours have actual ratio < 0.70; watch at estimate < 0.85 × p95. Severe delay (calibrated p ≥ threshold): act = lowest threshold with precision ≥ 0.5, watch ≥ 0.3, per airport, pooled when < 50 positives; null if unreachable and never alerts. Episodes: merge alert hours with ≤ 1 h gaps; hit = true event within ±1 h; true event = actual ratio < 0.70, or hourly severe-delay share ≥ act threshold. `degraded` fallback only if validation RMSE/Brier (n ≥ 30) ≤ climatology / `baseline_conditional_rate_v1` on the same rows. | Frozen calibrators, recommendations and alert metrics |

P10, P12, WP-D3 and WP-D4 are accepted. WP-D1/WP-D2 have the explicitly disclosed implementation choices above; WP-D7 is accepted pending lead confirmation; WP-D5 and WP-D6 remain pending. The planning PR does not reopen those decisions, lift an audit hold, approve model scores, or release the 2025 locked assessment.

Lead execution instruction, 2026-10-31: Agent 1 is to focus on implementing and delivering features, with no further auditor or mutation-audit runs unless the lead re-enables them. Normal Ruff/pytest checks continue. No unperformed audit is claimed as completed.

## Decision entry template

```text
ID / date / owner:
Question and options:
Decision and rationale:
Status: proposed | accepted | superseded
Evidence or organiser response:
Affected targets/contracts/configs:
Evaluation consequences:
Supersedes:
```

If unresolved semantics affect only one part of the system, continue independent work. Do not make a blocked label question a reason to stop fixtures, ingestion, delay models, or interface development.
