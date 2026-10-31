# airbus_challenge

Forecasts the hourly AAR proxy and severe delay risk (>45 min) 3–12 h ahead for KATL and KDFW. Airbus Challenge #5, Autonomous SG 2026.

The dataset has no true AAR, so capacity here is an AAR proxy built from hourly actual arrivals.

## Setup

```bash
uv sync
cp .env.example .env
```

On macOS, LightGBM also needs the OpenMP runtime: `brew install libomp`.

Pipeline code is not written yet. See `docs/challenge5.md` for the brief.

## Docs

- `docs/challenge5.md`: brief and rubric.
- `docs/PROJECT_SPEC.md`, `TEMPORAL_RULES.md`, `DATA_CONTRACTS.md`, `EVALUATION_PLAN.md`: target definitions, leakage rules, schemas, evaluation protocol.
- `docs/DECISIONS.md`: open questions for organisers. `docs/SOURCES.md`: data sources and CSV audit.
- `docs/ARCHITECTURE_AND_WORKPLAN.md`, `HANDOFF_TEMPLATE.md`, `prompts/`: optional three-agent workflow.
- `configs/airports.yaml`: headings, timezones, weather stations. `configs/experiment.yaml`: proposed splits and targets (not frozen).
