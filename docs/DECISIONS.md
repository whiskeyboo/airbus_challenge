# Decision register

This is the authoritative register for decisions that change scientific meaning or shared interfaces. A proposed default is permission to prepare reversible scaffolding, not evidence of organiser approval or a frozen experiment.

## Established requirements

| ID | Requirement | Basis |
| --- | --- | --- |
| R01 | Three coding agents with an integration lead | User's requested project structure |
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
| P02 | Python backend/data; FastAPI; React/TypeScript UI | Lead | Choose once before dependency lock |
| P03 | Seed 42; UTC internally; schema version 0.1.0 | Lead | Version and record changes |
| P04 | 2023 train; Jan-Jun 2024 validation; Jul-Dec 2024 calibration; 2025 final test | Lead | Confirm coverage and freeze before test access |
| P05 | Main airport prototype may use clearly named throughput while AAR is unresolved | Lead | Does not satisfy true-AAR validation |
| P06 | Separate conditional severe-delay and cancellation models | Lead/B | Preserve probability semantics |
| P07 | Forecast updates hourly; flight lead times anchored to scheduled departure | Lead | Record cohort/version policy |
| P08 | Supplemental data work starts with source documentation and small access tests | Lead/A | Confirm competition permission before incorporating into scored results |

## Open items

| ID | Question | Why it matters | Safe work meanwhile |
| --- | --- | --- | --- |
| O01 | Can organisers supply official hourly AAR? Which label/aggregation do they expect? | Defines the primary regression task | Build target adapters and throughput prototype |
| O02 | Are supplemental flight/weather datasets permitted? | Determines scored-data scope | Audit provided data, prepare adapters and fixtures |
| O03 | Are the supplied headings intended as true or magnetic? | Wind-component reference consistency | Preserve values and explicitly mark direct-comparison assumption |
| O04 | Is live inference required or is historical replay sufficient? | Live schedules/status need separate sources | Build reproducible replay |
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
