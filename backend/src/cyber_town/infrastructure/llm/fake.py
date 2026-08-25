"""Deterministic provider substitute for offline tests and CI."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderRequest,
)


class FakeProvider:
    """Return queued outcomes without performing network access."""

    def __init__(self, outcomes: Iterable[ProviderCompletion | Exception]) -> None:
        self._outcomes = deque(outcomes)
        self.requests: list[ProviderRequest] = []
        self.call_count = 0

    async def complete(self, request: ProviderRequest) -> ProviderCompletion:
        self.call_count += 1
        self.requests.append(request)
        if not self._outcomes:
            raise RuntimeError("Fake provider outcome queue is empty")

        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
