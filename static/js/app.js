/* Meteo Command UI. All remote and user-provided strings enter the DOM as text. */
"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    saved: [], selected: null, weather: null, mapCities: [], map: null, chart: null,
    mode: "daily", weatherSequence: 0, weatherController: null,
    savedSequence: 0, searchSequence: 0, searchController: null,
    searchTimer: null, candidates: [], candidateIndex: -1, saving: false,
    summaries: new Map(), savedNodes: new Map(),
  };
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const number = (value, suffix = "", digits = 0) => {
    if (!finite(value)) return "—";
    const rounded = value.toFixed(digits);
    return (Number(rounded) === 0 ? (0).toFixed(digits) : rounded) + suffix;
  };
  const cityKey = (city) => city.id ? `id:${city.id}` : `geo:${Number(city.lat).toFixed(4)},${Number(city.lon).toFixed(4)}`;
  const cityRegion = (city) => [city.province, city.prefecture].filter((part, i, all) => part && all.indexOf(part) === i && part !== city.name).join(" · ");
  const wmo = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "小毛毛雨", 53: "毛毛雨", 55: "强毛毛雨", 56: "冻毛毛雨", 57: "强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "米雪", 80: "小阵雨", 81: "阵雨", 82: "强阵雨",
    85: "小阵雪", 86: "强阵雪", 95: "雷暴", 96: "雷暴伴冰雹", 99: "强雷暴伴冰雹",
  };
  const condition = (code) => finite(code) ? (wmo[code] || "未知天气") : "数据缺失";
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  async function requestJSON(url, options = {}) {
    const controller = new AbortController();
    const parentSignal = options.signal;
    let timedOut = false;
    const abort = () => controller.abort();
    if (parentSignal?.aborted) controller.abort();
    parentSignal?.addEventListener("abort", abort, { once: true });
    const timer = window.setTimeout(() => { timedOut = true; controller.abort(); }, 22000);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal, headers: { Accept: "application/json", ...options.headers } });
      let data;
      try { data = await response.json(); } catch { throw new Error("服务返回了无法读取的数据，请稍后重试。"); }
      if (!response.ok || data?.status === "error") throw new Error(data?.msg || data?.message || "请求未完成，请稍后重试。");
      return data;
    } catch (error) {
      if (timedOut) throw new Error("请求超时，请检查网络后重试。");
      if (error.name === "TypeError") throw new Error("无法连接本地服务，请确认应用仍在运行。");
      throw error;
    } finally {
      clearTimeout(timer);
      parentSignal?.removeEventListener("abort", abort);
    }
  }

  function notify(message, error = false) {
    $("notification").textContent = message;
    $("notification").className = `notification${error ? " error" : ""}`;
    $("notification").hidden = !message;
  }

  function setCurrentTemperature(value) {
    $("currentTemperature").replaceChildren(document.createTextNode(number(value)), el("span", "", "°C"));
  }

  function setBusy(busy) {
    $("currentPanel").setAttribute("aria-busy", String(busy));
    $("refreshButton").disabled = busy || !state.selected;
    $("refreshButton").textContent = busy ? "正在更新…" : "刷新天气";
  }

  function clearWeather() {
    state.weather = null;
    setCurrentTemperature(null);
    $("currentCondition").textContent = "正在获取天气…";
    $("currentRange").textContent = "最高 —° / 最低 —°";
    ["apparentTemperature", "humidity", "wind", "pressure", "pm25", "uvIndex"].forEach((id) => { $(id).textContent = "—"; });
    $("pm25").removeAttribute("title");
    $("localTime").textContent = "数据以城市当地时间展示";
    $("dataStatus").className = "data-status";
    $("dataStatus").textContent = "正在获取天气与空气质量…";
    $("forecastList").replaceChildren();
    $("riskList").replaceChildren(el("p", "muted", "正在分析气象风险参考…"));
    $("exportButton").disabled = true;
    state.chart?.clear();
    $("chartEmpty").hidden = false;
    $("chartEmpty").textContent = "正在加载气象趋势…";
  }

  async function selectCity(city, focusMap = true) {
    state.selected = city;
    const sequence = ++state.weatherSequence;
    state.weatherController?.abort();
    state.weatherController = new AbortController();
    $("cityName").textContent = city.name;
    $("cityProvince").textContent = cityRegion(city) || city.province || "城市天气";
    clearWeather();
    notify("");
    updateSaveButton();
    highlightSaved();
    updateMapSelection(focusMap);
    setBusy(true);
    try {
      const query = new URLSearchParams({ lat: city.lat, lon: city.lon });
      const data = await requestJSON(`/api/weather_detail?${query}`, { signal: state.weatherController.signal });
      if (sequence !== state.weatherSequence) return;
      state.weather = data;
      state.summaries.set(cityKey(city), { data, fetched: Date.now() });
      renderWeather(data);
      const savedNode = state.savedNodes.get(cityKey(city));
      if (savedNode) renderSummary(savedNode, data);
    } catch (error) {
      if (sequence !== state.weatherSequence || error.name === "AbortError") return;
      $("currentCondition").textContent = "暂时无法获取天气";
      $("dataStatus").textContent = error.message;
      $("dataStatus").className = "data-status is-error";
      $("chartEmpty").textContent = "天气请求未完成，点击右上角刷新天气重试。";
      $("riskList").replaceChildren(el("p", "muted", "天气数据不可用，暂不能分析风险。"));
      notify(error.message, true);
    } finally {
      if (sequence === state.weatherSequence) setBusy(false);
    }
  }

  function renderWeather(data) {
    const c = data.current || {};
    const d = data.daily || {};
    const meta = data.meta || {};
    const today = (c.time || "").slice(0, 10);
    const todayIndex = (d.time || []).indexOf(today);
    setCurrentTemperature(c.temperature_2m);
    $("currentCondition").textContent = `${condition(c.weather_code)}${c.is_day === 0 ? " · 夜间" : ""}`;
    $("currentRange").textContent = `最高 ${number(d.temperature_2m_max?.[todayIndex], "°")} / 最低 ${number(d.temperature_2m_min?.[todayIndex], "°")}`;
    $("apparentTemperature").textContent = number(c.apparent_temperature, " °C");
    $("humidity").textContent = number(c.relative_humidity_2m, "%");
    $("wind").textContent = finite(c.wind_speed_10m) ? `${c.wind_direction_str || "—"} ${number(c.wind_speed_10m, " km/h", 1)}` : "—";
    $("pressure").textContent = number(c.surface_pressure, " hPa");
    $("pm25").textContent = finite(c.pm25) ? number(c.pm25, "", 1) : "暂不可用";
    if (c.air_quality_time) $("pm25").title = `空气质量模型时间：${c.air_quality_time.replace("T", " ")}（当地时间）`;
    $("uvIndex").textContent = number(d.uv_index_max?.[todayIndex], "", 1);
    const dataTime = c.time ? c.time.replace("T", " ") : "时间未知";
    const cacheLabel = meta.stale ? "历史缓存 · 上游暂不可用" : (meta.cached ? "最近缓存" : "已更新");
    $("dataStatus").textContent = `${cacheLabel} · 数据时间 ${dataTime}`;
    $("dataStatus").className = `data-status${meta.stale ? " is-stale" : ""}`;
    $("localTime").textContent = `当地时区 ${data.timezone || "未知"} · 温度 °C · 风速 km/h`;
    const warnings = Array.isArray(meta.warnings) ? meta.warnings.filter((item) => typeof item === "string") : [];
    if (meta.stale && !warnings.length) warnings.push("当前显示先前获取的缓存数据，请留意数据时间。");
    if (meta.air_quality_available === false && !warnings.some((text) => /空气|PM/.test(text))) warnings.push("空气质量暂不可用，其他天气数据可正常查看。");
    notify(warnings.join(" "));
    renderRisks(data.alerts, meta.risk_data_complete);
    renderTrend();
  }

  function renderRisks(alerts, complete) {
    const list = $("riskList");
    list.replaceChildren();
    if (!Array.isArray(alerts) || !alerts.length) {
      list.append(el("p", "muted", complete === false ? "风险分析所需数据不完整，暂无法提供完整风险参考。" : "当前返回数据未触发内置阈值，请结合实际情况安排出行。"));
      return;
    }
    alerts.forEach((alert) => {
      const level = ["danger", "warning"].includes(alert.level) ? alert.level : "info";
      const item = el("div", `risk-item ${level}`, alert.msg || "天气风险提示");
      if (alert.window) item.append(el("span", "", alert.window));
      if (alert.threshold) item.append(el("span", "", `规则：${alert.threshold}`));
      list.append(item);
    });
    if (complete === false) list.append(el("p", "muted", "部分风险输入缺失，以上提示可能不完整。"));
  }

  function getChart() {
    if (!window.echarts) return null;
    if (!state.chart) state.chart = echarts.init($("trendChart"), null, { renderer: "canvas" });
    return state.chart;
  }

  function renderTrend() {
    $("dailyTab").setAttribute("aria-pressed", String(state.mode === "daily"));
    $("hourlyTab").setAttribute("aria-pressed", String(state.mode === "hourly"));
    if (!state.weather) return;
    const hourly = state.mode === "hourly";
    const data = state.weather[hourly ? "hourly" : "daily"] || {};
    const dates = Array.isArray(data.time) ? data.time : [];
    const today = (state.weather.current?.time || "").slice(0, 10);
    $("trendDescription").textContent = hourly ? "城市当地时间 · 温度与逐小时降水概率" : "过去 2 天为回看数据，今天起为 7 天预报";
    $("forecastList").setAttribute("aria-label", hourly ? "逐小时天气预报" : "逐日天气预报");
    $("trendChart").setAttribute("aria-label", `${state.selected.name}${hourly ? "未来24小时" : "每日"}气温与降水概率图，下方列表提供同源文字数据`);
    $("forecastList").replaceChildren();
    $("exportButton").disabled = !dates.length;
    $("chartEmpty").hidden = dates.length > 0 && Boolean(window.echarts);
    if (!dates.length) $("chartEmpty").textContent = hourly ? "当前未返回逐小时数据，可切换每日趋势。" : "当前未返回逐日数据。";
    if (!window.echarts) $("chartEmpty").textContent = "图表资源未加载，下方仍可查看文字预报。";
    dates.forEach((date, index) => {
      const history = !hourly && today && date < today;
      const label = hourly ? `${date.slice(5, 10).replace("-", "/")} ${date.slice(11, 16)}` : (date === today ? "今天" : `${date.slice(5).replace("-", "/")}${history ? " · 历史" : ""}`);
      const day = el("div", `forecast-day${history ? " history" : ""}${!hourly && date === today ? " today" : ""}`);
      day.setAttribute("role", "listitem");
      day.append(el("div", "forecast-date", label), el("span", "forecast-condition", condition(data.weather_code?.[index])));
      const temperatures = el("div", "forecast-range", number((hourly ? data.temperature_2m : data.temperature_2m_max)?.[index], "°"));
      if (!hourly) temperatures.append(el("span", "", number(data.temperature_2m_min?.[index], "°")));
      day.append(temperatures);
      const rain = el("div", "forecast-rain", "降水概率 ");
      rain.append(el("span", "", number((hourly ? data.precipitation_probability : data.precipitation_probability_max)?.[index], "%")));
      day.append(rain);
      $("forecastList").append(day);
    });
    const chart = getChart();
    if (!chart) return;
    if (!dates.length) { chart.clear(); return; }
    const values = (key) => dates.map((_, index) => finite(data[key]?.[index]) ? data[key][index] : null);
    const series = [{ name: "降水概率", type: "bar", yAxisIndex: 1, data: values(hourly ? "precipitation_probability" : "precipitation_probability_max"), barMaxWidth: hourly ? 13 : 23, itemStyle: { color: "#dce9fa", borderRadius: [3, 3, 0, 0] }, emphasis: { itemStyle: { color: "#bdd3f2" } }, z: 1 }];
    const line = (name, field, color) => ({ name, type: "line", data: values(field), connectNulls: false, smooth: .16, showSymbol: !hourly, symbolSize: 5, lineStyle: { width: 2, color }, itemStyle: { color }, z: 3 });
    if (hourly) series.push(line("气温", "temperature_2m", "#2463c5"));
    else {
      const high = line("最高温", "temperature_2m_max", "#b36c38");
      if (dates.includes(today)) high.markLine = { silent: true, symbol: "none", lineStyle: { color: "#8c9bb0", width: 1, type: "dashed" }, label: { formatter: "今天", color: "#53647a", fontSize: 10 }, data: [{ xAxis: today }] };
      const history = dates.filter((date) => today && date < today);
      if (history.length) high.markArea = { silent: true, itemStyle: { color: "#f5f7fb" }, data: [[{ xAxis: dates[0] }, { xAxis: today || history[history.length - 1] }]] };
      series.push(high, line("最低温", "temperature_2m_min", "#2463c5"));
    }
    chart.setOption({
      animation: !reducedMotion.matches, animationDuration: 200, animationDurationUpdate: 200,
      textStyle: { fontFamily: '"Segoe UI","Microsoft YaHei",sans-serif' },
      legend: { top: 4, left: 31, itemWidth: 12, itemHeight: 7, textStyle: { fontSize: 10, color: "#53647a" }, data: hourly ? ["气温", "降水概率"] : ["最高温", "最低温", "降水概率"] },
      grid: { left: 44, right: 44, top: 46, bottom: 36 },
      tooltip: { trigger: "axis", renderMode: "richText", confine: true, textStyle: { fontSize: 11 }, valueFormatter: (value) => finite(value) ? String(value) : "数据缺失" },
      xAxis: { type: "category", data: dates, boundaryGap: true, axisTick: { show: false }, axisLine: { lineStyle: { color: "#dce4ed" } }, axisLabel: { color: "#53647a", fontSize: 10, hideOverlap: true, formatter: (value) => hourly ? `${value.slice(11, 16)}` : value.slice(5).replace("-", "/") } },
      yAxis: [{ type: "value", name: "°C", nameTextStyle: { color: "#53647a", fontSize: 10 }, scale: true, splitNumber: 3, axisLabel: { color: "#53647a", fontSize: 10 }, splitLine: { lineStyle: { color: "#edf1f6", type: "dashed" } } }, { type: "value", min: 0, max: 100, interval: 50, name: "%", nameTextStyle: { color: "#53647a", fontSize: 10 }, axisLabel: { color: "#53647a", fontSize: 10 }, splitLine: { show: false } }],
      series,
    }, true);
    chart.resize();
  }

  async function initMap() {
    if (!window.echarts) { $("mapMessage").textContent = "地图资源未加载，请通过搜索选择城市。"; return; }
    try {
      const [geo, cities] = await Promise.all([requestJSON("/static/data/china.json"), requestJSON("/api/map_data")]);
      if (!Array.isArray(cities)) throw new Error("城市节点数据格式异常");
      state.mapCities = cities;
      echarts.registerMap("china", geo);
      state.map = echarts.init($("chinaMap"), null, { renderer: "canvas" });
      state.map.setOption({ animation: !reducedMotion.matches, backgroundColor: "#f7fafe", tooltip: { trigger: "item", renderMode: "richText", formatter: (params) => params.data?.raw ? `${params.data.raw.name}\n${cityRegion(params.data.raw)}` : params.name, textStyle: { fontSize: 11 } }, geo: { map: "china", roam: true, zoom: 1.12, layoutCenter: ["48%", "48%"], layoutSize: "103%", scaleLimit: { min: .8, max: 8 }, itemStyle: { areaColor: "#e9f0f8", borderColor: "#a6bdd9", borderWidth: .65 }, emphasis: { label: { show: false }, itemStyle: { areaColor: "#dce8f8" } }, label: { show: false } }, series: [{ id: "cities", type: "scatter", coordinateSystem: "geo", symbolSize: 4, data: cities.map((city) => ({ name: city.name, value: [city.lon, city.lat], raw: city })), itemStyle: { color: "#3f75bb", opacity: .8 }, emphasis: { scale: 2 } }, { id: "selection", type: "scatter", coordinateSystem: "geo", symbolSize: 11, data: [], itemStyle: { color: "#2463c5", borderWidth: 2, borderColor: "#fff" }, z: 4 }] });
      state.map.on("click", (params) => { if (params.data?.raw) selectCity(params.data.raw); });
      $("mapMessage").hidden = true;
      $("mapCaption").textContent = `${cities.length} 个城市节点 · 拖动、缩放，点击查看天气`;
      updateMapSelection(false);
    } catch (error) {
      $("mapMessage").textContent = "地图暂不可用，请通过上方搜索选择城市。";
      $("resetMapButton").disabled = true;
    }
  }

  function updateMapSelection(focus) {
    if (!state.map || !state.selected) return;
    const city = state.selected;
    const update = { series: [{ id: "selection", data: [{ name: city.name, value: [city.lon, city.lat], raw: city }] }] };
    if (focus) update.geo = { center: [city.lon, city.lat], zoom: 2.8 };
    state.map.setOption(update);
  }

  function resetMap() {
    state.map?.setOption({ geo: { center: null, zoom: 1.12 } });
  }

  function updateSaveButton() {
    const saved = state.selected && state.saved.some((city) => cityKey(city) === cityKey(state.selected));
    $("saveButton").textContent = state.saving ? "正在保存…" : (saved ? "已关注 · 取消" : "加入关注");
    $("saveButton").disabled = !state.selected || state.saving;
    $("saveButton").setAttribute("aria-pressed", String(Boolean(saved)));
  }

  function highlightSaved() {
    for (const [key, nodes] of state.savedNodes) {
      const active = Boolean(state.selected && key === cityKey(state.selected));
      nodes.card.classList.toggle("active", active);
      if (active) nodes.select.setAttribute("aria-current", "true");
      else nodes.select.removeAttribute("aria-current");
    }
  }

  function renderSummary(nodes, data) {
    const current = data.current || {};
    nodes.temperature.textContent = number(current.temperature_2m, "°");
    nodes.condition.textContent = condition(current.weather_code);
    nodes.detail.textContent = `${data.meta?.stale ? "历史缓存 · " : ""}PM2.5 ${number(current.pm25)}${data.alerts?.length ? ` · ${data.alerts.length} 项提示` : ""}`;
  }

  async function loadSaved(autoSelect = false) {
    const sequence = ++state.savedSequence;
    try {
      const cities = await requestJSON("/api/saved_cities");
      if (sequence !== state.savedSequence) return;
      if (!Array.isArray(cities)) throw new Error("关注列表格式异常，请重试。");
      state.saved = cities;
      renderSaved(sequence);
      if (autoSelect && !state.selected && cities[0]) selectCity(cities[0], false);
    } catch (error) {
      if (sequence !== state.savedSequence) return;
      $("savedList").replaceChildren(el("p", "empty-saved", "关注列表读取失败。"));
      const retry = el("button", "button button-small", "重新读取");
      retry.type = "button";
      retry.addEventListener("click", () => loadSaved(autoSelect));
      $("savedList").append(retry);
      notify(error.message, true);
    }
  }

  function renderSaved(sequence) {
    $("savedList").replaceChildren();
    $("savedCount").textContent = String(state.saved.length);
    state.savedNodes.clear();
    if (!state.saved.length) $("savedList").append(el("p", "empty-saved", "还没有关注城市。搜索一座城市，点击“加入关注”。"));
    state.saved.forEach((city) => {
      const card = el("div", "saved-item");
      const select = el("button", "city-select");
      select.type = "button";
      const heading = el("div", "saved-item-title");
      heading.append(el("span", "saved-city-name", city.name), el("span", "saved-province", city.province));
      const weather = el("div", "saved-weather");
      const temperature = el("span", "saved-temp", "—°");
      const conditionNode = el("span", "", "读取中…");
      weather.append(temperature, conditionNode);
      const detail = el("div", "saved-detail", "正在获取观测数据");
      select.append(heading, weather, detail);
      select.addEventListener("click", () => selectCity(city));
      const remove = el("button", "remove-city", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", `取消关注${city.name}（${cityRegion(city) || city.province}）`);
      remove.addEventListener("click", () => manageCity("remove", city));
      card.append(select, remove);
      $("savedList").append(card);
      const nodes = { card, select, temperature, condition: conditionNode, detail };
      state.savedNodes.set(cityKey(city), nodes);
      const cached = state.summaries.get(cityKey(city));
      if (cached && Date.now() - cached.fetched < 300000) renderSummary(nodes, cached.data);
    });
    updateSaveButton();
    highlightSaved();
    const queue = state.saved.filter((city) => {
      const cache = state.summaries.get(cityKey(city));
      return !cache || Date.now() - cache.fetched >= 300000;
    });
    // Three workers cap background network traffic even with a full watchlist.
    const worker = async () => {
      while (queue.length && sequence === state.savedSequence) {
        const city = queue.shift();
        const nodes = state.savedNodes.get(cityKey(city));
        try {
          const query = new URLSearchParams({ lat: city.lat, lon: city.lon });
          const data = await requestJSON(`/api/weather_detail?${query}`);
          if (sequence !== state.savedSequence) return;
          state.summaries.set(cityKey(city), { data, fetched: Date.now() });
          renderSummary(nodes, data);
        } catch {
          if (sequence !== state.savedSequence) return;
          nodes.condition.textContent = "暂不可用";
          nodes.detail.textContent = "点击城市后可重试";
        }
      }
    };
    Promise.allSettled(Array.from({ length: Math.min(3, queue.length) }, worker));
  }

  async function manageCity(action, city) {
    if (state.saving) return;
    state.saving = true;
    updateSaveButton();
    document.querySelectorAll(".remove-city").forEach((button) => { button.disabled = true; });
    try {
      const response = await requestJSON("/api/manage_city", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, city }) });
      if (Array.isArray(response.list)) {
        state.saved = response.list;
        renderSaved(++state.savedSequence);
      } else await loadSaved();
      notify(action === "add" ? `已关注${city.name}，重启应用后仍会保留。` : `已取消关注${city.name}。`);
    } catch (error) { notify(error.message, true); }
    finally {
      state.saving = false;
      updateSaveButton();
      document.querySelectorAll(".remove-city").forEach((button) => { button.disabled = false; });
    }
  }

  function closeSearch() {
    clearTimeout(state.searchTimer);
    state.searchController?.abort();
    ++state.searchSequence;
    $("searchResults").hidden = true;
    $("searchInput").setAttribute("aria-expanded", "false");
    $("searchInput").removeAttribute("aria-activedescendant");
    state.candidates = [];
    state.candidateIndex = -1;
  }

  function showSearchMessage(message) {
    const status = el("p", "search-message", message);
    status.setAttribute("role", "option");
    status.setAttribute("aria-disabled", "true");
    $("searchResults").replaceChildren(status);
    $("searchResults").hidden = false;
    $("searchInput").setAttribute("aria-expanded", "true");
  }

  function chooseCandidate(city) {
    $("searchInput").value = city.name;
    closeSearch();
    selectCity(city);
  }

  async function searchCities() {
    const query = $("searchInput").value.trim();
    if (!query) { closeSearch(); return; }
    const sequence = ++state.searchSequence;
    state.searchController?.abort();
    state.searchController = new AbortController();
    state.candidates = [];
    state.candidateIndex = -1;
    $("searchInput").removeAttribute("aria-activedescendant");
    showSearchMessage("正在搜索城市…");
    try {
      const response = await requestJSON(`/api/search_cities?${new URLSearchParams({ q: query })}`, { signal: state.searchController.signal });
      if (sequence !== state.searchSequence) return;
      state.candidates = Array.isArray(response.cities) ? response.cities : [];
      if (!state.candidates.length) { showSearchMessage("未找到匹配城市，请试试省份或区县名称。"); return; }
      $("searchResults").replaceChildren();
      state.candidates.forEach((city, index) => {
        const option = el("button", "search-result");
        option.id = `search-option-${index}`;
        option.type = "button";
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", "false");
        option.append(el("strong", "", city.name), el("span", "", cityRegion(city) || city.province));
        option.addEventListener("click", () => chooseCandidate(city));
        $("searchResults").append(option);
      });
    } catch (error) {
      if (sequence !== state.searchSequence || error.name === "AbortError") return;
      showSearchMessage(error.message);
    }
  }

  function searchKeydown(event) {
    if (event.isComposing) return;
    if (event.key === "Escape") { closeSearch(); return; }
    if (!state.candidates.length || $("searchResults").hidden) return;
    if (["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      const increment = event.key === "ArrowDown" ? 1 : -1;
      state.candidateIndex = state.candidateIndex === -1 ? (increment === 1 ? 0 : state.candidates.length - 1) : (state.candidateIndex + increment + state.candidates.length) % state.candidates.length;
      document.querySelectorAll(".search-result").forEach((option, index) => option.setAttribute("aria-selected", String(index === state.candidateIndex)));
      const option = $(`search-option-${state.candidateIndex}`);
      $("searchInput").setAttribute("aria-activedescendant", option.id);
      option.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter" && state.candidateIndex >= 0) {
      event.preventDefault();
      chooseCandidate(state.candidates[state.candidateIndex]);
    }
  }

  function exportCSV() {
    if (!state.weather || !state.selected) return;
    const hourly = state.mode === "hourly";
    const data = state.weather[hourly ? "hourly" : "daily"] || {};
    const dates = Array.isArray(data.time) ? data.time : [];
    if (!dates.length) return;
    const headers = ["城市", "省份", "时区", "数据时间", "历史缓存", "当地日期时间", "类型", "天气", ...(hourly ? ["气温(°C)", "降水概率(%)", "降水量(mm)", "风速(km/h)"] : ["最高温(°C)", "最低温(°C)", "降水概率(%)", "降水量(mm)"])];
    const fields = hourly ? ["temperature_2m", "precipitation_probability", "precipitation", "wind_speed_10m"] : ["temperature_2m_max", "temperature_2m_min", "precipitation_probability_max", "precipitation_sum"];
    const today = (state.weather.current?.time || "").slice(0, 10);
    const rows = dates.map((date, index) => [state.selected.name, state.selected.province, state.weather.timezone || "", state.weather.current?.time || "", state.weather.meta?.stale ? "是" : "否", date, !hourly && today && date < today ? "历史回看" : "预报", condition(data.weather_code?.[index]), ...fields.map((field) => finite(data[field]?.[index]) ? data[field][index] : "")]);
    const escape = (value) => {
      let text = String(value ?? "");
      if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) text = "'" + text;
      return `"${text.replace(/"/g, '""')}"`;
    };
    const csv = "\ufeff" + [headers, ...rows].map((row) => row.map(escape).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" }));
    const link = el("a");
    link.href = url;
    link.download = `Meteo-${state.selected.name.replace(/[<>:"/\\|?*\x00-\x1F]/g, "_")}-${hourly ? "hourly" : "daily"}.csv`;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function init() {
    $("dateLabel").textContent = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" }).format(new Date());
    $("refreshButton").disabled = true;
    $("refreshButton").addEventListener("click", () => { if (state.selected) selectCity(state.selected, false); });
    $("resetMapButton").addEventListener("click", resetMap);
    $("saveButton").addEventListener("click", () => {
      if (!state.selected) return;
      manageCity(state.saved.some((city) => cityKey(city) === cityKey(state.selected)) ? "remove" : "add", state.selected);
    });
    $("dailyTab").addEventListener("click", () => { state.mode = "daily"; renderTrend(); });
    $("hourlyTab").addEventListener("click", () => { state.mode = "hourly"; renderTrend(); });
    $("exportButton").addEventListener("click", exportCSV);
    $("searchForm").addEventListener("submit", (event) => { event.preventDefault(); clearTimeout(state.searchTimer); searchCities(); });
    $("searchInput").addEventListener("input", (event) => {
      if (event.isComposing) return;
      closeSearch();
      if ($("searchInput").value.trim()) state.searchTimer = window.setTimeout(searchCities, 280);
    });
    $("searchInput").addEventListener("compositionend", () => { closeSearch(); state.searchTimer = window.setTimeout(searchCities, 280); });
    $("searchInput").addEventListener("keydown", searchKeydown);
    document.addEventListener("click", (event) => { if (!$("searchForm").contains(event.target)) closeSearch(); });
    const resize = () => { state.map?.resize(); state.chart?.resize(); };
    if (window.ResizeObserver) { const observer = new ResizeObserver(resize); observer.observe($("workspace")); }
    else window.addEventListener("resize", resize);
    reducedMotion.addEventListener?.("change", () => { renderTrend(); state.map?.setOption({ animation: !reducedMotion.matches }); });
    initMap();
    loadSaved(true);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
