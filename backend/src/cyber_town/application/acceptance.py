"""Explicitly metered provider wrapper for separately authorized acceptance only."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress

from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderProtocol,
    ProviderRequest,
    ProviderUsage,
)
from cyber_town.infrastructure.persistence.acceptance_ledger import (
    AcceptanceLedger,
    AcceptanceLedgerError,
    AcceptanceStep,
)


class MeteredAcceptanceProvider:
    """Reserve before dispatch and persist usage before returning completion data."""

    def __init__(
        self,
        *,
        provider: ProviderProtocol,
        ledger: AcceptanceLedger,
        authorization_id: str,
        step: AcceptanceStep,
        reserved_micro_usd: int,
        usage_cost: Callable[[ProviderUsage], int],
    ) -> None:
        self._provider = provider
        self._ledger = ledger
        self._authorization_id = authorization_id
        self._step = step
        self._reserved_micro_usd = reserved_micro_usd
        self._usage_cost = usage_cost

    async def complete(self, request: ProviderRequest) -> ProviderCompletion:
        """Persist reservation, perform one call, then settle usage before assertions."""

        reservation_id = self._ledger.reserve(
            authorization_id=self._authorization_id,
            step=self._step,
            model=request.model,
            reserved_micro_usd=self._reserved_micro_usd,
        )
        try:
            completion = await self._provider.complete(request)
            actual_micro_usd = self._usage_cost(completion.usage)
            self._ledger.record_usage(
                reservation_id,
                prompt_tokens=completion.usage.prompt_tokens,
                completion_tokens=completion.usage.completion_tokens,
                actual_micro_usd=actual_micro_usd,
            )
        except BaseException:
            with suppress(AcceptanceLedgerError):
                self._ledger.mark_unknown(reservation_id)
            raise
        return completion
