"""Headless boot verification for the Streamlit demo.

Imports the app module, then launches ``streamlit run`` briefly and asserts
the HTTP server responds before shutting it down. No browser required.

Both tests skip (rather than fail) when Streamlit is not installed, so the
rest of the suite stays runnable in a minimal or offline environment.
"""
from __future__ import annotations

import importlib.util
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "app" / "streamlit_app.py"

STREAMLIT_INSTALLED = importlib.util.find_spec("streamlit") is not None
requires_streamlit = pytest.mark.skipif(
    not STREAMLIT_INSTALLED, reason="streamlit is not installed"
)


def _free_port() -> int:
    """Reserve an ephemeral port from the OS.

    The previous hardcoded 8765 turned any unrelated listener -- or a parallel
    test run -- into a hard failure.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@requires_streamlit
def test_app_module_imports() -> None:
    """Pure import check - catches syntax/import errors without a server."""
    import src.app.streamlit_app as app  # noqa: F401

    assert callable(app.main)


def test_app_module_is_syntactically_valid() -> None:
    """Compile the app without importing it, so it runs with or without Streamlit."""
    compile(APP.read_text(encoding="utf-8"), str(APP), "exec")


@requires_streamlit
def test_streamlit_headless_boot() -> None:
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(APP),
            "--server.headless=true",
            f"--server.port={port}",
            "--server.address=127.0.0.1",
            "--browser.gatherUsageStats=false",
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        # 90s (up from 45s): first boot compiles the app + imports numpy/pypdf
        # and can genuinely exceed 45s on a cold or slow CI machine, which
        # surfaced as a spurious socket.timeout. This only bounds the failure
        # case; a healthy server returns as soon as it answers 200.
        deadline = time.time() + 90
        last_err: object = None
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
            proc.wait(timeout=10)


def test_app_runs_with_only_its_own_directory_on_syspath(tmp_path) -> None:
    """Regression: `streamlit run src/app/streamlit_app.py` must not need PYTHONPATH.

    Streamlit puts the SCRIPT'S OWN directory on sys.path, not the repo root,
    so `import src` used to raise ModuleNotFoundError. This reproduces those
    exact conditions with a stubbed `streamlit`, so it runs even when
    Streamlit is not installed.
    """
    harness = tmp_path / "mimic.py"
    harness.write_text(
        "import os, sys, types, pathlib\n"
        "APP = pathlib.Path(sys.argv[1]).resolve()\n"
        "ROOT = APP.parents[2]\n"
        "kept = [p for p in sys.path\n"
        "        if p not in ('', str(ROOT), str(pathlib.Path.cwd()))]\n"
        "os.chdir(str(pathlib.Path(sys.argv[2])))\n"
        "sys.path[:] = [str(APP.parent)] + kept\n"
        "stub = types.ModuleType('streamlit')\n"
        "class _Any:\n"
        "    def __call__(self, *a, **k): return self\n"
        "    def __getattr__(self, n): return self\n"
        "    def __enter__(self): return self\n"
        "    def __exit__(self, *a): return False\n"
        "stub.__getattr__ = lambda n: _Any()\n"
        "stub.session_state = {}\n"
        "sys.modules['streamlit'] = stub\n"
        "ns = {'__file__': str(APP), '__name__': '__mimic__'}\n"
        "exec(compile(APP.read_text(encoding='utf-8'), str(APP), 'exec'), ns)\n"
        "assert 'card_html' in ns, 'src imports did not resolve'\n"
        "print('BOOTSTRAP_OK')\n",
        encoding="utf-8",
    )
    foreign_cwd = tmp_path / "elsewhere"
    foreign_cwd.mkdir()
    proc = subprocess.run(
        [sys.executable, str(harness), str(APP), str(foreign_cwd)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"app body failed:\n{proc.stdout}\n{proc.stderr}"
    assert "BOOTSTRAP_OK" in proc.stdout


def test_bootstrap_precedes_first_src_import() -> None:
    """The sys.path insert is only effective if it runs before `from src...`."""
    source = APP.read_text(encoding="utf-8")
    bootstrap_at = source.index("sys.path.insert(0, str(_REPO_ROOT))")
    # Match real import statements at column 0 - the module docstring also
    # contains the text "from src." as usage documentation.
    match = re.search(r"^from src\.", source, re.MULTILINE)
    assert match is not None, "no top-level src import found"
    assert bootstrap_at < match.start()
