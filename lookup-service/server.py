"""Optional egress service. Only explicit city/search inputs leave the server."""
import asyncio
import html
import ipaddress
import json
import math
import os
import re
import secrets
import socket
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(8, connect=3), trust_env=False, follow_redirects=False,
                                       headers={"User-Agent": "Keno-B-Local-Research/1.0"})
    app.state.search_cache = {}
    app.state.page_cache = {}
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
async def health():
    ready = False
    try:
        root = SEARCH_URL.rsplit("/search", 1)[0] + "/"
        ready = (await app.state.http.get(root, timeout=1.2)).status_code < 500
    except httpx.HTTPError:
        pass
    return {"status": "ok", "search_ready": ready}


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


def cache_get(store, key, ttl):
    item = store.get(key)
    if not item or time.monotonic() - item[0] > ttl:
        store.pop(key, None)
        return None
    return item[1]


def cache_put(store, key, value, max_items=64):
    store[key] = (time.monotonic(), value)
    if len(store) > max_items:
        oldest = min(store, key=lambda k: store[k][0])
        store.pop(oldest, None)


def public_target(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
    return True


def visible_text(raw):
    text = raw.decode("utf-8", "ignore")
    text = re.sub(r"(?is)<(?:script|style|noscript|svg|form|nav|footer)[^>]*>.*?</(?:script|style|noscript|svg|form|nav|footer)>", " ", text)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text).strip()


def relevant_excerpt(text, query, limit=1200):
    if not text:
        return ""
    words = {w for w in re.findall(r"\w+", query.casefold()) if len(w) > 2}
    sentences = re.split(r"(?<=[.!?])\s+", text)
    scored = sorted(enumerate(sentences[:500]), key=lambda item: (
        len(words & set(re.findall(r"\w+", item[1].casefold()))), -item[0]), reverse=True)
    chosen = [sentence for _, sentence in scored[:5] if sentence]
    excerpt = " ".join(chosen) if chosen else text
    return excerpt[:limit]


def fact_signals(text):
    compact = " ".join(text.split())
    scores = sorted(set(re.findall(r"\b\d{1,2}\s*[-–:]\s*\d{1,2}\b", compact)))[:8]
    dates = sorted(set(
        re.findall(r"\b(?:\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[a-z]*\s+20\d{2}|20\d{2}[-/]\d{1,2}[-/]\d{1,2})\b", compact, re.I)
    ))[:8]
    return {"scores": scores, "dates": dates}


async def fetch_page(url, query):
    cached = cache_get(app.state.page_cache, url, 900)
    if cached is not None:
        return {**cached, "cache_hit": True}
    if not await asyncio.to_thread(public_target, url):
        return {"fetched": False, "reason": "non-public or unresolvable target"}
    try:
        async with app.state.http.stream("GET", url, timeout=httpx.Timeout(4.5, connect=2.0)) as response:
            if response.status_code >= 400:
                return {"fetched": False, "status": response.status_code}
            content_type = response.headers.get("content-type", "")
            if not any(kind in content_type for kind in ("text/html", "text/plain", "application/xhtml+xml")):
                return {"fetched": False, "reason": "unsupported content type"}
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 450_000:
                    break
                chunks.append(chunk)
        text = visible_text(b"".join(chunks))
        result = {"fetched": bool(text), "excerpt": relevant_excerpt(text, query),
                  "facts": fact_signals(text), "content_type": content_type[:100], "cache_hit": False}
        cache_put(app.state.page_cache, url, result, 128)
        return result
    except httpx.HTTPError:
        return {"fetched": False, "reason": "page fetch failed"}


def normalize_fact(value):
    return re.sub(r"\s+", "", value.casefold()).replace("–", "-")


def verification(pages):
    fetched = [p for p in pages if p.get("page", {}).get("fetched")]
    score_sets = [{normalize_fact(v) for v in p["page"]["facts"].get("scores", [])} for p in fetched]
    date_sets = [{normalize_fact(v) for v in p["page"]["facts"].get("dates", [])} for p in fetched]
    score_agreement = sorted(set.intersection(*score_sets)) if len(score_sets) >= 2 and all(score_sets) else []
    date_agreement = sorted(set.intersection(*date_sets)) if len(date_sets) >= 2 and all(date_sets) else []
    score_conflict = len(score_sets) >= 2 and all(score_sets) and not score_agreement
    date_conflict = len(date_sets) >= 2 and all(date_sets) and not date_agreement
    verified = len(fetched) >= 2 and bool(score_agreement or date_agreement)
    return {"status": "verified" if verified else "conflicting" if score_conflict or date_conflict else "reviewed" if fetched else "snippet_only",
            "verified_from": 2 if verified else 0, "conflict": bool(score_conflict or date_conflict),
            "agreements": {"scores": score_agreement, "dates": date_agreement},
            "fetched_pages": len(fetched)}


def source_quality(row, query):
    words = {w for w in re.findall(r"\w+", query.casefold()) if len(w) > 2}
    hay = (str(row.get("title", "")) + " " + str(row.get("content", ""))).casefold()
    overlap = len(words & set(re.findall(r"\w+", hay)))
    parsed = urlparse(str(row.get("url", "")))
    https = 1 if parsed.scheme == "https" else 0
    published = row.get("publishedDate") or row.get("published_date") or row.get("pubdate")
    freshness = 0
    if published:
        try:
            stamp = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
            age = max(0, (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).days)
            freshness = max(0, 30 - min(30, age))
        except (ValueError, TypeError):
            pass
    return overlap * 10 + https * 3 + freshness / 10


@app.post("/search", dependencies=[Depends(authenticate)])
async def search(value: Search):
    key = " ".join(value.query.casefold().split())
    cached = cache_get(app.state.search_cache, key, 300)
    if cached is not None:
        return {**cached, "cache_hit": True}
    payload = await fetch_json(SEARCH_URL, {"q": value.query, "format": "json", "safesearch": 1})
    rows = payload.get("results", [])
    if not isinstance(rows, list):
        raise HTTPException(502, "Invalid search response")
    candidates = []
    for row in rows[:12]:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url", ""))
        if urlparse(url).scheme not in {"http", "https"}:
            continue
        candidates.append({
            "title": plain(row.get("title", ""), 160), "url": url[:2000],
            "snippet": plain(row.get("content", ""), 360),
            "published_at": plain(row.get("publishedDate") or row.get("published_date") or row.get("pubdate") or "", 80),
            "_quality": source_quality(row, value.query)})
    candidates.sort(key=lambda row: row["_quality"], reverse=True)
    selected = candidates[:2]
    pages = await asyncio.gather(*(fetch_page(row["url"], value.query) for row in selected))
    results = [{**row, "page": page} for row, page in zip(selected, pages)]
    state = verification(results)
    if state["conflict"] and len(candidates) > 2:
        third = candidates[2]
        third_page = await fetch_page(third["url"], value.query)
        results.append({**third, "page": third_page})
        state = verification(results)
    for row in results:
        row["quality_score"] = round(float(row.pop("_quality", 0)), 2)
    response = {
        "query": value.query, "results": results,
        "sources": [{"title": row["title"], "url": row["url"]} for row in results],
        "verification": state, "cache_hit": False,
        "coverage": "Top two search results are ranked and page-fetched when safe; a third is fetched only when the first two conflict. Linked-page extraction is bounded and may be incomplete."
    }
    cache_put(app.state.search_cache, key, response, 64)
    return response
