"""
Voyager Travel MCP Server

Exposes travel-utility tools to any MCP-compatible agent (Voyager backend, Claude Code, etc.).
Run via stdio:  python server.py
"""

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("voyager-travel-tools")

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_FX_URL = "https://api.frankfurter.dev/v1/latest"


@mcp.tool()
async def get_weather(destination: str) -> dict:
    """
    Get a 7-day weather forecast for a travel destination.
    Returns daily high/low temperatures (°C), precipitation (mm), and wind speed (km/h).
    Use when the user asks about weather, packing, or conditions at a destination.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        geo = await client.get(
            _GEOCODE_URL,
            params={"name": destination, "count": 1, "language": "en", "format": "json"},
        )
        geo.raise_for_status()
        results = geo.json().get("results")
        if not results:
            return {"error": f"Could not find location: {destination}"}

        loc = results[0]
        lat, lon = loc["latitude"], loc["longitude"]
        place_name = f"{loc['name']}, {loc.get('country', '')}".strip(", ")

        forecast_resp = await client.get(
            _FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
                "timezone": "auto",
                "forecast_days": 7,
            },
        )
        forecast_resp.raise_for_status()
        data = forecast_resp.json()

    daily = data["daily"]
    return {
        "location": place_name,
        "forecast": [
            {
                "date": date,
                "temp_max_c": daily["temperature_2m_max"][i],
                "temp_min_c": daily["temperature_2m_min"][i],
                "precipitation_mm": daily["precipitation_sum"][i],
                "wind_speed_kmh": daily["wind_speed_10m_max"][i],
            }
            for i, date in enumerate(daily["time"])
        ],
    }


@mcp.tool()
async def get_exchange_rate(base: str, target: str) -> dict:
    """
    Get the current exchange rate between two currencies.
    Use ISO 4217 currency codes, e.g. 'USD', 'EUR', 'JPY', 'GBP'.
    Use when the user asks about money, budgeting, or currency conversion for a trip.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_FX_URL, params={"from": base.upper(), "to": target.upper()})
        if resp.status_code == 422:
            return {"error": f"Unknown currency code. Use ISO 4217 codes like USD, EUR, JPY."}
        resp.raise_for_status()
        data = resp.json()

    rate = data["rates"].get(target.upper())
    if rate is None:
        return {"error": f"Could not get rate for {target.upper()}"}

    return {
        "base": data["base"],
        "target": target.upper(),
        "rate": rate,
        "date": data["date"],
        "note": f"1 {data['base']} = {rate} {target.upper()}",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
