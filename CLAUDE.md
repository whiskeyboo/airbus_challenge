# Airbus Challenge #5: Predictive Airport Capacity & Delay Risk

Hackathon: Autonomous SG 2026 (AI & Aerospace track). Forecast hourly arrival throughput (AAR proxy) and severe departure-delay risk (>45 min) 3–12 h ahead for KATL and KDFW.

Brief and rubric: `docs/challenge5.md`. Who builds what: `docs/WORK_PLAN.md`. Phase tasks, dependencies and delivery gates: `docs/PHASE_PLAN.md`. Detailed reference specs in `docs/` (PROJECT_SPEC, TEMPORAL_RULES, DATA_CONTRACTS, EVALUATION_PLAN, SOURCES, DECISIONS). If they conflict with this file, this file wins.
Splits, horizons and targets: `configs/experiment.yaml`. Airports, headings, timezones, weather stations: `configs/airports.yaml`.

## Data sources
- **Provided CSV** `data/raw/Flight_Data_With_Weather_Final.csv` (2023-01 to 2025-07). From a public Google Drive folder, ID in `.env` as `DATA_GDRIVE_FOLDER_ID`; `download.py` fetches it with `gdown --folder` into `data/raw/`. It is a sparse flight sample (~6 ATL arrivals/day), has no wind direction, and its weather is recorded at flight time. Use it only for the separate CSV-only comparison; never for airport counts or as weather features.
- **BTS On-Time Performance** (full reporting-carrier flights) for hourly arrival throughput, volume and severe-delay labels (`docs/DECISIONS.md` R08).
- **IEM METAR** (observations) and **IEM TAF** (forecasts) for weather features, including wind direction.
- Supplemental public data is in scope per the brief (`docs/DECISIONS.md` O02). Still report the CSV-only ablation separately; never splice the two into one score.

## Judging (optimise for this)
Technical soundness 25%, Problem realism 20%, Honest evaluation 20%, Trust & traceability 20%, Impact 10%, Time 5%.
Judges ask: "Where does this fail, and how would your user know?" Working end-to-end pipeline + honest numbers beat UI polish.

## Stack
- Python 3.12, `uv` only (`uv add`, `uv run`). Never pip install.
- pandas, pyarrow, scikit-learn, lightgbm, shap, streamlit, plotly, matplotlib, pyyaml, gdown, python-dotenv, openai, airportsdata.
- Dev: ruff, pytest.
- Package lives in `src/airbus_challenge/`. Dashboard in `app/dashboard.py`.

## Hard rules (domain)
1. **No leakage.** At issue time T = target − h, features may only use data available by T: METAR observed ≤ T, TAFs issued ≤ T (valid after T is fine). Never use target-hour weather, the CSV's attached weather for that flight, or the target flight's own delay/arrival/cancellation fields. Pytests must show that adding or changing data after T leaves the features at T unchanged. Timestamps are timezone-aware UTC; BTS local HHMM clocks must be converted per `docs/TEMPORAL_RULES.md` §4.
2. **Runway directionality.** Never use raw wind speed alone. θ = wind_dir − runway_heading (radians); headwind = WS·cos θ; tailwind = max(0, −headwind); crosswind = |WS·sin θ|. Same for gusts. Headings from `configs/airports.yaml`; also compute the reciprocal (h+180). Keep calm, variable and missing direction distinct.
3. **Generalise.** Every function takes an ICAO code; no airport hard-coded outside `configs/airports.yaml`. Airport is a categorical feature.
4. **Normalise delays** by flight volume (share of departures >45 min, mean delay per flight), never raw totals across airports.
5. **AAR is a proxy.** No true AAR exists. Target = BTS arrivals (wheels-on) per UTC hour, plus ratio to a clear-weather ceiling (95th pct for that airport-hour in benign weather as defined in `configs/experiment.yaml`, fitted on train only). Label it "arrival throughput (AAR proxy)" everywhere; it reflects demand as well as capacity.
6. **Severe delay** = departure delay strictly > 45 min (45 is negative), among operated flights only. Cancelled flights are excluded, not negatives; report cancellation rate alongside. The probability is conditional on the flight operating.
7. **Time-based split only.** Train 2023, validation H1 2024, calibration H2 2024, test 2025 (see `configs/experiment.yaml`). No shuffling. Nothing (scalers, thresholds, calibration, tuning) is fitted on test. Also a leave-one-airport-out test.
8. **Baselines first, by task.** Throughput uses persistence (the last complete hour before T, starting at target − h − 1; marked as a simulated feed), train-only climatology, seasonal persistence and schedule-only comparators. Severe delay uses a smoothed train-only conditional-rate baseline and logistic regression; cancellation has a separate baseline. Compare every model with the required baselines for its own target on the same declared cohorts and scoring rows (`docs/EVALUATION_PLAN.md`).
9. **LLM / non-LLM split.** Numbers, thresholds and recommendations come from code (rules in `recommend.py`). The LLM in `explain.py` only writes a short brief from given prediction + SHAP drivers + input timestamps, cites them, and says "insufficient data" when inputs are missing. It never computes. SHAP drivers are associations, not causes.

## Pipeline modules
download.py → clean.py → requests.py → targets.py → iem.py → features.py → baselines.py → train.py → evaluate.py → recommend.py → explain.py → app/dashboard.py
- Intermediate data as parquet in `data/interim/`, `data/processed/` (gitignored). Every data-producing module runs as `uv run python -m airbus_challenge.<module>`.
- `evaluate.py` writes `reports/metrics.json` and figures: RMSE/MAE for the AAR proxy per horizon (3/6/9/12) and airport vs baselines; PR-AUC, recall@precision, Brier and reliability for delay >45, with prevalence and denominators; 3 worst misses with explanation.
- Run the `leakage-auditor` subagent after changes to features, training or evaluation.

## Working style
- Concise code. No defensive boilerplate, no long docstrings, no 200-line READMEs.
- Small steps: implement one module, run it on real data, show the output, then stop.
- Before writing code against any source, inspect actual columns; never assume names.
- Run `uv run ruff check --fix` and `uv run pytest` before saying a step is done.
- Commit after each working module with a clear message.
- Current date: 31 Oct 2026. Use current library APIs.
