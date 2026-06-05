"""General-purpose Discord commands (ping, echo, dice, whoami, halt)."""

import random
import time

from discord.ext import commands


class GeneralCog(commands.Cog):
    """Simple utility commands available to all users.

    Args:
        discord_bot: The bot instance (used by ``halt`` to shut down).
    """

    def __init__(self, discord_bot: commands.Bot) -> None:
        super().__init__()
        self._discord_bot = discord_bot

    @commands.command()
    async def ping(self, ctx: commands.Context):
        """``!#ping`` — Return the current server time."""
        await ctx.reply(content=time.asctime(time.localtime(time.time())))

    @commands.command()
    async def echo(self, ctx: commands.Context, *, s: str = "echo"):
        """``!#echo <text>`` — Echo back the provided text."""
        await ctx.reply(s)

    @commands.command()
    async def dice(self, ctx: commands.Context, *, arg: str = "6"):
        """``!#dice <n> ...`` — Roll dice with the given number of faces."""
        args = arg.split()
        d = []
        for i in args:
            if not (i.isdigit() and int(i) >= 1):
                await ctx.send(f"Invalid argument: {i}")
                return
            d.append(random.randint(1, int(i)))
        for i in d:
            await ctx.send(f"🎲: {i}")
        if len(d) > 1:
            await ctx.send(f"总和: {sum(d)}")

    @commands.command()
    async def whoami(self, ctx: commands.Context):
        """``!#whoami`` — Show your Discord display name."""
        await ctx.send(ctx.author.display_name)

    @commands.command()
    @commands.is_owner()
    async def halt(self, ctx: commands.Context):
        """``!#halt`` — Shut down the bot (owner only)."""
        await ctx.send("Shutting down...")
        await self._discord_bot.close()
