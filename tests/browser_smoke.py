"""Optional end-to-end regression checks against a running disposable instance.

pip install playwright==1.56.0 && python -m playwright install chromium
python tests/browser_smoke.py --url http://127.0.0.1:5000
Use METEO_DATA_DIR pointing at scratch data when starting the server.
"""

import argparse
import asyncio
import copy
import csv
import io
import json
from pathlib import Path

from playwright.async_api import async_playwright, expect


ROOT = Path(__file__).resolve().parents[1]


async def run(base_url, screenshots):
    report = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": 1440, "height": 1100}, locale="zh-CN", timezone_id="Asia/Shanghai", reduced_motion="reduce")
        errors = []
        context.on("page", lambda page: page.on("pageerror", lambda error: errors.append(str(error))))
        page = await context.new_page()
        requests = []
        page.on("request", lambda request: requests.append(request.url))
        await page.goto(base_url)
        await expect(page.locator("#cityName")).to_have_text("北京")
        await expect(page.locator("#currentPanel")).to_have_attribute("aria-busy", "false", timeout=30000)
        await expect(page.locator(".forecast-day")).to_have_count(9)
        await expect(page.locator("#chinaMap canvas")).to_have_count(1)
        await expect(page.locator("#mapMessage")).to_be_hidden()
        assert all(url.startswith(base_url) or url.startswith("data:") for url in requests), requests
        await page.locator("#resetMapButton").click()
        await page.locator("#trendPanel").scroll_into_view_if_needed()
        await page.evaluate("window.scrollTo(0,0)")
        if screenshots:
            screenshots.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshots / "dashboard.png"), full_page=True)
        report.append("real weather: daily 9 rows, map rendered, all runtime resources local")

        await page.locator("#hourlyTab").click()
        await expect(page.locator(".forecast-day")).to_have_count(24)
        async with page.expect_download() as download_info:
            await page.locator("#exportButton").click()
        download = await download_info.value
        path = await download.path()
        rows = list(csv.reader(io.StringIO(Path(path).read_text(encoding="utf-8-sig"))))
        assert len(rows) == 25 and "气温(°C)" in rows[0]
        await page.locator("#dailyTab").click()
        report.append("hourly mode and CSV download: 24 records with UTF-8 headers")

        await page.locator("#searchInput").fill("朝阳")
        await expect(page.locator(".search-result").nth(1)).to_be_visible()
        names = await page.locator(".search-result").all_text_contents()
        assert any("北京" in name for name in names) and any("辽宁" in name for name in names)
        await page.locator("#searchInput").press("ArrowDown")
        await page.locator("#searchInput").press("Enter")
        await expect(page.locator("#cityName")).to_have_text("朝阳")
        await expect(page.locator("#currentPanel")).to_have_attribute("aria-busy", "false", timeout=30000)
        await page.locator("#saveButton").click()
        await expect(page.locator(".saved-item")).to_have_count(4)
        await page.reload()
        await expect(page.locator(".saved-item")).to_have_count(4)
        await page.locator(".remove-city").last.click()
        await expect(page.locator(".saved-item")).to_have_count(3)
        report.append("same-name search, keyboard selection, add/reload/remove favourites")

        mobile = await context.new_page()
        await mobile.set_viewport_size({"width": 390, "height": 844})
        await mobile.goto(base_url)
        await expect(mobile.locator("#currentPanel")).to_have_attribute("aria-busy", "false", timeout=30000)
        await expect(mobile.locator(".forecast-day")).to_have_count(9)
        assert await mobile.evaluate("document.documentElement.scrollWidth <= innerWidth"), "mobile horizontal overflow"
        if screenshots:
            await mobile.screenshot(path=str(screenshots / "mobile.png"), full_page=True)
        report.append("390px mobile: all sections accessible without page horizontal overflow")

        fixture_response = await context.request.get(base_url + "/api/weather_detail?lat=39.905&lon=116.4053")
        fixture = await fixture_response.json()
        assert fixture_response.ok and fixture["status"] == "success"

        failed = await context.new_page()
        await failed.route("**/api/weather_detail?*", lambda route: route.fulfill(status=503, json={"status": "error", "msg": "测试上游暂不可用"}))
        await failed.goto(base_url)
        await expect(failed.locator("#dataStatus")).to_contain_text("测试上游暂不可用")
        await expect(failed.locator("#currentPanel")).to_have_attribute("aria-busy", "false")
        await expect(failed.locator("#refreshButton")).to_be_enabled()
        await expect(failed.locator(".saved-weather").filter(has_text="暂不可用")).to_have_count(3)
        report.append("provider failure: loaders finish, summaries fail visibly, retry stays available")

        stale_payload = copy.deepcopy(fixture)
        stale_payload["current"]["pm25"] = None
        stale_payload["current"]["temperature_2m"] = -0.1
        stale_payload["meta"].update(cached=True, stale=True, air_quality_available=False, risk_data_complete=False, warnings=["正在显示缓存；风险数据不完整。"])
        stale = await context.new_page()
        await stale.route("**/api/weather_detail?*", lambda route: route.fulfill(json=stale_payload))
        await stale.goto(base_url)
        await expect(stale.locator("#dataStatus")).to_contain_text("历史缓存")
        await expect(stale.locator("#pm25")).to_have_text("暂不可用")
        await expect(stale.locator("#currentTemperature")).to_have_text("0°C")
        await expect(stale.locator("#notification")).to_contain_text("数据不完整")
        report.append("stale data, missing PM2.5 and incomplete risk inputs stay explicit")

        race = await context.new_page()
        await race.route("**/api/saved_cities", lambda route: route.fulfill(json=[]))
        async def weather_race(route):
            is_beijing = "lat=39.905" in route.request.url
            payload = copy.deepcopy(fixture)
            payload["current"]["temperature_2m"] = 11 if is_beijing else 22
            if is_beijing:
                await asyncio.sleep(1)
            try:
                await route.fulfill(json=payload)
            except Exception:
                # Cancelling the obsolete request can close it before fulfilment.
                pass
        await race.route("**/api/weather_detail?*", weather_race)
        await race.goto(base_url)
        await expect(race.locator("#cityName")).to_have_text("选择一座城市")
        await expect(race.locator("#refreshButton")).to_be_disabled()
        await race.locator("#searchInput").fill("北京")
        await expect(race.locator(".search-result").first).to_be_visible()
        await race.locator(".search-result").first.click()
        await race.locator("#searchInput").fill("上海")
        await expect(race.locator(".search-result").first).to_contain_text("上海")
        await race.locator(".search-result").first.click()
        await expect(race.locator("#cityName")).to_have_text("上海")
        await expect(race.locator("#currentTemperature")).to_have_text("22°C")
        await asyncio.sleep(1.2)
        await expect(race.locator("#currentTemperature")).to_have_text("22°C")
        report.append("empty watchlist and delayed old-city response: selected city remains correct")
        assert not errors, errors
        await browser.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    result = asyncio.run(run(args.url.rstrip("/"), args.screenshots))
    print(json.dumps({"passed": len(result), "checks": result}, ensure_ascii=False, indent=2))
