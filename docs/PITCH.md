# Three-minute pitch outline

Fill the `[ ]` slots from `reports/RESULTS_dev.md`. Development numbers only (2023 train, 2024 scored); the locked 2025 test has not been run.

**1. The user and the decision (20 s).** A hub flow coordinator at KATL or KDFW, 3-12 h before a bank. Question: will arrival throughput drop, and which departures risk a delay over 45 min? There is no published hourly AAR, so we forecast BTS wheels-on per hour, the arrival throughput (AAR proxy), and say it reflects demand as well as capacity.

**2. No leakage, by construction (30 s).** Every forecast has an issue time T. Features use only METARs observed and TAFs issued by T, with runway-relative head, tail and crosswind. Splits are by time: train 2023, early stopping on H1 2024, calibration H2 2024, 2025 sealed behind a one-shot ledger. Tests show that changing data after T leaves features at T unchanged.

**3. Baselines first (40 s).**
- Throughput RMSE (touchdowns/hour, H2 2024): LightGBM `[ ]` vs climatology `[ ]`, seasonal persistence `[ ]`, schedule-only `[ ]`. Skill vs seasonal persistence `[ ]` (CI `[ ]`).
- Severe delay: PR-AUC 0.23 (KATL) / 0.21 (KDFW) against 9% / 12% prevalence, vs conditional-rate `[ ]` and logistic `[ ]`.

**4. Where it fails, and how the user knows (50 s).**
- Severe delay cannot single out flights. WP-D7 requires 50% precision to "act": never reached. KDFW "watch" reaches 30% precision with 7% recall (about 74 flags a day); KATL reaches neither. The product says so and abstains instead of alerting.
- Throughput "act" against the clear-weather ceiling fires on about 56% of hours: it mostly flags quiet hours. Say so; the fix is a schedule-relative rule.
- Weather-slice results: thunderstorm hours `[ ]` vs clear hours `[ ]`. Bad weather is about 2% of hours, so these intervals are wide.
- One worst miss from `failure_cases_dev.json`: what was known at T, and whether an advisory was possible.
- Every forecast carries `status` and `reason_codes`. Missing or stale weather is shown, never imputed silently.

**5. The product (30 s).** Historical replay dashboard with an issue-time slider. It shows the forecast and interval, source ages, code-computed recommendations under the WP-D7 thresholds, and a brief that only restates computed facts ("insufficient data" when inputs are missing). SHAP drivers are associations, not causes.

**6. What's next (10 s).** Lead release of the locked 2025 test, the label-release policy (WP-D1) and a real feed-latency policy (WP-D5). See [LIMITATIONS.md](LIMITATIONS.md).
