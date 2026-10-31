# Feature provenance and limitations

How one prediction traces back to its sources, where the inputs are weaker than they look, and how to rebuild everything. Weather and demand inputs only; labels and evaluation are covered elsewhere.

## (a) Worked example

`uv run python -m airbus_challenge.provenance` (default: KDFW throughput, issued 2024-05-27 18:00Z, h = 6, target hour 00Z) prints:

```
prediction_id cab921e6a2cd0702afe2d4e9270f7a4496f4e3a0737271d479acad694c9ab82f
  task=throughput airport=KDFW as_of=2024-05-27 18:00Z target=2024-05-28 00:00Z h=6
  snapshot_key=b38fb8ddbc4dcbb925703e491c23cf30 status=ok reasons=[]
  lineage metar_latest: metar/metar_KDFW_20221230_20250801.csv#line=14621 available 17:03Z
  lineage metar_window: available_at in (as_of - 6h, as_of], observed_at <= as_of
  lineage taf: 202405271731-KFWD-FTUS44-TAFDFW#01 available 17:41Z
  METAR observed 16:53Z available 17:03Z age 67 min
    KDFW 271653Z 12009KT 8SM FEW020 33/26 A2993 RMK AO2 SLP124 T03280256
  TAF 202405271731-KFWD-FTUS44-TAFDFW issued 17:31Z available 17:41Z age 29 min
     00 prevailing 27 17:31Z-27 23:00Z 12009KT 6SM HZ SCT040
   * 01 FM         27 23:00Z-28 03:00Z FM272300 12009KT P6SM VCTS SCT050CB BKN250
     02 FM         28 03:00Z-28 10:00Z FM280300 12007KT P6SM SCT160
     ... (03-05 later FM groups, not overlapping the target hour)
  features and registry entries:
    metar_crosswind_kt = 7.79 [kt; float; feature_snapshots; null if missing/stale; live-capable]
    taf_ts_prevailing = True [bool; feature_snapshots; null if uncovered; live-capable]
    taf_age_min = 29.0 [min; float; feature_snapshots; null if no eligible TAF; live-capable]
    sched_arr_h0 = 85.0 [flights/hour; double; demand_features; null if schedule source missing;
                         replay-only (retrospective schedule)]
  prediction lgbm_throughput_v1: 67.4 touchdowns/hour (p10 51.9, p90 76.2) status available
  HINDSIGHT (not known at T): realised touchdowns 4, scheduled 85
```

Reading it: the only TAF segment in force for 00Z (`*`) forecast thunderstorms in the vicinity with CB, and the feature carried it (`taf_ts_prevailing = True`). The model still predicted 67 arrivals against 85 scheduled; 4 landed. This is a real miss, and the evidence that should have warned was in the inputs. `tests/test_parity.py` recomputes this row and five others (an off-hour flight, `metar_stale`, `metar_cor_skipped`, `taf_conflict_fallback`, the KATL 2023-08-11 storm) from the weather tables at their exact `as_of`, and checks values, reason codes, windows, versions and lineage contributors are identical.

## (b) Freshness and latency limitations

- **Simulated latency (P13).** IEM does not evidence when a report was historically available. Every METAR and TAF counts as available 10 min after observation/issue. All availability is `simulated`, not measured.
- **On-the-hour issue times.** The :52 routine METAR becomes available at :02, so at T = hh:00 the latest usable report is about 67-68 min old (median `metar_age_min` 67-68 min for throughput). Off-hour flight requests see fresher reports (median ~37-38 min).
- **Corrected METARs excluded (P14).** IEM keeps only the corrected text and its send time is unknown, so COR reports get no `available_at` and are never used. On about 1.5% of snapshots a COR would have been the latest report; those rows carry `metar_cor_skipped` and use an older report. The 3-h staleness cutoff then affects 132 throughput rows (was 16).
- **TAF age and lead** (`reports/input_quality.json`, validation throughput): median TAF age 69 min at KATL vs 98 min at KDFW (p95 145 vs 220 min); lead from issue to target 4.2/4.6 h at h = 3 and 13.1/13.6 h at h = 12.
- **KDFW forecasts are sparser.** KFWD issues fewer amendments (about 5,000 vs 8,060 at KATL over the period) and almost never uses PROB30 (2 groups vs 3,093). Conditional-group features are near-empty at KDFW.
- **IEM parsed-column defects worked around.** IEM drops VRB winds and gusts, adds phantom sky layers, mishandles TAF hour 24 (`fx_valid_end`) and lacks `is_amendment` on many KATL rows. Wind, sky and validity are parsed from the raw text instead; amendment status comes from the WMO BBB suffix.
- **Missing METAR hours.** 17 airport-hours in the grid have no METAR at all (`eval_weather_slices` coverage = missing).
- **Demand is replay-only.** Schedule features use the BTS schedule as flown (retrospective archive), assumed known at every issue time. That is not evidenced live availability; a live system would need a schedule snapshot feed.
- **Runway heading reference (O03).** Headings 80/180 are used as given and compared directly with METAR wind (true north). True vs magnetic is unconfirmed; the error is a few degrees.
- **Evaluation slices are hindsight.** `eval_weather_slices.parquet` uses every report in the target hour, including COR, and is never a model input (the registry refuses its columns).

## (c) Regenerate

Run from the repo root, in this order (each writes to a temp name and renames):

| Step | Command | Output and recorded hashes |
|---|---|---|
| Weather | `uv run python -m airbus_challenge.iem` | `weather_observations/forecasts.parquet` + manifests (raw file sha256, retrieval times) |
| Features | `uv run python -m airbus_challenge.features` | `feature_snapshots.parquet`, `feature_lineage.parquet`; `data_snapshot_id` = hash of the raw weather sha256s (currently `adfb8b104f96880a`) |
| Demand | `uv run python -m airbus_challenge.demand` | `demand_features.parquet` + manifest (`output_sha256` e7fb22e8…, requests `parquet_sha256`) |
| Registry | `uv run python -m airbus_challenge.registry` | `feature_registry.json` (`content_sha256` abb975e8…, sha256 of the three input tables) |
| Slices | `uv run python -m airbus_challenge.slices` | `eval_weather_slices.parquet` + manifest (evaluation only) |
| Input QA | `uv run python -m airbus_challenge.input_qa` | `reports/input_quality.json` (registry and input hashes) |
| Train | `uv run python -m airbus_challenge.train` and `--task severe_delay` | `artifacts/lgbm_*_dev/` predictions, manifest (fit cutoff, requests sha256, registry hash) |

Prerequisites: `download.py` → `clean.py` → `targets.py` → `requests.py` (Agent 1) must have run. `features.py` and `demand.py` read only their declared projections; tests enforce this on every file open.
