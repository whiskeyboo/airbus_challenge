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
