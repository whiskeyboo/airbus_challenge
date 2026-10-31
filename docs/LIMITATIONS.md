# Limitations: where this fails, and how the user would know

Status at commit `33e8faf`, plus the first real development run (2026-10-31; dev splits only, no 2025 outcomes). Decision IDs refer to [DECISIONS.md](DECISIONS.md); gates to [PHASE_PLAN.md](PHASE_PLAN.md).

## Target meaning
- **There is no true AAR.** The target is arrival throughput (AAR proxy): BTS reporting-carrier wheels-on per UTC hour (O01). It reflects demand as well as capacity, so a quiet hour that is not a capacity cut still scores low. Non-reporting carriers (most cargo, GA) are absent.
- **The capacity ratio is experimental.** It divides by a clear-weather p95 per airport x local hour, fitted on 2023 benign hours only (P10). Its label target and missing-reference mapping are still pending (WP-D4).
- Runway headings are taken as given (80°/180°) and compared with true-north METAR wind; whether they are true or magnetic is unspecified, so components may be off by a few degrees (O03).

## Data scope and coverage
- **Partial hours (P12).** An hour is excluded if more than 5% of its arrivals cannot be placed in it. That removes 60 of 45,360 airport-hours (KATL 26, KDFW 34). The rate is 0.29% in IFR/thunderstorm hours vs 0.12% otherwise, so exclusions fall in bad weather. Excluded hours keep a null target with `exclusion_detail`, never zero. Persistence rows built from a partial source hour carry `source_hour_partial`.
- **The provided CSV is a sparse flight sample** (about 6 ATL arrivals/day, no wind direction, weather recorded at flight time). It is used only for the separate CSV-only comparison, never for airport counts or features, and never spliced into the main score (R08).
- **Unexplained 2025 ATL volume drop.** Teammates report January ATL volume of about 770 arrivals/day in January 2025 vs 848 in January 2024. This could shift the train/test distribution. A schedule-only drift audit (2-A1d) is planned but not done.
- Corrected (COR) METARs have unknown send times and are never used. About 1.5% of feature rows therefore use an older METAR (P13).
- Only two airports. Leave-one-airport-out is a limited transfer stress test, not evidence of global skill.

## Temporal assumptions (simulated, not live)
- **Label release.** BTS publishes months after the fact, but labels are treated as known at the fit cutoff. The release policy is pending (WP-D1). Until then, fitted references (including the P10 p95) may have earlier access to outcomes than a live system would.
- **Schedules** are BTS schedules as flown, treated as known in hindsight (`retrospective_schedule`). Late schedule changes were not captured as they happened.
- **Persistence is a simulated feed with zero latency** (`simulated_feed`, `FEED_LATENCY_H = 0` in `baselines.py`). This assumption flatters persistence. The feed latency policy is pending (WP-D5).
- **METAR/TAF** are usable 10 min after observation or issue (P13, simulated). A METAR older than 3 h makes its features null (`metar_stale`, P14). A TAF that does not cover the target is `taf_uncovered` and is never filled from another bulletin (P15).

## Severe delay
- The probability means departure delay > 45 min **given that the flight operates**. Cancelled flights are excluded, not counted as negatives, and the cancellation rate is reported separately (P06). It is not a probability over all scheduled flights.

## What the first real development run showed
Numbers below come from producer output (`train.py`, `calibrate.py`) on 2023/2024 data, not yet from the evaluator report with confidence intervals.
- **Severe delay cannot support flight-level alerts.** On calibration rows (H2 2024; validation was used for early stopping, so it is partly in-sample), PR-AUC is 0.234 at KATL (prevalence 8.9%) and 0.214 at KDFW (12.0%): roughly 2x better than chance at ranking. Brier is only about 4-6% better than predicting the base rate. Recall at 50% precision is about 0.
- **WP-D7 therefore sets no alerts where the evidence is missing.** On Oct-Dec 2024 (not used for fitting), no "act" threshold reaches 50% precision at either airport, and no "watch" threshold reaches 30% at KATL. KDFW "watch" (calibrated p >= 0.11) has 30% precision and 6.8% recall at about 74 flagged flights a day. `recommend.py` never alerts on a null threshold; the user sees the abstention reason `precision_target_not_reached`.
- **Arrival throughput (AAR proxy) is learned mostly from the schedule.** The top LightGBM gains are scheduled arrivals/departures around the target hour; weather features (TAF ceiling, freezing precipitation) rank lower. Whether weather adds skill is answered by the comparison with `baseline_schedule_v1` and the thunderstorm/IFR slices, not by importance.
- **Bad-weather hours are rare.** Thunderstorms occur in about 2% of target hours (KATL 1.8%, KDFW 2.0%), IFR in 9.0% / 5.6%, strong crosswind in 0.1-0.2%. Slice metrics for these hours have wide intervals; strong crosswind is close to anecdotal.
- **Persistence has gaps.** Persistence and seasonal persistence are `unavailable` on 128 of 70,212 throughput rows, where the source hour was excluded or empty.
- `train.py` marks 452 throughput rows `degraded` without a validated fallback (contract §8); the trigger needs confirming with its owner.

## Baselines
- Ordinary persistence is weak 3–12 h ahead. Validation RMSE (touchdowns/hour) for climatology / seasonal persistence / schedule-only / persistence:
  - KATL 6.75 / 7.14 / 7.47 / 38.2;
  - KDFW 9.87 / 10.91 / 11.95 / 33.0.
- **These are teammate development smoke-run numbers, not an accepted G3 report.** Skill is reported against climatology and seasonal persistence; every required baseline is still shown.

## Fallbacks
- No fallback is validated yet. A sparse climatology cell (< 8 rows, `climatology_cell_sparse`), an airport with no train history (`no_train_history`) or an incomplete persistence source hour gives `unavailable` with reason codes, not `degraded`. `degraded` is reserved for a fallback validated under WP-D7.

## Process limits
- **Audits are paused, so G3 is not accepted.** A passing test count is not gate acceptance.
- **The locked 2025 test has not been run.** It needs the lead's release after the model is frozen (G6; `--locked-test --approved-by`). Each claim is written exclusively to `data/locked_runs/` and mirrored to the committed `reports/locked_runs/`. A different machine with its own `data/` is a procedural risk until the mirror is pushed and pulled.
- SHAP drivers are associations, not causes.
- The LLM brief (`explain.py`) only restates facts computed by code, cites input timestamps, says "insufficient data" when inputs are missing, and falls back to a template if the LLM fails. It never computes numbers.
- No fuel, cost or prevented-delay benefit is measured. A replay alone cannot establish one.

## How the user would know
- **Per prediction:** `status` (`available` / `degraded` / `unavailable`) and `reason_codes` (for example `source_hour_partial`, `climatology_cell_sparse`, and the assumption marker `simulated_feed`). Weather snapshots carry their own status and codes (`metar_stale`, `taf_uncovered`). The dashboard shows both next to each forecast and warns when a row is unavailable.
- **Per run:** `artifacts/<run_id>/manifest.json` has status and reason-code counts, `fit_cutoff_utc`, data hashes and `commit_dirty`.
- **Per report:** `reports/metrics_dev.json` has `scoring_scope` (what was scored, with cutoffs), `availability_basis`, denominators, `n_degraded`, and the worst misses.
- **Per label:** P12 exclusion counts are in `data/labels/labels.manifest.json`; each excluded hour keeps its `exclusion_detail`.
- **Data mode:** every table and report carries `data_mode` (`real` or `fixture`). Fixture reports go to `reports/fixture/`, and the dashboard prints the data mode and commit beside each metrics file.
