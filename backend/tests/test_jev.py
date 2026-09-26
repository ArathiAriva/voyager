import pytest

from app import jev
from app.planning.router import is_planning_request, is_planning_request_with_jev


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    response = FakeResponse({
        "answers": {
            "intent": {
                "type": "choice",
                "choice": "planning",
                "confidence": 0.92,
            }
        }
    })

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return self.response


@pytest.mark.asyncio
async def test_jev_classifies_planning_message(monkeypatch):
    client = FakeClient()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(jev.httpx, "AsyncClient", lambda **kwargs: client)

    planning, confidence = await jev.classify_planning_intent("Could you organize my trip?")

    assert planning is True
    assert confidence == 0.92
    assert client.request[0] == jev.JEV_ENDPOINT
    assert client.request[1]["json"]["model"] == jev.DEFAULT_JEV_MODEL


@pytest.mark.asyncio
async def test_jev_router_requires_configured_confidence(monkeypatch):
    monkeypatch.setenv("JEV_ENABLED", "1")
    monkeypatch.setenv("JEV_PLANNING_THRESHOLD", "0.95")

    async def low_confidence(message):
        return True, 0.90

    monkeypatch.setattr(jev, "classify_planning_intent", low_confidence)
    message = "Kyoto sounds good for five days"
    assert is_planning_request(message) is False
    assert await is_planning_request_with_jev(message) is False


@pytest.mark.asyncio
async def test_jev_router_falls_back_when_disabled(monkeypatch):
    monkeypatch.delenv("JEV_ENABLED", raising=False)
    assert await is_planning_request_with_jev("Kyoto sounds good for five days") is False


@pytest.mark.asyncio
async def test_jev_filters_out_transient_preferences(monkeypatch):
    client = FakeClient()
    client.response = FakeResponse({
        "answers": {
            "preference_0": {"choice": "durable", "confidence": 0.91},
            "preference_1": {"choice": "transient", "confidence": 0.95},
        }
    })
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("JEV_ENABLED", "1")
    monkeypatch.setattr(jev.httpx, "AsyncClient", lambda **kwargs: client)

    preferences = await jev.filter_durable_preferences([
        "prefers boutique hotels", "is visiting Kyoto in April",
    ])

    assert preferences == ["prefers boutique hotels"]
    assert client.request[1]["json"]["state"]["preferences"][1] == "is visiting Kyoto in April"


@pytest.mark.asyncio
async def test_jev_memory_filter_fails_open_when_disabled(monkeypatch):
    monkeypatch.delenv("JEV_ENABLED", raising=False)
    preferences = ["prefers boutique hotels"]
    assert await jev.filter_durable_preferences(preferences) == preferences
