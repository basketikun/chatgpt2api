"""vn_weather — multi-source weather for Vietnam and worldwide.

Sources (togglable in Studio UI):
- Open-Meteo: global, free, no API key — primary
- wttr.in: free, no key — fallback
- NWS (US National Weather Service): free, US-only
- AccuWeather: free tier 50/day, needs ACCUWEATHER_API_KEY env var
"""

from __future__ import annotations

import logging, os
from typing import Any

import httpx
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("vn_weather")

WTTR_URL = "https://wttr.in/{location}"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEO = "https://geocoding-api.open-meteo.com/v1/search"
NWS_URL = "https://api.weather.gov/points/{lat},{lon}"
ACCUWEATHER_GEO = "https://dataservice.accuweather.com/locations/v1/cities/search"
ACCUWEATHER_CURRENT = "https://dataservice.accuweather.com/currentconditions/v1/{key}"

ALIAS = {
    "ha noi": "Hanoi", "hn": "Hanoi",
    "sai gon": "Ho Chi Minh City", "hcm": "Ho Chi Minh City",
    "tp hcm": "Ho Chi Minh City", "tp.hcm": "Ho Chi Minh City",
    "da nang": "Da Nang",
    "hue": "Hue",
    "hai phong": "Hai Phong",
    "can tho": "Can Tho",
}


def _is_enabled(source: str) -> bool:
    try:
        from src.sources_config import is_enabled as _chk
        return _chk("vn_weather", source)
    except Exception:
        return True


# ── Open-Meteo (primary, free global) ─────────────────────────────────────

def _open_meteo_current(query: str) -> str | None:
    if not _is_enabled("open_meteo"):
        return None
    try:
        with httpx.Client(timeout=10.0) as c:
            gr = c.get(OPEN_METEO_GEO, params={"name": query, "count": 1, "language": "vi"})
            gr.raise_for_status()
        geo = gr.json()
        results = (geo.get("results") or [])
        if not results:
            return None
        loc = results[0]
        name = loc.get("name", query)
        country = loc.get("country", "")
        lat, lon = loc["latitude"], loc["longitude"]

        with httpx.Client(timeout=10.0) as c:
            wr = c.get(OPEN_METEO_URL, params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m,cloud_cover,uv_index",
                "timezone": "auto",
            })
            wr.raise_for_status()
        w = wr.json().get("current", {})
        codes = {0: "Troi quang", 1: "It may", 2: "Co may", 3: "Nhieu may",
                 45: "Suong mu", 51: "Mua phun", 61: "Mua nho", 63: "Mua vua",
                 80: "Mua rao", 95: "Dong"}
        desc = codes.get(w.get("weather_code", 0), "?")
        return (
            f"**Thoi tiet {name}, {country} (Open-Meteo):** {desc}\n"
            f"- Nhiet do: {w.get('temperature_2m')}C (cam giac {w.get('apparent_temperature')}C)\n"
            f"- Do am: {w.get('relative_humidity_2m')}%\n"
            f"- Gio: {w.get('wind_speed_10m')} km/h\n"
            f"- May: {w.get('cloud_cover')}%\n"
            f"- UV: {w.get('uv_index')}"
        )
    except Exception as exc:
        logger.warning("Open-Meteo failed: %s", exc)
        return None


# ── NWS (US National Weather Service, free) ───────────────────────────────

def _nws_current(query: str) -> str | None:
    if not _is_enabled("nws"):
        return None
    try:
        with httpx.Client(timeout=10.0) as c:
            gr = c.get(OPEN_METEO_GEO, params={"name": query, "count": 1})
            gr.raise_for_status()
        results = (gr.json().get("results") or [])
        if not results:
            return None
        loc = results[0]
        if loc.get("country_code", "").upper() != "US":
            return None
        lat, lon = loc["latitude"], loc["longitude"]

        with httpx.Client(timeout=10.0) as c:
            pr = c.get(NWS_URL.format(lat=lat, lon=lon),
                       headers={"User-Agent": "vn-mcp-hub/0.1", "Accept": "application/json"})
            pr.raise_for_status()
        forecast_url = pr.json().get("properties", {}).get("forecast")
        if not forecast_url:
            return None
        with httpx.Client(timeout=10.0) as c:
            fr = c.get(forecast_url, headers={"User-Agent": "vn-mcp-hub/0.1", "Accept": "application/json"})
            fr.raise_for_status()
        period = (fr.json().get("properties", {}).get("periods") or [])[0]
        return (
            f"**Thoi tiet {loc.get('name', query)}, US (NWS):** {period.get('shortForecast','')}\n"
            f"- Nhiet do: {period.get('temperature')}F ({period.get('temperatureUnit','F')})\n"
            f"- Gio: {period.get('windSpeed','')} {period.get('windDirection','')}\n"
            f"- {period.get('detailedForecast','')}"
        )
    except Exception as exc:
        logger.warning("NWS failed: %s", exc)
        return None


# ── AccuWeather (free tier 50/day) ────────────────────────────────────────

def _accuweather_current(query: str) -> str | None:
    if not _is_enabled("accuweather"):
        return None
    api_key = os.environ.get("ACCUWEATHER_API_KEY", "")
    if not api_key:
        try:
            from src.sources_config import get_api_key
            api_key = get_api_key("accuweather")
        except Exception:
            pass
    if not api_key:
        return None
    try:
        with httpx.Client(timeout=10.0) as c:
            gr = c.get(ACCUWEATHER_GEO, params={"apikey": api_key, "q": query, "language": "vi"})
            gr.raise_for_status()
        results = gr.json() or []
        if not results:
            return None
        loc_key = results[0]["Key"]
        name = results[0].get("LocalizedName", query)
        country = results[0].get("Country", {}).get("LocalizedName", "")

        with httpx.Client(timeout=10.0) as c:
            cr = c.get(ACCUWEATHER_CURRENT.format(key=loc_key),
                       params={"apikey": api_key, "language": "vi", "details": "true"})
            cr.raise_for_status()
        cur = (cr.json() or [{}])[0]
        temp = cur.get("Temperature", {}).get("Metric", {}).get("Value", "?")
        feels = cur.get("RealFeelTemperature", {}).get("Metric", {}).get("Value", "?")
        desc = cur.get("WeatherText", "")
        humidity = cur.get("RelativeHumidity", "?")
        wind = cur.get("Wind", {})
        wind_speed = wind.get("Speed", {}).get("Metric", {}).get("Value", "?")
        wind_dir = wind.get("Direction", {}).get("Localized", "")
        uv = cur.get("UVIndex", "?")
        return (
            f"**Thoi tiet {name}, {country} (AccuWeather):** {desc}\n"
            f"- Nhiet do: {temp}C (cam giac {feels}C)\n"
            f"- Do am: {humidity}%\n"
            f"- Gio: {wind_speed} km/h {wind_dir}\n"
            f"- UV: {uv}"
        )
    except Exception as exc:
        logger.warning("AccuWeather failed: %s", exc)
        return None


# ── wttr.in (fallback, free) ──────────────────────────────────────────────

def _normalise(city: str) -> str:
    key = city.strip().lower()
    return ALIAS.get(key, city.strip())


def _wttr_current(city: str) -> str | None:
    if not _is_enabled("wttr"):
        return None
    location = _normalise(city)
    url = WTTR_URL.format(location=location.replace(" ", "+"))
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, params={"format": "j1", "lang": "vi"})
            r.raise_for_status()
        data = r.json()
        cur = (data.get("current_condition") or [{}])[0]
        nearest = (data.get("nearest_area") or [{}])[0]
        name = ((nearest.get("areaName") or [{}])[0]).get("value", "")
        country = ((nearest.get("country") or [{}])[0]).get("value", "")
        desc = ((cur.get("lang_vi") or [{}])[0]).get("value") or \
               ((cur.get("weatherDesc") or [{}])[0]).get("value", "")
        return (
            f"**Thoi tiet {name}, {country} (wttr.in):** {desc}\n"
            f"- Nhiet do: {cur.get('temp_C')}C (cam giac {cur.get('FeelsLikeC')}C)\n"
            f"- Do am: {cur.get('humidity')}%\n"
            f"- Gio: {cur.get('windspeedKmph')} km/h\n"
            f"- May: {cur.get('cloudcover')}%\n"
            f"- UV: {cur.get('uvIndex')}"
        )
    except Exception as exc:
        logger.warning("wttr fetch failed for %s: %s", city, exc)
        return None


# ── MCP Tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_current_weather(city: str) -> str:
    """Lay thoi tiet hien tai. Ho tro VN va quoc te.

    Args:
        city: Ten thanh pho (vd: "Ha Noi", "London", "New York").
    Returns:
        Mo ta thoi tiet: nhiet do, do am, gio, UV.
    """
    # Try sources in priority order: Open-Meteo -> AccuWeather -> NWS -> wttr
    for fn in (_open_meteo_current, _accuweather_current, _nws_current, _wttr_current):
        result = fn(city)
        if result:
            return result
    return f"Khong lay duoc thoi tiet cho '{city}'. Thu lai sau."


@mcp.tool()
def get_forecast(city: str, days: int = 3) -> str:
    """Lay du bao thoi tiet 1-3 ngay.

    Args:
        city: Ten thanh pho.
        days: So ngay du bao (1-3, mac dinh 3).
    Returns:
        Tom tat du bao tung ngay.
    """
    days = max(1, min(3, days))
    if not _is_enabled("wttr"):
        return "Du bao chi kha dung qua wttr.in (dang tat trong Sources). Bat wttr trong Studio."
    location = _normalise(city)
    url = WTTR_URL.format(location=location.replace(" ", "+"))
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, params={"format": "j1", "lang": "vi"})
            r.raise_for_status()
        data = r.json()
    except Exception as exc:
        return f"Khong lay duoc du bao cho '{city}': {exc}"
    weather = data.get("weather") or []
    lines = [f"**Du bao {city}:**"]
    for d in weather[:days]:
        date = d.get("date")
        mn = d.get("mintempC")
        mx = d.get("maxtempC")
        avg = d.get("avgtempC")
        hourly = d.get("hourly") or []
        midday = hourly[len(hourly) // 2] if hourly else {}
        desc = ((midday.get("lang_vi") or [{}])[0]).get("value") or \
               ((midday.get("weatherDesc") or [{}])[0]).get("value", "")
        lines.append(f"- {date}: {mn}-{mx}C (TB {avg}C), {desc}")
    return "\n".join(lines)
