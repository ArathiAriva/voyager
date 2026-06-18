import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from server import get_weather, get_exchange_rate

pytestmark = pytest.mark.asyncio

# ── Fixtures ─────────────────────────────────────────────────────────────────

GEO_RESPONSE = {
    "results": [{"name": "Tokyo", "country": "Japan", "latitude": 35.6895, "longitude": 139.6917}]
}

FORECAST_RESPONSE = {
    "daily": {
        "time": ["2026-06-18", "2026-06-19"],
        "temperature_2m_max": [24.0, 28.0],
        "temperature_2m_min": [19.0, 20.0],
        "precipitation_sum": [16.0, 0.5],
        "wind_speed_10m_max": [9.0, 8.0],
    }
}

FX_RESPONSE = {
    "base": "USD",
    "rates": {"JPY": 160.31},
    "date": "2026-06-17",
}


def _mock_response(json_data: dict, status_code: int = 200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    return mock


# ── get_weather ───────────────────────────────────────────────────────────────

async def test_get_weather_returns_forecast():
    mock_client = AsyncMock()
    mock_client.get.side_effect = [
        _mock_response(GEO_RESPONSE),
        _mock_response(FORECAST_RESPONSE),
    ]
    with patch("server.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__.return_value = mock_client
        result = await get_weather("Tokyo")

    assert result["location"] == "Tokyo, Japan"
    assert len(result["forecast"]) == 2
    assert result["forecast"][0]["date"] == "2026-06-18"
    assert result["forecast"][0]["temp_max_c"] == 24.0
    assert result["forecast"][0]["precipitation_mm"] == 16.0


async def test_get_weather_unknown_destination():
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response({"results": []})
    with patch("server.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__.return_value = mock_client
        result = await get_weather("Nonexistentville")

    assert "error" in result
    assert "Nonexistentville" in result["error"]


# ── get_exchange_rate ─────────────────────────────────────────────────────────

async def test_get_exchange_rate_returns_rate():
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(FX_RESPONSE)
    with patch("server.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__.return_value = mock_client
        result = await get_exchange_rate("USD", "JPY")

    assert result["base"] == "USD"
    assert result["target"] == "JPY"
    assert result["rate"] == 160.31
    assert "1 USD = 160.31 JPY" in result["note"]


async def test_get_exchange_rate_lowercases_codes():
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(FX_RESPONSE)
    with patch("server.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__.return_value = mock_client
        result = await get_exchange_rate("usd", "jpy")

    assert result["base"] == "USD"
    assert result["target"] == "JPY"


async def test_get_exchange_rate_invalid_currency():
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response({}, status_code=422)
    with patch("server.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__.return_value = mock_client
        result = await get_exchange_rate("USD", "XYZ")

    assert "error" in result
