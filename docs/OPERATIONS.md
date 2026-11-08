# 运行、升级与排查

## 本地启动

Windows Release 完整解压后，双击 `Start-Meteo.cmd`。它会调用同目录的 `Meteo-Command.exe`；源码目录下则创建虚拟环境、安装依赖并调用 `run.py`。源码首次启动需要网络访问 Python 包索引。

程序使用 Waitress，默认仅监听 `127.0.0.1:5000`。浏览器在 `/api/health` 返回成功后打开，不会在服务尚未启动时抢先跳转。关闭终端会停止服务；命令行按 `Ctrl+C` 也可以停止。

```powershell
# Release：指定端口、不自动打开浏览器
.\Meteo-Command.exe --port 5001 --no-browser

# 源码：指定用户数据目录
$env:METEO_DATA_DIR = 'D:\MeteoData'
python run.py
```

macOS / Linux：

```bash
METEO_DATA_DIR="$PWD/user-data" sh start.sh --port 5001 --no-browser
```

## 关注数据与升级

用户数据与程序文件分开保存，具体默认路径见 README。停止应用后，备份用户数据目录中的 `saved_cities.json`，再将新 Release 解压到新目录即可。升级时保留原用户数据目录，首次关注操作会创建存储文件。

v1 实际只使用内存列表，并未持续写入项目内的 `saved_cities.json`；退出旧进程后，未自行导出的关注无法恢复。v2 不会自动加载源码根目录的旧示例文件。最稳妥的迁移方式是在界面重新搜索并关注需要的城市。

如果确实有自行保存的旧 JSON，停止应用并备份新旧文件后，可以将旧文件显式复制到用户数据目录，命名为 `saved_cities.json`。兼容格式为包含 `name`、`lat`、`lon` 的数组，支持 `北京 - 北京市` 这类旧名称，但名称与坐标必须能匹配本地城市目录。读取时会在内存中规范化，直到下一次关注操作才写回新格式；无法匹配的文件会报告错误并保留原内容。

存储为 JSON 数组，每个城市记录包含本地目录中的 `id`，以及名称、行政区域和经纬度。请优先通过页面或 `/api/manage_city` 修改，避免手动编辑引入未知城市或重复记录。遇到坏文件时应用会保留原文件并提示错误；先备份，再更正或移走该文件以恢复默认列表。

关注文件的锁用于同一服务进程中的线程。不要让多个服务进程同时写入同一用户目录；不同实例请使用各自的 `METEO_DATA_DIR`。当前没有用户账号，同一实例所有访问者共享关注列表。

## 数据与网络

地图、图表脚本、页面与城市目录均在本地。天气和空气质量需要分别访问：

- `https://api.open-meteo.com/v1/forecast`
- `https://air-quality-api.open-meteo.com/v1/air-quality`

当前缓存位于进程内，重启会清空。正常查询缓存 5 分钟；天气上游失败时，可显示不超过 1 小时的缓存并标注状态。空气质量缺失不会替换成零。新城市在从未成功查询时没有可供回退的缓存。

`/api/health` 只检查本地应用就绪状态，不代表外部天气供应商当前可用。`/api/map_data` 返回城市坐标，不是全国温度热力图；程序不会在启动时抓取全国城市天气。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 端口已被占用 | 关闭另一实例，或使用 `--port 5001`。 |
| 浏览器未自动打开 | 手动访问终端显示的地址；检查是否设置 `METEO_NO_BROWSER=1`。 |
| 打开 EXE 缺少模块或资源 | 重新完整解压 ZIP；不要单独移动 EXE 或删除 `_internal`。 |
| 有地图但无法查询天气 | 检查 Open-Meteo 网络连通性、代理和上游限流，稍后重试。 |
| 显示缓存或空气质量不可用 | 留意数据时间，等待供应商恢复后刷新；缓存不代表当前实测值。 |
| 关注保存失败 | 检查 `METEO_DATA_DIR` 目录的写权限、磁盘空间与 JSON 完整性。 |
| Linux 缺少 venv | 安装系统的 `python3-venv` 包，再运行 `sh start.sh`。 |

## Docker

```bash
docker compose up --build -d
docker compose logs -f
docker compose down
```

Compose 将 `127.0.0.1:5000` 映射到容器，并使用 `meteo-data` 卷保存关注。普通 `down` 不删除卷；备份数据时保留该命名卷。容器内服务监听 `0.0.0.0`，但宿主机仍默认只暴露本机地址。

应用未内置认证，默认设置用于个人本地运行。部署至局域网或公网前，应由反向代理提供 HTTPS、认证和访问控制；需要隔离的用户应使用独立实例和数据目录。

## 发布构建

在目标 Windows x64 环境安装 Python 3.10+，运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/build_release.py
```

输出文件：

```text
dist/
├── Meteo-Command/                             # EXE + _internal + 文档与许可
├── Meteo-Command-v2.0.0-windows-amd64.zip
└── Meteo-Command-v2.0.0-windows-amd64.zip.sha256
```

构建脚本读取 `VERSION`，归档原生程序并生成 SHA-256。PyInstaller 不提供跨平台交叉编译；本版只分发 Windows 包。修改版本时同步维护 `VERSION`、`meteo/__init__.py` 与发布说明。

GitHub `Checks` 工作流运行回归测试；`Build release` 支持手动构建，推送匹配 `VERSION` 的 `v*` 标签会在构建、测试和 EXE 健康检查成功后生成草稿 Release。人工检查下载的产物后再发布。已有 Release 不会被工作流覆盖，重跑生成的产物保留在 Actions artifacts。
