from __future__ import annotations

import runpy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from cyber_town.application.provider import ProviderHistoryMessage, ProviderRequest
from cyber_town.infrastructure.llm.fake import FakeProvider

INTEGRATION_MODULE = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "scripts" / "dialogue_integration.py")
)
MEMORY_SCENARIOS = cast(Any, INTEGRATION_MODULE["MEMORY_SCENARIOS"])
_assert_memory_scenario = cast(Any, INTEGRATION_MODULE["_assert_memory_scenario"])


def provider_request(
    *,
    history: tuple[ProviderHistoryMessage, ...] = (),
    user_message: str = "Synthetic current message",
) -> ProviderRequest:
    return ProviderRequest(
        system_prompt="Synthetic persona",
        user_message=user_message,
        model="deepseek-v4-flash",
        temperature=0.6,
        max_tokens=256,
        timeout_seconds=12.0,
        history_messages=history,
    )


def test_fake_loopback_registers_multi_turn_and_recovery_scenarios() -> None:
    assert {scenario for scenario, _outcomes, _calls in MEMORY_SCENARIOS} == {
        "multi_turn",
        "multi_turn_recovery",
    }


def test_multi_turn_verifier_accepts_complete_increasing_history() -> None:
    provider = FakeProvider([])
    first = provider_request(user_message="First question")
    second = provider_request(
        user_message="Second question",
        history=(
            ProviderHistoryMessage("user", "First question"),
            ProviderHistoryMessage("assistant", "Synthetic first offline reply."),
        ),
    )
    third = provider_request(
        history=(
            *second.history_messages,
            ProviderHistoryMessage("user", "Second question"),
            ProviderHistoryMessage("assistant", "Synthetic second offline reply."),
        )
    )
    provider.requests.extend((first, second, third))
    provider.call_count = 3

    _assert_memory_scenario("multi_turn", provider)


@pytest.mark.parametrize("request_index,assistant_index", ((1, 1), (2, 1), (2, 3)))
def test_multi_turn_verifier_rejects_contaminated_assistant_history(
    request_index: int, assistant_index: int
) -> None:
    private_contamination = "private foreign assistant response 9182"
    first = provider_request(user_message="First question")
    second = provider_request(
        user_message="Second question",
        history=(
            ProviderHistoryMessage("user", "First question"),
            ProviderHistoryMessage("assistant", "Synthetic first offline reply."),
        ),
    )
    third = provider_request(
        history=(
            *second.history_messages,
            ProviderHistoryMessage("user", "Second question"),
            ProviderHistoryMessage("assistant", "Synthetic second offline reply."),
        )
    )
    requests = [first, second, third]
    contaminated_history = list(requests[request_index].history_messages)
    contaminated_history[assistant_index] = ProviderHistoryMessage(
        "assistant", private_contamination
    )
    requests[request_index] = replace(
        requests[request_index], history_messages=tuple(contaminated_history)
    )
    provider = FakeProvider([])
    provider.requests.extend(requests)
    provider.call_count = len(requests)

    with pytest.raises(RuntimeError, match="assistant") as captured:
        _assert_memory_scenario("multi_turn", provider)
    assert private_contamination not in str(captured.value)


@pytest.mark.parametrize("contaminate_recovered_reply", (False, True))
def test_recovery_verifier_rejects_contaminated_assistant_history(
    contaminate_recovered_reply: bool,
) -> None:
    private_contamination = "private recovery assistant response 2374"
    first = provider_request(user_message="First question")
    first_reply = (
        "Synthetic first offline reply." if contaminate_recovered_reply else private_contamination
    )
    second = provider_request(
        user_message="Second question",
        history=(
            ProviderHistoryMessage("user", "First question"),
            ProviderHistoryMessage("assistant", first_reply),
        ),
    )
    retried = replace(second)
    recovered_reply = (
        private_contamination
        if contaminate_recovered_reply
        else "Synthetic recovered offline reply."
    )
    fourth = provider_request(
        history=(
            *second.history_messages,
            ProviderHistoryMessage("user", "Second question"),
            ProviderHistoryMessage("assistant", recovered_reply),
        )
    )
    provider = FakeProvider([])
    provider.requests.extend((first, second, retried, fourth))
    provider.call_count = 4

    with pytest.raises(RuntimeError, match="assistant") as captured:
        _assert_memory_scenario("multi_turn_recovery", provider)
    assert private_contamination not in str(captured.value)


def test_multi_turn_verifier_rejects_missing_history_without_printing_content() -> None:
    provider = FakeProvider([])
    provider.requests.extend((provider_request(), provider_request(), provider_request()))
    provider.call_count = 3

    with pytest.raises(RuntimeError, match="history"):
        _assert_memory_scenario("multi_turn", provider)


def test_multi_turn_recovery_verifier_rejects_a_failed_ghost_turn() -> None:
    provider = FakeProvider([])
    first = provider_request()
    second = provider_request(
        history=(
            ProviderHistoryMessage("user", "First question"),
            ProviderHistoryMessage("assistant", "First reply"),
        )
    )
    ghost = replace(
        second,
        history_messages=(
            *second.history_messages,
            ProviderHistoryMessage("user", "Ghost question"),
            ProviderHistoryMessage("assistant", "Ghost reply"),
        ),
    )
    provider.requests.extend((first, second, ghost, ghost))
    provider.call_count = 4

    with pytest.raises(RuntimeError, match="history"):
        _assert_memory_scenario("multi_turn_recovery", provider)
