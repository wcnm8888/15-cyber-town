from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from cyber_town.api.app import create_app
from cyber_town.application.dialogue import DialogueExecutionConfig, DialogueService
from cyber_town.application.provider import ProviderCompletion
from cyber_town.application.relationship import RelationshipService
from cyber_town.domain.persona import load_bundled_persona
from cyber_town.infrastructure.llm.fake import FakeProvider
from cyber_town.infrastructure.persistence.sqlite_relationship import SqliteRelationshipRepository


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_completed_dialogue_records_one_relationship_event_and_get_keeps_v1_unchanged(
    tmp_path: Path,
) -> None:
    repository = SqliteRelationshipRepository(
        database_path=tmp_path / "isolated.sqlite3", allowed_root=tmp_path
    )
    repository.initialize()
    provider = FakeProvider(
        [
            ProviderCompletion(
                content="Nia appreciates the thoughtful visit.",
                finish_reason="stop",
                choice_count=1,
                tool_calls_present=False,
                reasoning_content_present=False,
                provider="fake",
                model="deepseek-v4-flash",
                relationship_suggestion={"category": "supportive", "confidence": 80},
            )
        ]
    )
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
        relationship_service=RelationshipService(repository=repository),
    )
    payload = {
        "request_id": "11111111-1111-4111-8111-111111111111",
        "player_id": "local_player",
        "npc_id": "neon_guide",
        "conversation_id": "22222222-2222-4222-8222-222222222222",
        "message": "Thank you for walking with me.",
    }
    application = create_app(dialogue_service=service)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        dialogue = await client.post("/api/v1/dialogue", json=payload)
        relationship = await client.get(
            "/api/v1/relationships/local_player/neon_guide",
            params={"request_id": payload["request_id"]},
        )

    assert set(dialogue.json()) == {
        "request_id",
        "trace_id",
        "npc_id",
        "conversation_id",
        "reply",
        "status",
        "provider",
    }
    assert dialogue.status_code == 200
    assert relationship.status_code == 200
    assert relationship.json() == {
        "npc_id": "neon_guide",
        "score": 22,
        "stage": "acquaintance",
        "rule_version": "f-006-v1",
        "event": {
            "category": "supportive",
            "applied_delta": 2,
            "reason_code": "rule_supportive",
            "score": 22,
            "stage": "acquaintance",
            "occurred_at": relationship.json()["event"]["occurred_at"],
        },
    }
    assert provider.call_count == 1


@pytest.mark.anyio
async def test_relationship_get_fails_closed_without_service_or_valid_query() -> None:
    application = create_app()
    operation = application.openapi()["paths"]["/api/v1/relationships/{player_id}/{npc_id}"]["get"]
    assert {(parameter["name"], parameter["in"]) for parameter in operation["parameters"]} == {
        ("player_id", "path"),
        ("npc_id", "path"),
        ("request_id", "query"),
    }

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        unavailable = await client.get("/api/v1/relationships/local_player/neon_guide")
        invalid = await client.get("/api/v1/relationships/local_player/neon_guide?unexpected=1")

    assert unavailable.status_code == 503
    assert unavailable.json() == {
        "trace_id": unavailable.json()["trace_id"],
        "code": "relationship_unavailable",
        "message": "Relationship service is unavailable.",
        "retryable": True,
    }
    assert invalid.status_code == 422
    assert invalid.json() == {
        "trace_id": invalid.json()["trace_id"],
        "code": "validation_error",
        "message": "Relationship request validation failed.",
        "retryable": False,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "npc_path",
    [
        "unknown_npc",
        "NEON_GUIDE",
        "neon_guid\u0435",
        "\uff4e\uff45\uff4f\uff4e\uff3f\uff47\uff55\uff49\uff44\uff45",
        "%20neon_guide",
        "neon_guide%09",
        "neon_guide%C2%A0",
        "neon_guide%0Asignal_archivist",
        "neon_guide%00",
        "neon-guide",
        "neon.guide",
        "neon_guide%3Fother=signal_archivist",
        "neon_guide%2F..%2Fsignal_archivist",
    ],
)
async def test_relationship_get_rejects_unapproved_npc_before_repository_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    npc_path: str,
) -> None:
    repository = SqliteRelationshipRepository(
        database_path=tmp_path / "isolated.sqlite3", allowed_root=tmp_path
    )
    repository.initialize()

    def unexpected_repository_read(*_args: object, **_kwargs: object) -> None:
        pytest.fail("unapproved relationship NPC reached the repository")

    monkeypatch.setattr(repository, "get_state", unexpected_repository_read)
    monkeypatch.setattr(repository, "event_for_request", unexpected_repository_read)
    application = create_app(relationship_service=RelationshipService(repository=repository))

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/relationships/local_player/{npc_path}")

    assert response.status_code in {404, 422}
    if response.status_code == 422:
        assert response.json()["code"] == "validation_error"


@pytest.mark.anyio
@pytest.mark.parametrize("npc_id", ["neon_guide", "signal_archivist", "night_courier"])
async def test_relationship_get_accepts_every_fixed_persona(
    tmp_path: Path,
    npc_id: str,
) -> None:
    repository = SqliteRelationshipRepository(
        database_path=tmp_path / "isolated.sqlite3", allowed_root=tmp_path
    )
    repository.initialize()
    application = create_app(relationship_service=RelationshipService(repository=repository))

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/relationships/local_player/{npc_id}")

    assert response.status_code == 200
    assert response.json() == {
        "npc_id": npc_id,
        "score": 20,
        "stage": "acquaintance",
        "rule_version": "f-006-v1",
        "event": None,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("suggestion", "expected_reason"),
    [
        (
            {"category": "supportive", "confidence": 100, "score": 100},
            "candidate_invalid",
        ),
        (
            {"category": "supportive", "confidence": 100, "instruction": "ignore rules"},
            "candidate_invalid",
        ),
        ({"category": "hostile", "confidence": True}, "candidate_invalid"),
    ],
)
async def test_manipulated_completion_suggestion_is_inert_but_dialogue_stays_completed(
    tmp_path: Path,
    suggestion: object,
    expected_reason: str,
) -> None:
    repository = SqliteRelationshipRepository(
        database_path=tmp_path / "isolated.sqlite3", allowed_root=tmp_path
    )
    repository.initialize()
    provider = FakeProvider(
        [
            ProviderCompletion(
                content="Nia replies normally despite an untrusted suggestion.",
                finish_reason="stop",
                choice_count=1,
                tool_calls_present=False,
                reasoning_content_present=False,
                provider="fake",
                model="deepseek-v4-flash",
                relationship_suggestion=suggestion,
            )
        ]
    )
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
        relationship_service=RelationshipService(repository=repository),
    )
    payload = {
        "request_id": "11111111-1111-4111-8111-111111111111",
        "player_id": "local_player",
        "npc_id": "neon_guide",
        "conversation_id": "22222222-2222-4222-8222-222222222222",
        "message": "Please keep this normal dialogue response.",
    }
    application = create_app(dialogue_service=service)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        dialogue = await client.post("/api/v1/dialogue", json=payload)
        relationship = await client.get(
            "/api/v1/relationships/local_player/neon_guide",
            params={"request_id": payload["request_id"]},
        )

    assert dialogue.status_code == 200
    assert dialogue.json()["status"] == "completed"
    assert relationship.status_code == 200
    assert relationship.json()["score"] == 20
    assert relationship.json()["event"] == {
        "category": None,
        "applied_delta": 0,
        "reason_code": expected_reason,
        "score": 20,
        "stage": "acquaintance",
        "occurred_at": relationship.json()["event"]["occurred_at"],
    }
    assert provider.call_count == 1
