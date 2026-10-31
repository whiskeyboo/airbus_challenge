# Temporal correctness and leakage controls

Enforced by pytest and reviewed by the `leakage-auditor` subagent.

## 1. Time semantics

Keep distinct: event/observation time, forecast issue time, forecast validity, historical availability, actual retrieval time, target time, and model-fit time.

A source may contribute at T only if `available_at_utc <= T`. An observation must additionally have `observed_at_utc <= T`. A TAF must have `issued_at_utc <= T`, but its validity is expected to cover future target hours. Use a documented latency when historical availability is simulated. Do not backdate a revised record merely because its event time is old.

## 2. As-of selection

1. Construct prediction requests before loading outcome columns into the feature process.
2. Restrict source records to the eligible availability cutoff.
3. Select the latest eligible, non-superseded bulletin for the station under a versioned amendment/correction policy.
4. Expand that bulletin's prevailing state and conditional groups over the target interval. If the target is uncovered, mark missing; do not silently resurrect a superseded bulletin or borrow a future amendment.
5. Compute observation features from trailing windows ending at T. A partially elapsed current hour contains only reports available by T, not the completed hour's aggregate.
6. Record source contributors, ages, transformations, and availability basis.
7. Assert temporal rules before returning the snapshot.

Never interpolate using future observations, backward-fill from future reports, or join a target hour to its realised weather. Archived reanalysis and final storm reports are not substitutes for historical forecasts.

## 3. Feature eligibility

| Feature | Policy |
| --- | --- |
| Calendar at target time | Allowed |
| Target-hour schedule demand | Allowed under an explicit schedule knowledge/version assumption |
| Observations available by T | Allowed |
| TAF issued and available by T, valid after T | Allowed |
| Recent realised operations | Only through a separately timestamped, evidenced or simulated event feed |
| Departed-flight delay rate | Allowed under availability policy; report selection bias and pair with pending/backlog if supported |
| Aircraft rotation/tail assignment | Exclude until historical assignment knowledge is evidenced |
| Final cancellation/diversion flags | Labels only unless a historical known-by-T status is independently established |
| Target flight's actual departure/arrival and delay causes | Forbidden as predictors |
| Target-period realised weather or revised forecast issued after T | Forbidden |
| NOAA final Storm Events for the target event | Retrospective evaluation only |

An outcome archive may be used to simulate a feed, but must be marked `simulated`; do not claim it demonstrates live-feed availability. Report a weather-plus-schedule variant that does not rely on this assumption.

## 4. BTS timestamp reconstruction

`FL_DATE` is the departure service date. Clock values are local HHMM, not elapsed minutes. Never concatenate that date with every departure/arrival field and assume correctness.

- Normalise 2400 to midnight on the next local date where appropriate; preserve raw fields.
- Map both endpoint airports to historical IANA timezone rules.
- Reconstruct scheduled departure with explicit treatment of DST ambiguous/nonexistent times.
- Use CRS elapsed time to derive/check scheduled arrival UTC and local date.
- Where valid, derive actual departure from scheduled departure plus signed departure delay, then check the raw local clock.
- Use taxi and elapsed durations to derive/check wheels-off, wheels-on, and actual gate arrival where the source definitions support it.
- Cancelled and diverted records may have partial paths; do not fabricate missing movements.
- Compare independent clock/duration paths within a documented tolerance. The lead must approve the tolerance before production use.
- Quarantine unresolved ambiguity and inconsistent records; preserve reason codes and counts by airport/month.

Do not simply attach a timezone to an ambiguous clock or force every flight to land on its departure date. Do not use reconstructed actual events as predictors before their simulated/evidenced availability.

## 5. Wind tests and source semantics

Convert degrees to radians before trigonometry. Positive headwind is wind from the runway-heading direction. Absolute crosswind is nonnegative. Tailwind is max(0, -headwind). Keep variable wind and missing direction distinct from calm wind.

Preserve true/magnetic reference metadata. The brief's numerical headings remain unchanged; direct comparison to true-north weather is a provisional assumption pending clarification. Real configuration switching is not part of the required fixed-heading experiment.

## 6. Training-time leakage

- Training rows need outcomes available by the simulated model-fit time, not merely target dates before it.
- The final test cannot influence imputation, scaling, category encoding, feature selection, hyperparameters, calibration, or alert thresholds.
- Keep all horizon variants of a flight in one target-date partition.
- For rolling-origin experiments, use explicit fit, calibration, and prediction cutoffs. Exclude overlapping incomplete outcomes at boundaries. Any additional embargo must have a documented purpose.
- Label creation may inspect future outcomes; feature construction may not. Keep those code paths separate.

## 7. Mandatory tests

1. A future METAR cannot affect an earlier snapshot.
2. A TAF amendment issued after T cannot affect a snapshot at T.
3. A pre-T TAF valid after T is accepted, while a post-T TAF is rejected.
4. Future simulated flight statuses cannot change a pre-T backlog or delay rate.
5. Partial-hour features exclude later-in-hour observations.
6. 2400, DST spring/fall, overnight arrivals, and delays over 24 hours are reconstructed or explicitly quarantined.
7. Airport-hour keys remain unique across repeated local hours.
8. 45-minute departure delay is negative, 46 is positive, cancellation is not a negative.
9. Changing final outcomes does not change feature snapshots.
10. Offline and served feature construction return the same snapshot on a pinned request.
11. Persistence for target hour s at horizon h uses the hour starting at s - h - 1, never the unfinished hour starting at s - h.

For each test retain a compact fixture and meaningful expected behaviour. Do not merely assert the implementation returns its own intermediate value.
