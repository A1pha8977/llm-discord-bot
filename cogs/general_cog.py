import random
import time

from discord.ext import commands


class GeneralCog(commands.Cog):
    def __init__(self, discord_bot: commands.Bot) -> None:
        self._discord_bot = discord_bot
        super().__init__()

    @commands.command()
    async def ping(self, ctx: commands.Context):
        await ctx.reply(content=time.asctime(time.localtime(time.time())))

    @commands.command()
    async def echo(self, ctx: commands.Context, *, s: str = "echo"):
        await ctx.reply(s)

    @commands.command()
    async def dice(self, ctx: commands.Context, *, arg="6"):
        args = arg.split(" ")
        d = []
        for i in args:
            if not i.isdigit():
                await ctx.send(f"Invalid argument: {i}")
                return
            d.append(random.randint(1, int(i)))
        for i in d:
            await ctx.send(f"🎲: {i}")
        if len(d) > 1:
            await ctx.send(f"总和: {sum(d)}")

    @commands.command()
    async def whoami(self, ctx: commands.Context):
        await ctx.send(ctx.author.display_name)

    @commands.command()
    async def halt(self, ctx: commands.Context):
        await ctx.send("Shutting down...")
        await self._discord_bot.close()
