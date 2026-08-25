"""Strict, versioned NPC persona loading."""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from importlib import resources
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

PERSONA_FILENAME = re.compile(r"^[a-z0-9_]+\.json$")
PersonaIdentifier = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=64),
]
PersonaPrompt = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=4_000),
]
Sha256Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]


class PersonaDefinition(BaseModel):
    """A frozen persona asset validated before it reaches the dialogue use case."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    npc_id: PersonaIdentifier
    version: PersonaIdentifier
    display_name: PersonaIdentifier
    system_prompt: PersonaPrompt
    content_sha256: Sha256Digest


def _reject_duplicate_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate persona member: {key}")
        result[key] = value
    return result


@lru_cache(maxsize=16)
def load_bundled_persona(filename: str) -> PersonaDefinition:
    """Load a bundled persona without allowing paths outside the persona package."""

    if PERSONA_FILENAME.fullmatch(filename) is None:
        raise ValueError("Invalid bundled persona filename")

    raw = resources.files("cyber_town.domain.personas").joinpath(filename).read_bytes()
    return parse_persona_bytes(raw)


def parse_persona_bytes(raw: bytes) -> PersonaDefinition:
    """Parse strict persona JSON bytes and attach a reproducible content digest."""

    payload = json.loads(raw, object_pairs_hook=_reject_duplicate_members)
    if not isinstance(payload, dict):
        raise ValueError("Bundled persona must contain a JSON object")
    if "content_sha256" in payload:
        raise ValueError("Bundled persona must not declare its own content digest")

    payload["content_sha256"] = hashlib.sha256(raw).hexdigest()
    return PersonaDefinition.model_validate(payload)
