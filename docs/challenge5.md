# Challenge #5 brief (Airbus, AI & Aerospace track)

**Question:** How might we use historical weather observations and flight performance data to predict airport runway capacity reductions and flight delay risk 3–12 hours before severe weather?

**Context:** Severe weather causes most air traffic delays. Capacity is cut reactively when weather arrives, so aircraft hold airborne or wait on taxiways burning fuel, and cancellations cascade. Goal: a Predictive Airport Capacity & Risk Model forecasting hourly arrival acceptance rate (AAR) and departure delay risk 3–12 h ahead.

## Required
- **Multi-source integration:** merge weather observations with flight delay records on timestamp + airport station ID.
- **AAR prediction:** evaluated by RMSE.
- **Delay risk classification:** flag flights at risk of severe delay (>45 min).
- **Dashboard / ATC decision support:** risk scores, historical trends, recommendations for controllers.
- **Automatic processing:** scripts download and process data with no manual steps.

## Must avoid
- **Temporal leakage:** using weather recorded at flight arrival time to predict that flight's delay. Use only data available before the event.
- **Ignoring runway direction:** compute crosswind and tailwind components relative to runway heading, not raw wind speed.
- **Overfitting to one airport:** pipeline must accept any ICAO code in the dataset.
- **Unnormalised delays:** normalise by flight volume when comparing airports.

## Data
- File: `data/raw/Flight_Data_With_Weather_Final.csv` (2023–2025).
- Airports: ATL (KATL) and DFW (KDFW), departures and arrivals.
- Weather fields include air temperature, precipitation, wind speed, peak gust, pressure, snow depth, weather condition codes.
- Assumed runway headings: ATL all operations at 80°, DFW all operations at 180°.

## Judging rubric (each scored 1–5, weighted)
| Criterion | Weight | Strong looks like |
|---|---|---|
| Problem realism | 20% | Named user, narrow workflow, clear status quo and cost |
| Technical soundness | 25% | Works end to end beyond a scripted demo; LLM for reading/explanation, statistics/rules for prediction and constraints |
| Honest evaluation | 20% | Stated metrics vs a baseline, test data described, at least one visible failure case with reason and fix |
| Trust & traceability | 20% | Outputs traceable to timestamped signals or applied rules; visible uncertainty; human stays in control |
| Impact | 10% | Credible before/after measure; measured vs estimated improvement distinguished |
| Time discipline | 5% | Early submission; focused pitch within 3 minutes |

Judges' question: "Where does this fail, and how would your user know?" They reward sound restraint over presentation polish.
