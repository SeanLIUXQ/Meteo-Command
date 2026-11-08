"""City catalogue, durable favourites and resilient Open-Meteo aggregation."""

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import csv
from datetime import datetime, timedelta, timezone
import json
import logging
import math
import os
from pathlib import Path
import sys
import tempfile
from threading import BoundedSemaphore, RLock
import time

from flask import Flask, jsonify, render_template, request
import requests
from werkzeug.exceptions import HTTPException

from . import __version__

LOG = logging.getLogger(__name__)
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
MAX_FAVOURITES = 20


def number(value):
    """Accept finite JSON numbers, never booleans or numeric-looking text."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        return None


def coordinates(lat, lon):
    try:
        if isinstance(lat, bool) or isinstance(lon, bool):
            raise ValueError
        latitude, longitude = float(lat), float(lon)
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            raise ValueError
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError
        return latitude, longitude
    except (TypeError, ValueError, OverflowError):
        raise ValueError("请提供有效的纬度（-90～90）和经度（-180～180）。") from None


def default_data_dir():
    if os.environ.get("METEO_DATA_DIR"):
        return Path(os.environ["METEO_DATA_DIR"]).expanduser().resolve()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Meteo-Command"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Meteo-Command"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "meteo-command"


class CityCatalog:
    def __init__(self, filename):
        self.cities = []
        self.by_id = {}
        self.aliases = {}
        groups = {}
        taiwan_major = {"台北", "高雄", "台中", "台南", "桃园", "新竹", "基隆", "嘉义", "花莲", "台东", "宜兰", "屏东", "苗栗", "南投"}
        with Path(filename).open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                lat, lon = coordinates(row["Latitude"], row["Longitude"])
                city = {
                    "id": row["Location_ID"], "name": row["Location_Name_ZH"],
                    "province": row["Adm1_Name_ZH"], "prefecture": row["Adm2_Name_ZH"],
                    "lat": lat, "lon": lon,
                }
                self.cities.append(city)
                self.by_id[city["id"]] = city
                self.aliases[city["id"]] = " ".join((city["name"], city["province"], city["prefecture"], row["Location_Name_EN"], row["Adm1_Name_EN"])).casefold()
                if "台湾" in city["province"]:
                    if city["name"].removesuffix("市") in taiwan_major:
                        groups[(city["province"], city["name"])] = city
                    continue
                key = (city["province"], city["prefecture"])
                previous = groups.get(key)
                rank = (city["name"].removesuffix("市") != city["prefecture"].removesuffix("市"), len(city["name"]))
                if previous is None:
                    groups[key] = city
                else:
                    old_rank = (previous["name"].removesuffix("市") != previous["prefecture"].removesuffix("市"), len(previous["name"]))
                    if rank < old_rank:
                        groups[key] = city
        self.map_cities = list(groups.values())

    def search(self, query, limit=20):
        query = query.strip().casefold()
        if not query:
            return []
        terms = query.replace("-", " ").split()
        matches = [city for city in self.cities if all(term in self.aliases[city["id"]] for term in terms)]
        matches.sort(key=lambda city: (city["name"].casefold() != query, not city["name"].casefold().startswith(query), len(city["name"]), city["province"], city["id"]))
        return matches[:limit]

    def resolve(self, data, legacy=False):
        if not isinstance(data, dict):
            raise ValueError("city 必须是城市对象。")
        if isinstance(data.get("id"), str) and data["id"] in self.by_id:
            return deepcopy(self.by_id[data["id"]])
        lat, lon = coordinates(data.get("lat"), data.get("lon"))
        name = data.get("name")
        if not isinstance(name, str) or not 1 <= len(name) <= 80:
            raise ValueError("请提供有效的城市名称。")
        province = data.get("province")
        if legacy and " - " in name:
            name, province = (part.strip() for part in name.split(" - ", 1))
        tolerance = 0.05 if legacy else 0.00011
        for city in self.cities:
            if city["name"] == name and (not province or city["province"] == province) and abs(city["lat"] - lat) < tolerance and abs(city["lon"] - lon) < tolerance:
                return deepcopy(city)
        raise ValueError("城市不在本地目录中，请从搜索结果或地图选择。")

    def defaults(self):
        return [deepcopy(next(city for city in self.cities if city["name"] == name and city["province"] == province)) for name, province in (("北京", "北京市"), ("上海", "上海市"), ("郴州", "湖南省"))]


class StorageError(Exception):
    pass


class CityStore:
    """Single-server, thread-safe store; failed writes leave previous bytes intact."""

    def __init__(self, data_dir, catalog):
        self.path = Path(data_dir) / "saved_cities.json"
        self.catalog = catalog
        self.lock = RLock()

    def _read(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, list) or len(raw) > MAX_FAVOURITES:
                raise ValueError("invalid favourites list")
            cities = [self.catalog.resolve(item, legacy=True) for item in raw]
            if len({city["id"] for city in cities}) != len(cities):
                raise ValueError("duplicate favourites")
            return cities
        except FileNotFoundError:
            return self.catalog.defaults()
        except (OSError, ValueError, TypeError) as exc:
            LOG.error("Cannot read favourites: %s", exc)
            raise StorageError("关注文件无法读取，已保留原文件。请备份后检查 saved_cities.json。") from exc

    def list(self):
        with self.lock:
            return self._read()

    def change(self, action, city):
        with self.lock:
            cities = self._read()
            existing = any(item["id"] == city["id"] for item in cities)
            if action == "add" and existing:
                return "exists", cities
            if action == "add":
                if len(cities) >= MAX_FAVOURITES:
                    raise ValueError(f"最多可关注 {MAX_FAVOURITES} 个城市。")
                cities.append(city)
            else:
                cities = [item for item in cities if item["id"] != city["id"]]
            temporary = None
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, prefix=".cities-", suffix=".tmp", delete=False) as target:
                    temporary = Path(target.name)
                    json.dump(cities, target, ensure_ascii=False, indent=2, allow_nan=False)
                    target.flush()
                    os.fsync(target.fileno())
                os.replace(temporary, self.path)
            except OSError as exc:
                LOG.error("Cannot save favourites: %s", exc)
                raise StorageError("关注保存失败，请检查数据目录权限或磁盘空间。") from exc
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        LOG.warning("Cannot remove temporary favourites file: %s", temporary)
            return "success", cities


def get_wind_direction(degrees):
    value = number(degrees)
    if value is None:
        return "--"
    return ["北", "东北", "东", "东南", "南", "西南", "西", "西北"][int((value % 360 + 22.5) / 45) % 8] + "风"


def analyze_risks(daily, current_data):
    """Transparent weather hints; these are not official hazard warnings."""
    alerts = []

    def add(kind, level, message, window, threshold):
        alerts.append({"kind": kind, "level": level, "msg": message, "window": window, "threshold": threshold})

    today = str(current_data.get("time", ""))[:10]
    times = daily.get("time", []) if isinstance(daily.get("time"), list) else []
    try:
        final_day = (datetime.fromisoformat(today) + timedelta(days=6)).date().isoformat()
    except (TypeError, ValueError):
        final_day = None
    indices = [index for index, day in enumerate(times) if isinstance(day, str) and today <= day <= final_day] if final_day else list(range(2, min(len(times), 9)))

    def values(key):
        array = daily.get(key, [])
        if not isinstance(array, list):
            return []
        return [value for index in indices if index < len(array) and (value := number(array[index])) is not None]

    wind = number(current_data.get("wind_speed_10m"))
    if wind is not None and wind >= 62:
        add("wind", "danger", f"当前大风：{wind:g} km/h，注意高空坠物。", "当前", "10米风速 ≥ 62 km/h")
    rain = values("precipitation_sum")
    if rain and max(rain) >= 50:
        add("rain", "warning", "未来7天存在单日强降水，出行注意积水。", "今天起7天", "单日降水量 ≥ 50 mm")
    codes = values("weather_code")
    if any(code in (95, 96, 99) for code in codes):
        add("storm", "danger", "未来7天有雷暴天气，户外活动注意避雷。", "今天起7天", "WMO 天气代码 95 / 96 / 99")
    elif any(code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82) for code in codes):
        add("precipitation", "primary", "未来7天有降雨，出行可备雨具。", "今天起7天", "WMO 降雨天气代码")
    high = values("temperature_2m_max")
    if high and max(high) >= 35:
        add("heat", "warning", "未来7天最高温可能达到35°C，注意防暑。", "今天起7天", "日最高气温 ≥ 35°C")
    low = values("temperature_2m_min")
    if low and min(low) <= -5:
        add("cold", "primary", "未来7天最低温可能低至-5°C，注意保暖与结冰。", "今天起7天", "日最低气温 ≤ -5°C")
    pm = number(current_data.get("pm25"))
    if pm is not None and pm >= 75:
        add("air", "danger" if pm >= 150 else "warning", f"当前 PM2.5 浓度较高（{pm:g} μg/m³），敏感人群减少户外活动。", "当前模型小时值", "PM2.5 ≥ 75 μg/m³；不是日均 AQI 分级")
    return alerts


class UpstreamError(Exception):
    pass


class WeatherService:
    def __init__(self, ttl=300, stale_ttl=3600, max_entries=128, clock=time.monotonic):
        self.ttl, self.stale_ttl, self.max_entries = ttl, stale_ttl, max_entries
        self.clock = clock
        self.cache = OrderedDict()
        self.cache_lock = RLock()
        self.key_locks = [RLock() for _ in range(32)]
        self.slots = BoundedSemaphore(8)
        self.pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="meteo-upstream")

    @staticmethod
    def _request(url, params):
        response = requests.get(url, params=params, timeout=(3.05, 8))
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or result.get("error"):
            raise UpstreamError("Invalid upstream response")
        return result

    @staticmethod
    def _series(raw, fields, max_rows):
        if not isinstance(raw, dict) or not isinstance(raw.get("time"), list):
            return {"time": [], **{field: [] for field in fields}}
        times = raw["time"][:max_rows]
        if not all(isinstance(value, str) and len(value) <= 32 for value in times):
            return {"time": [], **{field: [] for field in fields}}
        result = {"time": times}
        for field in fields:
            array = raw.get(field)
            result[field] = [number(array[index]) if isinstance(array, list) and index < len(array) else None for index in range(len(times))]
        return result

    def _fetch(self, lat, lon):
        current_fields = ("temperature_2m", "relative_humidity_2m", "weather_code", "wind_speed_10m", "wind_direction_10m", "apparent_temperature", "surface_pressure", "visibility", "is_day")
        daily_fields = ("weather_code", "temperature_2m_max", "temperature_2m_min", "uv_index_max", "precipitation_probability_max", "precipitation_sum", "sunrise", "sunset")
        hourly_fields = ("temperature_2m", "precipitation_probability", "precipitation", "weather_code", "wind_speed_10m")
        weather_params = {
            "latitude": lat, "longitude": lon, "current": ",".join(current_fields),
            "daily": ",".join(daily_fields), "hourly": ",".join(hourly_fields),
            "timezone": "auto", "past_days": 2, "forecast_days": 7, "wind_speed_unit": "kmh", "temperature_unit": "celsius", "precipitation_unit": "mm",
        }
        air_params = {"latitude": lat, "longitude": lon, "current": "pm2_5", "timezone": "auto"}
        future_weather = self.pool.submit(self._request, WEATHER_URL, weather_params)
        future_air = self.pool.submit(self._request, AIR_URL, air_params)
        try:
            weather = future_weather.result()
        except (requests.RequestException, ValueError, UpstreamError) as exc:
            future_air.cancel()
            raise UpstreamError("Weather provider unavailable") from exc
        raw_current = weather.get("current")
        if not isinstance(raw_current, dict) or number(raw_current.get("temperature_2m")) is None:
            raise UpstreamError("Missing current weather")
        local_time = raw_current.get("time")
        try:
            datetime.fromisoformat(local_time)
        except (ValueError, TypeError):
            raise UpstreamError("Invalid current weather time") from None
        current = {key: number(raw_current.get(key)) for key in current_fields}
        current["time"] = local_time
        current["wind_direction_str"] = get_wind_direction(current["wind_direction_10m"])
        current["pm25"] = None
        warnings = []
        if any(current[field] is None for field in current_fields):
            warnings.append("部分实时气象指标暂不可用，缺失值以空值显示。")
        try:
            air = future_air.result()
            air_current = air.get("current")
            pm = number(air_current.get("pm2_5")) if isinstance(air_current, dict) else None
            if pm is None or pm < 0:
                raise UpstreamError("Missing air quality")
            current["pm25"] = pm
            current["air_quality_time"] = air_current.get("time") if isinstance(air_current.get("time"), str) else None
        except (requests.RequestException, ValueError, UpstreamError):
            warnings.append("空气质量数据暂不可用，天气数据仍可查看。")
        daily = self._series(weather.get("daily"), daily_fields, 16)
        raw_daily = weather.get("daily")
        if isinstance(raw_daily, dict):
            for field in ("sunrise", "sunset"):
                array = raw_daily.get(field)
                daily[field] = [array[index] if isinstance(array, list) and index < len(array) and isinstance(array[index], str) else None for index in range(len(daily["time"]))]
        hourly_all = self._series(weather.get("hourly"), hourly_fields, 400)
        selected = [index for index, stamp in enumerate(hourly_all["time"]) if stamp >= local_time][:24]
        hourly = {key: [array[index] for index in selected] for key, array in hourly_all.items()}
        if not daily["time"]:
            warnings.append("逐日预报暂不可用。")
        if not hourly["time"]:
            warnings.append("逐小时预报暂不可用。")
        future_indices = [index for index, stamp in enumerate(daily["time"]) if stamp >= local_time[:10]][:7]
        risk_data_complete = len(future_indices) == 7 and current["wind_speed_10m"] is not None and all(daily[field][index] is not None for field in ("weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum") for index in future_indices)
        if not risk_data_complete:
            warnings.append("风险分析所需数据不完整，请结合完整预报与官方信息判断。")
        return {
            "status": "success", "current": current, "daily": daily, "hourly": hourly,
            "alerts": analyze_risks(daily, current),
            "timezone": weather.get("timezone") if isinstance(weather.get("timezone"), str) else "auto",
            "utc_offset_seconds": number(weather.get("utc_offset_seconds")),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "meta": {"cached": False, "stale": False, "air_quality_available": current["pm25"] is not None, "risk_data_complete": risk_data_complete, "warnings": warnings},
        }

    def _cached(self, key):
        with self.cache_lock:
            entry = self.cache.get(key)
            if entry is not None:
                self.cache.move_to_end(key)
                return entry[0], deepcopy(entry[1])
        return None

    def get(self, lat, lon):
        key = (round(lat, 4), round(lon, 4))
        with self.key_locks[hash(key) % len(self.key_locks)]:
            cached = self._cached(key)
            if cached is not None and self.clock() - cached[0] < self.ttl:
                cached[1]["meta"]["cached"] = True
                return cached[1]
            acquired = self.slots.acquire(timeout=0.1)
            try:
                if not acquired:
                    raise UpstreamError("Provider concurrency limit reached")
                payload = self._fetch(*key)
                with self.cache_lock:
                    self.cache[key] = (self.clock(), deepcopy(payload))
                    self.cache.move_to_end(key)
                    while len(self.cache) > self.max_entries:
                        self.cache.popitem(last=False)
                return payload
            except UpstreamError:
                if cached is not None and self.clock() - cached[0] < self.stale_ttl:
                    payload = cached[1]
                    payload["meta"]["cached"] = True
                    payload["meta"]["stale"] = True
                    payload["meta"]["warnings"].append("天气服务暂不可用，正在显示最近一小时内的缓存，请留意数据时间。")
                    return payload
                raise
            finally:
                if acquired:
                    self.slots.release()


def create_app(config=None):
    app = Flask(__name__, template_folder=str(RESOURCE_ROOT / "templates"), static_folder=str(RESOURCE_ROOT / "static"))
    app.config.update(MAX_CONTENT_LENGTH=16 * 1024, JSON_SORT_KEYS=False, METEO_DATA_DIR=default_data_dir())
    if config:
        app.config.update(config)
    app.json.ensure_ascii = False
    catalog = CityCatalog(RESOURCE_ROOT / "China-City-List-latest.csv")
    store = CityStore(app.config["METEO_DATA_DIR"], catalog)
    weather = WeatherService()
    app.extensions.update(meteo_catalog=catalog, meteo_store=store, meteo_weather=weather)

    def error(message, status=400):
        return jsonify(status="error", msg=message), status

    @app.errorhandler(HTTPException)
    def http_error(exc):
        if request.path.startswith("/api/"):
            return error("请求格式不正确。" if exc.code == 400 else "请求无法处理。", exc.code)
        return exc

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return render_template("index.html", version=__version__)

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", version=__version__, city_count=len(catalog.cities), map_city_count=len(catalog.map_cities), cache_ttl_seconds=weather.ttl, stale_ttl_seconds=weather.stale_ttl, max_saved_cities=MAX_FAVOURITES)

    @app.get("/api/map_data")
    def map_data():
        return jsonify(catalog.map_cities)

    @app.get("/api/saved_cities")
    def saved_cities():
        try:
            return jsonify(store.list())
        except StorageError as exc:
            return error(str(exc), 500)

    @app.post("/api/manage_city")
    def manage_city():
        if not request.is_json:
            return error("请使用 application/json 提交城市信息。", 415)
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or data.get("action") not in ("add", "remove"):
            return error("action 必须为 add 或 remove，且请求必须是 JSON 对象。")
        try:
            city = catalog.resolve(data.get("city"))
            status, cities = store.change(data["action"], city)
            return jsonify(status=status, list=cities)
        except ValueError as exc:
            return error(str(exc))
        except StorageError as exc:
            return error(str(exc), 500)

    def search_query():
        query = request.args.get("q", "").strip()
        if len(query) > 80:
            raise ValueError("搜索内容请控制在80个字符内。")
        return query

    @app.get("/api/search_cities")
    def search_cities():
        try:
            return jsonify(status="success", cities=catalog.search(search_query()))
        except ValueError as exc:
            return error(str(exc))

    @app.get("/api/find_city")
    def find_city():
        try:
            matches = catalog.search(search_query())
            if not matches:
                return error("未找到城市，请尝试城市名、省份或拼音。", 404)
            return jsonify(status="success", city=matches[0], cities=matches)
        except ValueError as exc:
            return error(str(exc))

    @app.get("/api/weather_detail")
    def weather_detail():
        try:
            lat, lon = coordinates(request.args.get("lat"), request.args.get("lon"))
            return jsonify(weather.get(lat, lon))
        except ValueError as exc:
            return error(str(exc))
        except UpstreamError:
            return error("天气服务暂不可用，请稍后重试。", 503)

    return app
