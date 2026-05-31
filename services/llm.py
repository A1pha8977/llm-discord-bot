import logging
from dataclasses import dataclass

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

_logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def to_readable(self) -> str:
        return f"prompt_tokens: {self.prompt_tokens}\ncompletion_tokens: {self.completion_tokens}\ntotal_tokens: {self.total_tokens}"


class LLMClient:

    def __init__(self, api_key: str, base_url: str, model_name: str, *,
        temperature = 0.7,
        max_output_tokens = 300,
        response_format = None,
    ):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.temperature = temperature
        self.max_output_tokens =  max_output_tokens
        self.response_format = response_format
        self._last_usage: TokenUsage | None = None
        self._total_usage = TokenUsage(0, 0, 0)

    async def complete(self, messages: list[ChatCompletionMessageParam]) -> str:
        kwargs: dict = dict(
            model=self.model_name,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
        )
        if self.response_format:
            kwargs["response_format"] = self.response_format
        response = await self._client.chat.completions.create(**kwargs)
        if response.usage:
            self._last_usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )
            self._total_usage = TokenUsage(
                self._total_usage.prompt_tokens + self._last_usage.prompt_tokens,
                self._total_usage.completion_tokens + self._last_usage.completion_tokens,
                self._total_usage.total_tokens + self._last_usage.total_tokens,
            )
        return response.choices[0].message.content or ""

    def get_last_usage(self) -> TokenUsage | None:
        return self._last_usage

    def get_total_usage(self) -> TokenUsage:
        return self._total_usage
