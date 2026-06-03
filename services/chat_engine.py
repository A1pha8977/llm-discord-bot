"""Chat engine: context formatting, LLM calling, profile management."""

import logging
from dataclasses import dataclass

from services.llm import LLMClient, TokenUsage
from services.llms import LLMClientFactory
from utils import config

_logger = logging.getLogger(__name__)


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


class ChatEngine:
    """Core engine: builds context, calls LLM, manages profiles.

    LLMClient instances are built once at construction. Default values for
    LLM and prompt profiles are read from ``config/bot.yaml``.

    ``openai.OpenAIError`` from LLM calls propagates to the caller.

    Raises:
        ValueError: On invalid or missing config.
    """

    def __init__(self):
        bot_cfg = config.load_bot_config()
        defaults = bot_cfg["defaults"]

        base_prompt_config = config.load_base_prompt_config()
        self._base_prompt: str = base_prompt_config["system"]
        
        self._character_config = config.load_character_prompt_config()
        self._llm_clients: dict[str, LLMClient] = LLMClientFactory.build()
        if not self._llm_clients:
            raise ValueError("no LLM clients configured")

        self._default_llm_name: str = defaults["llm_profile"]
        self._default_prompt_name: str = defaults["prompt_profile"]

        if self._default_prompt_name not in self._character_config:
            raise ValueError(
                f"default prompt_profile '{self._default_prompt_name}' not found in character config"
            )
        if self._default_llm_name not in self._llm_clients:
            raise ValueError(
                f"default llm_profile '{self._default_llm_name}' not found in providers config"
            )

        self._last_usage: TokenUsage | None = None

    # --- Public: profile info ---

    @property
    def llm_profile_names(self) -> set[str]:
        """All available LLM profile keys."""
        return set(self._llm_clients.keys())

    @property
    def prompt_profile_names(self) -> set[str]:
        """All available character prompt profile names."""
        return set(self._character_config.keys())

    # --- Public: core ---

    async def respond(
        self,
        messages: list[ChatMessage],
        *,
        llm_profile_name: str | None = None,
        prompt_profile_name: str | None = None,
    ) -> str:
        """Format messages, call the selected LLM client, and return text.

        Falls back to engine defaults when ``llm_profile_name`` or
        ``prompt_text`` is ``None``.

        ``openai.OpenAIError`` propagates to the caller.
        """
        if llm_profile_name is None:
            llm_profile_name = self._default_llm_name
        if prompt_profile_name is None:
            prompt_profile_name = self._default_prompt_name

        if llm_profile_name not in self._llm_clients:
            raise ValueError(f"LLM profile '{llm_profile_name}' not found")
        if prompt_profile_name not in self._character_config:
            raise ValueError(f"Prompt profile '{prompt_profile_name}' not found in character config")
        
        llm_client = self._llm_clients[llm_profile_name]
        api_messages = self._format(messages, self._character_config[prompt_profile_name])
        raw, usage = await llm_client.complete(
            messages=api_messages,  # type: ignore[arg-type]
        )
        self._last_usage = usage
        return raw

    # --- Public: usage ---

    def get_last_usage(self) -> TokenUsage | None:
        """Returns token usage for the last request."""
        return self._last_usage

    def get_total_usage(self) -> TokenUsage:
        """Returns cumulative token usage across all requests."""
        total = TokenUsage(0, 0, 0)
        for client in self._llm_clients.values():
            u = client.get_total_usage()
            total = TokenUsage(
                total.prompt_tokens + u.prompt_tokens,
                total.completion_tokens + u.completion_tokens,
                total.total_tokens + u.total_tokens,
            )
        return total

    # --- Internal ---

    def _format(
        self, messages: list[ChatMessage], prompt_text: str = ""
    ) -> list[dict]:
        """ChatMessage list → API message dict list."""
        system_content = self._base_prompt
        if prompt_text:
            system_content = f"{system_content}\n{prompt_text}"

        result = [{"role": "system", "content": system_content}]

        for msg in messages:
            if msg.role == "user":
                ts = msg.timestamp
                prefix = f"[{ts}] " if ts else ""
                content = f"{prefix}{msg.name}: {msg.content}"
            else:
                content = msg.content
            result.append({"role": msg.role, "content": content})

        return result
