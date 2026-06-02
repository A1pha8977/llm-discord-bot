from services.mimo import MimoClient
from utils import config
from services.deepseek import DeepSeekClient
import cogs.general_cog
import cogs.llm_cog
import discord
from discord.ext import commands

import os
import logging

logger = logging.getLogger(__name__)


class MyBot(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!#', intents=intents)

    async def setup_hook(self) -> None:
        await self.add_cog(cogs.general_cog.GeneralCog(self))
        DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
        if not DEEPSEEK_API_KEY:
            raise ValueError("Missing required environment variable: DEEPSEEK_API_KEY")
        MIMO_API_KEY = os.getenv("MIMO_API_KEY")
        if not MIMO_API_KEY:
            raise ValueError("Missing required environment variable: MIMO_API_KEY")

        await self.add_cog(cogs.llm_cog.LLMCog(self, DeepSeekClient(
            DEEPSEEK_API_KEY,
            model_name="deepseek-v4-flash",
            max_output_tokens=10000,
            response_format={'type': 'json_object'}
        ), "default"))

        # await self.add_cog(cogs.llm_cog.LLMCog(self, MimoClient(
        #     MIMO_API_KEY,
        #     model_name="mimo-v2.5-pro",
        #     max_output_tokens=10000,
        #     response_format={'type': 'json_object'}
        # )))
    async def on_ready(self):
        logger.info("Bot logged in as %s", self.user)


BOT = MyBot()