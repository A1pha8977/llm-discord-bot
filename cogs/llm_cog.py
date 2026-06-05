"""Discord Cog for LLM-powered chat replies with per-channel character prompts
and runtime LLM provider switching."""

import logging
import re

from discord import Message
from discord.abc import Messageable
from discord.ext import commands

from services.chat_engine import ChatContext, ChatEngine, ChatEngineError, ChatMessage
from services.llm import TokenUsage

_logger = logging.getLogger(__name__)


class LLMCog(commands.Cog):
    """Monitors @mentions, builds message context, calls LLM, and replies.

    All LLM logic is delegated to :class:`ChatEngine`.

    Args:
        discord_bot: The Discord bot instance.
        chat_engine: Pre-configured ChatEngine instance.
    """

    def __init__(
        self,
        discord_bot: commands.Bot,
        chat_engine: ChatEngine,
    ):
        self._discord_bot = discord_bot
        self._chat_engine = chat_engine
        self._channel_prompt: dict[int, str] = {}
        """channel_id → profile_name"""
        self._channel_llm: dict[int, str] = {}
        """channel_id → llm_profile_name"""

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        """Triggers ``on_mention`` when the bot is @mentioned."""
        if message.author.bot:
            return
        if message.guild and message.guild.me in message.mentions:
            await self.on_mention(message)

    async def on_mention(self, message: Message):
        """Shows typing indicator, builds context, calls LLM, and replies."""
        _logger.info(
            "[%s] | #%s | triggered by @%s",
            message.created_at.strftime("%H:%M"),
            self._channel_name(message.channel),
            message.author.display_name,
        )
        async with message.channel.typing():
            context = await self._build_context(message)
            channel_id = message.channel.id

            try:
                text, usage = await self._chat_engine.respond(
                    context,
                    llm_profile_name=self._channel_llm.get(channel_id),
                    prompt_profile_name=self._channel_prompt.get(channel_id),
                )
            except ChatEngineError as e:
                _logger.error(
                    "[%s] | #%s | LLM API error: %s",
                    message.created_at.strftime("%H:%M"),
                    self._channel_name(message.channel),
                    e,
                    exc_info=True,
                )
                text = f"LLM API ERROR: {e}"
                usage = TokenUsage(0, 0, 0)
            await self._reply_in_channel(message, text or "...")
            _logger.info(
                "[%s] | #%s | usage: %s",
                message.created_at.strftime("%H:%M"),
                self._channel_name(message.channel),
                usage,
            )

    @staticmethod
    def _channel_name(channel: Messageable) -> str:
        return getattr(channel, "name", str(channel))

    async def _build_context(self, message: Message) -> ChatContext:
        """Fetches channel history and builds a message list for the LLM."""
        guild = message.guild
        if guild is None:
            raise RuntimeError("guild is unexpectedly None in _build_context")

        context = ChatContext()
        async for msg in message.channel.history(limit=20):
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
            context.add(
                ChatMessage(
                    role="assistant" if msg.author == guild.me else "user",
                    content=msg.content,
                    name=msg.author.display_name,
                    timestamp=msg.created_at.strftime("%H:%M"),
                )
            )

        context.reverse()
        context.add(
            ChatMessage(
                role="user",
                content=message.content,
                name=message.author.display_name,
            )
        )
        return context

    async def _reply_in_channel(self, message: Message, text: str):
        """Replies to the triggering message."""
        assert text
        await message.reply(text)

    @commands.command()
    async def usage(self, ctx: commands.Context):
        """``usage`` — Displays cumulative token usage."""
        await ctx.send(f"COMMAND:\n{self._chat_engine.get_total_usage().to_readable()}")

    @commands.command()
    async def switch_prompt(
        self, ctx: commands.Context, prompt_profile_name: str | None = None
    ):
        """``switch_prompt <profile>`` — Switches character prompt for current channel."""
        available = self._chat_engine.prompt_profile_names
        if prompt_profile_name is None:
            await ctx.send(f"switch_prompt COMMAND:\nAvailable profiles: {available}")
            return
        if prompt_profile_name not in available:
            await ctx.send(
                f"switch_prompt COMMAND:\n{prompt_profile_name} does not exist"
            )
            return
        self._channel_prompt[ctx.channel.id] = prompt_profile_name
        _logger.info(
            "#%s | switch_prompt → %s",
            self._channel_name(ctx.channel),
            prompt_profile_name,
        )
        await ctx.send("switch_prompt COMMAND:\nswitch prompt succeeded")

    @commands.command()
    async def switch_llm(self, ctx: commands.Context, client_key: str | None = None):
        """``!#switch_llm <client_key>`` — Switch to a different LLM provider."""
        available_llm = self._chat_engine.llm_profile_names
        if client_key is None:
            await ctx.send(f"switch_llm COMMAND:\nAvailable: {available_llm}")
            return
        if client_key not in available_llm:
            await ctx.send(
                f"switch_llm COMMAND:\n'{client_key}' not found. Available: {available_llm}"
            )
            return
        self._channel_llm[ctx.channel.id] = client_key
        _logger.info(
            "#%s | switch_llm → %s",
            self._channel_name(ctx.channel),
            client_key,
        )
        await ctx.send(f"switch_llm COMMAND:\nswitched to {client_key}")
