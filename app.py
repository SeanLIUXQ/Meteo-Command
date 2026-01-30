from flask import Flask, render_template, request, jsonify
import requests
import csv
import concurrent.futures

app = Flask(__name__)

# --- 1. 数据加载与清洗 ---
CSV_FILE = 'China-City-List-latest.csv'
SAVED_CITIES = [
    {"name": "北京", "province": "北京市", "lat": 39.905, "lon": 116.405},
    {"name": "上海", "province": "上海市", "lat": 31.222, "lon": 121.458},
    {"name": "郴州", "province": "湖南省", "lat": 25.793, "lon": 113.033}
]
MAP_CITIES = []
ALL_CITIES_DICT = {}
TAIWAN_MAJOR = ['台北', '高雄', '台中', '台南', '桃园', '新竹', '基隆', '嘉义', '花莲', '台东', '宜兰', '屏东', '苗栗',
                '南投']
DIRECT_CITIES = ['北京', '上海', '天津', '重庆']

try:
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        prefecture_map = {}
        for row in reader:
            name = row['Location_Name_ZH']
            province = row['Adm1_Name_ZH']
            adm2 = row['Adm2_Name_ZH']
            city_data = {"name": name, "province": province, "lat": float(row['Latitude']),
                         "lon": float(row['Longitude'])}
            ALL_CITIES_DICT[name] = city_data
            ALL_CITIES_DICT[f"{name}-{province}"] = city_data

            if '台湾' in province or 'Taiwan' in row['Country_Region_EN']:
                if any(t in name for t in TAIWAN_MAJOR) and '区' not in name: MAP_CITIES.append(city_data)
                continue
            if province in DIRECT_CITIES:
                if name in DIRECT_CITIES: prefecture_map[province] = city_data
                continue
            if adm2 not in prefecture_map:
                prefecture_map[adm2] = city_data
            else:
                current_best = prefecture_map[adm2]['name']
                if len(name) < len(current_best) and name in adm2: prefecture_map[adm2] = city_data
        for k, v in prefecture_map.items(): MAP_CITIES.append(v)
except Exception as e:
    print(f"CSV Error: {e}")


def get_wind_direction(degrees):
    if degrees is None: return "--"
    dirs = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
    idx = int((degrees + 22.5) / 45) % 8
    return dirs[idx] + "风"


# --- 2. 灾害预警模型 (核心) ---
def analyze_risks(daily, current_data):
    alerts = []
    rain_codes = [51, 53, 55, 61, 63, 65, 80, 81, 82]
    storm_codes = [95, 96, 99]

    # 1. 实时极端天气
    wind = current_data.get('wind_speed_10m', 0)
    if wind > 100:
        alerts.append({"level": "danger", "msg": f"🌀 飓风/台风预警 (风速{wind}km/h)"})
    elif wind > 62:
        alerts.append({"level": "danger", "msg": f"🌬️ 烈风预警 (风速{wind}km/h)"})

    # 2. 地质灾害 (泥石流)
    precip_sum = sum(daily.get('precipitation_sum', [0] * 9))
    max_daily_rain = max(daily.get('precipitation_sum', [0] * 9))
    if precip_sum > 100 or max_daily_rain > 50:
        alerts.append({"level": "danger", "msg": "⛰️ 泥石流风险高"})

    # 3. 未来天气趋势 (从今天开始看)
    # 索引0=前天, 1=昨天, 2=今天, 3...=未来
    future_codes = daily['weather_code'][2:]

    if any(c in storm_codes for c in future_codes):
        alerts.append({"level": "danger", "msg": "⚡ 雷暴/冰雹预警"})
    elif any(c in [65, 81, 82] for c in future_codes):
        alerts.append({"level": "warning", "msg": "🌧️ 暴雨预警"})
    elif any(c in rain_codes for c in future_codes):
        alerts.append({"level": "primary", "msg": "☂️ 未来有雨"})

    # 4. 气温与污染
    temps = daily['temperature_2m_max'][2:]
    if max(temps) > 35: alerts.append({"level": "warning", "msg": "🔥 高温预警"})
    if min(daily['temperature_2m_min'][2:]) < -5: alerts.append({"level": "primary", "msg": "❄️ 寒潮预警"})

    pm = float(current_data.get('pm25', 0))
    if pm > 150:
        alerts.append({"level": "danger", "msg": f"😷 重度污染"})
    elif pm > 100:
        alerts.append({"level": "warning", "msg": f"😶 轻度污染"})

    return alerts


# --- 3. 路由 ---
@app.route('/')
def index(): return render_template('index.html')


@app.route('/api/map_data')
def get_map_data(): return jsonify(MAP_CITIES)


@app.route('/api/saved_cities')
def get_saved(): return jsonify(SAVED_CITIES)


@app.route('/api/manage_city', methods=['POST'])
def manage_city():
    data = request.json
    action = data.get('action')
    city_info = data.get('city')
    global SAVED_CITIES
    if action == 'add':
        for c in SAVED_CITIES:
            if c['name'] == city_info['name']: return jsonify({"status": "exists", "list": SAVED_CITIES})
        SAVED_CITIES.append(city_info)
    elif action == 'remove':
        SAVED_CITIES = [c for c in SAVED_CITIES if c['name'] != city_info['name']]
    return jsonify({"status": "success", "list": SAVED_CITIES})


@app.route('/api/find_city')
def find_city():
    query = request.args.get('q', '').strip()
    if not query: return jsonify({"status": "error"})
    if query in ALL_CITIES_DICT: return jsonify({"status": "success", "city": ALL_CITIES_DICT[query]})
    for name, data in ALL_CITIES_DICT.items():
        if query in name: return jsonify({"status": "success", "city": data})
    return jsonify({"status": "error"})


@app.route('/api/weather_detail')
def get_weather_detail():
    lat = request.args.get('lat')
    lon = request.args.get('lon')

    weather_url = "https://api.open-meteo.com/v1/forecast"
    weather_params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m,apparent_temperature,surface_pressure,visibility,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,uv_index_max,precipitation_probability_max,precipitation_sum",
        "timezone": "auto",
        "past_days": 2
    }
    air_url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    air_params = {"latitude": lat, "longitude": lon, "current": "pm2_5"}

    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_w = executor.submit(requests.get, weather_url, params=weather_params, timeout=5)
            future_a = executor.submit(requests.get, air_url, params=air_params, timeout=5)
            w_resp = future_w.result().json()
            a_resp = future_a.result().json()

        curr = w_resp.get('current', {})
        daily = w_resp.get('daily', {})
        curr['pm25'] = a_resp.get('current', {}).get('pm2_5', 0)
        curr['wind_direction_str'] = get_wind_direction(curr.get('wind_direction_10m'))

        alerts = analyze_risks(daily, curr)

        return jsonify({
            "status": "success",
            "current": curr,
            "daily": daily,
            "alerts": alerts
        })
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})


if __name__ == '__main__':
    app.run(debug=True, port=5000)