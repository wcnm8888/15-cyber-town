"""Minimal FastAPI application for local backend connectivity."""

from typing import Literal

from fastapi import FastAPI, status
from pydantic import BaseModel, ConfigDict

HEALTH_PATH = "/api/v1/health"


class HealthResponseV1(BaseModel):
    """Stable public response returned by the local health endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"] = "ok"
    service: Literal["cyber-town-backend"] = "cyber-town-backend"
    api_version: Literal["v1"] = "v1"


def create_app() -> FastAPI:
    """Build the HTTP application without external service dependencies."""

    application = FastAPI(title="Cyber Town API", version="0.1.0")

    @application.get(
        HEALTH_PATH,
        response_model=HealthResponseV1,
        status_code=status.HTTP_200_OK,
    )
    async def health() -> HealthResponseV1:
        return HealthResponseV1()

    return application


app = create_app()
