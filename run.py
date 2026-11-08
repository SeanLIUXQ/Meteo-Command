"""Local launcher shared by source, Docker and the frozen desktop build."""

import argparse
import logging
import os
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path
from time import monotonic, sleep


def version():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return (root / "VERSION").read_text(encoding="utf-8").strip()


def open_when_ready(url):
    deadline = monotonic() + 10
    while monotonic() < deadline:
        try:
            # Local probes must bypass system HTTP proxies.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(url + "/api/health", timeout=0.5) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except (OSError, ValueError):
            sleep(0.2)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Meteo-Command local weather dashboard")
    parser.add_argument("--version", action="version", version=version())
    parser.add_argument("--host", default=os.environ.get("METEO_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=os.environ.get("METEO_PORT", "5000"))
    parser.add_argument("--no-browser", action="store_true", default=os.environ.get("METEO_NO_BROWSER", "").lower() in {"1", "true", "yes"})
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    from app import app
    from waitress.server import create_server
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        server = create_server(app, host=args.host, port=args.port, threads=8)
    except OSError as exc:
        print(f"Cannot start on {args.host}:{args.port}: {exc}", file=sys.stderr)
        print("Close the other instance or use --port 5001 (METEO_PORT=5001).", file=sys.stderr)
        return 1
    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    if ":" in display_host:
        display_host = f"[{display_host}]"
    url = f"http://{display_host}:{args.port}"
    print(f"Meteo-Command {version()} | {url}", flush=True)
    print("Keep this window open. Press Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
