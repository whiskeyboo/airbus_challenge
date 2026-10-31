# Sources, verification status, and provided-data audit

Reference check date: 2026-10-31. These notes preserve the preceding review. They are not download logs or a guarantee of continuing endpoint availability. Agents must perform small access-and-parse smoke tests in the actual development environment.

## Challenge inputs

- `Autonomous SG 2026_Airbus Track.pdf`: Challenge 5, printed pages 5-6; rubric follows. Defines ATL/DFW, fixed headings, >45-minute departure-delay classification, airport AAR forecasts, public-data automation, and leakage/directionality/normalisation expectations.
- `Flight_Data_With_Weather_Final.csv`: supplied flight/weather sample. Preserve its original bytes and compute a SHA-256 when importing. Do not redistribute either attachment through this starter kit.

Observed full-file profile from the earlier review:

| Property | Value |
| --- | --- |
| Rows / columns | 148,273 / 123 |
| Date range | 2023-01-01 through 2025-07-31 |
| Distinct flight dates | 943 |
| ATL departures / arrivals | 8,415 / 5,429 |
| DFW departures / arrivals | 7,736 / 4,032 |
| Records involving ATL or DFW | 25,299 |
| Recorded departure delays >45 at ATL / DFW | 780 / 991 |
| Exact duplicate rows | 0 |
| Weather fields | Seven at origin, seven at destination |
| Snow fields | Constant zero at both endpoints |

These are audit observations, not production assertions. Recompute them when importing. The sampling process, weather units/provenance, and weather matching method are not established by the CSV. It lacks wind direction and cannot establish full airport movement counts. Target-hour attached weather cannot be used as an advance predictor.

## Public references

| Source | Reference | Verified in preceding review | Required implementation check |
| --- | --- | --- | --- |
| IEM METAR/ASOS | https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?help | Scriptable arguments; IP throttle; 429/503 handling | Station mapping, chosen units/fields, raw retrieval, gaps, report timing |
| IEM archive notes | https://mesonet.agron.iastate.edu/request/download.phtml | Historical archive is as-is with limited QC | Missing/trace/censored values, duplicate reports, quality rules |
| IEM TAF portal | https://mesonet.agron.iastate.edu/request/taf.php | Historical archive, raw references, issuance/validity, group fields | Actual station coverage, amendments, segment expansion |
| IEM TAF endpoint | https://mesonet.agron.iastate.edu/cgi-bin/request/taf.py?help | Query range limits issuance times, not validity times | Fetch enough pre-cutoff issuance history to cover targets |
| BTS release information | https://transtats.bts.gov/releaseinfo.asp | August 2026 listed at review date | Freeze study period; do not automatically chase latest data |
| BTS field definitions/download | https://www.transtats.bts.gov/DL_SelectFields.aspx?QO_fu146_anzr=b0-gvzr&gnoyr_VQ=FGJ | Reporting-carrier fields and local HHMM clock definitions | Automated retrieval route, zip schema, official field mapping |
| FAA hourly definitions | https://www.aspm.faa.gov/aspmhelp/index/ASPM_Data_Download__Detail_By_Hour.html | AAR is airport-supplied arrival rate; counts/demand separate | Label access, source resolution, sentinel values, aggregation |
| FAA download manual | https://aspmhelp.faa.gov/index/ASPM_Data_Download_Manual.html | Bulk module restricted; documented email-linked workflow | Organiser extract or approved access route; no bypass |
| NWS storm reports | https://www.weather.gov/unr/storm_reports | Final records available 90-120 days after events | Retrospective-only use; correct event-to-airport association |
| NOAA Storm Events | https://www.ncei.noaa.gov/access/storm-events-database/ | Public historical event archive | Bulk version, schema, locations, timestamp interpretation |
| NWS wind sensor | https://www.weather.gov/asos/WindSensor.html | METAR direction referenced to true north | Heading reference consistency |

Prefer provider documentation over third-party package assumptions. A package is optional; its successful installation does not prove its source downloader still works.

## Access-test record to produce

For each source record: tested URL/parameters excluding credentials, UTC test time, status, request duration, response checksum, parser version, returned fields, station/time coverage, example validation results, retry behaviour, and any access limitation. A saved manual ZIP may support cached development, but does not prove automatic public ingestion.

## Data governance

Record source terms, attribution, redistribution constraints, and permission for supplemental competition data. Never commit secrets or restricted source files. Public documentation does not imply public access to every underlying record. Use an approved organiser extract when provided and preserve its provenance.
