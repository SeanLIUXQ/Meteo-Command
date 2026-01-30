<img width="2149" height="1226" alt="image" src="https://github.com/user-attachments/assets/0f46959c-70ee-4e60-80d3-ce671d6d9709" /># 🌦️ Meteo Command | 中国各省县市区天气预报系统

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/) [![Flask](https://img.shields.io/badge/Flask-2.0%2B-green)](https://flask.palletsprojects.com/)[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

一个基于 Python Flask 构建的现代化全域气象监测系统。集成中国地级市可视化地图、多维度热力图层、极端天气智能预警以及历史数据回溯功能。

无需 API Key，开箱即用，数据源自 Open-Meteo。
<img width="2149" height="1226" alt="image" src="https://github.com/user-attachments/assets/271fe581-cef1-4f5f-8108-75a60b0723ec" />

---

## ✨ 核心功能

* **🌏 交互式可视化地图**
    * 基于 **ECharts** 的中国地理信息展示。
    * **多图层切换**：支持正常视图、温度热力图、气压分布图、云量分布图。
    * **智能交互**：点击城市平滑缩放定位（Fly-to），支持模糊搜索全国城市。
    * **性能优化**：后端并发请求，前端按需加载，流畅渲染 300+ 地级市节点。

* **🚨 智能灾害预警系统**
    * 内置逻辑算法，自动分析气象数据。
    * 支持 **台风/飓风、泥石流风险、雷暴、暴雨、高温、寒潮** 等极端天气检测。
    * **空气质量监控**：实时 PM2.5 分级预警（呼吸灯特效）。

* **📊 全面的数据面板**
    * **时光机**：同屏展示“过去2天历史”与“未来7天预测”的气温走势对比。
    * **微型气象站**：侧边栏实时显示关注城市的温度区间、天气图标及预警状态。
    * **专业指标**：包含体感温度、相对湿度、气压、能见度、紫外线指数、风向风速等。

---

## 📂 项目结构

```text
Meteo-Command/
│
├── app.py                     # Python 后端核心 (Flask, API 聚合, 并发处理)
├── China-City-List-latest.csv # 城市经纬度数据库 (含行政区划信息)
├── saved_cities.json          # 用户关注城市存储 (自动生成)
├── requirements.txt           # 项目依赖列表
│
└── templates/
    └── index.html             # 前端单页应用 (HTML/JS/ECharts/Bootstrap)
```

## 🚀 快速开始 (安装指南)

### 1. 环境准备

确保你的电脑已安装 [Python 3.8](https://www.python.org/) 或更高版本，以及 Git。

### 2. 克隆项目

Bash

```
git clone [https://github.com/你的用户名/Meteo-Command.git](https://github.com/你的用户名/Meteo-Command.git)
cd Meteo-Command
```

### 3. 创建虚拟环境 (推荐)

为了保持环境整洁，建议使用虚拟环境：

- **Windows:**

  Bash

  ```
  python -m venv venv
  .\venv\Scripts\activate
  ```

- **macOS / Linux:**

  Bash

  ```
  python3 -m venv venv
  source venv/bin/activate
  ```

### 4. 安装依赖

创建并安装 `requirements.txt`：

首先在项目根目录创建一个名为 `requirements.txt` 的文件，内容如下：

Plaintext

```
Flask
requests
```

然后运行安装命令：

Bash

```
pip install -r requirements.txt
```

### 5. 运行项目

Bash

```
python app.py
```

看到如下输出即表示启动成功：

Plaintext

```
 * Running on [http://127.0.0.1:5000](http://127.0.0.1:5000)
```

### 6. 访问应用

打开浏览器访问：[http://127.0.0.1:5000](https://www.google.com/url?sa=E&source=gmail&q=http://127.0.0.1:5000)

------

## 🛠️ 技术栈

- **后端**: Python, Flask, Concurrent.futures (线程池并发)
- **前端**: HTML5, Bootstrap 5 (UI布局)
- **数据可视化**: Apache ECharts (地图/热力图), Chart.js (折线图/注解)
- **数据源**:
  - [Open-Meteo API](https://open-meteo.com/) (天气/空气质量/历史数据)
  - 本地 CSV 数据库 (城市坐标)

------

## 🚢 部署指南

### 方法一：使用 Docker (推荐)

1. 在项目根目录创建 `Dockerfile`：

   Dockerfile

   ```
   FROM python:3.9-slim
   
   WORKDIR /app
   
   COPY requirements.txt requirements.txt
   RUN pip install -r requirements.txt
   
   COPY . .
   
   EXPOSE 5000
   
   CMD ["python", "app.py"]
   ```

2. 构建并运行：

   Bash

   ```
   docker build -t weather-dashboard .
   docker run -p 5000:5000 weather-dashboard
   ```

### 方法二：部署到云服务器 (Linux)

1. 上传代码到服务器。

2. 安装依赖 `pip install -r requirements.txt`。

3. 使用 Gunicorn 运行 (生产环境建议)：

   Bash

   ```
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```

------

## 📝 注意事项

1. **数据源**：本项目使用的 Open-Meteo 免费版 API 有调用频率限制（通常每小时几千次），个人使用完全足够。
2. **首次启动**：启动时后端会批量拉取全国主要城市的天气数据以生成热力图，这可能需要 2-3 秒的时间。
3. **CSV 文件**：`China-City-List-latest.csv` 是地图定位的核心，请勿删除或修改列名。

------

## 🤝 贡献

欢迎提交 Issue 或 Pull Request！ 如果你喜欢这个项目，请给一个 ⭐️ Star！

## 📄 License


[MIT License](https://www.google.com/search?q=LICENSE)
