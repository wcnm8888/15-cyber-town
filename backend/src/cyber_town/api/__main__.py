"""Run the local FastAPI application with validated project settings."""

from ipaddress import ip_address

import uvicorn

from cyber_town.api.app import app
from cyber_town.api.composition import build_dialogue_service
from cyber_town.config import Settings


def _validated_loopback_host(host: str) -> str:
    try:
        address = ip_address(host)
    except ValueError as error:
        raise ValueError("APP_HOST must be a loopback IP address") from error
    if not address.is_loopback:
        raise ValueError("APP_HOST must be a loopback IP address")
    return host


def main() -> None:
    """Start the local server using APP_HOST and APP_PORT settings."""

    settings = Settings()
    host = _validated_loopback_host(settings.app_host)
    app.state.dialogue_service = build_dialogue_service(settings)
    app.state.relationship_service = (
        None
        if app.state.dialogue_service is None
        else app.state.dialogue_service.relationship_service
    )
    uvicorn.run(
        app,
        host=host,
        port=settings.app_port,
    )


if __name__ == "__main__":
    main()
