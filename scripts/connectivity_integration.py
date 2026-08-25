"""Run real loopback FastAPI-to-Godot connectivity and recovery checks."""

from __future__ import annotations

import argparse
import contextlib
import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8000
REDIRECT_TARGET_PORT = 8001
HEALTH_PATH = "/api/v1/health"
EXPECTED_HEALTH = {
    "status": "ok",
    "service": "cyber-town-backend",
    "api_version": "v1",
}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _port_is_open(port: int = PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((HOST, port)) == 0


def _wait_for_port(
    expected_open: bool,
    timeout_seconds: float = 5.0,
    port: int = PORT,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _port_is_open(port) is expected_open:
            return
        time.sleep(0.05)
    state = "open" if expected_open else "released"
    raise RuntimeError(f"{HOST}:{port} did not become {state}")


def _read_health() -> dict[str, str]:
    connection = http.client.HTTPConnection(HOST, PORT, timeout=1.0)
    try:
        connection.request("GET", HEALTH_PATH)
        response = connection.getresponse()
        payload: object = json.loads(response.read().decode("utf-8"))
        if response.status != 200 or payload != EXPECTED_HEALTH:
            raise RuntimeError(
                f"unexpected FastAPI readiness response: {response.status} {payload}"
            )
        return EXPECTED_HEALTH.copy()
    finally:
        connection.close()


@contextlib.contextmanager
def _fastapi_server() -> Iterator[None]:
    if _port_is_open():
        raise RuntimeError(f"refusing to replace existing listener on {HOST}:{PORT}")

    environment = {
        name: value for name, value in os.environ.items() if name.casefold() != "llm_api_key"
    }
    environment.update(
        {
            "APP_HOST": HOST,
            "APP_PORT": str(PORT),
            "CYBER_TOWN_DISABLE_DOTENV": "1",
            "LLM_PROVIDER": "disabled",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "cyber_town.api"],
        cwd=PROJECT_ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(True)
        _read_health()
        yield
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
        _wait_for_port(False)


class _FixtureServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, mode: str, port: int = PORT) -> None:
        self.mode = mode
        self.request_count = 0
        super().__init__((HOST, port), _FixtureHandler)


class _FixtureHandler(BaseHTTPRequestHandler):
    server: _FixtureServer

    def do_GET(self) -> None:
        if self.path != HEALTH_PATH:
            self.send_error(404)
            return

        self.server.request_count += 1
        first_request = self.server.request_count == 1
        if self.server.mode == "timeout_then_ok" and first_request:
            time.sleep(3.5)
        if self.server.mode == "http_error_then_ok" and first_request:
            self._write_response(503, EXPECTED_HEALTH)
            return
        if self.server.mode == "always_unavailable":
            self._write_response(503, EXPECTED_HEALTH)
            return
        if self.server.mode == "duplicate_key":
            self._write_bytes(
                200,
                (
                    b'{"status":"not-ok","status":"ok",'
                    b'"service":"cyber-town-backend","api_version":"v1"}'
                ),
            )
            return
        if self.server.mode == "non_string_field":
            self._write_bytes(
                200,
                (
                    b'{"status":"ok","service":'
                    b'{"name":"cyber-town-backend","note":"x:y"},'
                    b'"api_version":"v1"}'
                ),
            )
            return
        if self.server.mode == "redirect":
            self.send_response(302)
            self.send_header(
                "Location",
                f"http://{HOST}:{REDIRECT_TARGET_PORT}{HEALTH_PATH}",
            )
            self.end_headers()
            return
        if self.server.mode == "invalid_then_ok" and first_request:
            self._write_bytes(200, b"not-json")
            return
        self._write_response(200, EXPECTED_HEALTH)

    def _write_response(self, status: int, payload: dict[str, str]) -> None:
        self._write_bytes(status, json.dumps(payload).encode("utf-8"))

    def _write_bytes(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with contextlib.suppress(
            BrokenPipeError,
            ConnectionAbortedError,
            ConnectionResetError,
        ):
            self.wfile.write(body)

    def log_message(self, _format: str, *args: object) -> None:
        return


@contextlib.contextmanager
def _fixture_server(mode: str, port: int = PORT) -> Iterator[_FixtureServer]:
    if _port_is_open(port):
        raise RuntimeError(f"refusing to replace existing listener on {HOST}:{port}")

    server = _FixtureServer(mode, port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _wait_for_port(True, port=port)
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
        if thread.is_alive():
            raise RuntimeError(f"fixture server did not stop for mode {mode}")
        _wait_for_port(False, port=port)


def _run_godot(godot: Path, scenario: str) -> None:
    command = [
        str(godot),
        "--headless",
        "--path",
        str(PROJECT_ROOT / "game"),
        "--script",
        "res://tests/run_integration.gd",
        "--",
        "--scenario",
        scenario,
    ]
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def run(godot: Path) -> None:
    if not godot.is_file():
        raise FileNotFoundError(f"Godot executable not found: {godot}")
    if _port_is_open():
        raise RuntimeError(f"integration requires a free {HOST}:{PORT}")

    # Engines/platforms may report an unused loopback port as either timeout or
    # another transport failure; both preserve the frozen result mapping.
    _run_godot(godot, "stopped_service")
    with _fixture_server("always_unavailable") as server:
        _run_godot(godot, "unavailable")
        if server.request_count != 1:
            raise RuntimeError(
                f"unavailable expected exactly one request, got {server.request_count}"
            )
    with _fixture_server("duplicate_key") as server:
        _run_godot(godot, "duplicate_rejected")
        if server.request_count != 1:
            raise RuntimeError(
                f"duplicate_rejected expected exactly one request, got {server.request_count}"
            )
    with _fixture_server("non_string_field") as server:
        _run_godot(godot, "non_string_rejected")
        if server.request_count != 1:
            raise RuntimeError(
                f"non_string_rejected expected exactly one request, got {server.request_count}"
            )
    with (
        _fixture_server("always_healthy", REDIRECT_TARGET_PORT) as target,
        _fixture_server("redirect") as source,
    ):
        _run_godot(godot, "redirect_rejected")
        if source.request_count != 1:
            raise RuntimeError(
                f"redirect_rejected expected exactly one source request, got {source.request_count}"
            )
        if target.request_count != 0:
            raise RuntimeError("redirect target must not be requested")
    with _fastapi_server():
        _run_godot(godot, "connected")

    fixture_scenarios: Sequence[tuple[str, str]] = (
        ("http_error_then_ok", "http_error_recovery"),
        ("invalid_then_ok", "invalid_recovery"),
        ("timeout_then_ok", "timeout_recovery"),
    )
    for fixture_mode, scenario in fixture_scenarios:
        with _fixture_server(fixture_mode) as server:
            _run_godot(godot, scenario)
            if server.request_count != 2:
                raise RuntimeError(
                    f"{scenario} expected exactly two requests, got {server.request_count}"
                )

    if _port_is_open() or _port_is_open(REDIRECT_TARGET_PORT):
        raise RuntimeError("integration left a loopback listener running")
    print("Local FastAPI-Godot connectivity integration passed (9 scenarios)")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _parse_args()
    try:
        run(arguments.godot.resolve())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Connectivity integration failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
