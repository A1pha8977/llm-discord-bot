"""LLM client abstraction with token usage tracking."""

import asyncio
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

_logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Token consumption per API request."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def to_readable(self) -> str:
        """Returns a human-readable string of token usage."""
        return f"prompt_tokens: {self.prompt_tokens}\ncompletion_tokens: {self.completion_tokens}\ntotal_tokens: {self.total_tokens}"


class LLMClient:
    """Provider-agnostic LLM API client backed by AsyncOpenAI.

    Args:
        api_key: API key for the LLM service.
        base_url: Base URL of the LLM API endpoint.
        model_name: Model name to use for completions.
        temperature: Sampling temperature (0.0 to 2.0).
        max_output_tokens: Maximum tokens in the response.
    """
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        *,
        temperature: float = 0.7,
        max_output_tokens: int = 300,
    ):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self._total_usage = TokenUsage(0, 0, 0)
        self._usage_lock = asyncio.Lock()

    async def complete(self, messages: list[ChatCompletionMessageParam], *, response_format: dict | None = None) -> tuple[str, TokenUsage]:
        """Send a chat completion request and return the response text and usage.

        Args:
            messages: List of chat messages in OpenAI format.
            response_format: Optional response format dict
                (e.g. ``{"type": "json_object"}``).

        Returns:
            A tuple of ``(response_text, token_usage)``.
        """
        kwargs: dict = dict(
            model=self.model_name,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
        )
        if response_format:
            kwargs["response_format"] = response_format
        response = await self._client.chat.completions.create(**kwargs)
        usage = TokenUsage(0, 0, 0)
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )
            async with self._usage_lock:
                self._total_usage = TokenUsage(
                    self._total_usage.prompt_tokens + usage.prompt_tokens,
                    self._total_usage.completion_tokens + usage.completion_tokens,
                    self._total_usage.total_tokens + usage.total_tokens,
                )
        if not response.choices:
            return "", usage
        return response.choices[0].message.content or "", usage

    async def complete_json(self, messages: list[ChatCompletionMessageParam]) -> tuple[str, TokenUsage]:
        """Call ``complete`` with ``response_format={"type": "json_object"}``."""
        return await self.complete(messages, response_format={"type": "json_object"})

    def get_total_usage(self) -> TokenUsage:
        """Returns cumulative token usage across all requests."""
        return self._total_usage
