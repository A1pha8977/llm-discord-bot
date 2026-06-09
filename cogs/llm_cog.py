"""Discord Cog for LLM-powered chat replies with per-channel character prompts
and runtime LLM provider switching."""

from discord.ext.commands.bot import Bot


import asyncio
import logging
from collections import deque

from discord import Message
from discord.abc import Messageable
from discord.ext import commands

from services.chat_engine import ChatContext, ChatEngine, ChatEngineError, ChatMessage
from services.llm import TokenUsage

_logger = logging.getLogger(__name__)


class LLMChatCog(commands.Cog):
    """Monitors @mentions, builds message context, calls LLM, and replies.

    All LLM logic is delegated to :class:`ChatEngine`.

    Args:
        discord_bot: The Discord bot instance.
        chat_engine: Pre-configured ChatEngine instance.
    """

    _MAX_CONTEXT = 20

    def __init__(
        self,
        discord_bot: commands.Bot,
        chat_engine: ChatEngine,
    ):
        self._discord_bot: Bot = discord_bot
        self._chat_engine: ChatEngine = chat_engine
        self._channel_prompt: dict[int, str] = {}
        self._channel_llm: dict[int, str] = {}
        self._context_queues: dict[int, deque[ChatMessage]] = {}
        """channel_id → fixed-size message deque for LLM context."""
        self._channel_locks: dict[int, asyncio.Lock] = {}


    # ------------------------------------------------------------------
    # Queue helpers
    # ------------------------------------------------------------------

    def _queue_add(self, channel_id: int, msg: ChatMessage) -> None:
        """Append a message to the channel's context deque.

        Once the deque reaches ``_MAX_CONTEXT``, the oldest message is
        automatically evicted ("FIFO with fixed capacity").
        """
        if channel_id not in self._context_queues:
            self._context_queues[channel_id] = deque[ChatMessage](
                maxlen=self._MAX_CONTEXT
            )
        self._context_queues[channel_id].append(msg)

    def _queue_get(self, channel_id: int) -> list[ChatMessage]:
        """Return all queued messages for *channel_id*, oldest first."""
        if channel_id not in self._context_queues:
            return []
        return list(self._context_queues[channel_id])

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        """Triggers ``on_mention`` when the bot is @mentioned.

        Always enqueues the user message first so that chronological
        order is preserved across concurrent ``on_message`` invocations.
        """
        if message.author.bot:
            return
        channel_id = message.channel.id
        lock = self._channel_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            self._update_context(channel_id, message)
        if message.guild and message.guild.me in message.mentions:
            await self.on_mention(message)

    async def on_mention(self, message: Message):
        """Handle an @mention by generating and dispatching an LLM reply.

        Serialized per-channel via :attr:`_channel_locks` to prevent
        out-of-order replies when multiple mentions arrive concurrently.
        """
        _logger.info(
            "[%s] | #%s | triggered by @%s",
            message.created_at.strftime("%H:%M"),
            self._channel_name(message.channel),
            message.author.display_name,
        )

        channel_id: int = message.channel.id
        lock = self._channel_locks.setdefault(channel_id, asyncio.Lock())

        async with lock, message.channel.typing():
            text, usage = await self._generate_reply(channel_id)
            self._enqueue_bot_reply(channel_id, text, usage)
            await self._reply_in_channel(message, text or "...")

        _logger.info(
            "[%s] | #%s | usage: %s",
            message.created_at.strftime("%H:%M"),
            self._channel_name(message.channel),
            usage,
        )

    async def _generate_reply(self, channel_id: int) -> tuple[str, TokenUsage]:
        """Build context from the queue, call the LLM, return (text, usage).

        On ``ChatEngineError``, returns an error string prefixed with
        ``"LLM API ERROR:"`` and a zero ``TokenUsage``.
        """
        context = ChatContext()
        context.extend(self._queue_get(channel_id))

        try:
            return await self._chat_engine.respond(
                context,
                llm_profile_name=self._channel_llm.get(channel_id),
                prompt_profile_name=self._channel_prompt.get(channel_id),
            )
        except ChatEngineError as e:
            _logger.error(
                "LLM API error (channel %d): %s",
                channel_id,
                e,
                exc_info=True,
            )
            return f"LLM API ERROR: {e}", TokenUsage(0, 0, 0)

    def _enqueue_bot_reply(
        self,
        channel_id: int,
        text: str,
        usage: TokenUsage,
    ) -> None:
        """Enqueue the bot's reply into the context queue if the LLM call succeeded."""
        if text and not text.startswith("LLM API ERROR:"):
            self._queue_add(
                channel_id,
                ChatMessage(
                    role="assistant",
                    content=text,
                    name=getattr(self._discord_bot.user, "display_name", "Bot"),
                ),
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_context(self, channel_id: int, message: Message):
        """Enqueue a user message from the channel into the context deque.

        Called for every non-bot message, not just @mentions.  This lets
        the LLM see the ambient conversation as context, capped by
        ``_MAX_CONTEXT`` (FIFO eviction).
        """
        self._queue_add(
            channel_id,
            ChatMessage(
                role="user",
                content=message.content,
                name=message.author.display_name,
            ),
        )

    @staticmethod
    def _channel_name(channel: Messageable) -> str:
        return getattr(channel, "name", str(channel))

    async def _reply_in_channel(self, message: Message, text: str):
        """Replies to the triggering message, splitting into multiple
        messages if *text* exceeds Discord's 2000-character limit.

        The first chunk is sent as a reply; subsequent chunks are sent
        as plain channel messages to preserve ordering without repeated
        @-mentions.
        """
        assert text
        chunks: list[str] = self._split_long_text(text)
        for i, chunk in enumerate(chunks):
            if i == 0:
                await message.reply(chunk)
            else:
                await message.channel.send(chunk)

    @staticmethod
    def _split_long_text(text: str, max_len: int = 1000) -> list[str]:
        """Split *text* into chunks no longer than *max_len*.

        Prefers splitting at newline boundaries.  When no good boundary
        exists within the limit, falls back to a hard cut at *max_len*.
        """
        if len(text) <= max_len:
            return [text]

        chunks: list[str] = []
        while len(text) > max_len:
            split_at = text.rfind("\n", 0, max_len)
            if split_at == -1 or split_at < max_len // 2:
                split_at = max_len
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        if text:
            chunks.append(text)
        return chunks

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

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

    @commands.command()
    async def clear_context(self, ctx: commands.Context):
        """``clear_context`` — Clears the LLM conversation context for this channel."""
        channel_id = ctx.channel.id
        size = len(self._context_queues.get(channel_id, ()))
        self._context_queues.pop(channel_id, None)
        _logger.info(
            "#%s | clear_context (%d messages)",
            self._channel_name(ctx.channel),
            size,
        )
        await ctx.send(
            f"clear_context COMMAND:\nContext cleared (was {size} messages)."
        )
