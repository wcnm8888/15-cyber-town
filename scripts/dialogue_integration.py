"""Exercise the real dialogue UI and FastAPI boundary with offline providers only."""

from __future__ import annotations

import argparse
import contextlib
import json
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request, Response

from cyber_town.api.app import create_app
from cyber_town.application.dialogue import DialogueExecutionConfig, DialogueService
from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUsage,
)
from cyber_town.domain.persona import load_bundled_persona
from cyber_town.infrastructure.llm.fake import FakeProvider

HOST = "127.0.0.1"
PORT = 8000
DIALOGUE_PATH = "/api/v1/dialogue"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _port_is_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((HOST, PORT)) == 0


def _wait_for_port(expected_open: bool) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if _port_is_open() is expected_open:
            return
        time.sleep(0.05)
    expected = "open" if expected_open else "released"
    raise RuntimeError(f"dialogue fixture port did not become {expected}")


def _completion(content: object = "Nia offers a synthetic offline reply.") -> ProviderCompletion:
    return ProviderCompletion(
        content=content,
        finish_reason="stop",
        choice_count=1,
        tool_calls_present=False,
        reasoning_content_present=False,
        provider="fake",
        model="deepseek-v4-flash",
        usage=ProviderUsage(prompt_tokens=4, completion_tokens=3),
    )


def _fake_application(
    outcomes: Sequence[ProviderCompletion | Exception],
) -> tuple[FastAPI, FakeProvider]:
    provider = FakeProvider(outcomes)
    persona = load_bundled_persona("nia_v1.json")
    service = DialogueService(
        personas={persona.npc_id: persona},
        provider=provider,
        config=DialogueExecutionConfig(
            model="deepseek-v4-flash",
            temperature=0.6,
            max_tokens=256,
            timeout_seconds=12.0,
            max_concurrency=2,
            idempotency_ttl_seconds=600.0,
            idempotency_max_entries=256,
        ),
    )
    return create_app(service), provider


def _malformed_application(mode: str) -> tuple[FastAPI, dict[str, int]]:
    application = FastAPI()
    observed = {"requests": 0}

    @application.post(DIALOGUE_PATH)
    async def malformed_dialogue(request: Request) -> Response:
        observed["requests"] += 1
        submitted = await request.json()
        payload = {
            "request_id": submitted["request_id"],
            "trace_id": str(uuid4()),
            "npc_id": submitted["npc_id"],
            "conversation_id": submitted["conversation_id"],
            "reply": "Nia offers a synthetic offline reply.",
            "status": "completed",
            "provider": "fake",
        }
        status_code = 201 if mode == "unexpected_status" else 200
        media_type: str | None = None if mode == "missing_content_type" else "application/json"
        if mode == "wrong_content_type":
            media_type = "text/plain"
        response = Response(
            content=json.dumps(payload),
            status_code=status_code,
            media_type=media_type,
        )
        if mode == "duplicate_content_type":
            response.headers.append("content-type", "text/plain")
        return response

    return application, observed


@contextlib.contextmanager
def _fixture_server(application: FastAPI) -> Iterator[None]:
    if _port_is_open():
        raise RuntimeError(f"refusing to replace existing listener on {HOST}:{PORT}")
    server = uvicorn.Server(
        uvicorn.Config(
            application,
            host=HOST,
            port=PORT,
            access_log=False,
            log_config=None,
            log_level="critical",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        _wait_for_port(True)
        yield
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)
        if thread.is_alive():
            raise RuntimeError("dialogue fixture server did not stop")
        _wait_for_port(False)


def _run_godot(godot: Path, scenario: str) -> None:
    subprocess.run(
        [
            str(godot),
            "--headless",
            "--path",
            str(PROJECT_ROOT / "game"),
            "--script",
            "res://tests/run_dialogue_fake_integration.gd",
            "--",
            "--scenario",
            scenario,
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )


def run(godot: Path) -> None:
    if not godot.is_file():
        raise FileNotFoundError(f"Godot executable not found: {godot}")
    if _port_is_open():
        raise RuntimeError(f"dialogue integration requires a free {HOST}:{PORT}")

    scenarios: Sequence[tuple[str, Sequence[ProviderCompletion | Exception], int]] = (
        ("success", [_completion()], 1),
        (
            "unavailable_recovery",
            [ProviderUnavailableError("synthetic provider outage"), _completion()],
            2,
        ),
        (
            "timeout_recovery",
            [ProviderTimeoutError("synthetic provider timeout"), _completion()],
            2,
        ),
        ("invalid_recovery", [_completion(None), _completion()], 2),
    )
    for scenario, outcomes, expected_calls in scenarios:
        application, provider = _fake_application(outcomes)
        with _fixture_server(application):
            _run_godot(godot, scenario)
        if provider.call_count != expected_calls:
            raise RuntimeError(
                f"{scenario} expected {expected_calls} fake provider calls, "
                f"got {provider.call_count}"
            )

    malformed_modes = (
        "wrong_content_type",
        "missing_content_type",
        "duplicate_content_type",
        "unexpected_status",
    )
    for mode in malformed_modes:
        application, observed = _malformed_application(mode)
        with _fixture_server(application):
            _run_godot(godot, mode)
        if observed["requests"] != 1:
            raise RuntimeError(f"{mode} expected exactly one offline HTTP request")

    if _port_is_open():
        raise RuntimeError("dialogue integration left its loopback listener running")
    print("Local fake FastAPI-Godot dialogue integration passed (8 scenarios)")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _parse_args()
    try:
        run(arguments.godot.resolve())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Dialogue integration failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
