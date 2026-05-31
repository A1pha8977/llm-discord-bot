from services.deepseek import get_deep_seek_client
from utils import config

import cogs.general_cog

import cogs.llm_cog
import discord
from discord.ext import commands

import logging

logger = logging.getLogger(__name__)



class MyBot(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!#', intents=intents)

    async def setup_hook(self) -> None:
        await self.add_cog(cogs.general_cog.GeneralCog(self))
        prompt_yaml = config.load_prompt_yaml()
        await self.add_cog(cogs.llm_cog.LLMCog(self, get_deep_seek_client(), f"{prompt_yaml["system_prompt"]}\n{prompt_yaml["role_play_prompt"]}"))

    async def on_ready(self):
        logger.info("Bot logged in as %s", self.user)


BOT = MyBot()