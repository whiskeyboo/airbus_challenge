# Three-minute pitch: airport throughput and delay risk

**The decision (20 seconds).** A flow coordinator at ATL or DFW needs 3–12 hours of warning. We forecast hourly arrivals and severe departure-delay risk, with a range and the weather evidence behind each forecast. Arrivals are an AAR proxy: they reflect demand as well as capacity.

**The approach (25 seconds).** We combine reporting-carrier schedules with weather available at forecast time, including runway-relative headwind, tailwind and crosswind. We fit on 2023, select models using early 2024, and compare them on late 2024. Historical schedule knowledge and source-release times are simulated.

**Development results (45 seconds).** In our controlled comparison, adding weather and runway components reduced late-2024 arrival forecast error (RMSE) from **6.90 to 6.79 arrivals/hour at ATL**, and **9.58 to 9.24 at DFW**. Schedules explain most of the signal; weather adds a modest improvement. Training on the other airport also beat the source-fitted schedule baseline in both directions, although performance was worse than training locally. The broader BTS delay model scored better than CSV-only training on the same sparse CSV sample. These are development comparisons, not a final test, and we do not claim statistically significant gains.

**Show the product and a failure (40 seconds).** Start with the routine-weather case: here are the forecast, model range and source times. Then open DFW on 27 May 2024. Six hours ahead, the dashboard's existing model predicted **67 arrivals**, against **85 scheduled**. Reveal historical outcomes: only **4** landed. The weather forecast already indicated thunderstorms. This is a real validation miss, not an independent final-test example. The coordinator needs the uncertainty and failure evidence, not just a confident number.

**Missing information and limits (35 seconds).** Open the no-prediction case: it says forecasts are unavailable instead of inventing zero arrivals. Stale-weather cases are also disclosed, but the existing model's degraded fallback is not validated. Severe-delay alerts did not reach our 50% precision target. Arrival alerts can flag quiet hours because demand affects the target. This is a historical demonstration; validation influenced model selection, and the locked 2025 test has not been run. A language model can write an explanation, but it does not calculate the forecast or decide the alert.

**The takeaway (15 seconds).** The working product gives a coordinator an early forecast, its supporting evidence and a visible reason to be cautious. We can demonstrate the whole path, including a serious miss and missing information. Operational use would require prospective validation and real feed agreements.

The controlled comparisons above are from [the Phase 3/4 experiment report](../reports/dev/phase34_experiments.md), which includes confidence intervals, denominators and run IDs. They are separate from the existing combined model used for the dashboard replay. Earlier primary-model and weather-slice results remain in [reports/RESULTS_dev.md](../reports/RESULTS_dev.md); assumptions and exceptions are in [LIMITATIONS.md](LIMITATIONS.md).

## Numbers for questions

All values below use H2 2024 development data. Each experiment compares models on its own common support; do not pool these rows or treat cross-experiment differences as paired tests.

| Comparison | ATL | DFW | Meaning |
|---|---:|---:|---|
| Schedule/calendar model | 6.90 | 9.58 | Arrival RMSE, touchdowns/hour; lower is better |
| Add weather and runway components | 6.79 | 9.24 | Controlled weather comparison |
| Add simulated operations | 6.80 | 9.10 | Separate optional feed experiment; not the dashboard model |
| Model trained at the other airport | 9.67 | 12.48 | Held-out airport RMSE |
| Source-fitted transfer schedule baseline | 10.15 | 13.52 | Comparator for the preceding row |
| CSV-only delay model | 0.182 | 0.196 | Average precision on CSV sample; higher is better |
| Existing BTS delay model on identical CSV sample | 0.212 | 0.225 | Separate paired analysis; no refit |

The CSV is roughly 1% of the broader source. Its estimates have greater uncertainty; Brier confidence intervals overlap. The normal evaluator provides arrival/Brier intervals; average-precision intervals are not implemented. The corrected combined calibration uses arrival act/watch ratios **0.70 / 0.85**. Those are fractions of a reference, not probabilities or guaranteed capacity.

## Rehearsal cases

Run `uv run streamlit run app/dashboard.py`. Select **Combined arrival and flight-risk model** (`lgbm_dev`) under **Forecast set**. In **Explore past cases**, find the named example and click **Open this case**, then return to **Overview**. Times below are UTC; the sidebar also displays airport local time. No API key is needed for the regular summary.

| Order | Example and issue time | What to do and say |
|---|---|---|
| 1 | **KDFW routine weather, no alert** — 2024-05-15 10:00 | Start with **Show historical outcomes** off. Show the landings/delay cards, forecast range, and weather/source details. Say: “No alert under these rules is not a guarantee.” |
| 2 | **KDFW thunderstorms, arrivals collapse around 00Z** — 2024-05-27 18:00 | Show the six-hour forecast, then the TAF covering 2024-05-28 00:00 UTC. Turn on **Show historical outcomes** only after explaining what was known. Point out 67 predicted, 85 scheduled and 4 actual arrivals. |
| 3 | **KATL morning thunderstorms (no predictions)** — 2023-08-11 08:00 | Opening another case resets the outcomes toggle. Explain that 2023 is the training period, so this development run has no forecasts here. Missing predictions are not zero arrivals; weather evidence can still be available. |
| Backup | **KDFW stale weather report** — 2024-01-20 20:00 | Expand weather details and show `metar_stale`. Say: “This model still emits degraded predictions, so we disclose that the missing-weather fallback is not validated.” |

Avoid using the old KATL 2024-01-15 18:00 example as an all-clear: its overnight horizons raise arrival alerts. Keep the optional **Generate a written summary** button out of the essential demo; it depends on suitable inputs and API configuration.

All four cases were checked with Streamlit's real-data interaction harness; the [verification record](../reports/dev/dashboard_rehearsal.json) includes the displayed cards, storm outcome reveal and missing-data behavior. The dashboard now shows the assessment computed from current rules, without an older saved assessment that could disagree. Team members should still practise the spoken handoff and click timing; only the six timed paragraphs are the spoken script.

## Submission

The organiser's 31 October “Submission & Judging” email directs teams to [boardingpass.work/experience](https://boardingpass.work/experience), sign in, choose their track and include their table number. It allows **one submission per table**; judges visit each table after submissions close. The email does not state a deadline or the form's required fields. Confirm those with the on-site organisers if the portal is not loading.
