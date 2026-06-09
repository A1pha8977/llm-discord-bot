"""LLM client abstraction with token usage tracking."""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.completion_usage import CompletionUsage

from services import tools
from services.tools.registry import ToolRegistry

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
        self._model_name = model_name
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self._total_usage = TokenUsage(0, 0, 0)
        self._usage_lock = asyncio.Lock()

    async def complete(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        response_format: dict | None = None,
    ) -> tuple[str, TokenUsage]:
        """Send a chat completion request and return the response text and usage.

        Args:
            messages: List of chat messages in OpenAI format.
            response_format: Optional response format dict
                (e.g. ``{"type": "json_object"}``).

        Returns:
            A tuple of ``(response_text, token_usage)``.
        """
        kwargs: dict[str, Any] = dict(
            model=self._model_name,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
        )
        if response_format:
            kwargs["response_format"] = response_format
        response = await self._client.chat.completions.create(**kwargs)
        usage = await self._track_usage(response.usage)
        if not response.choices:
            _logger.error("no choices in response for model=%s", self._model_name)
            return "", usage
        return response.choices[0].message.content or "", usage

    async def complete_json(
        self, messages: list[ChatCompletionMessageParam]
    ) -> tuple[str, TokenUsage]:
        """Call ``complete`` with ``response_format={"type": "json_object"}``."""
        return await self.complete(messages, response_format={"type": "json_object"})

    def get_total_usage(self) -> TokenUsage:
        """Returns cumulative token usage across all requests."""
        return self._total_usage

    async def complete_with_tools(
        self,
        messages: list[ChatCompletionMessageParam],
        tool_registry: ToolRegistry = tools.tool_registry,
        *,
        max_rounds: int = 2,
        response_format: dict | None = None,
    ) -> tuple[str, TokenUsage]:
        """Multi-round tool-calling loop.

        Each round calls the API with tools enabled. If the LLM calls a
        tool it is executed and the result appended to the message list.
        The loop continues until the LLM returns a text response (no
        tool_calls), or ``max_rounds`` is exhausted.

        Args:
            messages: Chat messages including the user's request.
            tool_registry: ToolRegistry instance for executing tool calls.
            max_rounds: Maximum tool-calling iterations.  Must be >= 2.

        Returns:
            A tuple of ``(final_text, total_token_usage)``.
        """
        if max_rounds < 2:
            raise ValueError("max_rounds must be >= 2")

        session_usage = TokenUsage(0, 0, 0)
        msgs: list[Any] = list(messages)

        kwargs: dict[str, Any] = dict(
            model=self._model_name,
            messages=cast(list[ChatCompletionMessageParam], msgs),
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
            tools=tool_registry.to_openai_schema(),
            tool_choice="auto",
        )
        if response_format:
            kwargs["response_format"] = response_format

        for round_num in range(max_rounds):
            response = await self._client.chat.completions.create(**kwargs)

            usage = await self._track_usage(response.usage)
            session_usage = TokenUsage(
                session_usage.prompt_tokens + usage.prompt_tokens,
                session_usage.completion_tokens + usage.completion_tokens,
                session_usage.total_tokens + usage.total_tokens,
            )

            if not response.choices:
                _logger.warning(
                    "no choices in response for model=%s round=%d",
                    self._model_name,
                    round_num + 1,
                )
                return "", session_usage

            choice = response.choices[0]

            if not choice.message.tool_calls:
                if not choice.message.content:
                    _logger.warning("empty response for model=%s", self._model_name)
                    return "", session_usage
                return choice.message.content, session_usage

            msgs.append(choice.message.model_dump(exclude_none=True))
            msgs.extend(
                await asyncio.to_thread(
                    self._execute_all_tool_calls,
                    tool_registry,
                    choice.message.tool_calls,
                )
            )

        _logger.warning(
            "max rounds (%d) reached without final answer for model=%s",
            max_rounds,
            self._model_name,
        )
        return "", session_usage

    @staticmethod
    def _execute_all_tool_calls(tool_registry, tool_calls) -> list[dict]:
        """Execute all tool calls and return tool response dicts."""
        responses: list[dict] = []
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                responses.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": (
                            f"Error: malformed JSON in arguments: "
                            f"{tc.function.arguments}"
                        ),
                    }
                )
                continue
            responses.append(tool_registry.execute(tc.function.name, tc.id, args))
        return responses

    async def _track_usage(self, response_usage: CompletionUsage | None) -> TokenUsage:
        """Extract token usage from an API response and update totals."""
        if response_usage is None:
            _logger.warning("no usage data for model=%s", self._model_name)
            return TokenUsage(0, 0, 0)
        usage = TokenUsage(
            prompt_tokens=response_usage.prompt_tokens,
            completion_tokens=response_usage.completion_tokens,
            total_tokens=response_usage.total_tokens,
        )
        async with self._usage_lock:
            self._total_usage = TokenUsage(
                self._total_usage.prompt_tokens + usage.prompt_tokens,
                self._total_usage.completion_tokens + usage.completion_tokens,
                self._total_usage.total_tokens + usage.total_tokens,
            )
        return usage
