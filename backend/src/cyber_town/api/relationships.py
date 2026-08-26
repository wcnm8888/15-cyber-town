"""Read-only HTTP boundary for deterministic player-to-NPC relationship state."""

from __future__ import annotations

from typing import Literal, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, FastAPI, Path, Query, Request, status
from fastapi.responses import JSONResponse

from cyber_town.application.relationship import RelationshipReadResult
from cyber_town.contracts.relationship import (
    RelationshipErrorV1,
    RelationshipEventSummaryV1,
    RelationshipResponseV1,
)
from cyber_town.domain.persona import load_bundled_personas
from cyber_town.domain.relationship import RelationshipScope
from cyber_town.infrastructure.persistence.sqlite_relationship import RelationshipStorageError

RELATIONSHIPS_PATH = "/api/v1/relationships/{player_id}/{npc_id}"


class RelationshipApplication(Protocol):
    """The minimum read capability exposed to this additive HTTP adapter."""

    def read(
        self,
        *,
        player_id: str,
        npc_id: str,
        request_id: UUID | None,
    ) -> RelationshipReadResult: ...


class RelationshipApiError(Exception):
    """A safe, endpoint-specific failure with no persistence or dialogue details."""

    def __init__(self, *, code: str, message: str, retryable: bool, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code


router = APIRouter()


def _trace_id_for(request: Request) -> str:
    from cyber_town.api.dialogue import trace_id_for

    return str(trace_id_for(request))


def _service_for(request: Request) -> RelationshipApplication:
    service = cast(
        RelationshipApplication | None,
        getattr(request.app.state, "relationship_service", None),
    )
    if service is None:
        raise RelationshipApiError(
            code="relationship_unavailable",
            message="Relationship service is unavailable.",
            retryable=True,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return service


def _request_values(
    request: Request,
    *,
    player_id: str,
    npc_id: str,
    raw_request_id: str | None,
) -> tuple[str, str, UUID | None]:
    if (
        set(request.query_params) - {"request_id"}
        or len(request.query_params.getlist("request_id")) > 1
    ):
        raise ValueError("Relationship query is invalid")
    RelationshipScope(player_id, npc_id)
    if npc_id not in load_bundled_personas():
        raise ValueError("Relationship NPC is not approved")
    if raw_request_id is None:
        return player_id, npc_id, None
    parsed = UUID(raw_request_id)
    if raw_request_id.lower() != str(parsed):
        raise ValueError("Relationship request identifier is invalid")
    return player_id, npc_id, parsed


@router.get(
    RELATIONSHIPS_PATH,
    response_model=RelationshipResponseV1,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": RelationshipErrorV1},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": RelationshipErrorV1},
    },
)
async def relationship(
    request: Request,
    player_id: str = Path(...),
    npc_id: str = Path(...),
    request_id: str | None = Query(default=None),
) -> RelationshipResponseV1:
    """Read state and an optional matching event without changing either one."""

    try:
        validated_player_id, validated_npc_id, parsed_request_id = _request_values(
            request,
            player_id=player_id,
            npc_id=npc_id,
            raw_request_id=request_id,
        )
    except (KeyError, TypeError, ValueError):
        raise RelationshipApiError(
            code="validation_error",
            message="Relationship request validation failed.",
            retryable=False,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from None
    try:
        result = _service_for(request).read(
            player_id=validated_player_id,
            npc_id=validated_npc_id,
            request_id=parsed_request_id,
        )
    except RelationshipStorageError:
        raise RelationshipApiError(
            code="relationship_unavailable",
            message="Relationship service is unavailable.",
            retryable=True,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from None
    event = result.event
    return RelationshipResponseV1(
        npc_id=validated_npc_id,
        score=result.state.score,
        stage=result.state.stage.value,
        rule_version=cast(Literal["f-006-v1"], result.state.rule_version),
        event=(
            None
            if event is None
            else RelationshipEventSummaryV1(
                category=None if event.category is None else event.category.value,
                applied_delta=event.applied_delta,
                reason_code=event.reason_code.value,
                score=event.after_score,
                stage=event.after_stage.value,
                occurred_at=event.occurred_at,
            )
        ),
    )


async def handle_relationship_error(request: Request, exception: Exception) -> JSONResponse:
    """Return only stable relationship error fields for expected endpoint failures."""

    if not isinstance(exception, RelationshipApiError):
        raise TypeError("Unexpected relationship exception type")
    body = RelationshipErrorV1(
        trace_id=_trace_id_for(request),
        code=cast(Literal["validation_error", "relationship_unavailable"], exception.code),
        message=exception.message,
        retryable=exception.retryable,
    )
    return JSONResponse(status_code=exception.status_code, content=body.model_dump(mode="json"))


def install_relationship_boundary(
    application: FastAPI,
    relationship_service: RelationshipApplication | None,
) -> None:
    """Install the additive route without changing the frozen Dialogue v1 boundary."""

    application.state.relationship_service = relationship_service
    application.include_router(router)
    application.add_exception_handler(RelationshipApiError, handle_relationship_error)
