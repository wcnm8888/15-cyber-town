"""Conservative UTF-8 working-context estimates, not provider token counts."""

from __future__ import annotations

from enum import StrEnum

from cyber_town.application.memory import ConversationTurn
from cyber_town.application.provider import ProviderHistoryMessage

CONTEXT_BUDGET_UNITS = 8_192
REQUEST_OVERHEAD_UNITS = 64
MESSAGE_OVERHEAD_UNITS = 16
RESPONSE_RESERVE_UNITS = 256


class ContextBudgetFailure(StrEnum):
    """Safe classification without retaining prompt or message contents."""

    CURRENT_MESSAGE = "current_message"
    MINIMUM_CONTEXT = "minimum_context"


class ContextBudgetError(ValueError):
    """The approved minimum context cannot safely fit its fixed allocation."""

    def __init__(self, failure: ContextBudgetFailure) -> None:
        super().__init__("The dialogue context exceeds its approved budget.")
        self.failure = failure


def estimate_context_units(
    system_prompt: str,
    current_message: str,
    history_messages: tuple[ProviderHistoryMessage, ...],
) -> int:
    """Estimate UTF-8 bytes and fixed envelope overhead; this is not token usage."""

    return (
        REQUEST_OVERHEAD_UNITS
        + MESSAGE_OVERHEAD_UNITS
        + len(system_prompt.encode("utf-8"))
        + sum(
            MESSAGE_OVERHEAD_UNITS + len(item.content.encode("utf-8")) for item in history_messages
        )
        + MESSAGE_OVERHEAD_UNITS
        + len(current_message.encode("utf-8"))
        + RESPONSE_RESERVE_UNITS
    )


def select_history_messages(
    system_prompt: str,
    current_message: str,
    turns: tuple[ConversationTurn, ...],
) -> tuple[ProviderHistoryMessage, ...]:
    """Retain newest whole turns first, then return them oldest-to-newest."""

    if not isinstance(turns, tuple) or any(
        not isinstance(turn, ConversationTurn) for turn in turns
    ):
        raise TypeError("Conversation history must contain immutable complete turns")

    minimum_units = (
        REQUEST_OVERHEAD_UNITS
        + MESSAGE_OVERHEAD_UNITS
        + len(system_prompt.encode("utf-8"))
        + MESSAGE_OVERHEAD_UNITS
        + 1
        + RESPONSE_RESERVE_UNITS
    )
    if minimum_units > CONTEXT_BUDGET_UNITS:
        raise ContextBudgetError(ContextBudgetFailure.MINIMUM_CONTEXT)

    remaining_units = CONTEXT_BUDGET_UNITS - estimate_context_units(
        system_prompt, current_message, ()
    )
    if remaining_units < 0:
        raise ContextBudgetError(ContextBudgetFailure.CURRENT_MESSAGE)

    selected_pairs: list[tuple[ProviderHistoryMessage, ProviderHistoryMessage]] = []
    for turn in reversed(turns):
        user = ProviderHistoryMessage(role="user", content=turn.user_message)
        assistant = ProviderHistoryMessage(role="assistant", content=turn.assistant_message)
        pair_units = (
            2 * MESSAGE_OVERHEAD_UNITS
            + len(user.content.encode("utf-8"))
            + len(assistant.content.encode("utf-8"))
        )
        if pair_units > remaining_units:
            break
        selected_pairs.append((user, assistant))
        remaining_units -= pair_units

    return tuple(message for pair in reversed(selected_pairs) for message in pair)
