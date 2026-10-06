"""Optional egress service. Only explicit city/search inputs leave the server."""
import html
import json
import math
import os
import re
import secrets
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

KEY = os.environ.get("KENO_API_KEY", "")
SEARCH_URL = os.environ.get("SEARCH_URL", "http://search:8080/search")


class City(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str = Field(min_length=2, max_length=300)


class Search(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=300)


def authenticate(authorization: str = Header(default="")):
    if len(KEY) < 32 or not secrets.compare_digest(authorization, "Bearer " + KEY):
        raise HTTPException(401, "Invalid access key")


@asynccontextmanager
async def lifespan(app):
    target = urlparse(SEARCH_URL)
    if target.scheme != "http" or target.hostname not in {"search", "localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("SEARCH_URL must point to the self-hosted search service")
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(8, connect=3), trust_env=False, follow_redirects=False)
    yield
    await app.state.http.aclose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


async def fetch_json(url, params):
    try:
        async with app.state.http.stream("GET", url, params=params) as response:
            response.raise_for_status()
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 2_000_000: raise ValueError("Lookup response too large")
                chunks.append(chunk)
        payload = json.loads(b"".join(chunks))
        if not isinstance(payload, dict): raise ValueError("Invalid lookup object")
        return payload
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Lookup provider unavailable or returned an invalid response")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/weather", dependencies=[Depends(authenticate)])
async def weather(value: City):
    locations = await fetch_json("https://geocoding-api.open-meteo.com/v1/search", {"name": value.city, "count": 1, "language": "en", "format": "json"})
    choices = locations.get("results", [])
    if not isinstance(choices, list): raise HTTPException(502, "Invalid geocoding response")
    if not choices: raise HTTPException(422, "City not found; specify a city and country")
    location = choices[0]
    try:
        latitude, longitude = float(location["latitude"]), float(location["longitude"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(502, "Invalid geocoding response")
    if not math.isfinite(latitude + longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise HTTPException(502, "Provider returned invalid coordinates")
    forecast = await fetch_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": latitude, "longitude": longitude, "timezone": "auto", "forecast_days": 1,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max"})
    if not isinstance(forecast.get("current"), dict) or not isinstance(forecast.get("daily"), dict):
        raise HTTPException(502, "Invalid forecast response")
    return {"provider": "Open-Meteo", "location": {k: location.get(k) for k in ("name", "country", "admin1", "latitude", "longitude")},
            "timezone": forecast.get("timezone"), "current": forecast.get("current"), "current_units": forecast.get("current_units"),
            "today": forecast.get("daily"), "daily_units": forecast.get("daily_units"),
            "sources": [{"title": "Open-Meteo forecast", "url": "https://open-meteo.com/"}],
            "note": "Model-based weather estimate, not a local sensor observation. Confirm the matched location."}


def plain(value, limit):
    return html.unescape(re.sub(r"<[^>]*>", "", str(value)))[:limit]


@app.post("/search", dependencies=[Depends(authenticate)])
async def search(value: Search):
    payload = await fetch_json(SEARCH_URL, {"q": value.query, "format": "json", "safesearch": 1})
    results = []
    rows = payload.get("results", [])
    if not isinstance(rows, list): raise HTTPException(502, "Invalid search response")
    for row in rows[:12]:
        if not isinstance(row, dict): continue
        url = str(row.get("url", ""))
        if urlparse(url).scheme not in {"http", "https"}: continue
        results.append({"title": plain(row.get("title", ""), 160), "url": url[:2000], "snippet": plain(row.get("content", ""), 420)})
        if len(results) >= 3: break
    return {"query": value.query, "results": results,
            "sources": [{"title": row["title"], "url": row["url"]} for row in results],
            "coverage": "up to three search snippets only; linked pages were not fetched or verified"}
