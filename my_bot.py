"""Discord Bot definition and assembly.

The :class:`MyBot` subclass registers cogs and injects the :class:`ChatEngine`
during ``setup_hook``.  Use ``create_bot()`` to get an instance.
"""

import cogs.general_cog
import cogs.guild_whitelist_cog
import cogs.llm_cog
import discord
from discord.ext import commands

from services.chat_engine import ChatEngine

import logging

logger = logging.getLogger(__name__)


class MyBot(commands.Bot):
    """Discord bot with LLM chat capabilities.

    Args:
        command_prefix: Command prefix string (set to ``'!#'``).
        intents: Discord gateway intents (``message_content`` required).
    """

    def __init__(self):
        """Initialize the bot with default intents."""
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!#', intents=intents)

    async def setup_hook(self) -> None:
        """Register cogs and instantiate the ChatEngine.

        Called once by discord.py before the bot logs in.
        """
        await self.add_cog(cogs.general_cog.GeneralCog(self))
        await self.add_cog(cogs.guild_whitelist_cog.GuildWhitelistCog(self))
        await self.add_cog(cogs.llm_cog.LLMChatCog(self, ChatEngine()))

    async def on_ready(self):
        """Log the bot's login name when the WebSocket connects."""
        logger.info("Bot logged in as %s", self.user)


def create_bot() -> MyBot:
    """Create a new MyBot instance."""
    return MyBot()
