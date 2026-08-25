"""Provider-neutral dialogue completion protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    """Token counts safe to retain as request metadata."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __post_init__(self) -> None:
        if self.prompt_tokens < 0 or self.completion_tokens < 0:
            raise ValueError("Provider token usage cannot be negative")

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class ProviderHistoryMessage:
    """One private, SDK-neutral message from a completed conversation turn."""

    role: Literal["user", "assistant"]
    content: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.role, str):
            raise TypeError("Historical message role must be a string")
        if self.role not in ("user", "assistant"):
            raise ValueError("Historical message role is not permitted")
        if not isinstance(self.content, str):
            raise TypeError("Historical message content must be a string")
        if not self.content.strip():
            raise ValueError("Historical message content cannot be blank")


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """The minimal provider input, independent of any SDK type."""

    system_prompt: str
    user_message: str
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: float
    thinking_enabled: bool = False
    stream: bool = False
    history_messages: tuple[ProviderHistoryMessage, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.history_messages, tuple):
            raise TypeError("Historical messages must be an immutable tuple")
        if len(self.history_messages) % 2:
            raise ValueError("Historical messages must contain complete conversation turns")
        for index, message in enumerate(self.history_messages):
            if not isinstance(message, ProviderHistoryMessage):
                raise TypeError("Historical messages must use provider-neutral values")
            expected_role = "user" if index % 2 == 0 else "assistant"
            if message.role != expected_role:
                raise ValueError("Historical messages must alternate user and assistant")


@dataclass(frozen=True, slots=True)
class ProviderCompletion:
    """Untrusted completion fields that the application service must validate."""

    content: object
    finish_reason: object
    choice_count: int
    tool_calls_present: bool
    reasoning_content_present: bool
    provider: str
    model: str
    usage: ProviderUsage = field(default_factory=ProviderUsage)


class ProviderError(Exception):
    """Base exception for classified provider failures."""


class ProviderTimeoutError(ProviderError):
    """The provider did not complete within the configured deadline."""


class ProviderUnavailableError(ProviderError):
    """The provider could not accept or complete the request."""


class ProviderInvalidResponseError(ProviderError):
    """The provider completed with an untrusted or unapproved response."""


class ProviderProtocol(Protocol):
    """A replaceable asynchronous dialogue provider."""

    async def complete(self, request: ProviderRequest) -> ProviderCompletion: ...
