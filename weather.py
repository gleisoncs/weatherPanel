"""Weather data from Open-Meteo (free, no API key required)."""
from __future__ import annotations

import bisect
import datetime as dt
import math
import random
from dataclasses import dataclass

import requests

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

CURRENT_VARS = [
    "temperature_2m", "relative_humidity_2m", "apparent_temperature", "is_day",
    "precipitation", "weather_code", "cloud_cover", "pressure_msl",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
]
HOURLY_VARS = [
    "temperature_2m", "relative_humidity_2m", "dew_point_2m", "precipitation",
    "precipitation_probability", "weather_code", "cloud_cover", "pressure_msl",
    "visibility", "wind_speed_10m", "is_day", "uv_index",
]
DAILY_VARS = [
    "weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
    "precipitation_probability_max", "sunrise", "sunset", "uv_index_max",
    "wind_speed_10m_max",
]

UNIT_PARAMS = {
    "metric": {"temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm"},
    "imperial": {"temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch"},
}
UNIT_LABELS = {
    "metric": {"temp": "C", "wind": "km/h", "rain": "mm", "vis": "km"},
    "imperial": {"temp": "F", "wind": "mph", "rain": "in", "vis": "mi"},
}


@dataclass
class Location:
    name: str
    lat: float
    lon: float
    country: str = ""


@dataclass
class Weather:
    location: Location
    now: dt.datetime            # local time at the location
    current: dict
    hourly: dict                # lists starting at the current hour; "time" holds datetimes
    daily: dict                 # lists starting today; "time" holds dates
    pressure_3h_ago: float | None
    units: dict
    fetched_at: dt.datetime     # local time of this machine


def geocode(city: str) -> Location:
    r = requests.get(GEOCODE_URL, params={"name": city, "count": 1, "format": "json"}, timeout=15)
    r.raise_for_status()
    results = r.json().get("results")
    if not results:
        raise LookupError(f"City not found: {city!r}")
    g = results[0]
    return Location(g["name"], g["latitude"], g["longitude"], g.get("country_code", ""))


def fetch(loc: Location, units: str = "metric") -> Weather:
    params = {
        "latitude": loc.lat,
        "longitude": loc.lon,
        "timezone": "auto",
        "past_days": 1,          # gives pressure history for the trend
        "forecast_days": 7,
        "current": ",".join(CURRENT_VARS),
        "hourly": ",".join(HOURLY_VARS),
        "daily": ",".join(DAILY_VARS),
        **UNIT_PARAMS[units],
    }
    r = requests.get(FORECAST_URL, params=params, timeout=20)
    if r.status_code != 200:
        try:
            reason = r.json().get("reason", r.text)
        except ValueError:
            reason = r.text
        raise RuntimeError(f"Open-Meteo error {r.status_code}: {reason}")
    return parse(r.json(), loc, units)


def parse(j: dict, loc: Location, units: str) -> Weather:
    cur = dict(j["current"])
    now = dt.datetime.fromisoformat(cur["time"])

    h = j["hourly"]
    times = [dt.datetime.fromisoformat(t) for t in h["time"]]
    i0 = max(bisect.bisect_right(times, now) - 1, 0)
    hourly = {k: v[i0:] for k, v in h.items() if k != "time"}
    hourly["time"] = times[i0:]

    vis = h["visibility"][i0]
    if vis is not None:
        if j.get("hourly_units", {}).get("visibility") == "ft":
            vis = vis / 5280 if units == "imperial" else vis * 0.0003048
        else:
            vis = vis / 1609.34 if units == "imperial" else vis / 1000
    cur["visibility"] = vis
    cur["dew_point"] = h["dew_point_2m"][i0]
    cur["uv_index"] = h["uv_index"][i0]

    d = j["daily"]
    days = [dt.date.fromisoformat(t) for t in d["time"]]
    di = days.index(now.date()) if now.date() in days else 0
    daily = {k: v[di:] for k, v in d.items() if k != "time"}
    daily["time"] = days[di:]
    daily["sunrise"] = [dt.datetime.fromisoformat(t) for t in daily["sunrise"]]
    daily["sunset"] = [dt.datetime.fromisoformat(t) for t in daily["sunset"]]

    return Weather(
        location=loc,
        now=now,
        current=cur,
        hourly=hourly,
        daily=daily,
        pressure_3h_ago=h["pressure_msl"][i0 - 3] if i0 >= 3 else None,
        units=UNIT_LABELS[units],
        fetched_at=dt.datetime.now(),
    )


def demo(loc: Location | None = None, units: str = "metric") -> Weather:
    """Synthetic but plausible data, for offline use and testing."""
    loc = loc or Location("Demo City", 52.52, 13.41, "DE")
    rnd = random.Random(7)
    now = dt.datetime.now().replace(second=0, microsecond=0)
    start = now.replace(minute=0)
    n = 24 * 7
    times = [start + dt.timedelta(hours=i) for i in range(n)]

    def wave(i, period, phase=0.0):
        return math.sin(2 * math.pi * (i + phase) / period)

    temp, hum, pres, cloud, rain, prob, code, wind, day, uv = ([] for _ in range(10))
    for i, t in enumerate(times):
        tt = 12 + 6 * math.sin(2 * math.pi * (t.hour - 9) / 24) + 3 * wave(i, 90) + rnd.uniform(-0.4, 0.4)
        cc = max(0, min(100, 55 + 45 * wave(i, 31, 4) + rnd.uniform(-10, 10)))
        rr = max(0.0, rnd.gauss(0.6, 1.0)) if cc > 80 else 0.0
        temp.append(round(tt, 1))
        hum.append(round(max(30, min(100, 72 - 18 * math.sin(2 * math.pi * (t.hour - 9) / 24) + cc / 8))))
        pres.append(round(1014 + 9 * wave(i, 70, 10) + rnd.uniform(-0.3, 0.3), 1))
        cloud.append(round(cc))
        rain.append(round(rr, 1))
        prob.append(round(min(100, cc * 0.9 if cc > 60 else cc / 4)))
        code.append(63 if rr > 2 else 61 if rr > 0.3 else 51 if rr > 0 else 3 if cc > 85 else 2 if cc > 45 else 1 if cc > 15 else 0)
        wind.append(round(12 + 8 * wave(i, 40), 1))
        is_day = 1 if 7 <= t.hour < 19 else 0
        day.append(is_day)
        uv.append(round(max(0, 5 * math.sin(math.pi * (t.hour - 7) / 12)) * (1 - cc / 150), 1) if is_day else 0)

    hourly = {
        "time": times, "temperature_2m": temp, "relative_humidity_2m": hum,
        "dew_point_2m": [round(tt - (100 - hh) / 5, 1) for tt, hh in zip(temp, hum)],
        "precipitation": rain, "precipitation_probability": prob, "weather_code": code,
        "cloud_cover": cloud, "pressure_msl": pres, "visibility": [10000] * n,
        "wind_speed_10m": wind, "is_day": day, "uv_index": uv,
    }
    days = [start.date() + dt.timedelta(days=k) for k in range(7)]
    daily = {"time": days, "weather_code": [], "temperature_2m_max": [], "temperature_2m_min": [],
             "precipitation_sum": [], "precipitation_probability_max": [], "sunrise": [], "sunset": [],
             "uv_index_max": [], "wind_speed_10m_max": []}
    for k, d in enumerate(days):
        sl = slice(max(0, k * 24 - start.hour), (k + 1) * 24 - start.hour)
        daily["weather_code"].append(max(code[sl] or [0]))
        daily["temperature_2m_max"].append(max(temp[sl] or [0]))
        daily["temperature_2m_min"].append(min(temp[sl] or [0]))
        daily["precipitation_sum"].append(round(sum(rain[sl]), 1))
        daily["precipitation_probability_max"].append(max(prob[sl] or [0]))
        daily["sunrise"].append(dt.datetime.combine(d, dt.time(7, 12)))
        daily["sunset"].append(dt.datetime.combine(d, dt.time(18, 41)))
        daily["uv_index_max"].append(max(uv[sl] or [0]))
        daily["wind_speed_10m_max"].append(max(wind[sl] or [0]))

    current = {
        "time": now.isoformat(), "temperature_2m": temp[0], "relative_humidity_2m": hum[0],
        "apparent_temperature": round(temp[0] - 1.8, 1), "is_day": day[0], "precipitation": rain[0],
        "weather_code": code[0], "cloud_cover": cloud[0], "pressure_msl": pres[0],
        "wind_speed_10m": wind[0], "wind_direction_10m": 215, "wind_gusts_10m": round(wind[0] * 1.7),
        "visibility": 10.0, "dew_point": hourly["dew_point_2m"][0], "uv_index": uv[0],
    }
    return Weather(loc, now, current, hourly, daily, pres[0] - 1.4, UNIT_LABELS[units], dt.datetime.now())
