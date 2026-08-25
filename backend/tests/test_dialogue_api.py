from __future__ import annotations

import inspect
import json
from uuid import UUID

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient, Response

from cyber_town.api.app import create_app
from cyber_town.api.dialogue import DialogueApplication
from cyber_town.api.dialogue import router as dialogue_router
from cyber_town.application.dialogue import (
    DialogueExecutionConfig,
    DialogueFailureKind,
    DialogueService,
    DialogueUseCaseError,
)
from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderProtocol,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from cyber_town.contracts.v1 import ApiErrorCode, DialogueRequestV1, DialogueResponseV1
from cyber_town.domain.persona import load_bundled_persona
from cyber_town.infrastructure.llm.fake import FakeProvider

DIALOGUE_PATH = "/api/v1/dialogue"
REQUEST_ID = "11111111-1111-4111-8111-111111111111"
CONVERSATION_ID = "22222222-2222-4222-8222-222222222222"
VALID_PAYLOAD: dict[str, object] = {
    "request_id": REQUEST_ID,
    "player_id": "local_player",
    "npc_id": "neon_guide",
    "conversation_id": CONVERSATION_ID,
    "message": "Where can I find a quiet street tonight?",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def completion(
    content: object = "The east arcade is quiet after midnight.",
    *,
    finish_reason: object = "stop",
) -> ProviderCompletion:
    return ProviderCompletion(
        content=content,
        finish_reason=finish_reason,
        choice_count=1,
        tool_calls_present=False,
        reasoning_content_present=False,
        provider="fake",
        model="fake-model",
    )


def make_service(provider: ProviderProtocol) -> DialogueService:
    return DialogueService(
        personas={"neon_guide": load_bundled_persona("nia_v1.json")},
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


async def request(
    dialogue_service: DialogueApplication | None,
    *,
    method: str = "POST",
    payload: object = VALID_PAYLOAD,
) -> Response:
    application = create_app(dialogue_service=dialogue_service)
    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, DIALOGUE_PATH, json=payload)


def assert_canonical_trace_id(value: object) -> None:
    assert isinstance(value, str)
    assert str(UUID(value)) == value


def assert_error(
    response: Response,
    *,
    status_code: int,
    code: ApiErrorCode,
    message: str,
    retryable: bool,
) -> None:
    assert response.status_code == status_code
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert set(body) == {"trace_id", "code", "message", "retryable"}
    assert_canonical_trace_id(body["trace_id"])
    assert body == {
        "trace_id": body["trace_id"],
        "code": code.value,
        "message": message,
        "retryable": retryable,
    }


@pytest.mark.anyio
async def test_dialogue_returns_the_exact_success_contract() -> None:
    provider = FakeProvider([completion()])

    response = await request(make_service(provider))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert set(body) == {
        "request_id",
        "trace_id",
        "npc_id",
        "conversation_id",
        "reply",
        "status",
        "provider",
    }
    assert_canonical_trace_id(body["trace_id"])
    assert body == {
        "request_id": REQUEST_ID,
        "trace_id": body["trace_id"],
        "npc_id": "neon_guide",
        "conversation_id": CONVERSATION_ID,
        "reply": "The east arcade is quiet after midnight.",
        "status": "completed",
        "provider": "fake",
    }
    assert provider.call_count == 1


@pytest.mark.anyio
async def test_dialogue_returns_degraded_fallback_as_http_200() -> None:
    response = await request(
        make_service(FakeProvider([completion(None, finish_reason="content_filter")]))
    )

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["provider"] == "local-fallback"


class RaisingDialogueService:
    def __init__(self, error: DialogueUseCaseError) -> None:
        self.error = error

    async def execute(
        self,
        dialogue_request: DialogueRequestV1,
        *,
        trace_id: UUID,
    ) -> DialogueResponseV1:
        del dialogue_request, trace_id
        raise self.error


@pytest.mark.parametrize(
    ("kind", "code", "status_code", "message", "retryable"),
    [
        (
            DialogueFailureKind.NPC_NOT_FOUND,
            ApiErrorCode.NPC_NOT_FOUND,
            404,
            "NPC is not available.",
            False,
        ),
        (
            DialogueFailureKind.CONFLICT,
            ApiErrorCode.CONFLICT,
            409,
            "The request conflicts with an existing request.",
            False,
        ),
        (
            DialogueFailureKind.UNSAFE_CONTENT,
            ApiErrorCode.UNSAFE_CONTENT,
            400,
            "The message could not be processed safely.",
            False,
        ),
        (
            DialogueFailureKind.PROVIDER_INVALID_RESPONSE,
            ApiErrorCode.PROVIDER_UNAVAILABLE,
            502,
            "The dialogue provider returned an invalid response.",
            True,
        ),
        (
            DialogueFailureKind.PROVIDER_UNAVAILABLE,
            ApiErrorCode.PROVIDER_UNAVAILABLE,
            503,
            "The dialogue provider is unavailable.",
            True,
        ),
        (
            DialogueFailureKind.PROVIDER_TIMEOUT,
            ApiErrorCode.PROVIDER_TIMEOUT,
            504,
            "The dialogue provider timed out.",
            True,
        ),
        (
            DialogueFailureKind.INTERNAL_ERROR,
            ApiErrorCode.INTERNAL_ERROR,
            500,
            "The dialogue request could not be completed.",
            False,
        ),
    ],
)
@pytest.mark.anyio
async def test_dialogue_maps_safe_application_errors(
    kind: DialogueFailureKind,
    code: ApiErrorCode,
    status_code: int,
    message: str,
    retryable: bool,
) -> None:
    error = DialogueUseCaseError(
        kind=kind,
        code=code,
        public_message=message,
        retryable=retryable,
    )

    response = await request(RaisingDialogueService(error))

    assert_error(
        response,
        status_code=status_code,
        code=code,
        message=message,
        retryable=retryable,
    )


@pytest.mark.parametrize(
    "provider_outcome",
    [
        ProviderTimeoutError("private timeout detail"),
        ProviderUnavailableError("private unavailable detail"),
        completion(None),
    ],
)
@pytest.mark.anyio
async def test_provider_failures_do_not_expose_private_details(
    provider_outcome: Exception | ProviderCompletion,
) -> None:
    response = await request(make_service(FakeProvider([provider_outcome])))

    assert response.status_code in {502, 503, 504}
    assert "private" not in response.text
    assert "detail" not in response.json()


class CountingDialogueService:
    def __init__(self) -> None:
        self.call_count = 0

    async def execute(
        self,
        dialogue_request: DialogueRequestV1,
        *,
        trace_id: UUID,
    ) -> DialogueResponseV1:
        del dialogue_request, trace_id
        self.call_count += 1
        raise AssertionError("invalid requests must not reach the application service")


@pytest.mark.parametrize(
    "payload",
    [
        {key: value for key, value in VALID_PAYLOAD.items() if key != "message"},
        {**VALID_PAYLOAD, "message": 123},
        {**VALID_PAYLOAD, "message": ""},
        {**VALID_PAYLOAD, "unexpected": "field"},
        {**VALID_PAYLOAD, "request_id": "not-a-uuid"},
    ],
)
@pytest.mark.anyio
async def test_fastapi_validation_is_normalized_without_calling_application(
    payload: dict[str, object],
) -> None:
    dialogue_service = CountingDialogueService()

    response = await request(dialogue_service, payload=payload)

    assert_error(
        response,
        status_code=422,
        code=ApiErrorCode.VALIDATION_ERROR,
        message="Request validation failed.",
        retryable=False,
    )
    assert dialogue_service.call_count == 0
    assert "detail" not in response.text
    assert "input" not in response.text


@pytest.mark.parametrize("duplicated_field", ["message", "request_id", "npc_id"])
@pytest.mark.anyio
async def test_duplicate_json_members_are_rejected_before_application_execution(
    duplicated_field: str,
) -> None:
    dialogue_service = CountingDialogueService()
    encoded = json.dumps(VALID_PAYLOAD)
    duplicate = json.dumps(VALID_PAYLOAD[duplicated_field])
    body = encoded.removesuffix("}") + f',"{duplicated_field}":{duplicate}' + "}"
    application = create_app(dialogue_service=dialogue_service)
    transport = ASGITransport(app=application, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            DIALOGUE_PATH,
            content=body,
            headers={"content-type": "application/json"},
        )

    assert_error(
        response,
        status_code=422,
        code=ApiErrorCode.VALIDATION_ERROR,
        message="Request validation failed.",
        retryable=False,
    )
    assert dialogue_service.call_count == 0


@pytest.mark.anyio
async def test_each_http_attempt_receives_a_new_trace_even_when_result_is_cached() -> None:
    provider = FakeProvider([completion()])
    service = make_service(provider)

    first = await request(service)
    second = await request(service)

    assert first.status_code == second.status_code == 200
    assert first.json()["trace_id"] != second.json()["trace_id"]
    assert provider.call_count == 1


@pytest.mark.anyio
async def test_provider_disabled_application_fails_closed_without_a_key() -> None:
    response = await request(None)

    assert_error(
        response,
        status_code=503,
        code=ApiErrorCode.PROVIDER_UNAVAILABLE,
        message="The dialogue service is disabled.",
        retryable=True,
    )


class UnexpectedFailureService:
    async def execute(
        self,
        dialogue_request: DialogueRequestV1,
        *,
        trace_id: UUID,
    ) -> DialogueResponseV1:
        del dialogue_request, trace_id
        raise RuntimeError("private unexpected detail 837465")


@pytest.mark.anyio
async def test_unexpected_http_boundary_failure_uses_safe_internal_error() -> None:
    response = await request(UnexpectedFailureService())

    assert_error(
        response,
        status_code=500,
        code=ApiErrorCode.INTERNAL_ERROR,
        message="The dialogue request could not be completed.",
        retryable=False,
    )
    assert "private unexpected detail" not in response.text


@pytest.mark.anyio
async def test_dialogue_rejects_non_post_method_without_calling_application() -> None:
    dialogue_service = CountingDialogueService()

    response = await request(dialogue_service, method="GET")

    assert response.status_code == 405
    assert dialogue_service.call_count == 0


def test_dialogue_route_is_thin_and_does_not_import_provider_sdk() -> None:
    application = create_app(dialogue_service=CountingDialogueService())
    operation = application.openapi()["paths"][DIALOGUE_PATH]
    route = next(
        route
        for route in dialogue_router.routes
        if isinstance(route, APIRoute) and route.path == DIALOGUE_PATH
    )

    assert set(operation) == {"post"}
    assert operation["post"]["requestBody"]["content"]["application/json"]["schema"]
    source = inspect.getsource(route.endpoint).lower()
    assert "openai" not in source
    assert "deepseek" not in source
    assert "persona" not in source
