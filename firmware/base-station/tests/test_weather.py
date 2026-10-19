from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import threading
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from kogane_base.tools import demo_assistant as demo
from kogane_base.tools.weather import WeatherClient, WeatherError, parse_forecast


NOW = datetime(2026, 10, 18, 5, 40, tzinfo=timezone.utc)


def forecast():
    return dict(utc_offset_seconds=-14400,
                current=dict(time="2026-10-18T01:30", temperature_2m=4.7, weather_code=0),
                current_units=dict(temperature_2m="°C"),
                daily=dict(time=["2026-10-18"], weather_code=[3], temperature_2m_max=[16.5], temperature_2m_min=[4.0]),
                daily_units=dict(temperature_2m_max="°C", temperature_2m_min="°C"))


def test_real_values_location_and_local_day_are_used_for_each_request():
    calls = []
    def opener(request, timeout):
        calls.append((request.full_url, timeout))
        data = (dict(results=[dict(name="Toronto", country_code="CA", latitude=43.7, longitude=-79.4)])
                if "geocoding-api" in request.full_url else forecast())
        return io.BytesIO(json.dumps(data).encode())
    client = WeatherClient(opener=opener, now=lambda: NOW)
    report = client.get_today()
    assert (report.temperature_c, report.high_c, report.low_c) == (4.7, 16.5, 4.0)
    assert report.condition == "Clear" and report.forecast_condition == "Overcast"
    assert report.forecast_date == "2026-10-18"
    assert report.updated_local == "2026-10-18T01:30:00-04:00"
    assert "currently 5 degrees Celsius" in report.spoken()
    assert "high of 16" in report.spoken() and "overcast" in report.spoken()
    client.get_today()
    assert len(calls) == 3  # Cache coordinates, refresh forecast every time.
    geo = parse_qs(urlsplit(calls[0][0]).query)
    query = parse_qs(urlsplit(calls[1][0]).query)
    assert geo["name"] == ["Toronto"] and geo["countryCode"] == ["CA"]
    assert query["timezone"] == ["auto"] and query["forecast_days"] == ["1"]
    assert query["temperature_unit"] == ["celsius"]
    assert all(timeout == 6 for _, timeout in calls)
    # Location is still on the previous local date when UTC has crossed midnight.
    local_previous = deepcopy(forecast())
    local_previous["daily"]["time"] = ["2026-10-17"]
    local_previous["current"]["time"] = "2026-10-17T23:30"
    assert parse_forecast(local_previous, "Toronto", datetime(2026, 10, 18, 3, 40, tzinfo=timezone.utc)).forecast_date == "2026-10-17"


@pytest.mark.parametrize("section,key,value", [
    ("daily", "time", ["2026-10-17"]),
    ("current", "time", "2026-10-17T21:00"),
    ("current", "time", "2026-10-18T04:00"),
    ("current", "temperature_2m", None),
    ("current", "temperature_2m", float("nan")),
    ("current", "weather_code", True),
    ("daily", "temperature_2m_min", []),
    ("daily", "temperature_2m_min", [50]),
    ("current_units", "temperature_2m", "°F"),
])
def test_incomplete_wrong_units_or_outdated_data_is_never_a_forecast(section, key, value):
    data = forecast()
    data[section][key] = value
    with pytest.raises(WeatherError):
        parse_forecast(data, "Toronto", NOW)


@pytest.mark.parametrize("body", [b'{}', b'{"results": []}', b'not json', b'[]', b'{"error": true}', b'x'*262145],
                         ids=["missing", "empty", "invalid-json", "array", "provider-error", "oversized"])
def test_bad_location_and_provider_responses_fail_cleanly(body):
    with pytest.raises(WeatherError):
        WeatherClient(opener=lambda *args, **kwargs: io.BytesIO(body), now=lambda: NOW).get_today()


@pytest.mark.parametrize("truncated", [False, True])
def test_network_failure_does_not_return_a_cached_or_preset_forecast(truncated):
    from http.client import IncompleteRead
    def fail(*args, **kwargs):
        if truncated:
            raise IncompleteRead(b'{"current":', 100)
        raise TimeoutError("timed out")
    client = WeatherClient(opener=fail, now=lambda: NOW)
    client.location = ("Toronto", 43.7, -79.4)
    with pytest.raises(WeatherError, match="internet"):
        client.get_today()


@pytest.mark.parametrize("fail_second", [False, True])
def test_controller_fetches_in_background_and_clears_previous_values_on_failure(tmp_path, monkeypatch, fail_second):
    frames, worker_ids = [], []
    report = parse_forecast(forecast(), "Toronto", NOW)
    class Client:
        count = 0
        def __init__(self, city, country):
            assert (city, country) == ("Toronto", "CA")
        def get_today(self):
            worker_ids.append(threading.get_ident())
            self.count += 1
            if fail_second and self.count == 2:
                raise WeatherError("Test offline")
            return report
    class Panel:
        def __init__(self, *args, **kwargs):
            self.stop, self.changed = threading.Event(), threading.Event()
            self.thread = SimpleNamespace(start=lambda: None, join=lambda **kw: None)
            self.error = ""
        def set_frame(self, image, **kwargs):
            frames.append(image)
    def microphone(model, commands, paused, stop, *args):
        commands.put(("keyboard", "weather"))
        if fail_second:
            rearm = args[6]
            if rearm.wait(.5):
                commands.put(("keyboard", "weather"))
    monkeypatch.setattr(demo, "WeatherClient", Client)
    monkeypatch.setattr(demo, "PanelOutput", Panel)
    monkeypatch.setattr(demo, "voice_worker", microphone)
    monkeypatch.setattr(demo, "BASE", tmp_path)
    assert demo.main(["--headless", "--mute", "--seconds", ".6"]) == 0
    assert all(worker != threading.get_ident() for worker in worker_ids)
    assert demo.card("weather_loading_keyboard").tobytes() in [image.tobytes() for image in frames]
    expected = demo.card("weather_keyboard", weather_error="Test offline") if fail_second else demo.card("weather_keyboard", weather_report=report)
    assert frames[-1].tobytes() == expected.tobytes()
    events = [json.loads(line) for line in (tmp_path/"outputs/assistant_events.jsonl").read_text().splitlines()]
    assert events[0]["weather"]["temperature_c"] == 4.7
    assert events[0]["input"] == "keyboard" and events[0]["content"] == "Open-Meteo forecast"
    if fail_second:
        assert events[-1]["weather"] is None and events[-1]["error"] == "Test offline"


def test_preview_does_not_connect_to_weather_service(tmp_path, monkeypatch):
    def fail(self):
        pytest.fail("Static preview must not request weather")
    monkeypatch.setattr(WeatherClient, "get_today", fail)
    monkeypatch.setattr(demo, "BASE", tmp_path)
    assert demo.main(["--preview", str(tmp_path/"cards")]) == 0
    assert (tmp_path/"cards/weather.png").exists()
