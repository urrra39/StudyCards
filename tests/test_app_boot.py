"""Headless boot verification for the Streamlit demo.

Imports the app module, then launches ``streamlit run`` briefly and asserts
the HTTP server responds before shutting it down. No browser required.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "app" / "streamlit_app.py"
PORT = 8765


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def test_app_module_imports() -> None:
    """Pure import check — catches syntax/import errors without a server."""
    import src.app.streamlit_app as app  # noqa: F401

    assert callable(app.main)


def test_streamlit_headless_boot() -> None:
    if not _port_free(PORT):
        raise RuntimeError(f"port {PORT} already in use")

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(APP),
            "--server.headless=true",
            f"--server.port={PORT}",
            "--server.address=127.0.0.1",
            "--browser.gatherUsageStats=false",
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = f"http://127.0.0.1:{PORT}"
    try:
        deadline = time.time() + 45
        last_err: Exception | None = None
        while time.time() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                raise RuntimeError(f"streamlit exited early ({proc.returncode}): {out[:800]}")
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    assert resp.status == 200
                    return
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last_err = exc
                time.sleep(0.5)
        raise RuntimeError(f"streamlit did not become ready: {last_err}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    # Allow `python tests/test_app_boot.py` as a manual smoke check.
    test_app_module_imports()
    test_streamlit_headless_boot()
    print("headless boot OK")
