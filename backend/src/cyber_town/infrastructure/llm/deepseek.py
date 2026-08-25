"""Isolated OpenAI-compatible adapter for the approved DeepSeek model."""

from __future__ import annotations

import logging
from typing import Any

from openai import APIError, APITimeoutError, AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import SecretStr

from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderInvalidResponseError,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUsage,
)
from cyber_town.config import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


class _SdkPrivacyFilter(logging.Filter):
    """Prevent SDK DEBUG records from serializing private completion payloads."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.INFO


_SDK_PRIVACY_FILTER = _SdkPrivacyFilter()


class DeepSeekProvider:
    """Translate SDK-specific requests and failures into neutral application types."""

    def __init__(
        self,
        *,
        credential: SecretStr,
        base_url: str,
        timeout_seconds: float,
        client: Any | None = None,
    ) -> None:
        if base_url != DEEPSEEK_BASE_URL or not credential.get_secret_value().strip():
            raise ProviderUnavailableError("The dialogue provider configuration is invalid.")

        sdk_logger = logging.getLogger("openai._base_client")
        if _SDK_PRIVACY_FILTER not in sdk_logger.filters:
            sdk_logger.addFilter(_SDK_PRIVACY_FILTER)

        client_options: dict[str, Any] = {
            "api_key": credential.get_secret_value(),
            "base_url": base_url,
            "timeout": timeout_seconds,
            "max_retries": 0,
        }
        self._client = client or AsyncOpenAI(**client_options)

    async def complete(self, request: ProviderRequest) -> ProviderCompletion:
        """Execute exactly one non-thinking, non-streaming completion request."""

        if request.model != DEEPSEEK_MODEL or request.thinking_enabled or request.stream:
            raise ProviderUnavailableError("The dialogue provider request is not approved.")

        try:
            request.__post_init__()
            for fact in request.long_term_facts:
                fact.__post_init__()
            for message in request.history_messages:
                message.__post_init__()
        except (TypeError, ValueError):
            raise ProviderUnavailableError(
                "The dialogue provider request is not approved."
            ) from None

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": request.system_prompt}
        ]
        for fact in request.long_term_facts:
            messages.append({"role": "user", "content": fact.as_user_content()})
        for message in request.history_messages:
            if message.role == "user":
                messages.append({"role": "user", "content": message.content})
            else:
                messages.append({"role": "assistant", "content": message.content})
        messages.append({"role": "user", "content": request.user_message})

        try:
            response = await self._client.chat.completions.create(
                model=request.model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=False,
                timeout=request.timeout_seconds,
                extra_body={"thinking": {"type": "disabled"}},
            )
        except APITimeoutError:
            raise ProviderTimeoutError("The dialogue provider timed out.") from None
        except APIError:
            raise ProviderUnavailableError("The dialogue provider is unavailable.") from None

        return self._translate_completion(response)

    @staticmethod
    def _translate_completion(response: Any) -> ProviderCompletion:
        try:
            if response.model != DEEPSEEK_MODEL:
                raise ValueError("Unapproved provider response model")
            usage = response.usage
            if usage is None:
                raise ValueError("Missing provider token usage")
            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
            if type(prompt_tokens) is not int or type(completion_tokens) is not int:
                raise ValueError("Invalid provider token usage")

            token_usage = ProviderUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            choices = response.choices
            if not isinstance(choices, list):
                raise ValueError("Invalid provider completion choices")
            choice_count = len(choices)
            choice = choices[0] if choice_count else None
            message = choice.message if choice is not None else None

            return ProviderCompletion(
                content=message.content if message is not None else None,
                finish_reason=choice.finish_reason if choice is not None else None,
                choice_count=choice_count,
                tool_calls_present=bool(getattr(message, "tool_calls", None)),
                reasoning_content_present=getattr(message, "reasoning_content", None) is not None,
                provider="deepseek",
                model=response.model,
                usage=token_usage,
            )
        except (AttributeError, TypeError, ValueError):
            raise ProviderInvalidResponseError(
                "The dialogue provider returned an invalid response."
            ) from None
