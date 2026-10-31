import io
import json
import urllib.error
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest

from airbus_challenge import download


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def test_months_treats_end_as_exclusive_and_crosses_years():
    assert download.months(utc(2022, 12, 30), utc(2023, 2, 1)) == [
        (2022, 12),
        (2023, 1),
    ]


def test_study_window_follows_experiment_config_with_lookback():
    assert download.study_window() == (utc(2022, 12, 30), utc(2025, 8, 1))


@pytest.mark.parametrize("icao,station", [("KATL", "ATL"), ("KDFW", "DFW")])
def test_weather_requests_use_configured_stations_in_utc(icao, station):
    start, end = utc(2023, 1, 1), utc(2023, 2, 1)
    metar_url, metar_path = download.metar_job(icao, start, end)
    taf_url, taf_path = download.taf_job(icao, start, end)
    metar, taf = parse_qs(urlparse(metar_url).query), parse_qs(urlparse(taf_url).query)
    assert metar["station"] == [station] and taf["station"] == [icao]
    assert metar["tz"] == taf["tz"] == ["Etc/UTC"]
    assert metar["report_type"] == ["3", "4"]
    assert icao in metar_path.name and icao in taf_path.name


def respond(monkeypatch, tmp_path, *responses):
    calls = iter(responses)

    def urlopen(request, timeout):
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise outcome
        return io.BytesIO(outcome)

    monkeypatch.setattr(download.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(download.time, "sleep", lambda s: None)
    monkeypatch.setattr(download, "RAW", tmp_path)
    monkeypatch.setattr(download, "MANIFEST", tmp_path / "manifest.json")
    return calls


def test_fetch_retries_rate_limit_then_records_manifest(monkeypatch, tmp_path):
    limited = urllib.error.HTTPError("url", 429, "slow down", {}, None)
    respond(monkeypatch, tmp_path, limited, b"station,valid\nATL,2023-01-01 00:52\n")
    path = download.fetch(("https://example.test/m", tmp_path / "metar" / "m.csv"))
    entry = json.loads((tmp_path / "manifest.json").read_text())["metar/m.csv"]
    assert path.exists() and entry["url"] == "https://example.test/m"
    assert entry["bytes"] == path.stat().st_size and entry["retrieved_at_utc"]


def test_fetch_never_leaves_a_header_only_response_as_finished(monkeypatch, tmp_path):
    respond(monkeypatch, tmp_path, *[b"station,valid\n"] * download.RETRY_ATTEMPTS)
    path = tmp_path / "metar" / "m.csv"
    with pytest.raises(ValueError):
        download.fetch(("https://example.test/m", path))
    assert not path.exists()


def test_fetch_does_not_retry_a_missing_file(monkeypatch, tmp_path):
    missing = urllib.error.HTTPError("url", 404, "not found", {}, None)
    calls = respond(monkeypatch, tmp_path, missing, b"never reached")
    with pytest.raises(urllib.error.HTTPError):
        download.fetch(("https://example.test/b.zip", tmp_path / "b.zip"))
    assert next(calls) == b"never reached"
