from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta
import json
from threading import Event
from unittest.mock import Mock

import pytest
import requests

from meteo.backend import AIR_URL, WEATHER_URL, CityStore, UpstreamError, WeatherService, analyze_risks, create_app, get_wind_direction


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "METEO_DATA_DIR": tmp_path})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def forecast():
    start = datetime(2026, 11, 7)
    return {
        "timezone": "Asia/Shanghai", "utc_offset_seconds": 28800,
        "current": {"time": "2026-11-09T10:15", "temperature_2m": 16, "weather_code": 0, "wind_speed_10m": 10, "wind_direction_10m": 90, "relative_humidity_2m": 60, "apparent_temperature": 15, "surface_pressure": 1013, "visibility": 10000, "is_day": 1},
        "daily": {
            "time": [(start + timedelta(days=i)).date().isoformat() for i in range(9)],
            "temperature_2m_max": [20] * 9, "temperature_2m_min": [5] * 9,
            "weather_code": [0] * 9, "precipitation_sum": [0] * 9,
        },
        "hourly": {
            "time": [(start + timedelta(hours=i)).isoformat(timespec="minutes") for i in range(216)],
            "temperature_2m": list(range(216)), "precipitation_probability": [0] * 216,
        },
    }


@pytest.fixture
def upstream(monkeypatch, forecast):
    def fetch(url, **kwargs):
        payload = forecast if url == WEATHER_URL else {"current": {"pm2_5": 20, "time": "2026-11-09T10:00"}}
        response = Mock()
        response.json.return_value = deepcopy(payload)
        return response
    mock = Mock(side_effect=fetch)
    monkeypatch.setattr("meteo.backend.requests.get", mock)
    return mock


def test_health_and_catalog_load_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app({"TESTING": True, "METEO_DATA_DIR": tmp_path})
    health = app.test_client().get("/api/health").get_json()
    assert health["version"] == "2.0.0"
    assert health["city_count"] > 3000
    assert health["map_city_count"] > 300


def test_same_name_search_and_pinyin(client):
    cities = client.get("/api/search_cities", query_string={"q": "朝阳"}).get_json()["cities"]
    exact = [city for city in cities if city["name"] == "朝阳"]
    assert len(exact) >= 3
    assert len({city["id"] for city in exact}) == len(exact)
    assert {"北京市", "吉林省", "辽宁省"} <= {city["province"] for city in exact}
    assert client.get("/api/search_cities?q=Beijing").get_json()["cities"]
    assert client.get("/api/find_city?q=北京").get_json()["city"]["name"] == "北京"
    assert client.get("/api/find_city?q=doesnotexist").status_code == 404
    assert client.get("/api/search_cities?q=" + "x" * 81).status_code == 400


@pytest.mark.parametrize("payload", [None, [], "add", {}, {"action": "clear"}, {"action": "add"}, {"action": "add", "city": []}, {"action": "add", "city": {"name": "example"}}, {"action": "add", "city": {"name": "<script>", "lat": 1, "lon": 2}}])
def test_manage_rejects_malformed_payload(client, payload):
    response = client.post("/api/manage_city", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


def test_manage_requires_json_and_bounds_body(client):
    assert client.post("/api/manage_city", data="x").status_code == 415
    assert client.post("/api/manage_city", data="{broken", content_type="application/json").status_code == 400
    assert client.post("/api/manage_city", data=json.dumps({"padding": "x" * 17000}), content_type="application/json").status_code == 413


def test_favourites_persist_and_same_name_remove_is_precise(app, tmp_path):
    client = app.test_client()
    cities = client.get("/api/search_cities?q=朝阳").get_json()["cities"][:3]
    for city in cities:
        assert client.post("/api/manage_city", json={"action": "add", "city": city}).status_code == 200
    assert client.post("/api/manage_city", json={"action": "add", "city": cities[0]}).get_json()["status"] == "exists"
    assert client.post("/api/manage_city", json={"action": "remove", "city": cities[0]}).status_code == 200
    restarted = create_app({"TESTING": True, "METEO_DATA_DIR": tmp_path}).test_client()
    ids = {city["id"] for city in restarted.get("/api/saved_cities").get_json()}
    assert cities[0]["id"] not in ids
    assert cities[1]["id"] in ids and cities[2]["id"] in ids


def test_favourites_limit_and_empty_list_stays_empty(app):
    store = app.extensions["meteo_store"]
    for city in store.list():
        store.change("remove", city)
    assert store.list() == []
    for city in app.extensions["meteo_catalog"].cities[:20]:
        store.change("add", city)
    with pytest.raises(ValueError, match="20"):
        store.change("add", app.extensions["meteo_catalog"].cities[20])


def test_corrupt_favourites_preserved_and_not_overwritten(app, tmp_path):
    path = tmp_path / "saved_cities.json"
    path.write_text("{broken", encoding="utf-8")
    client = app.test_client()
    assert client.get("/api/saved_cities").status_code == 500
    assert client.post("/api/manage_city", json={"action": "add", "city": {"id": "101010100"}}).status_code == 500
    assert path.read_text(encoding="utf-8") == "{broken"


def test_copied_legacy_favourites_are_canonicalized_without_rewriting(app, tmp_path):
    path = tmp_path / "saved_cities.json"
    legacy = '[{"name":"北京 - 北京市","lat":39.905,"lon":116.4053}]'
    path.write_text(legacy, encoding="utf-8")
    data = app.test_client().get("/api/saved_cities").get_json()
    assert data[0]["id"] == "101010100" and data[0]["name"] == "北京"
    assert path.read_text(encoding="utf-8") == legacy


def test_failed_atomic_write_preserves_previous_file(app, monkeypatch):
    store = app.extensions["meteo_store"]
    city = app.extensions["meteo_catalog"].cities[1]
    store.change("add", city)
    previous = store.path.read_bytes()
    monkeypatch.setattr("meteo.backend.os.replace", Mock(side_effect=OSError("disk full")))
    response = app.test_client().post("/api/manage_city", json={"action": "remove", "city": city})
    assert response.status_code == 500
    assert store.path.read_bytes() == previous
    assert not list(store.path.parent.glob(".cities-*.tmp"))


@pytest.mark.parametrize("query", ["", "lat=nan&lon=1", "lat=inf&lon=1", "lat=91&lon=0", "lat=0&lon=-181", "lat=abc&lon=1"])
def test_weather_rejects_bad_coordinates_without_network(client, upstream, query):
    assert client.get("/api/weather_detail?" + query).status_code == 400
    upstream.assert_not_called()


def test_weather_hourly_local_window_and_cache(client, upstream):
    response = client.get("/api/weather_detail?lat=39.9&lon=116.4")
    assert response.status_code == 200
    data = response.get_json()
    assert data["hourly"]["time"][0] == "2026-11-09T11:00"
    assert data["hourly"]["time"][-1] == "2026-11-10T10:00"
    assert data["hourly"]["temperature_2m"][0] == 59
    assert len(data["hourly"]["time"]) == 24
    assert len(data["daily"]["time"]) == 9
    assert data["current"]["pm25"] == 20
    assert data["meta"]["air_quality_available"] is True
    assert data["current"]["wind_direction_str"] == "东风"
    assert data["meta"]["cached"] is False
    assert client.get("/api/weather_detail?lat=39.9&lon=116.4").get_json()["meta"]["cached"] is True
    assert upstream.call_count == 2
    assert all(call.kwargs["params"]["timezone"] == "auto" for call in upstream.call_args_list)
    assert all(call.kwargs["timeout"] == (3.05, 8) for call in upstream.call_args_list)


def test_air_failure_does_not_hide_weather(app, upstream):
    original = upstream.side_effect
    upstream.side_effect = lambda url, **kwargs: (_ for _ in ()).throw(requests.Timeout()) if url == AIR_URL else original(url, **kwargs)
    response = app.test_client().get("/api/weather_detail?lat=39.9&lon=116.4")
    assert response.status_code == 200
    data = response.get_json()
    assert data["current"]["temperature_2m"] == 16
    assert data["current"]["pm25"] is None
    assert data["meta"]["air_quality_available"] is False
    assert data["meta"]["warnings"]


@pytest.mark.parametrize("pm", [None, "25", True, -1, float("nan")])
def test_air_missing_or_invalid_remains_unknown(app, upstream, pm):
    original = upstream.side_effect
    def fetch(url, **kwargs):
        response = original(url, **kwargs)
        if url == AIR_URL:
            response.json.return_value = {"current": {"pm2_5": pm}}
        return response
    upstream.side_effect = fetch
    data = app.test_client().get("/api/weather_detail?lat=1&lon=2").get_json()
    assert data["current"]["pm25"] is None
    assert data["meta"]["air_quality_available"] is False


def test_http_error_from_weather_is_503(client, upstream):
    upstream.side_effect = requests.HTTPError("secret provider details")
    response = client.get("/api/weather_detail?lat=1&lon=2")
    assert response.status_code == 503
    assert "secret" not in response.get_data(as_text=True)


def test_invalid_provider_shape_is_503(client, upstream):
    response = Mock()
    response.json.return_value = {"error": True, "reason": "invalid"}
    upstream.return_value = response
    upstream.side_effect = None
    assert client.get("/api/weather_detail?lat=1&lon=2").status_code == 503


def test_empty_optional_forecasts_degrade_explicitly(client, upstream, forecast):
    forecast["daily"] = {"time": []}
    forecast["hourly"] = None
    data = client.get("/api/weather_detail?lat=1&lon=2").get_json()
    assert data["status"] == "success"
    assert data["daily"]["time"] == [] and data["hourly"]["time"] == []
    assert len(data["meta"]["warnings"]) == 3
    assert data["meta"]["risk_data_complete"] is False


def test_stale_cache_expiry_and_payload_isolation(upstream):
    now = [0]
    service = WeatherService(clock=lambda: now[0], ttl=300, stale_ttl=3600, max_entries=1)
    first = service.get(1, 2)
    first["current"]["temperature_2m"] = 999
    assert service.get(1, 2)["current"]["temperature_2m"] == 16
    now[0] = 301
    upstream.side_effect = requests.Timeout()
    stale = service.get(1, 2)
    assert stale["meta"]["stale"] is True
    assert len(stale["meta"]["warnings"]) == 1
    assert len(service.get(1, 2)["meta"]["warnings"]) == 1
    now[0] = 3601
    with pytest.raises(UpstreamError):
        service.get(1, 2)


def test_bounded_cache_eviction(upstream):
    service = WeatherService(max_entries=2)
    for lat in (1, 2, 3):
        service.get(lat, 2)
    assert len(service.cache) == 2
    assert (1, 2) not in service.cache


def test_same_city_concurrent_calls_share_one_fetch(upstream):
    service = WeatherService()
    entered, release = Event(), Event()
    original = upstream.side_effect
    def fetch(url, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(url, **kwargs)
    upstream.side_effect = fetch
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(service.get, 1, 2) for _ in range(6)]
        assert entered.wait(5)
        release.set()
        results = [future.result() for future in futures]
    assert len(results) == 6
    assert upstream.call_count == 2


def test_risks_ignore_historical_rain_and_handle_nulls():
    daily = {
        "time": ["2026-11-07", "2026-11-08", "2026-11-09", "2026-11-10"],
        "precipitation_sum": [100, 100, 0, None], "weather_code": [95, 95, 0, None],
        "temperature_2m_max": [40, 40, 10, None], "temperature_2m_min": [-20, -20, 5, None],
    }
    assert analyze_risks(daily, {"time": "2026-11-09T10:00", "wind_speed_10m": None, "pm25": None}) == []
    assert analyze_risks({}, {"wind_speed_10m": None, "pm25": None}) == []
    assert analyze_risks({"precipitation_sum": [], "weather_code": [], "temperature_2m_max": [], "temperature_2m_min": []}, {}) == []


def test_risk_thresholds_are_explicit_and_do_not_claim_official_hazards():
    daily = {"time": ["2026-11-09"], "precipitation_sum": [50], "weather_code": [95], "temperature_2m_max": [35], "temperature_2m_min": [-5]}
    alerts = analyze_risks(daily, {"time": "2026-11-09T10:00", "wind_speed_10m": 62, "pm25": 150})
    assert {alert["kind"] for alert in alerts} == {"rain", "storm", "heat", "cold", "wind", "air"}
    assert all(alert["threshold"] and alert["window"] for alert in alerts)
    assert not any(term in alert["msg"] for term in ("台风", "泥石流", "寒潮", "预警") for alert in alerts)
    assert get_wind_direction(None) == "--"
    assert get_wind_direction(-90) == "西风"


def test_risks_exclude_days_outside_seven_day_window():
    daily = {"time": ["2026-11-16"], "weather_code": [95], "precipitation_sum": [100], "temperature_2m_max": [40], "temperature_2m_min": [-10]}
    assert analyze_risks(daily, {"time": "2026-11-09T10:15"}) == []
