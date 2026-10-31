# Three-minute pitch: airport throughput and delay risk

**The decision (20 seconds).** A flow coordinator at ATL or DFW needs 3–12 hours of warning. We forecast hourly arrivals and severe departure-delay risk. Our arrival measure is an AAR proxy: it reflects demand as well as capacity.

**The approach (25 seconds).** We combine reporting-carrier schedules with weather available at forecast time, including runway-relative headwind, tailwind and crosswind. Historical schedule knowledge and source-release times are simulated; this is not a live feed.

**Development results (45 seconds).** In the second half of 2024, arrival RMSE was **6.92 arrivals/hour at ATL**, versus **8.78** for climatology and **8.46** for schedule-only. At DFW it was **9.17**, versus **13.10** and **13.00**. Severe-delay average precision was **0.234 at ATL**, versus **0.123** for the conditional-rate baseline and **0.204** for logistic regression. At DFW it was **0.213**, versus **0.157** and **0.205**. These are development results, not a final test.

**A visible failure (40 seconds).** On 27 May 2024 at DFW, a forecast six hours ahead predicted **67 arrivals** in an hour when **4** reporting-carrier aircraft landed; **85** were scheduled. This was a validation case used during model selection. Thunderstorm-hour RMSE was **15.07 at ATL** and **22.15 at DFW**, versus **6.71** and **8.90** in non-thunderstorm hours. These are small descriptive slices across repeated horizons, without confidence intervals; non-thunderstorm does not necessarily mean clear.

**The product and its limits (40 seconds).** Show the DFW storm replay and its issue-time weather, then an unavailable-prediction case. The 50% precision target for a severe-delay “act” alert was not reached at either airport; DFW has a lower-precision “watch” setting. The throughput act rule flagged about 56% of assessed hours, often quiet hours. An LLM can explain code-computed facts but does not make the decision. H1 2024 influenced early stopping despite the recorded January fit cutoff; some degraded predictions lack a validated fallback; uncalibrated runs use provisional thresholds. The 2025 locked test has not been run.

Detailed development results are in [reports/RESULTS_dev.md](../reports/RESULTS_dev.md); assumptions and exceptions are in [LIMITATIONS.md](LIMITATIONS.md).

## Rehearsal cases

Run `uv run streamlit run app/dashboard.py`, choose a run, and use UTC issue times. The real-data dashboard was exercised on:

- **Thunderstorm:** KDFW, 2024-05-27 18:00. At the six-hour horizon, 67 predicted arrivals versus 4 realised. Enable hindsight only when showing what happened.
- **Normal comparison:** KATL, 2024-01-15 18:00.
- **Stale weather:** KDFW, 2024-01-20 20:00. The dashboard displays `metar_stale` and says METAR features are blank.
- **No prediction:** KATL, 2023-08-11 08:00; the dashboard explains that development predictions are unavailable.

## Submission

The organiser's 31 October “Submission & Judging” email directs teams to [boardingpass.work/experience](https://boardingpass.work/experience), sign in, choose their track and include their table number. It allows **one submission per table**; judges visit each table after submissions close. The email does not state a deadline or the form's required fields. Confirm those with the on-site organisers if the portal is not loading.
