from __future__ import annotations

import importlib
import inspect
import socket
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from cyber_town.api.app import app, create_app

HEALTH_PATH = "/api/v1/health"
EXPECTED_HEALTH = {
    "status": "ok",
    "service": "cyber-town-backend",
    "api_version": "v1",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


@pytest.mark.anyio
async def test_health_returns_the_exact_public_contract(client: AsyncClient) -> None:
    response = await client.get(HEALTH_PATH)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == EXPECTED_HEALTH
    assert set(response.json()) == set(EXPECTED_HEALTH)


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.anyio
async def test_health_rejects_non_get_methods(client: AsyncClient, method: str) -> None:
    response = await client.request(method, HEALTH_PATH)

    assert response.status_code == 405


def test_health_route_has_no_request_body_query_or_dependencies() -> None:
    route = next(
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path == HEALTH_PATH
    )

    assert route.methods == {"GET"}
    assert route.body_field is None
    assert route.dependant.query_params == []
    assert route.dependant.dependencies == []
    assert inspect.signature(route.endpoint).parameters == {}


@pytest.mark.anyio
async def test_health_does_not_open_network_or_database(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_side_effect(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("health endpoint attempted an external side effect")

    monkeypatch.setattr(socket, "create_connection", forbidden_side_effect)
    monkeypatch.setattr(sqlite3, "connect", forbidden_side_effect)

    response = await client.get(HEALTH_PATH)

    assert response.status_code == 200


def test_application_entrypoint_is_importable() -> None:
    api_main = importlib.import_module("cyber_town.api.__main__")

    assert callable(api_main.main)


def test_application_entrypoint_reads_host_and_port_from_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api_main = importlib.import_module("cyber_town.api.__main__")
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def capture_run(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_HOST", "127.0.0.2")
    monkeypatch.setenv("APP_PORT", "8123")
    monkeypatch.setenv("LLM_PROVIDER", "disabled")
    monkeypatch.setattr(api_main.uvicorn, "run", capture_run)

    api_main.main()

    assert calls == [((api_main.app,), {"host": "127.0.0.2", "port": 8123})]


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10"])
def test_application_entrypoint_rejects_non_loopback_host(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    host: str,
) -> None:
    api_main = importlib.import_module("cyber_town.api.__main__")
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_HOST", host)
    monkeypatch.setenv("APP_PORT", "8000")
    monkeypatch.setenv("LLM_PROVIDER", "disabled")
    monkeypatch.setattr(
        api_main.uvicorn,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="APP_HOST must be a loopback IP address"):
        api_main.main()

    assert calls == []
