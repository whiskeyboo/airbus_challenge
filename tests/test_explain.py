from types import SimpleNamespace

import pytest
from test_recommend import preds, reference

from airbus_challenge import explain
from airbus_challenge.recommend import recommend

DRIVERS = [
    {"feature": "crosswind_kt", "value": 18.0, "contribution": 4.2, "contribution_scale": "touchdowns/hour"},
    {"feature": "taf_ceiling_min_ft", "value": 800.0, "contribution": -3.1, "contribution_scale": "touchdowns/hour"},
]  # fmt: skip
TIMES = {
    "metar_observed_utc": "2024-03-05T11:53:00+00:00",
    "taf_issued_utc": "2024-03-05T11:20:00+00:00",
}


class FakeClient:
    def __init__(self, text=None, error=None):
        self.calls = []
        self.responses = SimpleNamespace(create=self._create)
        self.text, self.error = text, error

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(output_text=self.text)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(explain, "load_dotenv", lambda: None)


def rec(**kw):
    return recommend(preds(**kw), reference())


def test_template_without_key():
    out = explain.brief(rec(tp=80.0, p10=75.0), DRIVERS, TIMES)
    assert out["path"] == "template" and out["reason"] == ["no OPENAI_API_KEY"]
    text = out["text"]
    assert "Arrival throughput (AAR proxy)" in text and "80.0" in text
    assert "associations, not causes" in text and "provisional_until_WP-D7" in text
    assert (
        "2024-03-05T11:53:00+00:00" in text
        and "Cancellation, reported separately" in text
    )
    assert explain.unsupported_numbers(text, out["facts"]) == []


@pytest.mark.parametrize("case", ["unavailable", "no_drivers", "no_times"])
def test_insufficient_data(case):
    client = FakeClient("should not be called")
    r = (
        rec(tp=None, p10=None, tp_status="unavailable")
        if case == "unavailable"
        else rec()
    )
    drivers = [] if case == "no_drivers" else DRIVERS
    times = {} if case == "no_times" else TIMES
    out = explain.brief(r, drivers, times, client=client)
    assert out["path"] == "insufficient_data"
    assert out["text"].startswith("Insufficient data") and not client.calls


def test_llm_reply_accepted_when_numbers_match():
    reply = ("KATL at 2024-03-05T12:00:00+00:00: arrival throughput (AAR proxy) 95.0 touchdowns/hour, "
             "0.95 of the clear-weather p95; crosswind_kt=18.0 is associated with it.")  # fmt: skip
    client = FakeClient(reply)
    out = explain.brief(rec(), DRIVERS, TIMES, client=client)
    assert out["path"] == "llm" and out["text"] == reply
    assert "associations, not causes" in client.calls[0]["instructions"]


def test_invented_number_rejected():
    client = FakeClient(
        "Arrival throughput (AAR proxy) will drop to 61.7 touchdowns/hour."
    )
    out = explain.brief(rec(), DRIVERS, TIMES, client=client)
    assert out["path"] == "template"
    assert "61.7" in out["reason"][0] and "61.7" not in out["text"]
    assert out["rejected_llm_text"].startswith("Arrival")


def test_api_failure_falls_back():
    out = explain.brief(rec(), DRIVERS, TIMES, client=FakeClient(error=TimeoutError()))
    assert out["path"] == "template" and out["reason"] == ["llm_error: TimeoutError"]
