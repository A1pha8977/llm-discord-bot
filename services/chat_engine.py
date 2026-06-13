"""Chat engine: context formatting, LLM calling, profile management."""

import logging
from dataclasses import dataclass
from typing import cast

import openai
from openai.types.chat import ChatCompletionMessageParam

from services.llm import LLMClient, TokenUsage
from services.llms import LLMClientFactory
from utils import config

_logger = logging.getLogger(__name__)


class ChatEngineError(Exception):
    """Base exception for ChatEngine errors."""


@dataclass
class ChatMessage:
    """A normalized chat message for context building.

    Attributes:
        role: ``"user"``, ``"assistant"``, or ``"system"``.
        content: The message text.
        name: Display name of the sender (used in user message prefix).
        timestamp: ``HH:MM`` string for history messages, ``None`` for trigger.
    """

    role: str
    content: str
    name: str = ""
    timestamp: str | None = None

    @property
    def formatted_content(self) -> str:
        """Formatted message text for the LLM API."""
        if self.role == "user":
            ts = self.timestamp
            prefix = f"[{ts}] " if ts else ""
            return f"{prefix}{self.name}: {self.content}"
        return self.content


class ChatContext:
    """Manages a sequential chat conversation context.

    Args:
        messages: Optional initial messages. A shallow copy is made so
            mutations to the original list after construction do not
            affect the context.
    """

    def __init__(self, messages: list[ChatMessage] | None = None):
        self._messages: list[ChatMessage] = list(messages) if messages else []

    def add(self, msg: ChatMessage) -> None:
        """Append a message to the context."""
        self._messages.append(msg)

    def extend(self, msgs: list[ChatMessage]) -> None:
        """Extend the context with multiple messages."""
        self._messages.extend(msgs)

    def to_api_format(self) -> list[dict[str, str]]:
        """Export messages as OpenAI-compatible dicts (no system prompt)."""
        return [
            {"role": m.role, "content": m.formatted_content}
            for m in self._messages
        ]

    def clear(self) -> None:
        """Remove all messages."""
        self._messages.clear()

    def reverse(self) -> None:
        """Reverse the message order in place."""
        self._messages.reverse()

    def __len__(self) -> int:
        return len(self._messages)

    def __iter__(self):
        return iter(self._messages)


class ChatEngine:
    """Core engine: builds context, calls LLM, manages profiles.

    LLMClient instances are built once at construction. Default values for
    LLM and prompt profiles are read from ``config/bot.yaml``.

    ``openai.OpenAIError`` from LLM calls propagates to the caller.

    Raises:
        ValueError: On invalid or missing config.
    """

    def __init__(self):
        self._base_prompt = config.get_base_prompt()
        self._llm_clients: dict[str, LLMClient] = LLMClientFactory.build()
        self._default_llm_name = config.get_default_llm_profile()
        self._default_prompt_name = config.get_default_prompt_profile()

    # --- Public: profile info ---

    @property
    def llm_profile_names(self) -> set[str]:
        """All available LLM profile keys."""
        return set(self._llm_clients.keys())

    @property
    def prompt_profile_names(self) -> set[str]:
        """All available character prompt profile names."""
        return config.get_character_prompt_names()

    # --- Public: core ---

    async def respond(
        self,
        context: ChatContext,
        *,
        llm_profile_name: str | None = None,
        prompt_profile_name: str | None = None,
    ) -> tuple[str, TokenUsage]:
        """Format messages, call the selected LLM client, and return text and usage.

        Falls back to engine defaults when ``llm_profile_name`` or
        ``prompt_profile_name`` is ``None``.

        Raises:
            ChatEngineError: If the LLM API call fails.
        """
        llm_profile_name = self._resolve_llm_profile(llm_profile_name)
        prompt_profile_name = self._resolve_prompt_profile(prompt_profile_name)

        llm_client = self._llm_clients[llm_profile_name]
        api_messages = context.to_api_format()
        api_messages.insert(
            0,
            {
                "role": "system",
                "content": self._build_system_prompt(
                    config.get_character_prompt_text(prompt_profile_name)
                ),
            },
        )
        try:
            raw, usage = await llm_client.complete_with_tools(
                messages=cast(list[ChatCompletionMessageParam], api_messages),
                max_rounds=10,
            )
        except openai.OpenAIError as e:
            raise ChatEngineError(str(e)) from e
        return raw, usage

    # --- Public: usage ---

    def get_total_usage(self) -> TokenUsage:
        """Returns cumulative token usage across all requests."""
        p = c = t = 0
        for client in self._llm_clients.values():
            u = client.get_total_usage()
            p += u.prompt_tokens
            c += u.completion_tokens
            t += u.total_tokens
        return TokenUsage(p, c, t)

    # --- Internal ---

    def _resolve_llm_profile(self, name: str | None) -> str:
        name = name or self._default_llm_name
        if name not in self._llm_clients:
            raise ValueError(f"LLM profile '{name}' not found")
        return name

    def _resolve_prompt_profile(self, name: str | None) -> str:
        name = name or self._default_prompt_name
        if name not in config.get_character_prompt_names():
            raise ValueError(f"Prompt profile '{name}' not found in character config")
        return name

    def _build_system_prompt(self, prompt_text: str) -> str:
        if prompt_text:
            return f"{self._base_prompt}\n{prompt_text}"
        return self._base_prompt
