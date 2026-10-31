# Airbus Challenge #5: Predictive Airport Capacity & Delay Risk

Hackathon: Autonomous SG 2026 (AI & Aerospace track). Forecast hourly arrival acceptance rate (AAR) and severe delay risk (>45 min) 3–12 h ahead for KATL and KDFW, from `data/raw/Flight_Data_With_Weather_Final.csv` (2023–2025).

Full challenge spec and rubric: `docs/challenge5.md`.
Data source: public Google Drive folder, ID in `.env` as `DATA_GDRIVE_FOLDER_ID`. `download.py` fetches it with `gdown --folder` and flattens it into `data/raw/`.

## Judging (optimise for this)
Technical soundness 25%, Problem realism 20%, Honest evaluation 20%, Trust & traceability 20%, Impact 10%, Time 5%.
Judges ask: "Where does this fail, and how would your user know?" Working end-to-end pipeline + honest numbers beat UI polish.

## Stack
- Python 3.12, `uv` only (`uv add`, `uv run`). Never pip install.
- pandas, pyarrow, scikit-learn, lightgbm, shap, streamlit, plotly, pyyaml, gdown, python-dotenv, openai.
- Dev: ruff, pytest.
- Package lives in `src/airbus_challenge/`. Dashboard in `app/dashboard.py`.

## Hard rules (domain)
1. **No leakage.** For horizon h, features may only use weather/flight info timestamped ≤ t − h. Never use the target flight's own delay/arrival fields as features. A pytest must enforce this.
2. **Runway directionality.** Never use raw wind speed alone. θ = wind_dir − runway_heading; headwind = WS·cos θ; tailwind = −headwind; crosswind = |WS·sin θ|. Same for gusts. Headings from `configs/airports.yaml` (KATL 80°, KDFW 180°). Also compute reciprocal runway (h+180) as an alternative feature.
3. **Generalise.** Every function takes an ICAO code; no airport hard-coded outside `configs/airports.yaml`. Airport is a categorical feature.
4. **Normalise delays** by hourly flight volume (share of flights >45 min, mean delay per flight), never raw totals across airports.
5. **AAR is a proxy.** Dataset has no true AAR. Use hourly actual arrivals per airport, plus ratio to a clear-weather capacity ceiling (95th pct arrivals for that airport-hour in benign weather). Label it "AAR proxy" everywhere and document the limitation.
6. **Time-based split only.** Train 2023–2024, test 2025. No shuffling. Also a leave-one-airport-out test.
7. **Baselines first.** Persistence (value at t − h) and climatology (airport × hour × weekday mean). Every model metric is reported next to both.
8. **LLM / non-LLM split.** Numbers, thresholds and recommendations come from code (rules in `recommend.py`). The LLM in `explain.py` only writes a short brief from given prediction + SHAP drivers + input timestamps, cites them, and says "insufficient data" when inputs are missing. It never computes.

## Pipeline modules
download.py → clean.py → targets.py → features.py → train.py → evaluate.py → recommend.py → explain.py → app/dashboard.py
- Intermediate data as parquet in `data/interim/`, `data/processed/` (gitignored).
- `evaluate.py` writes `reports/metrics.json` and figures: RMSE/MAE for AAR proxy per horizon (3/6/9/12) and airport vs baselines; PR-AUC, recall@precision, Brier for delay>45; 3 worst misses with explanation.

## Working style
- Concise code. No defensive boilerplate, no long docstrings, no 200-line READMEs.
- Small steps: implement one module, run it on real data, show the output, then stop.
- Before writing code against the CSV, inspect actual columns; never assume names.
- Run `uv run ruff check --fix` and `uv run pytest` before saying a step is done.
- Commit after each working module with a clear message.
- Current date: 31 Oct 2026. Use current library APIs.
