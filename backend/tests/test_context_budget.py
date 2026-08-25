from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, Literal

import pytest

from cyber_town.application.context_budget import (
    ContextBudgetError,
    ContextBudgetFailure,
    estimate_context_units,
    select_history_messages,
)
from cyber_town.application.memory import ConversationTurn
from cyber_town.application.provider import ProviderHistoryMessage, ProviderRequest


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_history_message_accepts_only_approved_roles(role: Literal["user", "assistant"]) -> None:
    message = ProviderHistoryMessage(role=role, content="Approved content")

    assert message.role == role
    assert message.content == "Approved content"


@pytest.mark.parametrize(
    "role",
    ["system", "developer", "tool", "function", "USER", "", " user", None, 1, True, [], {}],
)
def test_history_message_rejects_role_injection_and_invalid_types(role: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        ProviderHistoryMessage(role=role, content="Approved content")


@pytest.mark.parametrize("content", [None, 1, True, [], {}, "", "   ", "\t\n"])
def test_history_message_rejects_invalid_content(content: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        ProviderHistoryMessage(role="user", content=content)


def test_history_message_is_immutable_and_redacts_sensitive_content() -> None:
    message = ProviderHistoryMessage(role="user", content="synthetic private history 7194")

    assert "synthetic private history 7194" not in repr(message)
    with pytest.raises(FrozenInstanceError):
        message.role = "assistant"  # type: ignore[misc]


def provider_request(**overrides: Any) -> ProviderRequest:
    values: dict[str, Any] = {
        "system_prompt": "Frozen persona",
        "user_message": "Current message",
        "model": "deepseek-v4-flash",
        "temperature": 0.6,
        "max_tokens": 256,
        "timeout_seconds": 12.0,
    }
    values.update(overrides)
    return ProviderRequest(**values)


def test_provider_request_history_defaults_to_empty_tuple() -> None:
    assert provider_request().history_messages == ()


def test_provider_request_accepts_complete_alternating_history() -> None:
    history = (
        ProviderHistoryMessage("user", "First question"),
        ProviderHistoryMessage("assistant", "First reply"),
        ProviderHistoryMessage("user", "Second question"),
        ProviderHistoryMessage("assistant", "Second reply"),
    )

    assert provider_request(history_messages=history).history_messages == history


@pytest.mark.parametrize(
    "history",
    [
        [ProviderHistoryMessage("user", "Question"), ProviderHistoryMessage("assistant", "Reply")],
        (ProviderHistoryMessage("user", "Question"),),
        (ProviderHistoryMessage("assistant", "Reply"),),
        (ProviderHistoryMessage("assistant", "Reply"), ProviderHistoryMessage("user", "Question")),
        (ProviderHistoryMessage("user", "Question"), ProviderHistoryMessage("user", "Another")),
        (
            ProviderHistoryMessage("user", "Question"),
            ProviderHistoryMessage("assistant", "Reply"),
            ProviderHistoryMessage("user", "Orphan"),
        ),
        ("user", "assistant"),
        None,
    ],
)
def test_provider_request_rejects_partial_or_malformed_history(history: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        provider_request(history_messages=history)


@pytest.mark.parametrize(
    ("content", "byte_count"),
    [("ascii", 5), ("你好", 6), ("🌃", 4), ("e\u0301", 3), ("é", 2)],
)
def test_estimate_counts_utf8_bytes_not_codepoints(content: str, byte_count: int) -> None:
    assert estimate_context_units("persona", content, ()) == 64 + 16 + 7 + 16 + byte_count + 256


def test_estimate_counts_every_history_message_overhead() -> None:
    history = (
        ProviderHistoryMessage("user", "你"),
        ProviderHistoryMessage("assistant", "🌃"),
    )

    assert estimate_context_units("p", "q", history) == 64 + 17 + (16 + 3) + (16 + 4) + 17 + 256


def test_exact_context_budget_is_accepted() -> None:
    persona = "p" * 7_839

    assert estimate_context_units(persona, "u", ()) == 8_192
    assert select_history_messages(persona, "u", ()) == ()


def test_current_message_one_unit_over_budget_is_validation_failure() -> None:
    persona = "p" * 7_839

    with pytest.raises(ContextBudgetError) as captured:
        select_history_messages(persona, "uu", ())

    assert captured.value.failure is ContextBudgetFailure.CURRENT_MESSAGE
    assert "uu" not in str(captured.value)


def test_persona_or_minimum_structure_over_budget_is_internal_failure() -> None:
    with pytest.raises(ContextBudgetError) as captured:
        select_history_messages("p" * 7_840, "u", ())

    assert captured.value.failure is ContextBudgetFailure.MINIMUM_CONTEXT


def test_history_retains_newest_complete_turns_and_sends_oldest_first() -> None:
    turns = (
        ConversationTurn("old question", "x" * 4_000),
        ConversationTurn("middle question", "middle reply"),
        ConversationTurn("new question", "new reply"),
    )

    selected = select_history_messages("p" * 4_000, "current", turns)

    assert [(message.role, message.content) for message in selected] == [
        ("user", "middle question"),
        ("assistant", "middle reply"),
        ("user", "new question"),
        ("assistant", "new reply"),
    ]
    assert estimate_context_units("p" * 4_000, "current", selected) <= 8_192


def test_history_drops_an_entire_pair_when_it_exceeds_budget_by_one() -> None:
    turns = (ConversationTurn("u", "a"),)

    assert select_history_messages("p" * 7_805, "u", turns) == (
        ProviderHistoryMessage("user", "u"),
        ProviderHistoryMessage("assistant", "a"),
    )
    assert select_history_messages("p" * 7_806, "u", turns) == ()


@pytest.mark.parametrize("turns", [None, [ConversationTurn("u", "a")], ("not-a-turn",)])
def test_history_selection_rejects_non_tuple_or_partial_turns(turns: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        select_history_messages("persona", "current", turns)
