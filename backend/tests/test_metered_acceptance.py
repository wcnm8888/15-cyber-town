from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from cyber_town.application.acceptance import MeteredAcceptanceProvider
from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderRequest,
    ProviderUnavailableError,
    ProviderUsage,
)
from cyber_town.infrastructure.llm.fake import FakeProvider
from cyber_town.infrastructure.persistence.acceptance_ledger import (
    AcceptanceBudgetError,
    AcceptanceLedger,
    AcceptanceLedgerError,
    AcceptanceStep,
)


@pytest.fixture
def ledger(tmp_path: Path) -> AcceptanceLedger:
    result = AcceptanceLedger(database_path=tmp_path / "metered.sqlite3", allowed_root=tmp_path)
    result.initialize()
    return result


def completion() -> ProviderCompletion:
    return ProviderCompletion(
        content="Synthetic offline acceptance reply.",
        finish_reason="stop",
        choice_count=1,
        tool_calls_present=False,
        reasoning_content_present=False,
        provider="fake",
        model="deepseek-v4-flash",
        usage=ProviderUsage(prompt_tokens=18, completion_tokens=9),
    )


def request() -> ProviderRequest:
    return ProviderRequest(
        system_prompt="Synthetic persona.",
        user_message="Synthetic acceptance question.",
        model="deepseek-v4-flash",
        temperature=0.6,
        max_tokens=256,
        timeout_seconds=12.0,
    )


def metered(ledger: AcceptanceLedger, provider: FakeProvider) -> MeteredAcceptanceProvider:
    return MeteredAcceptanceProvider(
        provider=provider,
        ledger=ledger,
        authorization_id="f-005-step-5-synthetic",
        step=AcceptanceStep.STEP_5,
        reserved_micro_usd=1_000,
        usage_cost=lambda usage: usage.prompt_tokens + usage.completion_tokens,
    )


def test_provider_usage_is_recorded_before_completion_returns_to_the_caller(
    ledger: AcceptanceLedger,
) -> None:
    provider = FakeProvider([completion()])

    result = asyncio.run(metered(ledger, provider).complete(request()))

    assert result.usage.total_tokens == 27
    assert ledger.summary().total_calls == 1
    assert ledger.summary().total_prompt_tokens == 18
    assert ledger.summary().total_completion_tokens == 9
    assert ledger.summary().total_micro_usd == 27


def test_later_semantic_failure_cannot_erase_already_persisted_usage(
    ledger: AcceptanceLedger,
) -> None:
    provider = FakeProvider([completion()])

    with pytest.raises(AssertionError):
        result = asyncio.run(metered(ledger, provider).complete(request()))
        assert result.content == "deliberately impossible semantic expectation"

    assert ledger.summary().total_calls == 1
    assert ledger.summary().total_micro_usd == 27
    assert ledger.summary().pending_calls == 0


def test_unresolved_prior_call_blocks_provider_before_dispatch(ledger: AcceptanceLedger) -> None:
    ledger.reserve(
        authorization_id="prior-synthetic",
        step=AcceptanceStep.STEP_5,
        model="deepseek-v4-flash",
        reserved_micro_usd=1,
    )
    provider = FakeProvider([completion()])

    with pytest.raises(AcceptanceLedgerError):
        asyncio.run(metered(ledger, provider).complete(request()))

    assert provider.call_count == 0


def test_provider_failure_is_preserved_as_unknown_and_blocks_followup_calls(
    ledger: AcceptanceLedger,
) -> None:
    provider = FakeProvider([ProviderUnavailableError("synthetic provider outage")])

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(metered(ledger, provider).complete(request()))

    assert ledger.summary().total_calls == 1
    assert ledger.summary().pending_calls == 1
    with pytest.raises(AcceptanceLedgerError):
        asyncio.run(metered(ledger, FakeProvider([completion()])).complete(request()))


def test_step_call_limit_blocks_ninth_provider_dispatch(ledger: AcceptanceLedger) -> None:
    provider = FakeProvider([completion() for _ in range(9)])
    wrapper = metered(ledger, provider)
    for _ in range(8):
        asyncio.run(wrapper.complete(request()))

    with pytest.raises(AcceptanceBudgetError):
        asyncio.run(wrapper.complete(request()))

    assert provider.call_count == 8


def test_unapproved_or_missing_usage_cost_fails_closed(ledger: AcceptanceLedger) -> None:
    provider = FakeProvider([completion()])
    wrapper = MeteredAcceptanceProvider(
        provider=provider,
        ledger=ledger,
        authorization_id="f-005-step-5-synthetic",
        step=AcceptanceStep.STEP_5,
        reserved_micro_usd=10,
        usage_cost=lambda _usage: 11,
    )

    with pytest.raises(AcceptanceBudgetError):
        asyncio.run(wrapper.complete(request()))

    assert provider.call_count == 1
    assert ledger.summary().pending_calls == 1


@pytest.mark.parametrize(
    ("prompt_tokens", "completion_tokens"),
    [(0, 0), (0, 4), (4, 0)],
)
def test_zero_official_usage_fails_closed_after_the_fake_provider_call(
    ledger: AcceptanceLedger, prompt_tokens: int, completion_tokens: int
) -> None:
    invalid_completion = replace(
        completion(),
        usage=ProviderUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )
    provider = FakeProvider([invalid_completion])

    with pytest.raises(ValueError):
        asyncio.run(metered(ledger, provider).complete(request()))

    assert provider.call_count == 1
    assert ledger.summary().total_calls == 1
    assert ledger.summary().pending_calls == 1
