# airbus_challenge

Forecasts hourly arrival throughput (AAR proxy) and severe departure-delay risk (>45 min) 3–12 h ahead for KATL and KDFW. Airbus Challenge #5, Autonomous SG 2026.

No true AAR is available, so capacity here is an AAR proxy: hourly actual arrivals from BTS On-Time data, plus their ratio to a clear-weather ceiling. Weather features come from IEM METAR/TAF; the provided CSV supplies delay labels.

## Setup

```bash
uv sync
cp .env.example .env
```

On macOS, LightGBM also needs the OpenMP runtime: `brew install libomp`.

Pipeline code is not written yet. See `docs/challenge5.md` for the brief.

## Docs

- `docs/challenge5.md`: brief and rubric.
- `docs/WORK_PLAN.md`: who builds what, and how the three agents work together.
- `docs/PROJECT_SPEC.md`, `TEMPORAL_RULES.md`, `DATA_CONTRACTS.md`, `EVALUATION_PLAN.md`: target definitions, leakage rules, schemas, evaluation protocol.
- `docs/DECISIONS.md`: open questions for organisers. `docs/SOURCES.md`: data sources and CSV audit.
- `configs/airports.yaml`: headings, timezones, weather stations. `configs/experiment.yaml`: splits, horizons and targets.
