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
from tempfile import TemporaryDirectory
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request, Response

from cyber_town.api.app import create_app
from cyber_town.application.dialogue import DialogueExecutionConfig, DialogueService
from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderHistoryMessage,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUsage,
)
from cyber_town.application.relationship import RelationshipService
from cyber_town.domain.persona import load_bundled_personas
from cyber_town.infrastructure.llm.fake import FakeProvider
from cyber_town.infrastructure.persistence.sqlite_relationship import SqliteRelationshipRepository

HOST = "127.0.0.1"
PORT = 8000
DIALOGUE_PATH = "/api/v1/dialogue"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TWO_LINE_VIEWPORT_REPLY = (
    "Nia begins a fresh conversation with her retained relationship snapshot."
)


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
        relationship_suggestion={"category": "friendly", "confidence": 80},
    )


MEMORY_SCENARIOS: tuple[tuple[str, tuple[ProviderCompletion | Exception, ...], int], ...] = (
    (
        "multi_turn",
        (
            _completion("Synthetic first offline reply."),
            _completion("Synthetic second offline reply."),
            _completion("Synthetic third offline reply."),
        ),
        3,
    ),
    (
        "multi_turn_recovery",
        (
            _completion("Synthetic first offline reply."),
            ProviderUnavailableError("synthetic second-turn provider outage"),
            _completion("Synthetic recovered offline reply."),
            _completion("Synthetic third offline reply."),
        ),
        4,
    ),
)


def _assert_memory_scenario(
    scenario: str,
    provider: FakeProvider,
    outcomes: Sequence[ProviderCompletion | Exception] | None = None,
) -> None:
    """Validate complete fake history without rendering private synthetic message text."""

    requests = provider.requests
    expected_outcomes = outcomes
    if expected_outcomes is None:
        expected_outcomes = next(
            (values for name, values, _calls in MEMORY_SCENARIOS if name == scenario),
            None,
        )
    if expected_outcomes is None or len(requests) != len(expected_outcomes):
        raise RuntimeError(f"{scenario} fake history outcomes did not match")

    expected_lengths = (0, 2, 4) if scenario == "multi_turn" else (0, 2, 2, 4)
    observed_lengths = tuple(len(request.history_messages) for request in requests)
    if observed_lengths != expected_lengths:
        raise RuntimeError(f"{scenario} fake history turn counts did not match")

    expected_history: list[ProviderHistoryMessage] = []
    for request, outcome in zip(requests, expected_outcomes, strict=True):
        for actual, expected in zip(request.history_messages, expected_history, strict=True):
            if actual.role != expected.role:
                raise RuntimeError(f"{scenario} fake history message roles did not match")
            if actual.content != expected.content:
                raise RuntimeError(
                    f"{scenario} fake {expected.role} history did not match its completed turn"
                )
        if isinstance(outcome, ProviderCompletion):
            if not isinstance(outcome.content, str) or not outcome.content.strip():
                raise RuntimeError(f"{scenario} fake assistant completion was invalid")
            expected_history.extend(
                (
                    ProviderHistoryMessage("user", request.user_message),
                    ProviderHistoryMessage("assistant", outcome.content.strip()),
                )
            )

    if scenario == "multi_turn_recovery":
        if requests[1].history_messages != requests[2].history_messages:
            raise RuntimeError("multi_turn_recovery fake history changed after a failed turn")
        if requests[1].user_message != requests[2].user_message:
            raise RuntimeError("multi_turn_recovery manual retry changed its user message")


@contextlib.contextmanager
def _fake_application(
    outcomes: Sequence[ProviderCompletion | Exception],
) -> Iterator[tuple[FastAPI, FakeProvider]]:
    """Build an isolated fake-only dialogue and relationship loopback fixture."""

    with TemporaryDirectory(prefix="cyber-town-f007-") as temporary_directory:
        root = Path(temporary_directory)
        repository = SqliteRelationshipRepository(
            database_path=root / "isolated.sqlite3",
            allowed_root=root,
        )
        repository.initialize()
        provider = FakeProvider(outcomes)
        service = DialogueService(
            personas=load_bundled_personas(),
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
            relationship_service=RelationshipService(repository=repository),
        )
        yield create_app(service), provider


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


def _run_multi_npc_godot(godot: Path) -> None:
    subprocess.run(
        [
            str(godot),
            "--headless",
            "--path",
            str(PROJECT_ROOT / "game"),
            "--script",
            "res://tests/run_multi_npc_fake_integration.gd",
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
        ("success", [_completion(TWO_LINE_VIEWPORT_REPLY)], 1),
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
    for scenario, outcomes, expected_calls in (*scenarios, *MEMORY_SCENARIOS):
        with _fake_application(outcomes) as (application, provider):
            with _fixture_server(application):
                _run_godot(godot, scenario)
            if provider.call_count != expected_calls:
                raise RuntimeError(
                    f"{scenario} expected {expected_calls} fake provider calls, "
                    f"got {provider.call_count}"
                )
            if scenario.startswith("multi_turn"):
                _assert_memory_scenario(scenario, provider, outcomes)

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

    multi_npc_outcomes = tuple(
        _completion(f"{display_name} returns an isolated synthetic reply.")
        for display_name in ("Nia", "Ivo", "Rhea")
    )
    with _fake_application(multi_npc_outcomes) as (application, provider):
        with _fixture_server(application):
            _run_multi_npc_godot(godot)
        if provider.call_count != 3:
            raise RuntimeError("multi-NPC loopback expected exactly three fake provider calls")
        personas = load_bundled_personas()
        expected_prompts = tuple(
            personas[npc_id].system_prompt
            for npc_id in ("neon_guide", "signal_archivist", "night_courier")
        )
        if tuple(request.system_prompt for request in provider.requests) != expected_prompts:
            raise RuntimeError("multi-NPC loopback did not preserve persona prompt ownership")
        if any(request.history_messages for request in provider.requests):
            raise RuntimeError("multi-NPC switch leaked short-term history across conversations")

    if _port_is_open():
        raise RuntimeError("dialogue integration left its loopback listener running")
    print("Local fake FastAPI-Godot dialogue integration passed (10 base + multi-NPC)")


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
