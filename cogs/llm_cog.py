from discord import Message
from discord.ext import commands
from services.llm import LLMClient

import json
from json import JSONDecodeError
import logging
import re

from utils import config

_logger = logging.getLogger(__name__)



MAX_CONTEXT_TOKENS = 3000

def _estimate_tokens(messages: list[dict]) -> int:
    return sum(len(str(m.get("content", ""))) for m in messages) // 4


class LLMCog(commands.Cog):

    def __init__(self, discord_bot: commands.Bot, llm_client: LLMClient, character_prompt: str = ""):
        self._discord_bot = discord_bot
        self._llm_client = llm_client
        base_prompt = config.load_prompt_yaml("config/llm_base_prompt.yaml")["system"]
        self._system_prompt = (
            f"{base_prompt}\n{character_prompt}" if character_prompt else base_prompt
        )

    async def cog_load(self) -> None:
        return await super().cog_load()

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.author.bot:
            return
        if message.guild and message.guild.me in message.mentions:
            await self.on_mention(message)

    async def on_mention(self, message: Message):
        async with message.channel.typing():
            messages = await self._build_context(message)
            _logger.info(messages)
            result = await self._call_llm(messages)
        await self._reply_in_channel(message, result, message.content)

    async def _build_context(self, message: Message) -> list[dict]:
        guild = message.guild
        assert guild is not None
        channel = message.channel
        user_display_name = message.author.display_name

        history = []
        async for msg in channel.history(limit=20):
            if msg.id == message.id:
                continue
            if msg.author.bot and msg.author != guild.me:
                continue
            if not msg.content.strip():
                continue
            if re.match(r"LLM.*ERROR:", msg.content) or re.match(r".*COMMAND:", msg.content):
                continue
            role = "assistant" if msg.author == guild.me else "user"
            history.append({
                "role": role,
                "content": f"[{msg.created_at.strftime('%H:%M')}] {msg.author.display_name}: {msg.content}",
            })
        history.reverse()

        return [  # type: ignore[return-value]
            {"role": "system", "content": self._system_prompt},
        ] + history + [
            {"role": "user", "content": f"{user_display_name}: {message.content}"},
        ]

    async def _call_llm(self, messages: list[dict]) -> dict:
        try:
            raw_response: str = await self._llm_client.complete(
                messages=messages,  # type: ignore[arg-type]
            )
            response: dict = json.loads(raw_response) if raw_response else {"status": "error", "text": "empty response"}
        except JSONDecodeError as e:
            _logger.error(f"{e} last context: {messages[-1]["content"]}\nresponse: {raw_response}")
            return {"status": "error", "text": f"JSON decode error: {e}"}
        except Exception as e:
            _logger.error(f"{e} last context: {messages[-1]["content"]}\nresponse: {raw_response}")
            return {"status": "error", "text": f"API error: {e}"}
        return response

    async def _reply_in_channel(self, message: Message, result: dict, fallback_content: str):
        status = result.get("status", "error")
        text = result.get("text", "")

        if status == "error":
            await message.reply(f"LLM ERROR: {text}")
        elif text:
            await message.reply(f"{text}")
        else:
            _logger.warning("LLM empty response content=%s", fallback_content)
        _logger.info(self._llm_client.get_last_usage())


    @commands.command()
    async def usage(self, ctx: commands.Context):
        await ctx.send(f"COMMAND:\n{self._llm_client.get_total_usage().to_readable()}")

    async def _maybe_compress(self, channel_id: int):
        raise NotImplementedError("_maybe_compress")

    @staticmethod
    def _split_message(text: str, limit: int = 2000) -> list[str]:
        chunks = []
        while len(text) > limit:
            split_at = text.rfind("\n", 0, limit)
            if split_at == -1:
                split_at = limit
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()
        if text:
            chunks.append(text)
        return chunks
