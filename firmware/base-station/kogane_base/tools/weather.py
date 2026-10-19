"""Free Open-Meteo forecast requests; no API key, audio upload or preset fallback."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from http.client import HTTPException
import json
import math
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class WeatherError(RuntimeError):
    pass


CONDITIONS = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Freezing fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow",
    77: "Snow grains", 80: "Rain showers", 81: "Rain showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorms", 96: "Storms with hail",
    99: "Storms with hail",
}


@dataclass(frozen=True)
class WeatherReport:
    city: str
    temperature_c: float
    condition: str
    high_c: float
    low_c: float
    forecast_condition: str
    forecast_date: str
    updated_local: str
    fetched_utc: str

    def spoken(self):
        return (f"In {self.city}, it is currently {self.temperature_c:.0f} degrees Celsius, "
                f"with {self.condition.lower()}. Today's forecast is {self.forecast_condition.lower()}, "
                f"with a high of {self.high_c:.0f} and a low of {self.low_c:.0f} degrees.")


def _number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Invalid weather value")
    return float(value)


def parse_forecast(data, city, now):
    try:
        if data.get("error"):
            raise ValueError("Provider rejected request")
        offset = _number(data["utc_offset_seconds"], -50400, 50400)
        local_zone = timezone(timedelta(seconds=offset))
        local_now = now.astimezone(local_zone)
        daily, current = data["daily"], data["current"]
        day = date.fromisoformat(daily["time"][0])
        if day != local_now.date():
            raise ValueError("Forecast is not for today")
        updated = datetime.fromisoformat(current["time"])
        updated = updated.replace(tzinfo=local_zone) if updated.tzinfo is None else updated
        age = (now-updated.astimezone(timezone.utc)).total_seconds()
        if not -1800 <= age <= 7200:
            raise ValueError("Current conditions are outdated")
        if (data["current_units"]["temperature_2m"] != "°C" or
            data["daily_units"]["temperature_2m_max"] != "°C" or
            data["daily_units"]["temperature_2m_min"] != "°C"):
            raise ValueError("Unexpected temperature units")
        temperature = _number(current["temperature_2m"], -100, 70)
        high = _number(daily["temperature_2m_max"][0], -100, 70)
        low = _number(daily["temperature_2m_min"][0], -100, 70)
        if high < low:
            raise ValueError("Invalid daily temperature range")
        def condition(code):
            number = _number(code, 0, 999)
            if not number.is_integer():
                raise ValueError("Invalid condition code")
            return CONDITIONS.get(int(number), "Conditions unavailable")
        return WeatherReport(city, temperature, condition(current["weather_code"]), high, low,
                             condition(daily["weather_code"][0]), day.isoformat(),
                             updated.astimezone(local_zone).isoformat(), now.isoformat())
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        raise WeatherError("The weather service returned incomplete or outdated data") from exc


class WeatherClient:
    def __init__(self, city="Toronto", country="CA", *, opener=urlopen, now=None, timeout=6):
        self.city, self.country = city.strip(), country.upper()
        if not self.city or len(self.city) > 120 or len(self.country) != 2 or not self.country.isalpha():
            raise ValueError("Provide a city and a two-letter country code")
        self.opener, self.now, self.timeout = opener, now or (lambda: datetime.now(timezone.utc)), timeout
        self.location = None

    def _get(self, endpoint, params):
        request = Request(endpoint+"?"+urlencode(params), headers={"User-Agent": "Kogane/0.1 (personal weather display)"})
        try:
            with self.opener(request, timeout=self.timeout) as response:
                body = response.read(262145)
            if len(body) > 262144:
                raise ValueError("Weather response too large")
            data = json.loads(body.decode("utf-8"))
            if not isinstance(data, dict) or data.get("error"):
                raise ValueError("Invalid provider response")
            return data
        except (OSError, ValueError, HTTPException) as exc:
            raise WeatherError("Could not reach the weather service; check the laptop internet connection") from exc

    def get_today(self):
        if self.location is None:
            data = self._get("https://geocoding-api.open-meteo.com/v1/search",
                             dict(name=self.city, count=1, language="en", format="json", countryCode=self.country))
            try:
                place = data["results"][0]
                latitude = _number(place["latitude"], -90, 90)
                longitude = _number(place["longitude"], -180, 180)
                if place["country_code"].upper() != self.country or not isinstance(place["name"], str):
                    raise ValueError("Wrong location")
                self.location = (place["name"], latitude, longitude)
            except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
                raise WeatherError(f"Could not find {self.city} in {self.country}") from exc
        city, latitude, longitude = self.location
        data = self._get("https://api.open-meteo.com/v1/forecast", dict(
            latitude=latitude, longitude=longitude, timezone="auto", forecast_days=1,
            temperature_unit="celsius", current="temperature_2m,weather_code",
            daily="weather_code,temperature_2m_max,temperature_2m_min"))
        return parse_forecast(data, city, self.now())
