"""Thin HTTP boundary for the version-one dialogue use case."""

from __future__ import annotations

import json
from typing import Annotated, Protocol, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from cyber_town.application.dialogue import DialogueFailureKind, DialogueUseCaseError
from cyber_town.contracts.v1 import (
    ApiErrorCode,
    ApiErrorV1,
    DialogueRequestV1,
    DialogueResponseV1,
)

DIALOGUE_PATH = "/api/v1/dialogue"


class DialogueApplication(Protocol):
    """The only application capability exposed to the HTTP adapter."""

    async def execute(
        self,
        dialogue_request: DialogueRequestV1,
        *,
        trace_id: UUID,
    ) -> DialogueResponseV1: ...


router = APIRouter()


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object member")
        result[key] = value
    return result


async def parse_dialogue_request(request: Request) -> DialogueRequestV1:
    """Validate the JSON bytes in Pydantic's strict JSON mode.

    Strict UUID contracts intentionally accept canonical JSON strings while rejecting
    Python-side string coercion, so FastAPI's decoded-dict validation cannot be used here.
    """

    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if content_type != "application/json":
        raise RequestValidationError([])
    try:
        body = await request.body()
        json.loads(body, object_pairs_hook=_unique_json_object)
        return DialogueRequestV1.model_validate_json(body)
    except (ValidationError, ValueError):
        raise RequestValidationError([]) from None


def trace_id_for(request: Request) -> UUID:
    """Return one server-generated correlation id for this HTTP attempt."""

    trace_id = getattr(request.state, "trace_id", None)
    if isinstance(trace_id, UUID):
        return trace_id
    trace_id = uuid4()
    request.state.trace_id = trace_id
    return trace_id


def _dialogue_service_for(request: Request) -> DialogueApplication:
    service = cast(
        DialogueApplication | None,
        getattr(request.app.state, "dialogue_service", None),
    )
    if service is None:
        raise DialogueUseCaseError(
            kind=DialogueFailureKind.PROVIDER_UNAVAILABLE,
            code=ApiErrorCode.PROVIDER_UNAVAILABLE,
            public_message="The dialogue service is disabled.",
            retryable=True,
        )
    return service


@router.post(
    DIALOGUE_PATH,
    response_model=DialogueResponseV1,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ApiErrorV1},
        status.HTTP_404_NOT_FOUND: {"model": ApiErrorV1},
        status.HTTP_409_CONFLICT: {"model": ApiErrorV1},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiErrorV1},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ApiErrorV1},
        status.HTTP_502_BAD_GATEWAY: {"model": ApiErrorV1},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ApiErrorV1},
        status.HTTP_504_GATEWAY_TIMEOUT: {"model": ApiErrorV1},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": DialogueRequestV1.model_json_schema(mode="validation")
                }
            },
        }
    },
)
async def dialogue(
    dialogue_request: Annotated[DialogueRequestV1, Depends(parse_dialogue_request)],
    request: Request,
) -> DialogueResponseV1:
    """Validate the public request and delegate all behavior to the use case."""

    return await _dialogue_service_for(request).execute(
        dialogue_request,
        trace_id=trace_id_for(request),
    )


def _status_for(error: DialogueUseCaseError) -> int:
    if error.kind == DialogueFailureKind.PROVIDER_INVALID_RESPONSE:
        return status.HTTP_502_BAD_GATEWAY

    return {
        ApiErrorCode.UNSAFE_CONTENT: status.HTTP_400_BAD_REQUEST,
        ApiErrorCode.NPC_NOT_FOUND: status.HTTP_404_NOT_FOUND,
        ApiErrorCode.CONFLICT: status.HTTP_409_CONFLICT,
        ApiErrorCode.PROVIDER_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
        ApiErrorCode.PROVIDER_TIMEOUT: status.HTTP_504_GATEWAY_TIMEOUT,
        ApiErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
        ApiErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
    }[error.code]


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: ApiErrorCode,
    message: str,
    retryable: bool,
) -> JSONResponse:
    error = ApiErrorV1(
        trace_id=trace_id_for(request),
        code=code,
        message=message,
        retryable=retryable,
    )
    return JSONResponse(
        status_code=status_code,
        content=error.model_dump(mode="json"),
    )


async def handle_dialogue_error(request: Request, exception: Exception) -> JSONResponse:
    """Translate a classified application failure without exposing its cause."""

    if not isinstance(exception, DialogueUseCaseError):
        raise TypeError("Unexpected dialogue exception type")
    return _error_response(
        request,
        status_code=_status_for(exception),
        code=exception.code,
        message=exception.public_message,
        retryable=exception.retryable,
    )


async def handle_validation_error(request: Request, exception: Exception) -> JSONResponse:
    """Replace FastAPI's detailed 422 body with the stable public contract."""

    if not isinstance(exception, RequestValidationError):
        raise TypeError("Unexpected validation exception type")
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=ApiErrorCode.VALIDATION_ERROR,
        message="Request validation failed.",
        retryable=False,
    )


async def handle_unexpected_error(request: Request, exception: Exception) -> JSONResponse:
    """Fail closed at the HTTP boundary without returning exception details."""

    del exception
    return _error_response(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code=ApiErrorCode.INTERNAL_ERROR,
        message="The dialogue request could not be completed.",
        retryable=False,
    )


def install_dialogue_boundary(
    application: FastAPI,
    dialogue_service: DialogueApplication | None,
) -> None:
    """Install the route, injectable use case and stable exception handlers."""

    application.state.dialogue_service = dialogue_service
    application.include_router(router)
    application.add_exception_handler(DialogueUseCaseError, handle_dialogue_error)
    application.add_exception_handler(RequestValidationError, handle_validation_error)
    application.add_exception_handler(Exception, handle_unexpected_error)
