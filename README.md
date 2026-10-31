# airbus_challenge

Forecasts hourly arrival throughput (AAR proxy) and severe departure-delay risk (>45 min, conditional on the flight operating) 3–12 h ahead for KATL and KDFW, for Airbus Challenge #5 (Autonomous SG 2026). No true AAR exists, so the target is BTS reporting-carrier wheels-on per UTC hour, plus its ratio to a train-only clear-weather ceiling. Weather features come from IEM METAR/TAF, using only reports available at issue time and runway-relative wind components. The provided CSV is scored only as a separate CSV-only comparison. Splits are time-based: train 2023, validation H1 2024, calibration H2 2024, locked test Jan–Jul 2025. **Read [docs/LIMITATIONS.md](docs/LIMITATIONS.md) before trusting any number.**

## Setup

```bash
uv sync
cp .env.example .env   # DATA_GDRIVE_FOLDER_ID; OPENAI_API_KEY for the brief
```

On macOS, LightGBM also needs the OpenMP runtime: `brew install libomp`.

## Pipeline

download → clean → requests → iem → targets → features → baselines + flight_baselines → train (teammate, in progress) → evaluate → failures (in progress) → recommend → explain → dashboard

`train.py` is being built by a teammate and `failures.py` is in progress. `recommend.py` uses provisional thresholds until WP-D7.

Development run, in order. `iem` runs before `targets` because the P12 exclusion audit reads METARs.

```bash
uv run python -m airbus_challenge.download    # provided CSV, IEM METAR/TAF, BTS -> data/raw/
uv run python -m airbus_challenge.clean       # flights.parquet
uv run python -m airbus_challenge.requests    # prediction_requests.parquet
uv run python -m airbus_challenge.iem         # weather_observations / weather_forecasts
uv run python -m airbus_challenge.targets     # airport_hourly.parquet, data/labels/labels.parquet
uv run python -m airbus_challenge.features    # feature_snapshots / feature_lineage
uv run python -m airbus_challenge.baselines   # artifacts/baselines_dev/
uv run python -m airbus_challenge.flight_baselines  # artifacts/baselines_flight_dev/
uv run python -m airbus_challenge.evaluate --runs baselines_dev baselines_flight_dev  # reports/metrics_dev.json + figures
uv run python -m airbus_challenge.recommend --run <run_id>  # advisories.parquet for the dashboard
```

Dashboard (historical replay with an issue-time slider):

```bash
uv run streamlit run app/dashboard.py
```

Checks: `uv run ruff check --fix` and `uv run pytest`.

## Outputs

- `data/raw/`, `data/interim/`, `data/processed/`, `data/labels/`: parquet plus `.manifest.json` (gitignored).
- `artifacts/<run_id>/`: `predictions.parquet` and `manifest.json` (cutoff, hashes, status and reason counts).
- `reports/`: `metrics_dev.json` and figures from real data.
- `reports/fixture/`: the same outputs from fixture data (gitignored), so they are never confused with real results.

## Locked 2025 test

Not run. It needs the lead's explicit release after the model is frozen (gate G6). It runs once, via `--locked-test --approved-by <lead>` on `baselines` and `evaluate`. Each claim is recorded in `data/locked_runs/` and mirrored to the committed `reports/locked_runs/`. Never use 2025 to pick features, thresholds or models.

## Docs

- [docs/LIMITATIONS.md](docs/LIMITATIONS.md): where it fails and how the user would know.
- [docs/challenge5.md](docs/challenge5.md): brief and rubric.
- [docs/WORK_PLAN.md](docs/WORK_PLAN.md), [docs/PHASE_PLAN.md](docs/PHASE_PLAN.md): owners, phases, gates.
- [docs/DECISIONS.md](docs/DECISIONS.md): accepted and pending decisions.
- [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md), [docs/TEMPORAL_RULES.md](docs/TEMPORAL_RULES.md), [docs/DATA_CONTRACTS.md](docs/DATA_CONTRACTS.md), [docs/EVALUATION_PLAN.md](docs/EVALUATION_PLAN.md), [docs/SOURCES.md](docs/SOURCES.md): targets, leakage rules, schemas, evaluation, sources.
- `configs/experiment.yaml` (splits, horizons, targets), `configs/airports.yaml` (headings, timezones, stations).
