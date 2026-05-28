import json

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam


class LLMClient:

    _SYSTEM_PROMPT = (
        "Always reply in JSON format: "
        '{"status": "ok", "text": "your reply"} '
        'or {"status": "error", "text": "reason if unable to answer (ENGLISH ONLY)".\n'
        '严格限制输出长度限制在100字符以内, 如果无法在限制内回答需要在text指出超出限制'
    )

    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        temperature: float = 0.7,
        MAX_TOKENS: int = 300,
    ) -> dict:
        messages = self._inject_json_instruction(messages)
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=MAX_TOKENS,
            response_format={"type": "json_object"}, #TODO 其他LLM可能不支持 {"type": "json_object"}
        )
        content = response.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"status": "error", "text": "JSONDecodeError"}

    async def chat_text(
        self,
        messages: list[ChatCompletionMessageParam],
        temperature: float = 0.7,
        max_tokens: int = 300,
    ) -> str:
        result = await self.chat(messages, temperature, max_tokens)
        if result.get("status") == "error":
            return f"LLM Error: {result.get("text", "Unknown error")} :middle_finger: "
        return result.get("text", "")

    async def compress(
        self, messages: list[ChatCompletionMessageParam],
    ) -> str:
        msgs: list[ChatCompletionMessageParam] = [  # type: ignore[assignment]
            {
                "role": "system",
                "content": (
                    "你是一个对话摘要助手。请将以下对话历史压缩为一段简洁的摘要，"
                    "保留关键信息和上下文。用中文输出。"
                ),
            },
            {
                "role": "user",
                "content": "\n".join(
                    f"[{m['role']}]: {m['content']}"  # type: ignore[typeddict-item]
                    for m in messages
                ),
            },
        ]
        result = await self.chat(msgs, temperature=0.3)
        return result.get("text", "")

    def _inject_json_instruction(
        self,
        messages: list[ChatCompletionMessageParam],
    ) -> list[ChatCompletionMessageParam]:
        for m in messages:
            if m.get("role") == "system":  # type: ignore[typeddict-item]
                m["content"] = f"{m['content']}\n{self._SYSTEM_PROMPT}"  # type: ignore[index]
                return messages
        messages.insert(  # type: ignore[typeddict-item]
            0, {"role": "system", "content": self._SYSTEM_PROMPT},
        )
        return messages
