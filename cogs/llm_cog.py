"""Discord Cog for LLM-powered chat replies with per-channel character prompts."""

import json
import logging
import re
from json import JSONDecodeError

from discord import Message
from discord.ext import commands

from services.llm import LLMClient
from utils import config

_logger = logging.getLogger(__name__)


# TODO: unused
def _estimate_tokens(messages: list[dict]) -> int:
    return sum(len(str(m.get("content", ""))) for m in messages) // 4


class LLMCog(commands.Cog):
    """Monitors @mentions, builds message context, calls LLM, and replies.

    Supports per-channel character prompt switching at runtime via
    ``!#switch_prompt <profile>``.

    Args:
        discord_bot: The Discord bot instance.
        llm_client: An LLMClient instance for API calls.
        default_character_prompt_profile: Optional default profile name. Fails fast
            with ``ValueError`` if not found in character config.

    Raises:
        ValueError: If ``default_character_prompt_profile`` is provided but not
            found in the character prompt configuration.
    """
    def __init__(
        self,
        discord_bot: commands.Bot,
        llm_client: LLMClient,
        default_character_prompt_profile: str | None = None,
    ):
        self._discord_bot = discord_bot
        self._llm_client = llm_client
        self._base_prompt = config.load_base_prompt_config()["system"]
        self._character_config = config.load_character_prompt_config() or {}
        if default_character_prompt_profile:
            if not self._character_config:
                raise ValueError("character_prompt_config not found")
            if default_character_prompt_profile not in self._character_config:
                raise ValueError(f"profile '{default_character_prompt_profile}' not found")
            self._default_character_prompt = self._character_config[default_character_prompt_profile]
            assert self._default_character_prompt
        else: 
            self._default_character_prompt = ""
        self._character_prompt: dict[int, str] = {}

    async def cog_load(self) -> None:
        return await super().cog_load()

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        """Triggers ``on_mention`` when the bot is @mentioned."""
        if message.author.bot:
            return
        if message.guild and message.guild.me in message.mentions:
            await self.on_mention(message)

    async def on_mention(self, message: Message):
        """Shows typing indicator, builds context, calls LLM, and replies."""
        async with message.channel.typing():
            messages = await self._build_context(message)
            _logger.info(messages)
            result = await self._call_llm(messages)
        await self._reply_in_channel(message, result, message.content)

    async def _build_context(self, message: Message) -> list[dict]:
        """Fetches channel history and builds a message list for the LLM.

        Pulls up to 20 recent messages, filters out:
        - The triggering message itself
        - Other bots (except self)
        - Empty messages
        - Messages starting with ``LLM *ERROR:`` or ``*COMMAND:``

        Returns a list of ``{"role": ..., "content": ...}`` dicts with a
        system prompt, formatted history, and the triggering message.
        """
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
            if re.match(r"LLM.*ERROR:", msg.content) or re.match(
                r".*COMMAND:", msg.content
            ):
                continue
            role = "assistant" if msg.author == guild.me else "user"
            history.append(
                {
                    "role": role,
                    "content": f"[{msg.created_at.strftime('%H:%M')}] {msg.author.display_name}: {msg.content}",
                }
            )
        history.reverse()

        character_text = self._resolve_character_prompt(message.channel.id)
        system_content = f"{self._base_prompt}\n{character_text}"

        return (
            [  # type: ignore[return-value]
                {"role": "system", "content": system_content},
            ]
            + history
            + [
                {"role": "user", "content": f"{user_display_name}: {message.content}"},
            ]
        )

    def _resolve_character_prompt(self, channel_id: int) -> str:
        """Returns the character prompt text for a given channel.

        Falls back to ``_default_character_prompt`` if none is set for the channel.
        """
        return self._character_prompt.get(channel_id, self._default_character_prompt)

    async def _call_llm(self, messages: list[dict]) -> dict:
        """Calls ``LLMClient.complete`` and parses the JSON response.

        Returns:
            A dict with ``status`` ("ok" or "error") and ``text`` fields.
        """
        raw_response: None | str = None
        try:
            raw_response = await self._llm_client.complete(
                messages=messages,  # type: ignore[arg-type]
            )
            response: dict = (
                json.loads(raw_response)
                if raw_response
                else {"status": "error", "text": "empty response"}
            )
        except JSONDecodeError as e:
            _logger.error(
                f"{e} last context: {messages[-1]['content']}\nresponse: {raw_response}"
            )
            return {"status": "error", "text": f"JSON decode error: {e}"}
        except Exception as e:
            _logger.error(
                f"{e} last context: {messages[-1]['content']}\nresponse: {raw_response or ''}"
            )
            return {"status": "error", "text": f"API ERROR\n```{e}```"}
        return response

    async def _reply_in_channel(
        self, message: Message, result: dict, fallback_content: str
    ):
        """Replies to the triggering message based on the result status.

        - ``error`` status: sends ``LLM ERROR: {text}``
        - ``ok`` status with text: sends the text
        - otherwise: logs a warning with the fallback content
        """
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
        """``!#usage`` — Displays cumulative token usage."""
        await ctx.send(f"COMMAND:\n{self._llm_client.get_total_usage().to_readable()}")

    @commands.command()
    async def switch_prompt(self, ctx: commands.Context, prompt_profile_name: str):
        """``!#switch_prompt <profile>`` — Switches character prompt for current channel."""
        if prompt_profile_name not in self._character_config:
            await ctx.send(f"switch_prompt COMMAND:\n{prompt_profile_name} do not exist")
            return
        self._character_prompt[ctx.channel.id] = self._character_config[prompt_profile_name]
        await ctx.send("switch_prompt COMMAND:\nswitch prompt succeeded")
        

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
