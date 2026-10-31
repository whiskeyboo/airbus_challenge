# Three-agent work plan

Three agents build the pipeline in parallel, each in its own worktree and branch. `CLAUDE.md` and the specs in `docs/` still govern the science.

| Person | Role |
|---|---|
| Integrator | Runs Agents 1 and 2, reviews output, runs `leakage-auditor`, merges branches, owns shared files |
| Teammate | Runs Agent 3, owns the story: named user, the "where does it fail" slide, the 3-minute pitch |

## Before any agent starts

Do these in order, on `main`:

1. Merge `feat/public-data-download`. The downloaders are finished, so no agent builds them.
2. Merge `chore/agent-split`, which holds this plan and the ignore-rule fix.
3. Add the two missing dependencies on a branch and merge it. Agents don't run `uv add`.
   ```bash
   uv add matplotlib airportsdata
   ```
4. Settle the proposed benign-weather rule (`docs/DECISIONS.md` P10) and the delay-model population (O08).
5. Create one worktree per agent on the machine that runs it. `.gitignore` must be updated first, or `git add -A` commits the `data` link. Run these from the main repo root; `$PWD` keeps the links absolute whatever the clone path.
   ```bash
   git worktree add ../ac-flights -b flights main
   ```
   ```bash
   ln -s "$PWD/data" ../ac-flights/data
   ```
   ```bash
   ln -s "$PWD/.env" ../ac-flights/.env
   ```
   Repeat for `../ac-weather` on branch `weather`. Agent 3 uses `../ac-model` on branch `model`.

The teammate's machine needs its own data, because `data/` isn't in git:

```bash
uv run python -m airbus_challenge.download
```

BTS takes about 20 minutes. Compare the printed CSV checksum with the integrator's.

## Who builds what

| | Agent 1: Flights | Agent 2: Weather | Agent 3: Modelling and product |
|---|---|---|---|
| **Code** | `clean.py`, `requests.py`, `targets.py` | `iem.py`, `features.py` | `baselines.py`, `train.py`, `evaluate.py`, then `recommend.py`, `explain.py`, `app/dashboard.py` |
| **Writes** | `flights.parquet`, `prediction_requests.parquet`, `airport_hourly.parquet`, `labels.parquet` | `weather_observations.parquet`, `weather_forecasts.parquet`, `feature_snapshots.parquet`, `feature_lineage.parquet` | `artifacts/<run_id>/predictions.parquet`, `reports/metrics.json`, figures |
| **Tests** | `tests/test_flights.py`: `docs/TEMPORAL_RULES.md` §7 tests 6, 7, 8 | `tests/test_leakage.py`: tests 1–5 and 9, plus wind components | `tests/test_baselines.py`: test 11. `tests/test_evaluate.py`. Test 10 if serving is built |
| **Main risk** | Local HHMM to UTC, including origin timezones. Cancelled flights are excluded from severe-delay labels | Nothing after T reaches a feature. Calm, variable and missing wind stay distinct | Baselines fit on train only. The evaluator reads saved predictions and labels, never the model |

Contract sections: flights §4, airport hours §5, requests and features §6, labels §7, weather §2–3, predictions §8, metrics §9.

## Build order

| Step | Who | Delivers | Unblocks |
|---|---|---|---|
| 1 | Agent 1 | `flights.parquet` with `in_provided_csv` flag | Demand features, request building |
| 2 | Agent 1 | `requests.py` and `prediction_requests.parquet` | Labels, features |
| 3 | Agent 1 | `airport_hourly.parquet` (raw arrival counts) and `labels.parquet` | First real baseline numbers |
| 4 | Agent 2 | `weather_observations.parquet`, `weather_forecasts.parquet` | Clear-weather ceiling |
| 5 | Agent 1 | Capacity ratio added to `airport_hourly.parquet` | Second target |
| 6 | Agent 2 | Feature snapshots and lineage at issue time T | Model training |
| 7 | Agent 3 | Frozen model on validation and calibration data | Final test |
| 8 | Agent 3, integrator approves | One locked test run, then metrics, 3 worst misses | Recommendations, brief, dashboard, slides |

Nobody waits idle. Agent 2 builds weather parsing and wind features from step 0. Agent 3 starts on a small fake `airport_hourly` file with the contract's columns and `data_mode = fixture`, generated in its tests. Its numbers are never reported. The provided CSV can't stand in, because it has at most 4 arrivals in any hour.

## Rules

- **Files:** an agent edits only the files it owns. The integrator owns `CLAUDE.md`, `configs/`, `docs/`, `pyproject.toml`, `uv.lock` and `download.py`. Agents ask for shared changes in their handoff.
- **Data:** each parquet has one writer. Write to a temporary name, then rename, because worktrees share `data/`.
- **Delivery:** something is delivered when its code is merged and it regenerates with `uv run python -m airbus_challenge.<module>`. A file that exists on one machine doesn't count.
- **Merging:** merge each working module. Before merging, run `uv run ruff check --fix` and `uv run pytest`, then the `leakage-auditor` for feature, training or evaluation changes. There is no CI.
- **Syncing:** everyone pulls `main` after each merge.
- **Test set:** nothing reads 2025 outcomes before step 8, and step 8 runs once. Findings after that are labelled exploratory.

## Still open

Tracked in `docs/DECISIONS.md`: P10 benign weather, O08 delay-model population, O09 test window, O10 Drive folder.

## Kickoff prompts

**Agent 1:**
> Read `CLAUDE.md`, `docs/WORK_PLAN.md`, `docs/TEMPORAL_RULES.md` §4 and `docs/DATA_CONTRACTS.md` §4–7. You are Agent 1 on branch `flights`. Inspect a real BTS zip in `data/raw/bts/`, then build `clean.py` for flights touching an airport in `configs/airports.yaml`. Use `airportsdata` for timezones, with an override for any airport it lacks, and report coverage. Show the output and stop before `requests.py`.

**Agent 2:**
> Read `CLAUDE.md`, `docs/WORK_PLAN.md`, `docs/TEMPORAL_RULES.md` and `docs/DATA_CONTRACTS.md` §2, §3 and §6. You are Agent 2 on branch `weather`. Inspect the files in `data/raw/metar/` and `data/raw/taf/`, then build `iem.py` to write the observation and forecast tables. Preserve raw reports. Variable wind has a blank `drct` and shows `VRB` in the raw METAR. Show the output and stop before `features.py`.

**Agent 3:**
> Read `CLAUDE.md`, `docs/WORK_PLAN.md`, `docs/EVALUATION_PLAN.md` and `docs/DATA_CONTRACTS.md` §5 and §7–9. You are Agent 3 on branch `model`. Build `baselines.py` against a fake `airport_hourly` table with `data_mode = fixture`: persistence from the last complete hour before T, marked as a simulated feed, plus climatology and schedule-only baselines fitted on train only. Show the output and stop before `train.py`.
