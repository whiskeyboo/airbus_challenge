# Decision register

This is the authoritative register for decisions that change scientific meaning or shared interfaces. A proposed default is permission to prepare reversible scaffolding, not evidence of organiser approval or a frozen experiment.

## Established requirements

| ID | Requirement | Basis |
| --- | --- | --- |
| R01 | Single-agent workflow governed by `CLAUDE.md`; three-agent plan removed (see commit 066be0d) | User decision, 2026-10-31 |
| R02 | Ample time; prioritise a comprehensive, rigorous project | User instruction |
| R03 | ATL and DFW; headings 80 and 180 degrees | Challenge 5 brief, pages 5-6 |
| R04 | Forecast 3-12 hours ahead; use 3/6/9/12 as planned horizons | Brief plus reviewed plan |
| R05 | Severe departure delay is strictly >45 minutes | Brief, page 5 |
| R06 | Avoid time leakage and include runway directionality | Brief, page 5 |
| R07 | Preserve AAR/throughput distinction | FAA definition and reviewed methodological correction |

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

## Resolved from the brief (team decisions, 2026-10-31)

Basis: `Autonomous SG 2026_Airbus Track.pdf`, Challenge 5, pages 5-6. These are readings of the brief, not organiser answers; revisit if the organisers say otherwise.

| ID | Question | Decision | Evidence in brief |
| --- | --- | --- | --- |
| O02 | Supplemental public data permitted? | **Yes.** BTS, IEM METAR/TAF and NOAA storm data are in scope. CSV-only results are still reported as a separate ablation. | "ingests publicly available weather observations (METARs/TAFs and NOAA storm logs)"; "Scripts that download and process public datasets automatically" |
| O01 | Official hourly AAR available? | **No.** Nothing is supplied, so the target is the BTS arrival-throughput proxy (P05), scored by RMSE as the brief asks. Labelled "arrival throughput (AAR proxy)". | "Accurate prediction of Arrival Acceptance Rates, measured by Root Mean Squared Error"; provided data has no AAR |
| O04 | Live inference required? | **No.** Historical replay with an issue-time slider in the dashboard. Live is optional stretch only. | "Dashboard that displays risk scores alongside historical trends" |
| O03 | Headings true or magnetic? | **Unspecified; use as given** and compare directly with METAR wind (true north). Documented as an assumption; error is a few degrees. | "All flights take-off and land at heading degree 80 / 180" |

## Open items

| ID | Question | Why it matters | Safe work meanwhile |
| --- | --- | --- | --- |
| O05 | Which repository, agent tools, runtime and hosting environment will be used? | Determines setup and deployment | Prepare portable interfaces; no external deployment |
| O06 | What historical schedule/status knowledge can be evidenced? | Prevents availability overclaims | Declare retrospective simulation and exclude unsupported features |
| O07 | Is sufficient AAR/TAF/flight coverage available for proposed partitions? | Determines defensible evaluation window | Coverage audit only; do not choose periods based on test skill |

The agents must not invent organiser answers. The humans may send these questions; coding agents must not send external messages without explicit authorisation.

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
