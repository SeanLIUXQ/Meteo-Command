"""User-facing launcher failures must be actionable and must not hang."""

import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def launch(*args, cwd, data_dir):
    env = {**os.environ, "METEO_DATA_DIR": str(data_dir), "METEO_NO_BROWSER": "1"}
    return subprocess.run(
        [sys.executable, str(ROOT / "run.py"), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_version_works_outside_the_project(tmp_path):
    result = launch("--version", cwd=tmp_path, data_dir=tmp_path / "data")
    assert result.returncode == 0
    assert result.stdout.strip() == (ROOT / "VERSION").read_text().strip()
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("port", ["0", "65536", "invalid"])
def test_invalid_port_exits_with_usage(port, tmp_path):
    result = launch("--port", port, cwd=tmp_path, data_dir=tmp_path / "data")
    assert result.returncode == 2
    assert "port" in result.stderr
    assert "Traceback" not in result.stderr


def test_occupied_port_exits_with_recovery_advice(tmp_path):
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        result = launch("--port", str(port), cwd=tmp_path, data_dir=tmp_path / "data")
    assert result.returncode == 1
    assert "--port 5001" in result.stderr
    assert "Traceback" not in result.stderr
