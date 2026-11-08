"""Verify an extracted native release from an unrelated directory, without APIs."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
from time import monotonic, sleep
import urllib.parse
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True)
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(path):
        with opener.open(base + path, timeout=3) as response:
            assert response.status == 200
            return response.read()

    def get_json(path):
        return json.loads(get(path))

    with tempfile.TemporaryDirectory(prefix="meteo smoke 空格 ") as scratch:
        env = {**os.environ, "METEO_DATA_DIR": str(Path(scratch) / "user-data"), "METEO_NO_BROWSER": "1"}
        def start():
            process = subprocess.Popen([str(executable), "--port", str(port), "--no-browser"], cwd=scratch, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            deadline = monotonic() + 30
            while monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError(process.communicate()[0].decode(errors="replace"))
                try:
                    health = get_json("/api/health")
                    assert health["version"] == "2.0.0"
                    return process
                except OSError:
                    sleep(.1)
            process.terminate()
            process.wait(timeout=10)
            raise AssertionError("Native server did not become healthy")

        def stop(process):
            process.terminate()
            process.communicate(timeout=10)

        process = start()
        try:
            page = get("/")
            assert b"js/app.js" in page and b"css/app.css" in page
            for path in ("/static/vendor/echarts.min.js", "/static/css/app.css", "/static/js/app.js"):
                assert len(get(path)) > 100
            assert get_json("/static/data/china.json")["features"]
            assert len(get_json("/api/map_data")) > 300
            cities = get_json("/api/search_cities?q=" + urllib.parse.quote("成都"))["cities"]
            city = cities[0]
            request = urllib.request.Request(base + "/api/manage_city", data=json.dumps({"action": "add", "city": city}).encode(), headers={"Content-Type": "application/json"}, method="POST")
            with opener.open(request, timeout=3) as response:
                assert json.load(response)["status"] == "success"
            assert (Path(scratch) / "user-data/saved_cities.json").is_file()
        finally:
            stop(process)
        process = start()
        try:
            saved = get_json("/api/saved_cities")
            assert len(saved) == 4 and any(item["id"] == city["id"] for item in saved)
        finally:
            stop(process)
    print("PASS: native startup, assets, city catalogue, Unicode data path and favourites across process restart")


if __name__ == "__main__":
    main()
