import cogs.general_cog
import cogs.llm_cog
import discord
from discord.ext import commands

from services.chat_engine import ChatEngine

import logging

logger = logging.getLogger(__name__)


class MyBot(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!#', intents=intents)

    async def setup_hook(self) -> None:
        await self.add_cog(cogs.general_cog.GeneralCog(self))
        await self.add_cog(cogs.llm_cog.LLMCog(self, ChatEngine()))

    async def on_ready(self):
        logger.info("Bot logged in as %s", self.user)


BOT = MyBot()
