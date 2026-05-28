import discord
from discord.ext import commands

import cogs.general
import cogs.deepseek_cog

class MyBot(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='/', intents=intents)

    async def setup_hook(self) -> None:
        await self.add_cog(cogs.general.GeneralCog())
        await self.add_cog(cogs.deepseek_cog.DeepSeekCog())

    async def on_ready(self):
        print("HELLO")

BOT = MyBot()